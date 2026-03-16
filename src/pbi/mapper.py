"""Project mapper — generates a human-readable YAML index of the entire PBIP project."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from pbi.project import Project, Page, Visual
from pbi.filters import get_filters, parse_filter
from pbi.formatting import get_conditional_formats
from pbi.properties import decode_pbi_value


def generate_map(
    project: Project,
    *,
    page_filter: str | None = None,
    pages_only: bool = False,
    model_only: bool = False,
) -> str:
    """Generate a full YAML map of the project.

    Args:
        page_filter: Show only this page (name, display name, or 1-based index).
        pages_only: Show pages only, no model section.
        model_only: Show model only, no pages section.
    """
    lines: list[str] = []
    rel = _rel_path_fn(project.root)

    # Header
    lines.append(f"# Project: {project.project_name}")
    lines.append(f"# Report:  {project.report_folder.name}")
    lines.append(f"# Generated: {date.today().isoformat()}")
    lines.append("# Regenerate: pbi map")
    lines.append("# Edit a page: pbi page export \"Page Name\" -o page.yaml")
    lines.append("")

    # Semantic model
    if not pages_only:
        _write_model_section(lines, project)

    if model_only:
        return "\n".join(lines) + "\n"

    # Report-level filters
    if not page_filter:
        _write_filters_section(lines, project.get_report_meta(), "report", indent=0)

    # Pages
    lines.append("pages:")
    meta = project.get_pages_meta()
    active_page = meta.get("activePageName")

    all_pages = project.get_pages()

    if page_filter:
        # Resolve the page filter via project.find_page for consistent lookup
        try:
            matched = project.find_page(page_filter)
            all_pages = [matched]
        except ValueError:
            lines.append(f"  # No page matching \"{page_filter}\"")
            return "\n".join(lines) + "\n"

    for page in all_pages:
        visuals = project.get_visuals(page)
        _write_page(lines, project, page, visuals, active_page, rel)

    return "\n".join(lines) + "\n"


def _write_model_section(lines: list[str], project: Project) -> None:
    """Write the semantic model summary."""
    try:
        from pbi.model import SemanticModel
        model = SemanticModel.load(project.root)
    except (FileNotFoundError, ImportError):
        lines.append("model: null  # no semantic model found")
        lines.append("")
        return

    lines.append("model:")
    for table in model.tables:
        lines.append(f"  {_ys(table.name)}:")
        visible_cols = [c.name for c in table.columns if not c.is_hidden]
        if visible_cols:
            lines.append(f"    columns: [{', '.join(_ys(c) for c in visible_cols)}]")
        hidden_cols = [c.name for c in table.columns if c.is_hidden]
        if hidden_cols:
            lines.append(f"    hidden:  [{', '.join(_ys(c) for c in hidden_cols)}]")
        if table.measures:
            lines.append(f"    measures: [{', '.join(_ys(m.name) for m in table.measures)}]")
        if table.hierarchies:
            for h in table.hierarchies:
                levels_str = " > ".join(lv.column for lv in h.levels)
                lines.append(f"    hierarchy {_ys(h.name)}: [{levels_str}]")
    lines.append("")


def _write_page(
    lines: list[str],
    project: Project,
    page: Page,
    visuals: list[Visual],
    active_page: str | None,
    rel,
) -> None:
    """Write a single page entry."""
    flags = []
    if active_page == page.name:
        flags.append("active")
    if page.visibility == "HiddenInViewMode":
        flags.append("hidden")
    flag_str = f"  # {', '.join(flags)}" if flags else ""

    lines.append(f"  - name: {_ys(page.display_name)}{flag_str}")
    lines.append(f"    id: {page.name}")
    lines.append(f"    path: {rel(page.folder)}")
    lines.append(f"    size: {page.width} x {page.height}")

    # Page-level filters
    _write_filters_section(lines, page.data, "page", indent=4)

    if not visuals:
        lines.append("    visuals: []")
        lines.append("")
        return

    # Detect groups: visuals with visualGroup instead of visual
    groups: dict[str, Visual] = {}
    children: dict[str, list[Visual]] = {}  # group_name -> children
    ungrouped: list[Visual] = []

    for v in visuals:
        if "visualGroup" in v.data:
            groups[v.name] = v
        elif v.data.get("parentGroupName"):
            parent = v.data["parentGroupName"]
            children.setdefault(parent, []).append(v)
        else:
            ungrouped.append(v)

    lines.append("    visuals:")

    # Write groups first
    for group_name, group_vis in groups.items():
        group_children = children.get(group_name, [])
        _write_group(lines, project, group_vis, group_children, rel)

    # Then ungrouped visuals
    for v in ungrouped:
        _write_visual(lines, project, v, indent=6, rel=rel)

    lines.append("")


def _write_group(
    lines: list[str],
    project: Project,
    group: Visual,
    children: list[Visual],
    rel,
) -> None:
    """Write a visual group with its children."""
    lines.append(f"      - group: {_ys(group.name)}")
    lines.append(f"        path: {rel(group.folder)}")
    if not children:
        lines.append("        visuals: []")
        return

    lines.append("        visuals:")
    for v in children:
        _write_visual(lines, project, v, indent=10, rel=rel)


def _write_visual(
    lines: list[str],
    project: Project,
    visual: Visual,
    indent: int,
    rel,
) -> None:
    """Write a single visual entry."""
    pad = " " * indent
    pos = visual.position

    # Label: use friendly name if set, otherwise show type + truncated id
    name = visual.name
    vtype = visual.visual_type
    is_hex_name = all(c in "0123456789abcdef" for c in name) and len(name) >= 16
    label = f"{vtype}:{name[:12]}…" if is_hex_name else name

    lines.append(f"{pad}- name: {_ys(label)}")
    if not is_hex_name:
        lines.append(f"{pad}  type: {vtype}")
    else:
        lines.append(f"{pad}  type: {vtype}")
        lines.append(f"{pad}  id: {name}")
    lines.append(f"{pad}  path: {rel(visual.folder)}")
    lines.append(f"{pad}  position: {pos.get('x', 0)}, {pos.get('y', 0)}")
    lines.append(f"{pad}  size: {pos.get('width', 0)} x {pos.get('height', 0)}")

    if visual.data.get("isHidden"):
        lines.append(f"{pad}  hidden: true")

    # Title from formatting
    title = _get_visual_title(visual)
    if title:
        lines.append(f"{pad}  title: {_ys(title)}")

    # Bindings
    bindings = project.get_bindings(visual)
    if bindings:
        lines.append(f"{pad}  bindings:")
        # Group by role
        by_role: dict[str, list[tuple[str, str, str]]] = {}
        for role, entity, prop, ftype in bindings:
            by_role.setdefault(role, []).append((entity, prop, ftype))

        for role, fields in by_role.items():
            if len(fields) == 1:
                entity, prop, ftype = fields[0]
                suffix = " (measure)" if ftype == "measure" else ""
                lines.append(f"{pad}    {role}: {entity}.{_ys(prop)}{suffix}")
            else:
                lines.append(f"{pad}    {role}:")
                for entity, prop, ftype in fields:
                    suffix = " (measure)" if ftype == "measure" else ""
                    lines.append(f"{pad}      - {entity}.{_ys(prop)}{suffix}")

    # Sort definition
    sorts = project.get_sort(visual)
    if sorts:
        entity, prop, ftype, direction = sorts[0]
        suffix = " (measure)" if ftype == "measure" else ""
        lines.append(f"{pad}  sort: {entity}.{_ys(prop)}{suffix} {direction}")

    # Key chart formatting
    _write_chart_summary(lines, visual, pad)

    # Conditional formatting
    _write_conditional_formatting(lines, visual, pad)

    # Visual-level filters
    _write_filters_section(lines, visual.data, "visual", indent=len(pad) + 2)


def _get_visual_title(visual: Visual) -> str | None:
    """Extract title text from visualContainerObjects."""
    title_entries = (
        visual.data
        .get("visual", {})
        .get("visualContainerObjects", {})
        .get("title", [])
    )
    if not title_entries:
        return None
    text_raw = title_entries[0].get("properties", {}).get("text")
    if text_raw is None:
        return None
    decoded = decode_pbi_value(text_raw)
    return str(decoded) if decoded else None


def _ys(value: str) -> str:
    """Format a string for YAML output — quote if needed."""
    if not value:
        return '""'
    needs_quote = (
        any(c in value for c in ':{}[]#&*!|>\'"@%,')
        or value.startswith(("-", " "))
        or value != value.strip()
        or value.lower() in ("true", "false", "null", "yes", "no")
    )
    if needs_quote:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _write_filters_section(
    lines: list[str], data: dict, level: str, indent: int,
) -> None:
    """Write a filters summary if any filters exist."""
    filters = get_filters(data)
    if not filters:
        return

    pad = " " * indent
    items = []
    for f in filters:
        info = parse_filter(f, level)
        vals = ", ".join(info.values) if info.values else "all"
        flags = []
        if info.is_hidden:
            flags.append("hidden")
        if info.is_locked:
            flags.append("locked")
        flag_str = f" ({', '.join(flags)})" if flags else ""
        items.append(f"{info.field_entity}.{info.field_prop} {info.filter_type}: {vals}{flag_str}")

    lines.append(f"{pad}filters:")
    for item in items:
        lines.append(f"{pad}  - {item}")


def _write_chart_summary(lines: list[str], visual: Visual, pad: str) -> None:
    """Write key chart formatting properties if present."""
    objects = visual.data.get("visual", {}).get("objects", {})
    if not objects:
        return

    summaries = []

    # Legend
    legend = _get_obj_prop(objects, "legend", "show")
    if legend is not None:
        pos = _get_obj_prop(objects, "legend", "position")
        legend_str = f"legend: {_fmt_val(legend)}"
        if pos is not None:
            legend_str += f" ({_fmt_val(pos)})"
        summaries.append(legend_str)

    # Labels
    labels_show = _get_obj_prop(objects, "labels", "show")
    if labels_show is not None:
        summaries.append(f"labels: {_fmt_val(labels_show)}")

    # Axes
    for axis_key, axis_name in [("categoryAxis", "xAxis"), ("valueAxis", "yAxis")]:
        show = _get_obj_prop(objects, axis_key, "show")
        if show is not None:
            summaries.append(f"{axis_name}: {_fmt_val(show)}")

    if summaries:
        lines.append(f"{pad}  formatting: {{{', '.join(summaries)}}}")


def _write_conditional_formatting(lines: list[str], visual: Visual, pad: str) -> None:
    """Write conditional formatting summary if present."""
    formats = get_conditional_formats(visual.data)
    if not formats:
        return

    items = []
    for f in formats:
        items.append(f"{f.object_name}.{f.property_name}: {f.details}")

    lines.append(f"{pad}  conditionalFormatting:")
    for item in items:
        lines.append(f"{pad}    - {item}")


def _get_obj_prop(objects: dict, key: str, prop: str) -> object | None:
    """Read a single property from visual objects."""
    entries = objects.get(key, [])
    if not entries or not isinstance(entries, list):
        return None
    raw = entries[0].get("properties", {}).get(prop)
    if raw is None:
        return None
    return decode_pbi_value(raw)


def _fmt_val(val: object) -> str:
    """Format a decoded PBI value for display."""
    if isinstance(val, bool):
        return str(val).lower()
    return str(val)


def _rel_path_fn(root: Path):
    """Return a function that converts absolute paths to relative."""
    def rel(path: Path) -> str:
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)
    return rel
