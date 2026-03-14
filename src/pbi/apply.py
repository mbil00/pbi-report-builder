"""Declarative YAML apply engine for PBI reports.

Parses a YAML specification and applies it to the report, creating or
updating pages and visuals as needed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from pbi.project import Project, Page, Visual
from pbi.properties import (
    VISUAL_PROPERTIES,
    PAGE_PROPERTIES,
    set_property,
)
from pbi.filters import add_categorical_filter


@dataclass
class ApplyResult:
    """Summary of what was changed by an apply operation."""
    pages_created: list[str] = field(default_factory=list)
    pages_updated: list[str] = field(default_factory=list)
    visuals_created: list[tuple[str, str]] = field(default_factory=list)
    visuals_updated: list[tuple[str, str]] = field(default_factory=list)
    properties_set: int = 0
    bindings_added: int = 0
    filters_added: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.pages_created or self.pages_updated
            or self.visuals_created or self.visuals_updated
        )


def apply_yaml(
    project: Project,
    yaml_content: str,
    *,
    page_filter: str | None = None,
    dry_run: bool = False,
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

        _apply_page(project, page_spec, result, dry_run=dry_run)

    return result


def _apply_page(
    project: Project,
    page_spec: dict,
    result: ApplyResult,
    *,
    dry_run: bool,
) -> None:
    """Apply a single page specification."""
    page_name = page_spec["name"]

    # Find or create page
    try:
        page = project.find_page(page_name)
        result.pages_updated.append(page_name)
    except ValueError:
        # Page not found — create it
        width = page_spec.get("width", 1280)
        height = page_spec.get("height", 720)
        display_option = page_spec.get("displayOption", "FitToPage")
        if dry_run:
            result.pages_created.append(page_name)
            return
        page = project.create_page(
            page_name,
            width=width,
            height=height,
            display_option=display_option,
        )
        result.pages_created.append(page_name)

    if dry_run and page_name in result.pages_created:
        return

    # Apply page properties
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
                    set_property(page.data, prop_name, value, PAGE_PROPERTIES)
                    result.properties_set += 1
                except ValueError as e:
                    result.errors.append(f"Page {page_name}: {prop_name}: {e}")
            else:
                result.properties_set += 1

    # Apply page-level nested objects (background, outspace)
    _apply_nested_properties(
        page.data, page_spec,
        exclude_keys={"name", "width", "height", "displayOption", "visibility",
                       "visuals", "filters", "type"},
        registry=PAGE_PROPERTIES,
        result=result,
        context=f"Page {page_name}",
        dry_run=dry_run,
    )

    # Apply page-level filters
    if "filters" in page_spec:
        _apply_filters(page.data, page_spec["filters"], result,
                       context=f"Page {page_name}", dry_run=dry_run)

    if not dry_run:
        page.save()

    # Apply visuals
    visuals_spec = page_spec.get("visuals", [])
    if not isinstance(visuals_spec, list):
        result.errors.append(f"Page {page_name}: 'visuals' must be a list.")
        return

    for vis_spec in visuals_spec:
        if isinstance(vis_spec, dict):
            _apply_visual(project, page, vis_spec, result, dry_run=dry_run)


def _apply_visual(
    project: Project,
    page: Page,
    vis_spec: dict,
    result: ApplyResult,
    *,
    dry_run: bool,
) -> None:
    """Apply a single visual specification."""
    page_name = page.display_name
    vis_name = vis_spec.get("name")
    vis_type = vis_spec.get("type")

    if not vis_name and not vis_type:
        result.errors.append(f"Page {page_name}: visual must have 'name' or 'type'.")
        return

    # Find existing visual
    visual: Visual | None = None
    if vis_name:
        try:
            visual = project.find_visual(page, vis_name)
        except ValueError:
            pass

    if visual is None and vis_type:
        # Create new visual
        x, y = _parse_position(vis_spec.get("position", "0, 0"))
        w, h = _parse_size(vis_spec.get("size", "300 x 200"))
        if dry_run:
            result.visuals_created.append((page_name, vis_name or vis_type))
            return
        visual = project.create_visual(page, vis_type, x=x, y=y, width=w, height=h)
        if vis_name:
            visual.data["name"] = vis_name
            visual.save()
        result.visuals_created.append((page_name, vis_name or vis_type))
    elif visual is None:
        result.errors.append(
            f"Page {page_name}: visual \"{vis_name}\" not found and no 'type' "
            f"specified for creation."
        )
        return
    else:
        result.visuals_updated.append((page_name, vis_name or visual.name))

    if dry_run:
        # Count would-be changes
        _count_dry_run_changes(vis_spec, result)
        return

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

    # Apply visual properties (nested objects become dot-separated props)
    exclude_keys = {"name", "type", "position", "size", "bindings", "sort",
                     "filters", "isHidden"}
    _apply_nested_properties(
        visual.data, vis_spec,
        exclude_keys=exclude_keys,
        registry=VISUAL_PROPERTIES,
        result=result,
        context=f"{page_name}/{vis_name or visual.name}",
        dry_run=dry_run,
    )

    # isHidden
    if "isHidden" in vis_spec:
        visual.data["isHidden"] = bool(vis_spec["isHidden"])
        result.properties_set += 1

    # Bindings
    if "bindings" in vis_spec:
        _apply_bindings(project, visual, vis_spec["bindings"], result)

    # Sort
    if "sort" in vis_spec:
        _apply_sort(project, visual, vis_spec["sort"], result)

    # Filters
    if "filters" in vis_spec:
        _apply_filters(visual.data, vis_spec["filters"], result,
                       context=f"{page_name}/{vis_name or visual.name}",
                       dry_run=dry_run)

    visual.save()


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
) -> None:
    """Flatten nested YAML dicts into dot-separated property names and apply them.

    Example: {"title": {"show": true, "text": "Hello"}}
    becomes: title.show=true, title.text=Hello
    """
    for key, value in spec.items():
        if key in exclude_keys:
            continue

        prop_name = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"

        if isinstance(value, dict):
            # Recurse into nested dict
            _apply_nested_properties(
                data, value,
                exclude_keys=set(),
                registry=registry,
                result=result,
                context=context,
                dry_run=dry_run,
                prefix=prop_name,
            )
        else:
            # Leaf value — apply as property
            str_value = str(value)
            if dry_run:
                result.properties_set += 1
                continue
            try:
                set_property(data, prop_name, str_value, registry)
                result.properties_set += 1
            except ValueError as e:
                result.errors.append(f"{context}: {prop_name}: {e}")


def _apply_bindings(
    project: Project,
    visual: Visual,
    bindings: dict,
    result: ApplyResult,
) -> None:
    """Apply data bindings from the YAML spec."""
    for role, field_ref in bindings.items():
        if isinstance(field_ref, list):
            # Multiple bindings for this role
            for ref in field_ref:
                _add_single_binding(project, visual, role, str(ref), result)
        else:
            _add_single_binding(project, visual, role, str(field_ref), result)


def _add_single_binding(
    project: Project,
    visual: Visual,
    role: str,
    field_ref: str,
    result: ApplyResult,
) -> None:
    """Add a single data binding."""
    # Parse "Table.Field" or "Table.Field (measure)"
    is_measure = field_ref.endswith("(measure)")
    clean_ref = field_ref.replace("(measure)", "").strip()
    dot = clean_ref.find(".")
    if dot == -1:
        result.errors.append(f"Invalid binding ref: {field_ref}")
        return
    entity = clean_ref[:dot]
    prop = clean_ref[dot + 1:]
    field_type = "measure" if is_measure else "column"

    # Auto-detect from semantic model
    if not is_measure:
        try:
            from pbi.model import SemanticModel
            model = SemanticModel.load(project.root)
            _, prop, field_type = model.resolve_field(clean_ref)
        except (FileNotFoundError, ValueError, TypeError):
            pass

    project.add_binding(visual, role, entity, prop, field_type=field_type)
    result.bindings_added += 1


def _apply_sort(
    project: Project,
    visual: Visual,
    sort_spec: str,
    result: ApplyResult,
) -> None:
    """Apply sort from a spec like 'Table.Field Descending'."""
    parts = str(sort_spec).strip().split()
    if len(parts) < 1:
        return

    field_ref = parts[0]
    # Handle "(measure)" in the middle
    is_measure = "(measure)" in sort_spec
    field_ref = field_ref.replace("(measure)", "").strip()
    direction = "Descending"
    for part in parts[1:]:
        if part.lower() in ("ascending", "asc"):
            direction = "Ascending"
        elif part.lower() in ("descending", "desc"):
            direction = "Descending"

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


def _apply_filters(
    data: dict,
    filters_spec: list,
    result: ApplyResult,
    *,
    context: str,
    dry_run: bool,
) -> None:
    """Apply filters from the YAML spec."""
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

        if filter_type.lower() in ("categorical", "include", "exclude"):
            str_values = [str(v) for v in values] if values else []
            if str_values:
                add_categorical_filter(
                    data, entity, prop, str_values,
                    is_hidden=is_hidden,
                    is_locked=is_locked,
                )
                result.filters_added += 1
        else:
            result.warnings.append(
                f"{context}: filter type '{filter_type}' not yet supported in apply."
            )


def _parse_position(value: Any) -> tuple[int, int]:
    """Parse position from '50, 80' or a dict {'x': 50, 'y': 80}."""
    if isinstance(value, dict):
        return int(value.get("x", 0)), int(value.get("y", 0))
    parts = str(value).split(",")
    if len(parts) == 2:
        return int(parts[0].strip()), int(parts[1].strip())
    return 0, 0


def _parse_size(value: Any) -> tuple[int, int]:
    """Parse size from '600 x 400' or a dict {'width': 600, 'height': 400}."""
    if isinstance(value, dict):
        return int(value.get("width", 300)), int(value.get("height", 200))
    text = str(value)
    # Try "600 x 400" or "600x400"
    match = re.match(r"(\d+)\s*x\s*(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 300, 200


def _count_dry_run_changes(vis_spec: dict, result: ApplyResult) -> None:
    """Count property changes for dry-run reporting."""
    exclude = {"name", "type", "position", "size", "bindings", "sort",
                "filters", "isHidden"}
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
