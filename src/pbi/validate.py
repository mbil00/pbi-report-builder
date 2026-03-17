"""Schema validation for PBIR report files.

Validates visual.json, page.json, and other report definition files against
known structural rules. Does not require downloading external schemas — uses
built-in checks for common errors.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from pbi.project import Project, _read_json


@dataclass
class ValidationIssue:
    """A single validation issue."""

    file: str
    level: str  # "error" or "warning"
    message: str
    path: str = ""


def validate_project(project: Project) -> list[ValidationIssue]:
    """Validate the entire project. Returns list of issues found."""
    issues: list[ValidationIssue] = []

    # Validate report.json
    report_path = project.definition_folder / "report.json"
    if report_path.exists():
        issues.extend(_validate_report(report_path))
    else:
        issues.append(ValidationIssue(
            "definition/report.json", "error", "Missing report.json"
        ))

    # Validate pages
    pages_dir = project.definition_folder / "pages"
    if pages_dir.exists():
        pages_meta = pages_dir / "pages.json"
        if pages_meta.exists():
            issues.extend(_validate_pages_meta(pages_meta, pages_dir))

        for page_dir in sorted(pages_dir.iterdir()):
            if not page_dir.is_dir():
                continue
            page_json = page_dir / "page.json"
            if page_json.exists():
                issues.extend(_validate_page(page_json))
            else:
                issues.append(ValidationIssue(
                    f"pages/{page_dir.name}/page.json", "error",
                    "Page directory exists but page.json is missing"
                ))

            # Validate visuals
            visuals_dir = page_dir / "visuals"
            if visuals_dir.exists():
                for visual_dir in sorted(visuals_dir.iterdir()):
                    if not visual_dir.is_dir():
                        continue
                    visual_json = visual_dir / "visual.json"
                    if visual_json.exists():
                        rel = f"pages/{page_dir.name}/visuals/{visual_dir.name}/visual.json"
                        issues.extend(_validate_visual(visual_json, rel))
                    else:
                        issues.append(ValidationIssue(
                            f"pages/{page_dir.name}/visuals/{visual_dir.name}/visual.json",
                            "error", "Visual directory exists but visual.json is missing"
                        ))

    # Validate visual layout (overlaps, out-of-bounds, zero sizes)
    issues.extend(_validate_layout(project))

    # Validate cross-table relationships in visual bindings
    issues.extend(_validate_visual_relationships(project))

    # Validate bookmarks
    bookmarks_dir = project.definition_folder / "bookmarks"
    if bookmarks_dir.exists():
        meta_path = bookmarks_dir / "bookmarks.json"
        if meta_path.exists():
            issues.extend(_validate_bookmarks_meta(meta_path))
        for bm_file in sorted(bookmarks_dir.glob("*.bookmark.json")):
            issues.extend(_validate_bookmark(bm_file))

    return issues


def _validate_json_file(path: Path) -> tuple[dict | None, list[ValidationIssue]]:
    """Try to read a JSON file. Returns (data, issues)."""
    rel = str(path.relative_to(path.parents[3])) if len(path.parts) > 3 else path.name
    try:
        data = _read_json(path)
        return data, []
    except json.JSONDecodeError as e:
        return None, [ValidationIssue(rel, "error", f"Invalid JSON: {e}")]


def _validate_report(path: Path) -> list[ValidationIssue]:
    """Validate report.json structure."""
    data, issues = _validate_json_file(path)
    if data is None:
        return issues

    rel = "definition/report.json"

    if "$schema" not in data:
        issues.append(ValidationIssue(rel, "warning", "Missing $schema field"))

    for i, pkg in enumerate(data.get("resourcePackages", [])):
        if "resourcePackage" in pkg:
            issues.append(ValidationIssue(
                rel,
                "error",
                "resourcePackages entries must be ResourcePackage objects directly, "
                "not wrapped in a 'resourcePackage' property",
                path=f"resourcePackages[{i}]",
            ))
            continue

        if isinstance(pkg.get("type"), int):
            issues.append(ValidationIssue(
                rel,
                "error",
                "resourcePackages.type must use the schema string enum (for example 'RegisteredResources'), not numeric codes",
                path=f"resourcePackages[{i}].type",
            ))

        for j, item in enumerate(pkg.get("items", [])):
            if isinstance(item.get("type"), int):
                issues.append(ValidationIssue(
                    rel,
                    "error",
                    "resourcePackages item.type must use the schema string enum (for example 'CustomTheme'), not numeric codes",
                    path=f"resourcePackages[{i}].items[{j}].type",
                ))

    issues.extend(_validate_filter_config(data.get("filterConfig"), rel, "filterConfig"))

    return issues


def _validate_pages_meta(path: Path, pages_dir: Path) -> list[ValidationIssue]:
    """Validate pages.json metadata."""
    data, issues = _validate_json_file(path)
    if data is None:
        return issues

    rel = "definition/pages/pages.json"
    order = data.get("pageOrder", [])

    # Check for referenced pages that don't exist
    for page_name in order:
        if not (pages_dir / page_name).exists():
            issues.append(ValidationIssue(
                rel, "error",
                f"pageOrder references '{page_name}' but directory does not exist"
            ))

    # Check for page directories not in order
    for page_dir in pages_dir.iterdir():
        if page_dir.is_dir() and page_dir.name not in order:
            issues.append(ValidationIssue(
                rel, "warning",
                f"Page directory '{page_dir.name}' exists but is not in pageOrder"
            ))

    return issues


def _validate_page(path: Path) -> list[ValidationIssue]:
    """Validate a page.json file."""
    data, issues = _validate_json_file(path)
    if data is None:
        return issues

    page_name = path.parent.name
    rel = f"pages/{page_name}/page.json"

    if "$schema" not in data:
        issues.append(ValidationIssue(rel, "warning", "Missing $schema field"))

    if "displayName" not in data:
        issues.append(ValidationIssue(rel, "warning", "Missing displayName"))

    # Validate page type consistency
    page_type = data.get("type")
    if page_type in ("Drillthrough", "Tooltip"):
        if "pageBinding" not in data:
            issues.append(ValidationIssue(
                rel, "error",
                f"Page type is '{page_type}' but pageBinding is missing"
            ))
        elif data["pageBinding"].get("type") != page_type:
            issues.append(ValidationIssue(
                rel, "error",
                f"Page type is '{page_type}' but pageBinding.type is "
                f"'{data['pageBinding'].get('type')}'"
            ))

    # Validate dimensions
    width = data.get("width", 0)
    height = data.get("height", 0)
    if width <= 0 or height <= 0:
        issues.append(ValidationIssue(
            rel, "warning",
            f"Invalid dimensions: {width}x{height}"
        ))

    # Validate visual interactions reference existing visuals
    interactions = data.get("visualInteractions", [])
    if interactions:
        visuals_dir = path.parent / "visuals"
        visual_names = set()
        if visuals_dir.exists():
            for vdir in visuals_dir.iterdir():
                if vdir.is_dir():
                    vjson = vdir / "visual.json"
                    if vjson.exists():
                        try:
                            vdata = _read_json(vjson)
                            visual_names.add(vdata.get("name", vdir.name))
                        except json.JSONDecodeError:
                            visual_names.add(vdir.name)

        for interaction in interactions:
            source = interaction.get("source", "")
            target = interaction.get("target", "")
            itype = interaction.get("type", "")

            if source and source not in visual_names:
                issues.append(ValidationIssue(
                    rel, "warning",
                    f"Interaction source '{source}' not found on page"
                ))
            if target and target not in visual_names:
                issues.append(ValidationIssue(
                    rel, "warning",
                    f"Interaction target '{target}' not found on page"
                ))
            valid_types = {"Default", "DataFilter", "HighlightFilter", "NoFilter"}
            if itype and itype not in valid_types:
                issues.append(ValidationIssue(
                    rel, "error",
                    f"Invalid interaction type '{itype}'"
                ))

    for i, entry in enumerate(data.get("objects", {}).get("outspace", [])):
        props = entry.get("properties", {})
        if "backgroundColor" in props:
            issues.append(ValidationIssue(
                rel,
                "error",
                "page.objects.outspace properties use 'color', not 'backgroundColor'",
                path=f"objects.outspace[{i}].properties.backgroundColor",
            ))

    issues.extend(_validate_filter_config(data.get("filterConfig"), rel, "filterConfig"))

    return issues


def _validate_visual(path: Path, rel: str) -> list[ValidationIssue]:
    """Validate a visual.json file."""
    data, issues = _validate_json_file(path)
    if data is None:
        return issues

    if "$schema" not in data:
        issues.append(ValidationIssue(rel, "warning", "Missing $schema field"))

    if "name" not in data:
        issues.append(ValidationIssue(rel, "error", "Missing name field"))

    if "position" not in data:
        issues.append(ValidationIssue(rel, "error", "Missing position field"))

    # Must have either visual or visualGroup
    has_visual = "visual" in data
    has_group = "visualGroup" in data
    if not has_visual and not has_group:
        issues.append(ValidationIssue(
            rel, "error",
            "Must have either 'visual' or 'visualGroup' key"
        ))
    if has_visual and has_group:
        issues.append(ValidationIssue(
            rel, "error",
            "Cannot have both 'visual' and 'visualGroup' keys"
        ))

    if has_visual:
        visual = data["visual"]
        if "visualType" not in visual:
            issues.append(ValidationIssue(
                rel, "error", "Missing visual.visualType"
            ))

        # Check for common property errors in visualContainerObjects
        if "visualContainerObjects" in data:
            issues.append(ValidationIssue(
                rel, "error",
                "visualContainerObjects must be nested under visual.visualContainerObjects, not at the root of visual.json"
            ))

        container_objects = visual.get("visualContainerObjects", {})
        for obj_name, entries in container_objects.items():
            if not isinstance(entries, list):
                issues.append(ValidationIssue(
                    rel, "error",
                    f"visualContainerObjects.{obj_name} must be an array, got {type(entries).__name__}"
                ))
            elif entries:
                for i, entry in enumerate(entries):
                    if not isinstance(entry, dict):
                        issues.append(ValidationIssue(
                            rel, "error",
                            f"visualContainerObjects.{obj_name}[{i}] must be an object"
                        ))
                    elif "properties" not in entry:
                        issues.append(ValidationIssue(
                            rel, "warning",
                            f"visualContainerObjects.{obj_name}[{i}] has no 'properties' key"
                        ))

        # Check objects (chart formatting)
        objects = visual.get("objects", {})
        for obj_name, entries in objects.items():
            if not isinstance(entries, list):
                issues.append(ValidationIssue(
                    rel, "error",
                    f"visual.objects.{obj_name} must be an array, got {type(entries).__name__}"
                ))

        # Schema validation — check objects and properties against extracted PBI capabilities
        visual_type = visual.get("visualType")
        if visual_type and objects:
            issues.extend(_validate_visual_schema(visual_type, objects, rel))

    # Validate parentGroupName is a string
    parent = data.get("parentGroupName")
    if parent is not None and not isinstance(parent, str):
        issues.append(ValidationIssue(
            rel, "error",
            f"parentGroupName must be a string, got {type(parent).__name__}"
        ))

    issues.extend(_validate_filter_config(data.get("filterConfig"), rel, "filterConfig"))

    # Check for crash-causing patterns
    issues.extend(_validate_visual_name(data, rel))
    if has_visual:
        issues.extend(_validate_gradient_null_strategy(data["visual"], rel))
        issues.extend(_validate_orphaned_column_metadata(data["visual"], rel))

    return issues


def _validate_visual_name(data: dict, rel: str) -> list[ValidationIssue]:
    """Check that visual name uses only identifier-safe characters."""
    issues: list[ValidationIssue] = []
    name = data.get("name", "")
    if name and re.search(r"[^a-zA-Z0-9_-]", name):
        issues.append(ValidationIssue(
            rel, "error",
            f'Visual name "{name}" contains unsupported characters '
            "(spaces, colons, etc.). Power BI will refuse to load the report.",
            path="name",
        ))
    return issues


def _validate_gradient_null_strategy(visual: dict, rel: str) -> list[ValidationIssue]:
    """Check that linearGradient2/3 objects include nullColoringStrategy."""
    issues: list[ValidationIssue] = []
    objects = visual.get("objects", {})
    for obj_key, entries in objects.items():
        if not isinstance(entries, list):
            continue
        for i, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            props = entry.get("properties", {})
            for prop_name, prop_val in props.items():
                if not isinstance(prop_val, dict):
                    continue
                fill_rule = (
                    prop_val.get("solid", {}).get("color", {})
                    .get("expr", {}).get("FillRule", {}).get("FillRule", {})
                )
                for grad_key in ("linearGradient2", "linearGradient3"):
                    gradient = fill_rule.get(grad_key)
                    if gradient and "nullColoringStrategy" not in gradient:
                        issues.append(ValidationIssue(
                            rel, "error",
                            f"objects.{obj_key}[{i}].{prop_name}: {grad_key} is missing "
                            "nullColoringStrategy — Power BI will crash.",
                            path=f"objects.{obj_key}[{i}].properties.{prop_name}",
                        ))
    return issues


def _validate_orphaned_column_metadata(visual: dict, rel: str) -> list[ValidationIssue]:
    """Check for columnWidth/columnFormatting entries referencing unbound fields."""
    issues: list[ValidationIssue] = []
    query_state = visual.get("query", {}).get("queryState", {})
    bound_refs: set[str] = set()
    for _role, config in query_state.items():
        for proj in config.get("projections", []):
            ref = proj.get("queryRef", "")
            if ref:
                bound_refs.add(ref.lower())

    objects = visual.get("objects", {})
    for obj_key in ("columnWidth", "columnFormatting"):
        entries = objects.get(obj_key, [])
        if not isinstance(entries, list):
            continue
        for i, entry in enumerate(entries):
            metadata = entry.get("selector", {}).get("metadata")
            if metadata and metadata.lower() not in bound_refs:
                issues.append(ValidationIssue(
                    rel, "warning",
                    f"objects.{obj_key}[{i}] references \"{metadata}\" "
                    "which is not bound to any projection.",
                    path=f"objects.{obj_key}[{i}]",
                ))
    return issues


def _validate_bookmark(path: Path) -> list[ValidationIssue]:
    """Validate a bookmark.json file."""
    data, issues = _validate_json_file(path)
    if data is None:
        return issues

    rel = f"bookmarks/{path.name}"

    if "$schema" not in data:
        issues.append(ValidationIssue(rel, "warning", "Missing $schema field"))

    for required in ("displayName", "name", "explorationState"):
        if required not in data:
            issues.append(ValidationIssue(
                rel, "error", f"Missing required field: {required}"
            ))

    exploration = data.get("explorationState", {})
    if "activeSection" not in exploration:
        issues.append(ValidationIssue(
            rel, "warning", "explorationState missing activeSection"
        ))

    for section_name, section_state in exploration.get("sections", {}).items():
        if "visualContainers" not in section_state:
            issues.append(ValidationIssue(
                rel,
                "error",
                f'Section "{section_name}" is missing required visualContainers state',
                path=f"explorationState.sections.{section_name}",
            ))
            continue

        for visual_name, visual_state in section_state.get("visualContainers", {}).items():
            single_visual = visual_state.get("singleVisual", {})
            if "displayState" in single_visual:
                issues.append(ValidationIssue(
                    rel,
                    "error",
                    "Bookmark uses singleVisual.displayState; the published bookmark schema requires singleVisual.display",
                    path=(
                        "explorationState.sections."
                        f"{section_name}.visualContainers.{visual_name}.singleVisual.displayState"
                    ),
                ))

    return issues


def _validate_bookmarks_meta(path: Path) -> list[ValidationIssue]:
    """Validate bookmarks metadata shape."""
    data, issues = _validate_json_file(path)
    if data is None:
        return issues

    rel = "definition/bookmarks/bookmarks.json"

    if "bookmarkOrder" in data:
        issues.append(ValidationIssue(
            rel,
            "error",
            "bookmarks.json uses legacy bookmarkOrder; the published schema requires an items array",
            path="bookmarkOrder",
        ))

    items = data.get("items")
    if items is None:
        issues.append(ValidationIssue(rel, "error", "Missing items array"))
    elif not isinstance(items, list):
        issues.append(ValidationIssue(rel, "error", "items must be an array"))

    return issues


def _validate_filter_config(
    filter_config: dict | None,
    rel: str,
    path_prefix: str,
) -> list[ValidationIssue]:
    """Validate filter structures against the published PBIR schema."""
    issues: list[ValidationIssue] = []
    if not filter_config:
        return issues

    for i, filter_obj in enumerate(filter_config.get("filters", [])):
        filter_path = f"{path_prefix}.filters[{i}]"
        where = filter_obj.get("filter", {}).get("Where", [])

        if filter_obj.get("type") == "TopN":
            if any("Top" in clause.get("Condition", {}) for clause in where):
                issues.append(ValidationIssue(
                    rel,
                    "error",
                    "TopN filter uses unsupported Condition.Top payload; the published PBIR semanticQuery schema does not define it",
                    path=filter_path,
                ))

        if filter_obj.get("type") == "RelativeDate":
            if any("RelativeDate" in clause.get("Condition", {}) for clause in where):
                issues.append(ValidationIssue(
                    rel,
                    "error",
                    "RelativeDate filter uses unsupported Condition.RelativeDate payload; the published PBIR semanticQuery schema does not define it",
                    path=filter_path,
                ))

    return issues


def _validate_layout(project: Project) -> list[ValidationIssue]:
    """Check visual positions for overlaps, out-of-bounds, and zero sizes."""
    issues: list[ValidationIssue] = []

    for page in project.get_pages():
        visuals = project.get_visuals(page)
        page_w = page.width
        page_h = page.height

        rects: list[tuple[str, str, int, int, int, int]] = []  # (name, rel, x, y, w, h)

        for vis in visuals:
            if "visualGroup" in vis.data:
                continue
            pos = vis.position
            x = int(pos.get("x", 0))
            y = int(pos.get("y", 0))
            w = int(pos.get("width", 0))
            h = int(pos.get("height", 0))
            rel = f"pages/{page.folder.name}/visuals/{vis.folder.name}/visual.json"

            # Zero/negative dimensions
            if w <= 0 or h <= 0:
                issues.append(ValidationIssue(
                    rel, "warning",
                    f'Visual "{vis.name}" has invalid size: {w}x{h}',
                ))
                continue

            # Out of bounds
            if x + w > page_w + 5:  # 5px tolerance
                issues.append(ValidationIssue(
                    rel, "warning",
                    f'Visual "{vis.name}" extends {x + w - page_w}px past right edge '
                    f'(x={x}, w={w}, page={page_w})',
                ))
            if y + h > page_h + 5:
                issues.append(ValidationIssue(
                    rel, "warning",
                    f'Visual "{vis.name}" extends {y + h - page_h}px past bottom edge '
                    f'(y={y}, h={h}, page={page_h})',
                ))

            rects.append((vis.name, rel, x, y, w, h))

        # Check overlaps (only report significant ones > 10px in both axes)
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                n1, r1, x1, y1, w1, h1 = rects[i]
                n2, _r2, x2, y2, w2, h2 = rects[j]
                ox = max(0, min(x1 + w1, x2 + w2) - max(x1, x2))
                oy = max(0, min(y1 + h1, y2 + h2) - max(y1, y2))
                if ox > 10 and oy > 10:
                    issues.append(ValidationIssue(
                        r1, "warning",
                        f'Visual "{n1}" overlaps "{n2}" by {ox}x{oy}px',
                    ))

    return issues


def _validate_visual_relationships(project: Project) -> list[ValidationIssue]:
    """Check visual bindings for cross-table fields without relationship paths."""
    issues: list[ValidationIssue] = []

    try:
        from pbi.modeling.schema import SemanticModel
        model = SemanticModel.load(project.root)
    except (FileNotFoundError, Exception):
        return issues  # No model or can't load — skip

    if not model.relationships:
        return issues  # No relationships to validate against

    table_names = {t.name.lower() for t in model.tables}

    for page in project.get_pages():
        for visual in project.get_visuals(page):
            query_state = visual.data.get("visual", {}).get("query", {}).get("queryState", {})
            if not query_state:
                continue

            # Collect all tables referenced by this visual
            tables_used: set[str] = set()
            for _role, config in query_state.items():
                for proj in config.get("projections", []):
                    ref = proj.get("queryRef", "")
                    dot = ref.find(".")
                    if dot > 0:
                        table = ref[:dot]
                        if table.lower() in table_names:
                            tables_used.add(table)

            if len(tables_used) < 2:
                continue

            # Check that every pair of tables has a relationship path
            table_list = sorted(tables_used)
            for i in range(len(table_list)):
                for j in range(i + 1, len(table_list)):
                    path = model.find_path(table_list[i], table_list[j])
                    if path is None:
                        # Measures-only tables don't need relationships
                        try:
                            t1 = model.find_table(table_list[i])
                            t2 = model.find_table(table_list[j])
                            if not t1.columns or not t2.columns:
                                continue
                        except ValueError:
                            pass
                        rel = f"pages/{page.folder.name}/visuals/{visual.folder.name}/visual.json"
                        issues.append(ValidationIssue(
                            rel,
                            "warning",
                            f'Visual "{visual.name}" references tables '
                            f'"{table_list[i]}" and "{table_list[j]}" '
                            f'which have no relationship path',
                        ))

    return issues


def _validate_visual_schema(
    visual_type: str,
    objects: dict,
    rel: str,
) -> list[ValidationIssue]:
    """Validate visual.objects against the extracted PBI capability schema.

    Checks that object names and property names are valid for the visual type.
    """
    from pbi.visual_schema import validate_object, validate_property

    issues: list[ValidationIssue] = []

    for obj_name, entries in objects.items():
        obj_warning = validate_object(visual_type, obj_name)
        if obj_warning is not None:
            issues.append(ValidationIssue(
                rel, "warning",
                f"Schema: {obj_warning}",
            ))
            continue

        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            props = entry.get("properties", {})
            for prop_name in props:
                prop_warning = validate_property(visual_type, obj_name, prop_name)
                if prop_warning is not None:
                    issues.append(ValidationIssue(
                        rel, "warning",
                        f"Schema: {prop_warning}",
                    ))

    return issues
