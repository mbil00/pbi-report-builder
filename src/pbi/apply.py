"""Declarative YAML apply engine for PBI reports.

Parses a YAML specification and applies it to the report, creating or
updating pages and visuals as needed.
"""

from __future__ import annotations

import copy
import difflib
import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pbi.project import Project, Page, Visual, sanitize_visual_name
from pbi.properties import (
    VISUAL_PROPERTIES,
    PAGE_PROPERTIES,
    normalize_property_name,
    set_property,
)
from pbi.filters import add_categorical_filter
from pbi.roles import normalize_visual_role
from pbi.roundtrip import (
    apply_page_roundtrip_fields,
    build_projection,
    iter_nested_property_assignments,
    match_existing_projection,
    parse_binding_items,
)
from pbi.styles import StylePreset, get_style


@dataclass
class ApplyResult:
    """Summary of what was changed by an apply operation."""
    pages_created: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    visuals_created: list[tuple[str, str]] = field(default_factory=list)
    visuals_updated: list[tuple[str, str]] = field(default_factory=list)
    visuals_deleted: list[tuple[str, str]] = field(default_factory=list)
    properties_set: int = 0
    bindings_added: int = 0
    filters_added: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rolled_back: bool = False

    @property
    def has_changes(self) -> bool:
        return bool(
            self.pages_created or self.pages_updated
            or self.visuals_created or self.visuals_updated
            or self.visuals_deleted
        )


_MISSING_MODEL = object()


@dataclass
class _ApplySession:
    """Per-run caches and rollback bookkeeping for apply."""

    dry_run: bool
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    snapshot_dir: Path | None = None
    model: Any = _MISSING_MODEL

    def ensure_snapshot(self, project: Project) -> None:
        """Create the definition snapshot lazily on the first write-intent path."""
        if self.dry_run or self.snapshot_dir is not None:
            return
        self.temp_dir = tempfile.TemporaryDirectory()
        self.snapshot_dir = Path(self.temp_dir.name) / "definition"
        shutil.copytree(project.definition_folder, self.snapshot_dir)

    def restore(self, project: Project) -> None:
        if self.snapshot_dir is None:
            return
        _restore_definition_snapshot(project, self.snapshot_dir)
        project.clear_caches()

    def get_model(self, project: Project) -> Any | None:
        """Load the semantic model once per apply run."""
        if self.model is _MISSING_MODEL:
            try:
                from pbi.modeling.schema import SemanticModel

                self.model = SemanticModel.load(project.root)
            except Exception:
                self.model = None
        return self.model

    def cleanup(self) -> None:
        if self.temp_dir is not None:
            self.temp_dir.cleanup()


def _page_spec_may_mutate(page_spec: dict, *, overwrite: bool) -> bool:
    """Return True when a page spec can lead to on-disk changes."""
    if overwrite and "visuals" in page_spec:
        return True
    return any(key != "name" for key in page_spec)


def _sort_visuals(visuals: list[Visual]) -> None:
    visuals.sort(
        key=lambda v: (
            v.position.get("y", 0),
            v.position.get("x", 0),
        )
    )


@dataclass
class _PageVisualState:
    """Per-page visual state reused across one apply pass."""

    page: Page
    visuals: list[Visual]
    _by_folder: dict[str, Visual] = field(default_factory=dict, init=False, repr=False)
    _by_name: dict[str, Visual] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        _sort_visuals(self.visuals)
        self._reindex()

    def _reindex(self) -> None:
        self._by_folder = {}
        self._by_name = {}
        for visual in self.visuals:
            self._by_folder.setdefault(visual.folder.name, visual)
            self._by_name.setdefault(visual.name, visual)

    def add(self, visual: Visual) -> None:
        self.visuals.append(visual)
        _sort_visuals(self.visuals)
        self._reindex()

    def remove(self, visual: Visual) -> None:
        self.visuals[:] = [candidate for candidate in self.visuals if candidate.folder != visual.folder]
        self._reindex()

    def refresh(self) -> None:
        _sort_visuals(self.visuals)
        self._reindex()

    def find_visual(self, identifier: str) -> Visual:
        raw_identifier = identifier
        if identifier.startswith(("#", "@")):
            identifier = identifier[1:]

        visual = self._by_folder.get(identifier)
        if visual is not None:
            return visual

        visual = self._by_name.get(identifier)
        if visual is not None:
            return visual

        try:
            idx = int(identifier) - 1
            if 0 <= idx < len(self.visuals):
                return self.visuals[idx]
        except ValueError:
            pass

        id_lower = identifier.lower()
        type_matches = [v for v in self.visuals if v.visual_type.lower() == id_lower]
        if len(type_matches) == 1:
            return type_matches[0]

        matches = [v for v in self.visuals if id_lower in v.name.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(f'"{v.name}" ({v.visual_type})' for v in matches)
            raise ValueError(
                f'Ambiguous visual "{identifier}". Matches: {names}'
            )

        all_names = [v.name for v in self.visuals] + [v.visual_type for v in self.visuals]
        close = difflib.get_close_matches(identifier, all_names, n=3, cutoff=0.5)
        if close:
            suggestion = ", ".join(f'"{n}"' for n in close)
            raise ValueError(
                f'Visual "{raw_identifier}" not found on "{self.page.display_name}". '
                f"Did you mean: {suggestion}?"
            )
        available = ", ".join(
            f'{i+1}: {v.name} ({v.visual_type})'
            for i, v in enumerate(self.visuals)
        )
        raise ValueError(
            f'Visual "{raw_identifier}" not found on "{self.page.display_name}". '
            f"Available: {available}"
        )


def apply_yaml(
    project: Project,
    yaml_content: str,
    *,
    page_filter: str | None = None,
    dry_run: bool = False,
    overwrite: bool = False,
    continue_on_error: bool = False,
) -> ApplyResult:
    """Apply a YAML specification to the project.

    Args:
        project: The PBIP project to modify.
        yaml_content: YAML string to parse and apply.
        page_filter: Only apply to this page (by name).
        dry_run: If True, validate and report what would change without modifying files.

    Returns:
        ApplyResult with summary of changes made.
    """
    result = ApplyResult()
    style_cache: dict[str, StylePreset] = {}
    session = _ApplySession(dry_run=dry_run)

    try:
        spec = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        result.errors.append(f"Invalid YAML: {e}")
        return result

    if not isinstance(spec, dict):
        result.errors.append("YAML must be a mapping with a 'pages' key.")
        return result

    pages_spec = spec.get("pages", [])
    if not isinstance(pages_spec, list):
        result.errors.append("'pages' must be a list.")
        return result

    try:
        try:
            for page_spec in pages_spec:
                if not isinstance(page_spec, dict):
                    result.errors.append(f"Each page must be a mapping, got: {type(page_spec).__name__}")
                    continue

                page_name = page_spec.get("name")
                if not page_name:
                    result.errors.append("Each page must have a 'name' key.")
                    continue

                if page_filter and page_name.lower() != page_filter.lower():
                    continue

                if _page_spec_may_mutate(page_spec, overwrite=overwrite):
                    session.ensure_snapshot(project)

                _apply_page(
                    project,
                    page_spec,
                    result,
                    dry_run=dry_run,
                    overwrite=overwrite,
                    style_cache=style_cache,
                    session=session,
                )

            # Apply bookmarks (top-level)
            bookmarks_spec = spec.get("bookmarks", [])
            if isinstance(bookmarks_spec, list) and bookmarks_spec:
                session.ensure_snapshot(project)
                _apply_bookmarks(project, bookmarks_spec, result, dry_run=dry_run, session=session)
        except Exception:
            if session.snapshot_dir is not None:
                session.restore(project)
                result.rolled_back = True
            raise

        if result.errors and session.snapshot_dir is not None and not continue_on_error:
            session.restore(project)
            result.rolled_back = True

        return result
    finally:
        session.cleanup()


def _apply_page(
    project: Project,
    page_spec: dict,
    result: ApplyResult,
    *,
    dry_run: bool,
    overwrite: bool,
    style_cache: dict[str, StylePreset],
    session: _ApplySession,
) -> None:
    """Apply a single page specification."""
    page_name = page_spec["name"]

    # Find or create page
    page_is_new = False
    try:
        page = project.find_page(page_name)
        result.pages_updated.append(page_name)
    except ValueError:
        # Page not found — create it
        width = page_spec.get("width", 1280)
        height = page_spec.get("height", 720)
        display_option = page_spec.get("displayOption", "FitToPage")
        page_is_new = True
        if dry_run:
            result.pages_created.append(page_name)
            page = None  # type: ignore[assignment]
        else:
            page = project.create_page(
                page_name,
                width=width,
                height=height,
                display_option=display_option,
            )
            result.pages_created.append(page_name)

    page_state = None if (dry_run and page_is_new) else _PageVisualState(page=page, visuals=project.get_visuals(page))

    # Apply page properties (skip for dry-run on new pages — no page object)
    if not (dry_run and page_is_new):
        page_error_count = len(result.errors)
        page_props = {
            "width": "width",
            "height": "height",
            "displayOption": "displayOption",
            "visibility": "visibility",
        }
        for yaml_key, prop_name in page_props.items():
            if yaml_key in page_spec:
                value = str(page_spec[yaml_key])
                if not dry_run:
                    try:
                        sw = set_property(page.data, prop_name, value, PAGE_PROPERTIES)
                        result.properties_set += 1
                        for w in sw:
                            result.warnings.append(f"Page {page_name}: {w}")
                    except ValueError as e:
                        result.errors.append(f"Page {page_name}: {prop_name}: {e}")
                else:
                    result.properties_set += 1

        try:
            result.properties_set += apply_page_roundtrip_fields(
                page.data,
                page_spec,
                project_root=project.root,
                dry_run=dry_run,
                model=session.get_model(project),
            )
        except ValueError as e:
            result.errors.append(f"Page {page_name}: {e}")
            return

        # Apply page-level nested objects (background, outspace)
        _apply_nested_properties(
            page.data, page_spec,
            exclude_keys={"name", "width", "height", "displayOption", "visibility",
                           "visuals", "filters", "interactions", "bookmarks",
                           "type", "pageBinding", "tooltip", "drillthrough"},
            registry=PAGE_PROPERTIES,
            result=result,
            context=f"Page {page_name}",
            dry_run=dry_run,
        )

        # Apply page-level filters
        if "filters" in page_spec:
            _apply_filters(page.data, page_spec["filters"], result,
                           context=f"Page {page_name}", dry_run=dry_run,
                           project=project, session=session)

        if not dry_run and len(result.errors) == page_error_count:
            page.save()

    # Apply visuals
    visuals_spec = page_spec.get("visuals", [])
    if not isinstance(visuals_spec, list):
        result.errors.append(f"Page {page_name}: 'visuals' must be a list.")
        return

    kept_visual_ids: set[str] = set()
    for vis_spec in visuals_spec:
        if isinstance(vis_spec, dict):
            if dry_run and page_is_new:
                # For dry-run on new pages, just count the visuals that would be created
                vis_name = vis_spec.get("name") or vis_spec.get("type", "unknown")
                result.visuals_created.append((page_name, vis_name))
                _count_dry_run_changes(vis_spec, result)
            else:
                _apply_visual(
                    project,
                    page,
                    vis_spec,
                    result,
                    dry_run=dry_run,
                    style_cache=style_cache,
                    keep_visual_ids=kept_visual_ids if overwrite else None,
                    session=session,
                    page_state=page_state,
                )

    if overwrite and not page_is_new and page_state is not None:
        for visual in list(page_state.visuals):
            if visual.folder.name not in kept_visual_ids:
                result.visuals_deleted.append((page_name, visual.name))
                if not dry_run:
                    project.delete_visual(visual)
                    page_state.remove(visual)

    # Apply interactions AFTER visuals so newly created visuals can be resolved
    if not (dry_run and page_is_new) and "interactions" in page_spec:
        _apply_interactions(project, page, page_spec["interactions"], result,
                            context=f"Page {page_name}", dry_run=dry_run, session=session, page_state=page_state)
        if not dry_run and len(result.errors) == page_error_count:
            page.save()


def _apply_visual(
    project: Project,
    page: Page,
    vis_spec: dict,
    result: ApplyResult,
    *,
    dry_run: bool,
    style_cache: dict[str, StylePreset],
    keep_visual_ids: set[str] | None = None,
    session: _ApplySession,
    page_state: _PageVisualState,
) -> None:
    """Apply a single visual specification."""
    page_name = page.display_name
    vis_name = vis_spec.get("name")
    vis_id = vis_spec.get("id")
    vis_type = vis_spec.get("type")

    if not vis_name and not vis_type:
        result.errors.append(f"Page {page_name}: visual must have 'name' or 'type'.")
        return

    # Find existing visual
    visual: Visual | None = None
    if vis_id:
        visual = page_state._by_folder.get(vis_id)
    if vis_name:
        try:
            visual = visual or page_state.find_visual(vis_name)
        except ValueError:
            pass

    # Handle visual type conversion: existing visual with different type
    if visual is not None and vis_type and visual.visual_type != vis_type:
        old_type = visual.visual_type
        x, y = _parse_position(vis_spec.get("position", f"{visual.position.get('x', 0)}, {visual.position.get('y', 0)}"))
        w, h = _parse_size(vis_spec.get("size", f"{visual.position.get('width', 300)} x {visual.position.get('height', 200)}"))
        if dry_run:
            result.visuals_deleted.append((page_name, vis_name or visual.name))
            result.visuals_created.append((page_name, vis_name or vis_type))
        else:
            project.delete_visual(visual)
            page_state.remove(visual)
            visual = project.create_visual(page, vis_type, x=x, y=y, width=w, height=h)
            if vis_name:
                visual.data["name"] = sanitize_visual_name(vis_name)
                visual.save()
            page_state.add(visual)
            result.visuals_deleted.append((page_name, f"{vis_name or visual.name} ({old_type})"))
            result.visuals_created.append((page_name, vis_name or vis_type))
    elif visual is None and vis_type:
        # Create new visual
        x, y = _parse_position(vis_spec.get("position", "0, 0"))
        w, h = _parse_size(vis_spec.get("size", "300 x 200"))
        if dry_run:
            result.visuals_created.append((page_name, vis_name or vis_type))
        else:
            visual = project.create_visual(page, vis_type, x=x, y=y, width=w, height=h)
            if vis_name:
                visual.data["name"] = sanitize_visual_name(vis_name)
                visual.save()
            page_state.add(visual)
            result.visuals_created.append((page_name, vis_name or vis_type))
    elif visual is None:
        result.errors.append(
            f"Page {page_name}: visual \"{vis_name}\" not found and no 'type' "
            f"specified for creation."
        )
        return
    else:
        result.visuals_updated.append((page_name, vis_name or visual.name))

    visual_type = visual.visual_type if visual is not None else vis_type
    context = f"{page_name}/{vis_name or visual.name if visual is not None else vis_type}"
    try:
        style_assignments = _resolve_style_assignments(
            project,
            vis_spec.get("style"),
            visual_type=visual_type,
            style_cache=style_cache,
        )
    except (FileNotFoundError, ValueError) as e:
        result.errors.append(f"{context}: {e}")
        return

    visual_error_count = len(result.errors)

    if dry_run:
        # Count would-be changes
        result.properties_set += len(style_assignments)
        _count_dry_run_changes(vis_spec, result)
        return

    if keep_visual_ids is not None:
        keep_visual_ids.add(visual.folder.name)

    for style_name, prop_name, value in style_assignments:
        try:
            sw = set_property(visual.data, prop_name, str(value), VISUAL_PROPERTIES)
            result.properties_set += 1
            for w in sw:
                result.warnings.append(f"{context}: {w}")
        except ValueError as e:
            result.errors.append(f'{context}: style "{style_name}" {prop_name}: {e}')
            return

    raw_pbir = vis_spec.get("pbir")
    if isinstance(raw_pbir, dict):
        _apply_raw_visual_payload(visual, raw_pbir)

    # Apply position/size if specified
    if "position" in vis_spec:
        x, y = _parse_position(vis_spec["position"])
        visual.data.setdefault("position", {})["x"] = x
        visual.data["position"]["y"] = y
        result.properties_set += 2

    if "size" in vis_spec:
        w, h = _parse_size(vis_spec["size"])
        visual.data.setdefault("position", {})["width"] = w
        visual.data["position"]["height"] = h
        result.properties_set += 2

    # Support x/y/width/height as direct keys (aliases for position/size)
    pos = visual.data.setdefault("position", {})
    for key in ("x", "y", "width", "height"):
        if key in vis_spec and key not in ("position", "size"):
            pos[key] = int(vis_spec[key])
            result.properties_set += 1

    # Textbox content
    if "text" in vis_spec and visual_type == "textbox":
        _apply_textbox_content(visual, vis_spec, result)

    # Apply visual properties (nested objects become dot-separated props)
    exclude_keys = {"id", "name", "type", "position", "size", "bindings", "sort",
                     "filters", "conditionalFormatting", "isHidden", "pbir", "style",
                     "kpis", "layout", "accentBar", "referenceLabelLayout",
                     "text", "textStyle", "x", "y", "width", "height"}
    _apply_nested_properties(
        visual.data, vis_spec,
        exclude_keys=exclude_keys,
        registry=VISUAL_PROPERTIES,
        result=result,
        context=context,
        dry_run=dry_run,
        ignore_selector_errors=isinstance(raw_pbir, dict),
        ignore_unknown_roots=_raw_object_roots(raw_pbir) if isinstance(raw_pbir, dict) else None,
    )

    # isHidden
    if "isHidden" in vis_spec:
        visual.data["isHidden"] = bool(vis_spec["isHidden"])
        result.properties_set += 1

    # Bindings
    if "bindings" in vis_spec:
        _apply_bindings(project, visual, vis_spec["bindings"], result, session=session)

    # Sort
    if "sort" in vis_spec:
        _apply_sort(project, visual, vis_spec["sort"], result)

    # Filters
    if "filters" in vis_spec:
        _apply_filters(visual.data, vis_spec["filters"], result,
                       context=context,
                       dry_run=dry_run,
                       project=project, session=session)

    # Conditional formatting
    if "conditionalFormatting" in vis_spec:
        _apply_conditional_formatting(visual.data, vis_spec["conditionalFormatting"],
                                      result, context=context, dry_run=dry_run)

    # KPI shorthand for cardVisual
    if "kpis" in vis_spec:
        kpis_list = vis_spec["kpis"]
        if not isinstance(kpis_list, list):
            result.errors.append(f"{context}: kpis must be a list of KPI definitions.")
        else:
            from pbi.card import expand_kpis
            try:
                count = expand_kpis(
                    visual.data,
                    kpis_list,
                    layout=vis_spec.get("layout"),
                    accent_bar=vis_spec.get("accentBar"),
                    ref_label_layout=vis_spec.get("referenceLabelLayout"),
                )
                result.properties_set += count
            except (ValueError, KeyError) as e:
                result.errors.append(f"{context}: kpis expansion failed: {e}")

    if len(result.errors) != visual_error_count:
        return

    visual.save()
    page_state.refresh()


def _apply_nested_properties(
    data: dict,
    spec: dict,
    *,
    exclude_keys: set[str],
    registry: dict,
    result: ApplyResult,
    context: str,
    dry_run: bool,
    prefix: str = "",
    ignore_selector_errors: bool = False,
    ignore_unknown_roots: set[str] | None = None,
) -> None:
    """Flatten nested YAML dicts into dot-separated property names and apply them.

    Example: {"title": {"show": true, "text": "Hello"}}
    becomes: title.show=true, title.text=Hello
    """
    for prop_name, value in iter_nested_property_assignments(
        spec,
        exclude_keys=exclude_keys,
        prefix=prefix,
    ):
        str_value = str(value)
        if dry_run:
            result.properties_set += 1
            continue
        try:
            sw = set_property(data, prop_name, str_value, registry)
            result.properties_set += 1
            for w in sw:
                result.warnings.append(f"{context}: {w}")
        except ValueError as e:
            if ignore_selector_errors and "[" in prop_name and "]" in prop_name:
                continue
            root = prop_name.split(".", 1)[0]
            if ignore_unknown_roots and root in ignore_unknown_roots:
                continue
            result.errors.append(f"{context}: {prop_name}: {e}")


def _raw_object_roots(raw_pbir: dict) -> set[str]:
    """Return YAML object roots projected from the raw visual payload."""
    visual = raw_pbir.get("visual", {})
    roots = set(visual.get("objects", {}).keys())
    roots.update(visual.get("visualContainerObjects", {}).keys())
    roots.update({
        "shadow" if "dropShadow" in roots else "",
        "subtitle" if "subTitle" in roots else "",
        "header" if "visualHeader" in roots else "",
        "tooltip" if "visualTooltip" in roots else "",
        "action" if "visualLink" in roots else "",
        "xAxis" if "categoryAxis" in roots else "",
        "yAxis" if "valueAxis" in roots else "",
        "line" if "lineStyles" in roots else "",
        "dataColors" if "dataPoint" in roots else "",
    })
    roots.discard("")
    return roots


def _apply_textbox_content(
    visual: Visual,
    vis_spec: dict,
    result: ApplyResult,
) -> None:
    """Apply plain text content to a textbox visual."""
    text = str(vis_spec.get("text", ""))
    style = vis_spec.get("textStyle", {})
    if not isinstance(style, dict):
        style = {}

    text_style: dict[str, Any] = {}
    if "fontFamily" in style:
        text_style["fontFamily"] = f"'{style['fontFamily']}'"
    if "fontSize" in style:
        text_style["fontSize"] = f"'{style['fontSize']}pt'"
    if "fontColor" in style:
        text_style["color"] = {"expr": {"Literal": {"Value": f"'{style['fontColor']}'"}}}
    if "bold" in style:
        text_style["fontWeight"] = "'bold'" if style["bold"] else "'normal'"

    text_run: dict[str, Any] = {"value": f"'{text}'"}
    if text_style:
        text_run["textStyle"] = text_style

    paragraphs = [{"textRuns": [text_run]}]
    visual.data.setdefault("visual", {})["objects"] = {
        "general": [{
            "properties": {
                "paragraphs": paragraphs,
            },
        }],
    }
    result.properties_set += 1


def _apply_bindings(
    project: Project,
    visual: Visual,
    bindings: dict,
    result: ApplyResult,
    *,
    session: _ApplySession,
) -> None:
    """Apply data bindings from the YAML spec."""
    from pbi.columns import set_column_width

    query_state = (
        visual.data
        .setdefault("visual", {})
        .setdefault("query", {})
        .setdefault("queryState", {})
    )

    for role, field_ref in bindings.items():
        canonical_role = normalize_visual_role(visual.visual_type, role)
        existing_projections = copy.deepcopy(
            query_state.get(canonical_role, {}).get("projections", [])
        )
        try:
            parsed_items = parse_binding_items(
                project.root,
                field_ref,
                model=session.get_model(project),
            )
        except ValueError as e:
            result.errors.append(f"Invalid binding: {e}")
            continue
        new_projections: list[dict[str, Any]] = []

        for item in parsed_items:
            projection = match_existing_projection(existing_projections, item)
            if projection is None:
                projection = build_projection(item)
            else:
                projection = copy.deepcopy(projection)
            if item.display_name is not None:
                projection["displayName"] = item.display_name
            new_projections.append(projection)
            result.bindings_added += 1

            if item.width is not None:
                query_ref = projection.get("queryRef", f"{item.entity}.{item.prop}")
                set_column_width(visual, query_ref, item.width)

        if new_projections:
            query_state[canonical_role] = {"projections": new_projections}
        else:
            query_state.pop(canonical_role, None)


def _apply_sort(
    project: Project,
    visual: Visual,
    sort_spec: str,
    result: ApplyResult,
) -> None:
    """Apply sort from a spec like 'Table.Field Descending' or 'Measures Table.Total Devices (measure) Descending'."""
    text = str(sort_spec).strip()
    if not text:
        return

    # Handle "(measure)" annotation
    is_measure = "(measure)" in text
    text = text.replace("(measure)", "").strip()

    # Extract direction from the end (last word if it's a direction keyword)
    direction = "Descending"
    for suffix in ("Ascending", "ascending", "asc", "Descending", "descending", "desc"):
        if text.endswith(f" {suffix}"):
            direction = "Ascending" if suffix.lower() in ("ascending", "asc") else "Descending"
            text = text[: -len(suffix)].strip()
            break

    # Everything remaining is the field reference (Table.Field, may contain spaces)
    field_ref = text

    dot = field_ref.find(".")
    if dot == -1:
        result.errors.append(f"Invalid sort field: {sort_spec}")
        return

    entity = field_ref[:dot]
    prop = field_ref[dot + 1:]
    field_type = "measure" if is_measure else "column"

    project.set_sort(
        visual, entity, prop,
        field_type=field_type,
        descending=(direction == "Descending"),
    )
    result.properties_set += 1


def _resolve_apply_field(
    field_ref: str,
    project: Project,
    *,
    session: _ApplySession | None = None,
) -> tuple[str, str, str, str | None]:
    """Resolve a field reference to (entity, prop, field_type, data_type).

    Uses the semantic model when available to distinguish columns from
    measures and to determine the data type for literal formatting.
    """
    dot = field_ref.find(".")
    entity = field_ref[:dot]
    prop = field_ref[dot + 1:]

    try:
        model = session.get_model(project) if session is not None else None
        if model is None:
            from pbi.modeling.schema import SemanticModel

            model = SemanticModel.load(project.root)
        resolved_entity, resolved_prop, field_type = model.resolve_field(field_ref)
        data_type = None
        if field_type == "column":
            try:
                table = model.find_table(resolved_entity)
                for col in table.columns:
                    if col.name == resolved_prop:
                        data_type = col.data_type
                        break
            except (ValueError, KeyError):
                pass
        return resolved_entity, resolved_prop, field_type, data_type
    except Exception:
        return entity, prop, "column", None


def _apply_filters(
    data: dict,
    filters_spec: list,
    result: ApplyResult,
    *,
    context: str,
    dry_run: bool,
    project: Project | None = None,
    session: _ApplySession | None = None,
) -> None:
    """Apply filters from the YAML spec."""
    if filters_spec and not dry_run:
        config = data.setdefault("filterConfig", {})
        config["filters"] = []

    for f_spec in filters_spec:
        if not isinstance(f_spec, dict):
            result.errors.append(f"{context}: filter must be a mapping.")
            continue

        field_ref = f_spec.get("field", "")
        filter_type = f_spec.get("type", "Categorical")
        values = f_spec.get("values", [])
        is_hidden = f_spec.get("hidden", False)
        is_locked = f_spec.get("locked", False)

        dot = field_ref.find(".")
        if dot == -1:
            result.errors.append(f"{context}: filter field must be Table.Field format: {field_ref}")
            continue

        entity = field_ref[:dot]
        prop = field_ref[dot + 1:]

        if dry_run:
            result.filters_added += 1
            continue

        raw_filter = f_spec.get("raw")
        if isinstance(raw_filter, dict):
            config = data.setdefault("filterConfig", {})
            config.setdefault("filters", []).append(copy.deepcopy(raw_filter))
            result.filters_added += 1
        elif filter_type.lower() in ("categorical", "include", "exclude"):
            str_values = [str(v) for v in values] if values else []
            if str_values:
                if filter_type.lower() == "include":
                    from pbi.filters import add_include_filter

                    add_include_filter(
                        data, entity, prop, str_values,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                    )
                elif filter_type.lower() == "exclude":
                    from pbi.filters import add_exclude_filter

                    add_exclude_filter(
                        data, entity, prop, str_values,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                    )
                else:
                    add_categorical_filter(
                        data, entity, prop, str_values,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                    )
                result.filters_added += 1
        elif filter_type.lower() == "topn":
            from pbi.filters import add_topn_filter

            count = f_spec.get("count", 10)
            by_ref = f_spec.get("by", "")
            direction = f_spec.get("direction", "Top")
            by_dot = by_ref.find(".")
            if by_dot == -1:
                result.errors.append(f"{context}: topN filter 'by' must be Table.Field format: {by_ref}")
                continue
            by_entity = by_ref[:by_dot]
            by_prop = by_ref[by_dot + 1:]

            # Resolve field types via model
            order_field_type = "measure"
            if project is not None:
                _, _, order_field_type, _ = _resolve_apply_field(
                    by_ref, project, session=session
                )

            add_topn_filter(
                data, entity, prop,
                n=int(count),
                order_entity=by_entity,
                order_prop=by_prop,
                order_field_type=order_field_type,
                direction=direction.capitalize(),
                is_hidden=is_hidden,
                is_locked=is_locked,
            )
            result.filters_added += 1
        elif filter_type.lower() == "range":
            from pbi.filters import add_range_filter

            min_val = f_spec.get("min")
            max_val = f_spec.get("max")

            # Resolve field type and data type via model
            field_type = "column"
            data_type = None
            if project is not None:
                entity, prop, field_type, data_type = _resolve_apply_field(
                    field_ref, project, session=session
                )

            add_range_filter(
                data, entity, prop,
                min_val=str(min_val) if min_val is not None else None,
                max_val=str(max_val) if max_val is not None else None,
                field_type=field_type,
                is_hidden=is_hidden,
                is_locked=is_locked,
                data_type=data_type,
            )
            result.filters_added += 1
        else:
            result.warnings.append(
                f"{context}: filter type '{filter_type}' not yet supported in apply."
            )


def _apply_conditional_formatting(
    data: dict,
    cf_spec: dict,
    result: ApplyResult,
    *,
    context: str,
    dry_run: bool,
) -> None:
    """Apply conditional formatting from the YAML spec.

    Expected format:
      conditionalFormatting:
        dataPoint.fill:
          mode: measure
          source: Table.Measure
        values.fontColor:
          mode: gradient
          source: Table.Field
          min: { color: "#FF0000", value: 0 }
          max: { color: "#00FF00", value: 100 }
    """
    from pbi.formatting import (
        GradientStop,
        build_gradient_format,
        build_measure_format,
        build_rules_format,
        set_conditional_format,
    )

    if not isinstance(cf_spec, dict):
        result.errors.append(
            f"{context}: conditionalFormatting must be a mapping of property -> config, not a {type(cf_spec).__name__}."
        )
        return

    for prop_path, config in cf_spec.items():
        if not isinstance(config, dict):
            result.errors.append(f"{context}: conditionalFormatting.{prop_path} must be a mapping.")
            continue

        dot = prop_path.find(".")
        if dot == -1:
            result.errors.append(f"{context}: conditionalFormatting key must be object.prop: {prop_path}")
            continue
        obj_name = prop_path[:dot]
        prop_name = prop_path[dot + 1:]

        mode = config.get("mode", "measure")
        source = config.get("source", "")
        src_dot = source.find(".")
        if src_dot == -1:
            result.errors.append(f"{context}: conditionalFormatting source must be Table.Field: {source}")
            continue
        src_entity = source[:src_dot]
        src_prop = source[src_dot + 1:]

        if dry_run:
            result.properties_set += 1
            continue

        column_ref = config.get("column")

        if mode == "measure":
            value = build_measure_format(src_entity, src_prop)
        elif mode == "gradient":
            min_spec = config.get("min", {})
            max_spec = config.get("max", {})
            mid_spec = config.get("mid")
            min_stop = GradientStop(str(min_spec.get("color", "#FF0000")), float(min_spec.get("value", 0)))
            max_stop = GradientStop(str(max_spec.get("color", "#00FF00")), float(max_spec.get("value", 100)))
            mid_stop = GradientStop(str(mid_spec.get("color", "")), float(mid_spec.get("value", 50))) if mid_spec else None
            null_strategy = config.get("nullStrategy")
            value = build_gradient_format(src_entity, src_prop, min_stop, max_stop, mid_stop, null_strategy=null_strategy)
        elif mode == "rules":
            rules_list = config.get("rules", [])
            if not isinstance(rules_list, list) or not rules_list:
                result.errors.append(f"{context}: conditionalFormatting rules mode requires a non-empty 'rules' list.")
                continue
            else_spec = config.get("else")
            else_color = None
            if isinstance(else_spec, dict):
                else_color = else_spec.get("color")
            elif isinstance(else_spec, str):
                else_color = else_spec
            parsed_rules = []
            for rule in rules_list:
                if not isinstance(rule, dict):
                    result.errors.append(f"{context}: each rule must be a mapping with 'if' and 'color' keys.")
                    break
                rule_value = rule.get("if")
                rule_color = rule.get("color")
                if rule_value is None or rule_color is None:
                    result.errors.append(f"{context}: each rule must have 'if' and 'color' keys.")
                    break
                parsed_rules.append({"value": str(rule_value), "color": str(rule_color)})
            else:
                value = build_rules_format(src_entity, src_prop, parsed_rules, else_color=else_color)
            if len(parsed_rules) != len(rules_list):
                continue
        else:
            result.errors.append(f"{context}: conditionalFormatting mode must be 'measure', 'gradient', or 'rules': {mode}")
            continue

        set_conditional_format(data, obj_name, prop_name, value, column=column_ref)
        result.properties_set += 1


def _apply_bookmarks(
    project: Project,
    bookmarks_spec: list,
    result: ApplyResult,
    *,
    dry_run: bool,
    session: _ApplySession,
) -> None:
    """Apply bookmark definitions from the YAML spec."""
    from pbi.bookmarks import create_bookmark

    for entry in bookmarks_spec:
        if not isinstance(entry, dict):
            result.errors.append("Bookmark must be a mapping.")
            continue

        name = entry.get("name", "")
        page_ref = entry.get("page", "")
        if not name or not page_ref:
            result.errors.append("Bookmark requires 'name' and 'page'.")
            continue

        hide = entry.get("hide", [])
        target = entry.get("target")
        capture_data = entry.get("captureData", True)
        capture_display = entry.get("captureDisplay", True)
        capture_page = entry.get("capturePage", True)

        if dry_run:
            result.properties_set += 1
            continue

        try:
            page = project.find_page(page_ref)
            visuals = project.get_visuals(page)
            create_bookmark(
                project,
                display_name=name,
                page=page,
                visuals=visuals,
                hidden_visuals=hide if hide else None,
                target_visuals=target if target else None,
                suppress_data=not bool(capture_data),
                suppress_display=not bool(capture_display),
                suppress_active_section=not bool(capture_page),
            )
            result.properties_set += 1
        except (ValueError, FileNotFoundError) as e:
            result.errors.append(f"Bookmark \"{name}\": {e}")


def _apply_interactions(
    project: Project,
    page: Page,
    interactions_spec: list,
    result: ApplyResult,
    *,
    context: str,
    dry_run: bool,
    session: _ApplySession,
    page_state: _PageVisualState,
) -> None:
    """Apply interaction definitions from the YAML spec."""
    from pbi.interactions import set_interaction

    for entry in interactions_spec:
        if not isinstance(entry, dict):
            result.errors.append(f"{context}: interaction must be a mapping.")
            continue

        source = entry.get("source", "")
        target = entry.get("target", "")
        itype = entry.get("type", "DataFilter")

        if not source or not target:
            result.errors.append(f"{context}: interaction requires 'source' and 'target'.")
            continue

        if dry_run:
            result.properties_set += 1
            continue

        # Resolve visual names to handle friendly names
        try:
            src_vis = page_state.find_visual(source)
            tgt_vis = page_state.find_visual(target)
            set_interaction(page, src_vis.name, tgt_vis.name, itype)
            result.properties_set += 1
        except ValueError as e:
            result.errors.append(f"{context}: interaction {source}->{target}: {e}")


def _parse_number(value: Any) -> int | float:
    """Parse a JSON/YAML scalar into an int or float."""
    if isinstance(value, (int, float)):
        return int(value) if float(value).is_integer() else float(value)

    text = str(value).strip()
    number = float(text)
    return int(number) if number.is_integer() else number


def _parse_position(value: Any) -> tuple[int | float, int | float]:
    """Parse position from '50, 80' or a dict {'x': 50, 'y': 80}."""
    if isinstance(value, dict):
        return _parse_number(value.get("x", 0)), _parse_number(value.get("y", 0))
    parts = str(value).split(",")
    if len(parts) == 2:
        return _parse_number(parts[0]), _parse_number(parts[1])
    return 0, 0


def _parse_size(value: Any) -> tuple[int | float, int | float]:
    """Parse size from '600 x 400' or a dict {'width': 600, 'height': 400}."""
    if isinstance(value, dict):
        return _parse_number(value.get("width", 300)), _parse_number(value.get("height", 200))
    text = str(value)
    # Try "600 x 400" or "600x400", including PBIR float dimensions.
    match = re.match(r"([0-9]+(?:\.[0-9]+)?)\s*x\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
    if match:
        return _parse_number(match.group(1)), _parse_number(match.group(2))
    return 300, 200


def _apply_raw_visual_payload(visual: Visual, raw_pbir: dict) -> None:
    """Restore the exact exported PBIR payload for a visual."""
    for key, value in raw_pbir.items():
        visual.data[key] = copy.deepcopy(value)


def _count_dry_run_changes(vis_spec: dict, result: ApplyResult) -> None:
    """Count property changes for dry-run reporting."""
    exclude = {"id", "name", "type", "position", "size", "bindings", "sort",
                "filters", "isHidden", "pbir", "style"}
    for key, value in vis_spec.items():
        if key in exclude:
            continue
        if isinstance(value, dict):
            result.properties_set += len(value)
        else:
            result.properties_set += 1

    if "bindings" in vis_spec:
        for _role, ref in vis_spec["bindings"].items():
            if isinstance(ref, list):
                result.bindings_added += len(ref)
            else:
                result.bindings_added += 1

    if "filters" in vis_spec:
        result.filters_added += len(vis_spec["filters"])


def _resolve_style_assignments(
    project: Project,
    style_spec: Any,
    *,
    visual_type: str | None,
    style_cache: dict[str, StylePreset],
) -> list[tuple[str, str, Any]]:
    """Resolve ordered style references into applicable property assignments."""
    if style_spec is None:
        return []
    if isinstance(style_spec, str):
        style_names = [style_spec]
    elif isinstance(style_spec, list) and all(isinstance(item, str) for item in style_spec):
        style_names = style_spec
    else:
        raise ValueError("'style' must be a string or list of strings.")

    assignments: list[tuple[str, str, Any]] = []
    for style_name in style_names:
        if style_name not in style_cache:
            style_cache[style_name] = get_style(project, style_name)
        preset = style_cache[style_name]
        for raw_prop_name, value in preset.properties.items():
            prop_name = normalize_property_name(raw_prop_name, VISUAL_PROPERTIES)
            prop_def = VISUAL_PROPERTIES.get(prop_name)
            if visual_type and prop_def and prop_def.visual_types and visual_type not in prop_def.visual_types:
                continue
            assignments.append((style_name, prop_name, value))
    return assignments


def _restore_definition_snapshot(project: Project, snapshot_dir: Path) -> None:
    """Restore the report definition directory from a pre-apply snapshot."""
    if project.definition_folder.exists():
        shutil.rmtree(project.definition_folder)
    shutil.copytree(snapshot_dir, project.definition_folder)
