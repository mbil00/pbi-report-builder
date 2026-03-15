"""Visual CLI commands and shared visual inspection helpers."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from pbi.properties import (
    VISUAL_PROPERTIES,
    canonical_object_property_name,
    get_known_default,
    get_property,
    get_visual_objects,
    list_properties,
    property_aliases_for,
    set_property,
)

from .common import ProjectOpt, console, get_project, parse_property_assignments, resolve_field_type

visual_app = typer.Typer(help="Visual operations.", no_args_is_help=True)
visual_arrange_app = typer.Typer(help="Visual layout operations.", no_args_is_help=True)
visual_sort_app = typer.Typer(help="Visual sort operations.", no_args_is_help=True)
visual_format_app = typer.Typer(help="Visual conditional formatting operations.", no_args_is_help=True)
visual_app.add_typer(visual_sort_app, name="sort")
visual_app.add_typer(visual_format_app, name="format")
visual_app.add_typer(visual_arrange_app, name="arrange")


def collect_visual_property_rows(
    visual_data: dict,
    *,
    include_core: bool = True,
) -> list[tuple[str, str]]:
    """Collect explicit visual properties for inspection views."""
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if include_core:
        for prop_name, prop_def in VISUAL_PROPERTIES.items():
            if not prop_def.json_path:
                continue
            value = get_property(visual_data, prop_name, VISUAL_PROPERTIES)
            if value is None:
                continue
            key = (prop_name, str(value))
            if key in seen:
                continue
            seen.add(key)
            rows.append((prop_name, str(value)))

    from pbi.properties import decode_pbi_value

    for section in ("visualContainerObjects", "objects"):
        section_data = visual_data.get("visual", {}).get(section, {})
        if not isinstance(section_data, dict):
            continue
        for obj_name, entries in section_data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                selector = entry.get("selector", {})
                selector_name = selector.get("metadata") or selector.get("id")
                for prop_name, raw_value in entry.get("properties", {}).items():
                    decoded = decode_pbi_value(raw_value)
                    canonical = canonical_object_property_name(
                        obj_name,
                        prop_name,
                        VISUAL_PROPERTIES,
                        objects_path=section,
                        selector=selector.get("id"),
                    )
                    label = canonical
                    if selector_name:
                        label = f"{label} [{selector_name}]"
                    key = (label, str(decoded))
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append((label, str(decoded)))

    return rows


def resolve_visual_property_value(
    visual_data: dict,
    prop_name: str,
    *,
    include_defaults: bool = False,
) -> tuple[object | None, str]:
    """Resolve an explicit or known-default value for a single visual property."""
    value = get_property(visual_data, prop_name, VISUAL_PROPERTIES)
    if value is not None:
        return value, "explicit"
    if include_defaults:
        visual_type = visual_data.get("visual", {}).get("visualType")
        default = get_known_default(prop_name, VISUAL_PROPERTIES, visual_type=visual_type)
        if default is not None:
            return default, "default"
    return None, ""


def collect_effective_visual_property_rows(
    visual_data: dict,
    *,
    include_core: bool,
    include_defaults: bool,
) -> list[tuple[str, str, str]]:
    """Collect effective visual properties with their source."""
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    visual_type = visual_data.get("visual", {}).get("visualType")

    explicit_rows = collect_visual_property_rows(visual_data, include_core=include_core)
    for prop_name, value in explicit_rows:
        rows.append((prop_name, value, "explicit"))
        seen.add(prop_name)

    if not include_defaults:
        return rows

    for prop_name, prop_def in sorted(VISUAL_PROPERTIES.items()):
        group = "core" if prop_def.json_path else "container"
        if not include_core and group == "core":
            continue
        if prop_def.visual_types and visual_type not in prop_def.visual_types:
            continue
        if prop_name in seen:
            continue
        default = get_known_default(prop_name, VISUAL_PROPERTIES, visual_type=visual_type)
        if default is None:
            continue
        rows.append((prop_name, str(default), "default"))

    return rows


def flatten_visual_diff_spec(
    visual_spec: dict,
    *,
    include_core: bool,
) -> dict[str, str]:
    """Flatten a canonical exported visual spec into path/value rows for diffing."""
    import copy

    filtered = copy.deepcopy(visual_spec)
    filtered.pop("id", None)
    filtered.pop("name", None)
    if not include_core:
        for key in ("position", "size", "isHidden"):
            filtered.pop(key, None)
    else:
        position = filtered.get("position")
        if isinstance(position, str):
            parts = [part.strip() for part in position.split(",", 1)]
            if len(parts) == 2:
                filtered["position"] = {"x": parts[0], "y": parts[1]}
        size = filtered.get("size")
        if isinstance(size, str):
            parts = [part.strip() for part in size.lower().split("x", 1)]
            if len(parts) == 2:
                filtered["size"] = {"width": parts[0], "height": parts[1]}

    rows: dict[str, str] = {}
    _flatten_diff_value(filtered, rows)
    return rows


def _flatten_diff_value(
    value: object,
    rows: dict[str, str],
    *,
    prefix: str = "",
) -> None:
    """Recursively flatten a nested exported spec into dotted paths."""
    if isinstance(value, dict):
        if not value and prefix:
            rows[prefix] = "{}"
            return
        for key, child in value.items():
            child_prefix = key if not prefix else f"{prefix}.{key}"
            _flatten_diff_value(child, rows, prefix=child_prefix)
        return

    if isinstance(value, list):
        if not value:
            rows[prefix] = "[]"
            return
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            _flatten_diff_value(child, rows, prefix=child_prefix)
        return

    rows[prefix] = _stringify_diff_value(value)


def _stringify_diff_value(value: object) -> str:
    """Stringify scalar values for visual diff output."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def prepare_visual_property_updates(
    data: dict,
    pairs: list[tuple[str, str]],
    *,
    measure_ref: str | None = None,
) -> tuple[dict, list[tuple[str, object, object]]]:
    """Apply a property batch to a copy of the visual for validation."""
    import copy

    updated = copy.deepcopy(data)
    changes: list[tuple[str, object, object]] = []
    for prop, value in pairs:
        old = get_property(updated, prop, VISUAL_PROPERTIES, measure_ref=measure_ref)
        try:
            set_property(updated, prop, value, VISUAL_PROPERTIES, measure_ref=measure_ref)
        except ValueError as e:
            raise ValueError(f"{prop}: {e}") from e
        new = get_property(updated, prop, VISUAL_PROPERTIES, measure_ref=measure_ref)
        changes.append((prop, old, new))
    return updated, changes


@visual_app.command("types")
def visual_types(
    visual_type: Annotated[str | None, typer.Argument(help="Show roles for a specific visual type.")] = None,
) -> None:
    """List known visual types and their data roles."""
    from pbi.roles import list_visual_type_info, normalize_visual_type

    if visual_type:
        normalized = normalize_visual_type(visual_type)
        all_types = list_visual_type_info()
        matches = [info for info in all_types if normalized.lower() in info.visual_type.lower()]
        if not matches:
            console.print(f'[red]Unknown visual type "{visual_type}".[/red]')
            console.print("[dim]Use 'pbi visual types' to see all known types.[/dim]")
            raise typer.Exit(1)
        for info in matches:
            table = Table(title=info.visual_type, box=box.SIMPLE)
            table.add_column("Role", style="bold cyan")
            table.add_column("Description")
            table.add_column("Multi", style="dim", justify="center")
            for role in info.roles:
                table.add_row(role["name"], role["description"], role["multi"])
            console.print(table)
            console.print(f"[dim]Status:[/dim] {info.status}")
            console.print(f"[dim]{info.note}[/dim]")
        return

    table = Table(title="Visual Types & Data Roles", box=box.SIMPLE)
    table.add_column("Visual Type", style="cyan")
    table.add_column("Status", style="dim")
    table.add_column("Roles")

    for info in list_visual_type_info():
        role_names = ", ".join(role["name"] for role in info.roles) if info.roles else "-"
        table.add_row(info.visual_type, info.status, role_names)

    console.print(table)
    console.print("\n[dim]role-backed = role metadata modeled; sample-backed = observed in exported PBIR but binding roles are not modeled yet.[/dim]")
    console.print("[dim]Use 'pbi visual types <type>' for detailed role info.[/dim]")


@visual_sort_app.command("get")
def visual_sort_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show a visual's sort definition."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    sorts = proj.get_sort(vis)
    if not sorts:
        console.print("[dim]No sort definition.[/dim]")
        return
    for entity, prop, ftype, direction in sorts:
        kind = " (measure)" if ftype == "measure" else ""
        console.print(f"[cyan]{entity}.{prop}[/cyan]{kind} {direction}")


@visual_sort_app.command("set")
def visual_sort_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    field: Annotated[str, typer.Argument(help="Sort field as Table.Field.")],
    direction: Annotated[str, typer.Option("--direction", help="Sort direction: asc or desc.")] = "desc",
    field_type: Annotated[str, typer.Option("--field-type", help="Field type: auto, column, or measure.")] = "auto",
    project: ProjectOpt = None,
) -> None:
    """Set a visual's sort definition."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if direction not in {"asc", "desc"}:
        console.print("[red]Error:[/red] --direction must be 'asc' or 'desc'.")
        raise typer.Exit(1)

    try:
        entity, prop, resolved_field_type = resolve_field_type(proj, field, field_type)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    descending = direction == "desc"
    proj.set_sort(vis, entity, prop, field_type=resolved_field_type, descending=descending)
    console.print(f'Sort set: [cyan]{entity}.{prop}[/cyan] {"Descending" if descending else "Ascending"}')


@visual_sort_app.command("clear")
def visual_sort_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's sort definition."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if proj.clear_sort(vis):
        console.print("Sort definition removed.")
    else:
        console.print("[dim]No sort definition to remove.[/dim]")


@visual_format_app.command("get")
def visual_format_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show conditional formatting on a visual."""
    from pbi.formatting import get_conditional_formats

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    formats = get_conditional_formats(vis.data)
    if not formats:
        console.print("[dim]No conditional formatting on this visual.[/dim]")
        return
    table = Table(title="Conditional Formatting", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Mode")
    table.add_column("Source", style="bold")
    table.add_column("Details", style="dim")
    for fmt in formats:
        table.add_row(f"{fmt.object_name}.{fmt.property_name}", fmt.format_type, fmt.field_ref, fmt.details)
    console.print(table)


@visual_format_app.command("set")
def visual_format_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    prop: Annotated[str, typer.Argument(help="Property as object.prop (e.g. dataPoint.fill).")],
    mode: Annotated[str, typer.Option("--mode", help="Formatting mode: measure or gradient.")],
    source: Annotated[str, typer.Option("--source", help="Source field: Table.Measure for measure mode, Table.Field for gradient mode.")],
    min_color: Annotated[str | None, typer.Option("--min-color", help="Gradient minimum color (#hex).")] = None,
    min_value: Annotated[float | None, typer.Option("--min-value", help="Gradient minimum value.")] = None,
    mid_color: Annotated[str | None, typer.Option("--mid-color", help="Gradient midpoint color (#hex).")] = None,
    mid_value: Annotated[float | None, typer.Option("--mid-value", help="Gradient midpoint value.")] = None,
    max_color: Annotated[str | None, typer.Option("--max-color", help="Gradient maximum color (#hex).")] = None,
    max_value: Annotated[float | None, typer.Option("--max-value", help="Gradient maximum value.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set conditional formatting on a visual property."""
    from pbi.formatting import GradientStop, build_gradient_format, build_measure_format, set_conditional_format

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    dot = prop.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Property must be object.prop format (e.g. dataPoint.fill).")
        raise typer.Exit(1)
    obj_name, prop_name = prop[:dot], prop[dot + 1 :]

    if mode not in {"measure", "gradient"}:
        console.print("[red]Error:[/red] --mode must be 'measure' or 'gradient'.")
        raise typer.Exit(1)

    if mode == "measure":
        src_dot = source.find(".")
        if src_dot == -1:
            console.print("[red]Error:[/red] --source must be Table.Measure format for --mode measure.")
            raise typer.Exit(1)
        src_entity, src_prop = source[:src_dot], source[src_dot + 1 :]
        value = build_measure_format(src_entity, src_prop)
        set_conditional_format(vis.data, obj_name, prop_name, value)
        vis.save()
        console.print(f"Set [cyan]{prop}[/cyan] = measure [bold]{src_entity}.{src_prop}[/bold]")
        return

    if min_color is None or min_value is None or max_color is None or max_value is None:
        console.print("[red]Error:[/red] Gradient mode requires --min-color, --min-value, --max-color, and --max-value.")
        raise typer.Exit(1)

    src_dot = source.find(".")
    if src_dot == -1:
        console.print("[red]Error:[/red] --source must be Table.Field format for --mode gradient.")
        raise typer.Exit(1)
    src_entity, src_prop = source[:src_dot], source[src_dot + 1 :]

    min_c = min_color if min_color.startswith("#") else f"#{min_color}"
    max_c = max_color if max_color.startswith("#") else f"#{max_color}"
    mid_stop = None
    if mid_color is not None and mid_value is not None:
        mid_c = mid_color if mid_color.startswith("#") else f"#{mid_color}"
        mid_stop = GradientStop(mid_c, mid_value)
    elif mid_color is not None or mid_value is not None:
        console.print("[red]Error:[/red] Both --mid-color and --mid-value are required for a 3-stop gradient.")
        raise typer.Exit(1)

    value = build_gradient_format(
        src_entity,
        src_prop,
        min_stop=GradientStop(min_c, min_value),
        max_stop=GradientStop(max_c, max_value),
        mid_stop=mid_stop,
    )
    set_conditional_format(vis.data, obj_name, prop_name, value)
    vis.save()

    stops = f"{min_c}@{min_value}"
    if mid_stop:
        stops += f" -> {mid_stop.color}@{mid_stop.value}"
    stops += f" -> {max_c}@{max_value}"
    console.print(f"Set [cyan]{prop}[/cyan] = gradient by [bold]{src_entity}.{src_prop}[/bold] [{stops}]")


@visual_format_app.command("clear")
def visual_format_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    prop: Annotated[str, typer.Argument(help="Property as object.prop (e.g. dataPoint.fill).")],
    project: ProjectOpt = None,
) -> None:
    """Clear conditional formatting from a visual property."""
    from pbi.formatting import clear_conditional_format

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    dot = prop.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Property must be object.prop format (e.g. dataPoint.fill).")
        raise typer.Exit(1)
    obj_name, prop_name = prop[:dot], prop[dot + 1 :]

    if clear_conditional_format(vis.data, obj_name, prop_name):
        vis.save()
        console.print(f"Cleared conditional formatting from [cyan]{prop}[/cyan].")
    else:
        console.print(f"[dim]No conditional formatting on {prop}.[/dim]")


@visual_app.command("column")
def visual_column(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    column: Annotated[str | None, typer.Argument(help="Field: Table.Field, display name, or index. Omit to list all projection-backed fields.")] = None,
    width: Annotated[float | None, typer.Option("--width", "-w", help="Column width in pixels.")] = None,
    rename: Annotated[str | None, typer.Option("--rename", help="Rename column header.")] = None,
    align: Annotated[str | None, typer.Option("--align", help="Column alignment: Left, Center, Right.")] = None,
    font_color: Annotated[str | None, typer.Option("--font-color", help="Column font color (#hex).")] = None,
    back_color: Annotated[str | None, typer.Option("--back-color", help="Column background color (#hex).")] = None,
    display_units: Annotated[int | None, typer.Option("--display-units", help="Label display units (0=auto, 1=none, 1000=K, 1000000=M, etc.).")] = None,
    precision: Annotated[int | None, typer.Option("--precision", help="Decimal places.")] = None,
    clear_width: Annotated[bool, typer.Option("--clear-width", help="Remove column width override.")] = False,
    clear_format: Annotated[bool, typer.Option("--clear-format", help="Remove per-column formatting.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List, resize, rename, or format projection-backed visual fields."""
    from pbi.columns import (
        clear_column_format,
        clear_column_width,
        find_column,
        get_columns,
        rename_column,
        set_column_format,
        set_column_width,
    )

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if column is None:
        columns = get_columns(vis)
        if not columns:
            console.print("[dim]No projection-backed fields on this visual.[/dim]")
            return
        table = Table(title=f"Columns on {vis.visual_type}", box=box.SIMPLE)
        table.add_column("#", style="dim", width=3)
        table.add_column("Field", style="cyan")
        table.add_column("Display Name")
        table.add_column("Type", style="dim")
        table.add_column("Width", justify="right")
        table.add_column("Formatting", style="dim")
        for index, col in enumerate(columns, 1):
            display = col.display_name or col.prop
            width_str = str(int(col.width)) if col.width else "-"
            fmt_parts = []
            if "alignment" in col.formatting:
                fmt_parts.append(f"align:{col.formatting['alignment']}")
            if "fontColor" in col.formatting:
                fmt_parts.append(f"color:{col.formatting['fontColor']}")
            fmt_str = ", ".join(fmt_parts) if fmt_parts else "-"
            table.add_row(str(index), f"{col.entity}.{col.prop}", display, col.field_type, width_str, fmt_str)
        console.print(table)
        return

    try:
        col = find_column(vis, column)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    changed = False
    if clear_width:
        if clear_column_width(vis, col.query_ref):
            console.print(f"Cleared width override on [cyan]{col.entity}.{col.prop}[/cyan].")
            changed = True
        else:
            console.print("[dim]No width override to clear.[/dim]")

    if clear_format:
        if clear_column_format(vis, col.query_ref):
            console.print(f"Cleared formatting on [cyan]{col.entity}.{col.prop}[/cyan].")
            changed = True
        else:
            console.print("[dim]No column formatting to clear.[/dim]")

    if width is not None:
        set_column_width(vis, col.query_ref, width)
        console.print(f"[dim]{col.entity}.{col.prop} width:[/dim] {int(width)}")
        changed = True

    if rename is not None:
        old_name = col.display_name or col.prop
        rename_column(vis, col.query_ref, rename)
        console.print(f"[dim]{col.entity}.{col.prop}:[/dim] {old_name} [dim]->[/dim] {rename}")
        changed = True

    has_format = any(value is not None for value in [align, font_color, back_color, display_units, precision])
    if has_format:
        set_column_format(
            vis,
            col.query_ref,
            alignment=align,
            font_color=font_color,
            back_color=back_color,
            display_units=display_units,
            precision=precision,
        )
        parts = []
        if align:
            parts.append(f"align={align}")
        if font_color:
            parts.append(f"fontColor={font_color}")
        if back_color:
            parts.append(f"backColor={back_color}")
        if display_units is not None:
            parts.append(f"displayUnits={display_units}")
        if precision is not None:
            parts.append(f"precision={precision}")
        console.print(f"[dim]{col.entity}.{col.prop} format:[/dim] {', '.join(parts)}")
        changed = True

    if changed:
        vis.save()
    elif not clear_width and not clear_format:
        display = col.display_name or col.prop
        console.print(f"[bold]{col.entity}.{col.prop}[/bold]")
        console.print(f"  Role: {col.role}")
        console.print(f"  Type: {col.field_type}")
        console.print(f"  Display name: {display}")
        console.print(f"  Query ref: {col.query_ref}")
        if col.width:
            console.print(f"  Width: {int(col.width)}")
        if col.formatting:
            for key, value in col.formatting.items():
                console.print(f"  {key}: {value}")


@visual_app.command("properties")
def visual_props(
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Show only properties for this visual type.")] = None,
    group: Annotated[str | None, typer.Option("--group", "-g", help="Filter by group: position, core, container, chart.")] = None,
    match: Annotated[str | None, typer.Option("--match", help="Filter properties by name, alias, or description text.")] = None,
    show_aliases: Annotated[bool, typer.Option("--show-aliases", help="Show accepted raw/alias input forms for each property.")] = False,
) -> None:
    """List available visual properties."""
    props = list_properties(VISUAL_PROPERTIES, group=group, visual_type=visual_type)
    if match:
        needle = match.lower()
        filtered = []
        for name, vtype, desc, prop_group, enum_values in props:
            aliases = property_aliases_for(name, VISUAL_PROPERTIES)
            if needle in name.lower() or needle in desc.lower() or any(needle in alias.lower() for alias in aliases):
                filtered.append((name, vtype, desc, prop_group, enum_values))
        props = filtered

    if not props:
        filters = []
        if visual_type:
            filters.append(f'type="{visual_type}"')
        if group:
            filters.append(f'group="{group}"')
        if match:
            filters.append(f'match="{match}"')
        console.print(f'[yellow]No properties match filters: {", ".join(filters)}[/yellow]')
        return

    title = "Visual Properties"
    if visual_type:
        title += f" ({visual_type})"
    if group:
        title += f" [{group}]"

    table = Table(title=title, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Group", style="dim")
    table.add_column("Description")
    table.add_column("Values", style="dim")
    if show_aliases:
        table.add_column("Accepted Input", style="dim", overflow="fold")

    current_group = None
    for name, vtype, desc, prop_group, enum_values in props:
        if prop_group != current_group:
            if current_group is not None:
                table.add_section()
            current_group = prop_group
        vals = ", ".join(enum_values) if enum_values else ""
        row = [name, vtype, prop_group or "", desc, vals]
        if show_aliases:
            aliases = property_aliases_for(name, VISUAL_PROPERTIES)
            row.append(", ".join(aliases))
        table.add_row(*row)

    console.print(table)
    console.print(
        "\n[dim]Use 'chart:<object>.<prop>' for unregistered chart properties. "
        "Use --visual-type <visualType> to filter by chart type.[/dim]"
    )


@visual_app.command("objects")
def visual_objects(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show all chart formatting objects currently set on a visual."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    chart_objects = get_visual_objects(vis.data)
    if not chart_objects:
        console.print(f"[dim]No chart objects on {vis.visual_type} \"{vis.name}\".[/dim]")
        return

    table = Table(title=f"Chart Objects on {vis.visual_type}", box=box.SIMPLE)
    table.add_column("Object", style="cyan")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    for obj_key in sorted(chart_objects):
        props = chart_objects[obj_key]
        first = True
        for prop_name, value in sorted(props.items()):
            obj_label = obj_key if first else ""
            table.add_row(obj_label, prop_name, str(value))
            first = False
        table.add_section()

    console.print(table)
    console.print(f"\n[dim]Set with: pbi visual set {page} {visual} chart:<object>.<prop>=<value>[/dim]")


@visual_app.command("list")
def visual_list(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """List all visuals on a page."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)

    table = Table(title=f'Visuals on "{pg.display_name}"', box=box.SIMPLE)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan", max_width=24)
    table.add_column("Type")
    table.add_column("Position", style="dim")
    table.add_column("Size", style="dim")
    table.add_column("Z", style="dim", justify="right")

    for index, vis in enumerate(visuals, 1):
        pos = vis.position
        hidden = " [yellow](hidden)[/yellow]" if vis.data.get("isHidden") else ""
        table.add_row(
            str(index),
            f"{vis.name[:24]}{hidden}",
            vis.visual_type,
            f'{pos.get("x", 0)}, {pos.get("y", 0)}',
            f'{pos.get("width", 0)}x{pos.get("height", 0)}',
            str(pos.get("z", 0)),
        )

    console.print(table)


@visual_app.command("get")
def visual_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    props: Annotated[list[str] | None, typer.Argument(help="Property or properties to read (omit for overview).")] = None,
    all_props: Annotated[bool, typer.Option("--all-props", help="Show all explicit registered and object properties.")] = False,
    defaults: Annotated[bool, typer.Option("--defaults", help="Show effective values using explicit values plus known defaults.")] = False,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Show raw JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show visual details or one or more specific properties."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw and props:
        console.print("[red]Error:[/red] --raw cannot be combined with explicit properties.")
        raise typer.Exit(1)
    if raw and all_props:
        console.print("[red]Error:[/red] --raw cannot be combined with --all-props.")
        raise typer.Exit(1)
    if raw and defaults:
        console.print("[red]Error:[/red] --raw cannot be combined with --defaults.")
        raise typer.Exit(1)
    if props and all_props:
        console.print("[red]Error:[/red] Explicit properties cannot be combined with --all-props.")
        raise typer.Exit(1)

    if raw:
        import json

        console.print_json(json.dumps(vis.data, indent=2))
        return

    if all_props or defaults:
        rows = collect_effective_visual_property_rows(
            vis.data,
            include_core=all_props,
            include_defaults=defaults,
        )
        table = Table(title=f"{vis.name}", box=box.SIMPLE)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        if defaults:
            table.add_column("Source", style="dim")
        for prop_name, value, source in rows:
            if defaults:
                table.add_row(prop_name, value, source)
            else:
                table.add_row(prop_name, value)
        console.print(table)
        return

    if props:
        if len(props) == 1 and not defaults:
            value = get_property(vis.data, props[0], VISUAL_PROPERTIES)
            console.print(value)
            return

        table = Table(title=f"{vis.name}", box=box.SIMPLE)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        if defaults:
            table.add_column("Source", style="dim")
        for prop in props:
            value, source = resolve_visual_property_value(vis.data, prop, include_defaults=defaults)
            if defaults:
                table.add_row(prop, "" if value is None else str(value), source)
            else:
                table.add_row(prop, "" if value is None else str(value))
        console.print(table)
        return

    pos = vis.position
    table = Table(title=f"{vis.visual_type}", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Name", vis.name)
    table.add_row("Folder", vis.folder.name)
    table.add_row("Type", vis.visual_type)
    table.add_row("Position", f'{pos.get("x", 0)}, {pos.get("y", 0)}')
    table.add_row("Size", f'{pos.get("width", 0)} x {pos.get("height", 0)}')
    table.add_row("Z-Order", str(pos.get("z", 0)))
    table.add_row("Hidden", str(vis.data.get("isHidden", False)))

    object_rows = collect_visual_property_rows(vis.data, include_core=False)
    if object_rows:
        table.add_section()
        for prop_name, value in object_rows:
            table.add_row(prop_name, value)

    query = vis.data.get("visual", {}).get("query", {}).get("queryState", {})
    if query:
        table.add_section()
        for role, config in query.items():
            projections = config.get("projections", [])
            fields = []
            for projection in projections:
                ref = projection.get("queryRef", projection.get("nativeQueryRef", "?"))
                fields.append(ref)
            table.add_row(f"[dim]Data:[/dim] {role}", ", ".join(fields))

    sorts = proj.get_sort(vis)
    if sorts:
        table.add_section()
        for entity, sort_prop, ftype, direction in sorts:
            kind = " (measure)" if ftype == "measure" else ""
            table.add_row("[dim]Sort:[/dim]", f"{entity}.{sort_prop}{kind} {direction}")

    console.print(table)


@visual_app.command("get-page")
def visual_get_page(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Only include visuals of this type.")] = None,
    all_props: Annotated[bool, typer.Option("--all-props", help="Include core properties like position and hidden state.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show explicit properties for every visual on a page."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    if visual_type:
        visuals = [vis for vis in visuals if vis.visual_type == visual_type]

    table = Table(title=f'Visual Properties on "{pg.display_name}"', box=box.SIMPLE)
    table.add_column("Visual", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    row_count = 0
    for vis in visuals:
        for prop_name, value in collect_visual_property_rows(vis.data, include_core=all_props):
            table.add_row(vis.name, vis.visual_type, prop_name, value)
            row_count += 1

    if row_count == 0:
        console.print("[dim]No explicit visual properties matched the current filters.[/dim]")
        return

    console.print(table)


@visual_app.command("diff")
def visual_diff(
    left_page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    left_visual: Annotated[str, typer.Argument(help="Source visual name, type, or index.")],
    right_page: Annotated[str, typer.Argument(help="Comparison page name, display name, or index.")],
    right_visual: Annotated[str, typer.Argument(help="Comparison visual name, type, or index.")],
    all_props: Annotated[bool, typer.Option("--all-props", help="Include core properties like position and hidden state.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Compare canonical exported visual specs between two visuals."""
    from pbi.export import export_visual_spec

    proj = get_project(project)
    try:
        left_pg = proj.find_page(left_page)
        left_vis = proj.find_visual(left_pg, left_visual)
        right_pg = proj.find_page(right_page)
        right_vis = proj.find_visual(right_pg, right_visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    left_props = flatten_visual_diff_spec(export_visual_spec(proj, left_vis), include_core=all_props)
    right_props = flatten_visual_diff_spec(export_visual_spec(proj, right_vis), include_core=all_props)

    ordered_keys: list[str] = []
    for prop_name in [*left_props.keys(), *right_props.keys()]:
        if prop_name not in ordered_keys:
            ordered_keys.append(prop_name)

    rows = []
    for prop_name in ordered_keys:
        left_value = left_props.get(prop_name, "")
        right_value = right_props.get(prop_name, "")
        if left_value == right_value:
            continue
        rows.append((prop_name, left_value, right_value))

    if not rows:
        console.print("[dim]No property differences found.[/dim]")
        return

    table = Table(title=f"{left_vis.name} vs {right_vis.name}", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column(f"{left_pg.display_name}/{left_vis.name}")
    table.add_column(f"{right_pg.display_name}/{right_vis.name}")
    for prop_name, left_value, right_value in rows:
        table.add_row(prop_name, left_value, right_value)
    console.print(table)


@visual_app.command("set")
def visual_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    project: ProjectOpt = None,
    for_measure: Annotated[str | None, typer.Option("--for-measure", help="Target a specific measure queryRef for per-measure formatting.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show what would change without saving.")] = False,
) -> None:
    """Set visual properties."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        pairs = parse_property_assignments(assignments)
        updated, changes = prepare_visual_property_updates(vis.data, pairs, measure_ref=for_measure)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for prop, old, new in changes:
        label = f"{prop} ({for_measure})" if for_measure else prop
        if dry_run:
            console.print(f"Would set {label}: {old} [dim]->[/dim] {new}")
        else:
            console.print(f"[dim]{label}:[/dim] {old} [dim]->[/dim] {new}")

    if dry_run:
        return

    vis.data = updated
    vis.save()


@visual_app.command("set-all")
def visual_set_all(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value ...")],
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Only apply to visuals of this type (e.g. slicer, cardVisual, tableEx).")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show what would change without saving.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set properties on multiple visuals at once."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    if visual_type:
        visuals = [vis for vis in visuals if vis.visual_type == visual_type]
        if not visuals:
            console.print(f'[yellow]No visuals of type "{visual_type}" on page "{pg.display_name}".[/yellow]')
            raise typer.Exit(0)

    visuals = [vis for vis in visuals if "visualGroup" not in vis.data]

    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    prepared: list[tuple[object, dict, list[tuple[str, object, object]]]] = []
    for vis in visuals:
        try:
            updated, changes = prepare_visual_property_updates(vis.data, pairs)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {vis.name}: {e}")
            raise typer.Exit(1)
        prepared.append((vis, updated, changes))

    if dry_run:
        totals: dict[str, int] = {}
        for _vis, _updated, changes in prepared:
            for prop, old, new in changes:
                if old != new:
                    totals[prop] = totals.get(prop, 0) + 1
        if not totals:
            console.print("[dim]No changes would be applied.[/dim]")
            return
        for prop, count in totals.items():
            console.print(f"Would set {prop} on [cyan]{count}[/cyan] visual(s)")
        return

    count_done = 0
    for vis, updated, _changes in prepared:
        vis.data = updated
        vis.save()
        count_done += 1

    scope = f"visual-type={visual_type}" if visual_type else "all"
    props_str = " ".join(f"{prop}={value}" for prop, value in pairs)
    console.print(f'Applied {props_str} to [cyan]{count_done}[/cyan] visuals ({scope})')


@visual_app.command("move")
def visual_move(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    x: Annotated[int, typer.Option("--x", help="X position.")],
    y: Annotated[int, typer.Option("--y", help="Y position.")],
    project: ProjectOpt = None,
) -> None:
    """Move a visual to a new position."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old_x = vis.position.get("x", 0)
    old_y = vis.position.get("y", 0)
    vis.data.setdefault("position", {})["x"] = x
    vis.data["position"]["y"] = y
    vis.save()
    console.print(f"[dim]Moved:[/dim] {old_x},{old_y} [dim]->[/dim] {x},{y}")


@visual_app.command("resize")
def visual_resize(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    width: Annotated[int, typer.Option("-W", "--width", help="Width.")],
    height: Annotated[int, typer.Option("-H", "--height", help="Height.")],
    project: ProjectOpt = None,
) -> None:
    """Resize a visual."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old_w = vis.position.get("width", 0)
    old_h = vis.position.get("height", 0)
    vis.data.setdefault("position", {})["width"] = width
    vis.data["position"]["height"] = height
    vis.save()
    console.print(f"[dim]Resized:[/dim] {old_w}x{old_h} [dim]->[/dim] {width}x{height}")


@visual_app.command("create")
def visual_create(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual_type: Annotated[str, typer.Argument(help="Visual type (e.g. clusteredColumnChart, card, table, slicer).")],
    x: Annotated[int, typer.Option(help="X position.")] = 0,
    y: Annotated[int, typer.Option(help="Y position.")] = 0,
    width: Annotated[int, typer.Option("-W", "--width", help="Width.")] = 300,
    height: Annotated[int, typer.Option("-H", "--height", help="Height.")] = 200,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Friendly name for the visual.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Create a new visual on a page."""
    from pbi.roles import is_known_visual_type, normalize_visual_type

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    canonical_visual_type = normalize_visual_type(visual_type)
    if visual_type != canonical_visual_type:
        console.print(
            f'[dim]Using canonical visual type [cyan]{canonical_visual_type}[/cyan] '
            f'for alias "{visual_type}".[/dim]'
        )
    elif not is_known_visual_type(visual_type):
        console.print(
            f'[yellow]Warning:[/yellow] "{visual_type}" is not in the CLI visual catalog. '
            "Creating a raw visual container."
        )

    vis = proj.create_visual(pg, canonical_visual_type, x=x, y=y, width=width, height=height)
    if name:
        vis.data["name"] = name
        vis.save()
    display = name or vis.name
    console.print(
        f'Created [cyan]{canonical_visual_type}[/cyan] "{display}" on "{pg.display_name}" '
        f"@ {x},{y} {width}x{height}"
    )


@visual_arrange_app.command("row")
def visual_arrange_row(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to arrange left-to-right.")],
    x: Annotated[int, typer.Option("--x", help="Starting X position.")] = 0,
    y: Annotated[int, typer.Option("--y", help="Shared Y position.")] = 0,
    gap: Annotated[int, typer.Option("--gap", help="Horizontal gap between visuals.")] = 16,
    project: ProjectOpt = None,
) -> None:
    """Arrange visuals in a horizontal row using their current widths."""
    if len(visuals) < 2:
        console.print("[red]Error:[/red] Provide at least two visuals to arrange.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        ordered_visuals = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    cursor_x = x
    for vis in ordered_visuals:
        width = int(vis.position.get("width", 0))
        vis.data.setdefault("position", {})["x"] = cursor_x
        vis.data["position"]["y"] = y
        vis.save()
        cursor_x += width + gap

    console.print(
        f'Arranged [cyan]{len(ordered_visuals)}[/cyan] visuals in a row on "{pg.display_name}" '
        f"starting at {x},{y} with gap {gap}"
    )


@visual_arrange_app.command("grid")
def visual_arrange_grid(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to arrange in reading order.")],
    columns: Annotated[int, typer.Option("--columns", help="Number of visuals per row.")] = 2,
    x: Annotated[int, typer.Option("--x", help="Starting X position.")] = 0,
    y: Annotated[int, typer.Option("--y", help="Starting Y position.")] = 0,
    column_gap: Annotated[int, typer.Option("--column-gap", help="Horizontal gap between visuals.")] = 16,
    row_gap: Annotated[int, typer.Option("--row-gap", help="Vertical gap between rows.")] = 16,
    project: ProjectOpt = None,
) -> None:
    """Arrange visuals in a wrapped grid using their current sizes."""
    if len(visuals) < 2:
        console.print("[red]Error:[/red] Provide at least two visuals to arrange.")
        raise typer.Exit(1)
    if columns < 1:
        console.print("[red]Error:[/red] --columns must be at least 1.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        ordered_visuals = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    cursor_x = x
    cursor_y = y
    row_height = 0

    for index, vis in enumerate(ordered_visuals):
        width = int(vis.position.get("width", 0))
        height = int(vis.position.get("height", 0))
        vis.data.setdefault("position", {})["x"] = cursor_x
        vis.data["position"]["y"] = cursor_y
        vis.save()

        row_height = max(row_height, height)
        is_last_in_row = (index + 1) % columns == 0
        if is_last_in_row:
            cursor_x = x
            cursor_y += row_height + row_gap
            row_height = 0
        else:
            cursor_x += width + column_gap

    console.print(
        f'Arranged [cyan]{len(ordered_visuals)}[/cyan] visuals in a [cyan]{columns}[/cyan]-column grid '
        f'on "{pg.display_name}" starting at {x},{y}'
    )


@visual_arrange_app.command("column")
def visual_arrange_column(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to arrange top-to-bottom.")],
    x: Annotated[int, typer.Option("--x", help="Shared X position.")] = 0,
    y: Annotated[int, typer.Option("--y", help="Starting Y position.")] = 0,
    gap: Annotated[int, typer.Option("--gap", help="Vertical gap between visuals.")] = 16,
    project: ProjectOpt = None,
) -> None:
    """Arrange visuals in a vertical column using their current heights."""
    if len(visuals) < 2:
        console.print("[red]Error:[/red] Provide at least two visuals to arrange.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        ordered_visuals = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    cursor_y = y
    for vis in ordered_visuals:
        height = int(vis.position.get("height", 0))
        vis.data.setdefault("position", {})["x"] = x
        vis.data["position"]["y"] = cursor_y
        vis.save()
        cursor_y += height + gap

    console.print(
        f'Arranged [cyan]{len(ordered_visuals)}[/cyan] visuals in a column on "{pg.display_name}" '
        f"starting at {x},{y} with gap {gap}"
    )


@visual_app.command("copy")
def visual_copy(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Source visual name, type, or index.")],
    to_page: Annotated[str | None, typer.Option("--to-page", help="Target page (default: same page).")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Name for the copy.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Copy/duplicate a visual, optionally to a different page."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
        target = proj.find_page(to_page) if to_page else pg
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    new_vis = proj.copy_visual(vis, target, new_name=name)
    dest = f' to "{target.display_name}"' if to_page else ""
    console.print(f'Copied [cyan]{vis.visual_type}[/cyan] "{vis.name}"{dest} -> "{new_vis.name}"')


@visual_app.command("paste-style")
def visual_paste_style(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    source: Annotated[str, typer.Argument(help="Source visual (copy style FROM).")],
    target: Annotated[str | None, typer.Argument(help="Target visual (paste style TO). Omit with --visual-type to style multiple visuals.")] = None,
    to_page: Annotated[str | None, typer.Option("--to-page", help="Target page if different from source.")] = None,
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Apply to all target-page visuals of this type.")] = None,
    scope: Annotated[str, typer.Option("--scope", help="Copy scope: all, container, or chart.")] = "all",
    project: ProjectOpt = None,
) -> None:
    """Copy formatting from one visual to another (format painter)."""
    import copy

    if scope not in {"all", "container", "chart"}:
        console.print("[red]Error:[/red] --scope must be 'all', 'container', or 'chart'.")
        raise typer.Exit(1)
    if target and visual_type:
        console.print("[red]Error:[/red] Use either an explicit target or --visual-type, not both.")
        raise typer.Exit(1)
    if not target and not visual_type:
        console.print("[red]Error:[/red] Provide a target visual or use --visual-type for batch style copy.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        src_page = proj.find_page(page)
        src_vis = proj.find_visual(src_page, source)
        tgt_page = proj.find_page(to_page) if to_page else src_page
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        if target:
            target_visuals = [proj.find_visual(tgt_page, target)]
        else:
            target_visuals = [
                vis for vis in proj.get_visuals(tgt_page) if vis.visual_type == visual_type and "visualGroup" not in vis.data
            ]
            if tgt_page.folder == src_page.folder:
                target_visuals = [vis for vis in target_visuals if vis.folder != src_vis.folder]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not target_visuals:
        if visual_type:
            console.print(f'[yellow]No target visuals of type "{visual_type}" on page "{tgt_page.display_name}".[/yellow]')
            raise typer.Exit(0)
        console.print(f'[yellow]Target visual "{target}" not found.[/yellow]')
        raise typer.Exit(0)

    copied = []
    src_visual = src_vis.data.get("visual", {})
    container = None
    objects = None

    if scope in {"all", "container"}:
        container = src_visual.get("visualContainerObjects")
        if container:
            copied.append("container")

    if scope in {"all", "chart"}:
        objects = src_visual.get("objects")
        if objects:
            copied.append("chart")

    if not copied:
        console.print("[yellow]Source visual has no formatting to copy.[/yellow]")
        raise typer.Exit(0)

    for tgt_vis in target_visuals:
        if scope in {"all", "container"}:
            if container:
                tgt_vis.data.setdefault("visual", {})["visualContainerObjects"] = copy.deepcopy(container)
            else:
                tgt_vis.data.get("visual", {}).pop("visualContainerObjects", None)
        if scope in {"all", "chart"}:
            if objects:
                tgt_vis.data.setdefault("visual", {})["objects"] = copy.deepcopy(objects)
            else:
                tgt_vis.data.get("visual", {}).pop("objects", None)
        tgt_vis.save()

    copied_scope = " + ".join(copied)
    if target:
        tgt_label = f'"{target_visuals[0].name}"'
        if to_page:
            tgt_label += f' on "{tgt_page.display_name}"'
        console.print(f'Copied [cyan]{copied_scope}[/cyan] formatting: "{src_vis.name}" -> {tgt_label}')
        return

    console.print(
        f'Copied [cyan]{copied_scope}[/cyan] formatting from "{src_vis.name}" to '
        f'[cyan]{len(target_visuals)}[/cyan] "{visual_type}" visual(s) on "{tgt_page.display_name}"'
    )


@visual_app.command("rename")
def visual_rename(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    name: Annotated[str, typer.Argument(help="New friendly name for the visual.")],
    project: ProjectOpt = None,
) -> None:
    """Give a visual a friendly name for easier CLI reference."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old_name = vis.name
    vis.data["name"] = name
    vis.save()
    console.print(f'Renamed "{old_name}" -> "[cyan]{name}[/cyan]"')


@visual_app.command("delete")
def visual_delete(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a visual."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f'Delete {vis.visual_type} "{vis.name}"?')
        if not confirm:
            raise typer.Abort()

    proj.delete_visual(vis)
    console.print(f'Deleted [cyan]{vis.visual_type}[/cyan] "{vis.name}"')


@visual_app.command("group")
def visual_group(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to group (at least 2).")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Group display name.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Group visuals together into a visual group."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis_list = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        group = proj.create_group(pg, vis_list, display_name=name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    names = ", ".join(f'"{vis.name}"' for vis in vis_list)
    console.print(f'Grouped {names} -> "[cyan]{group.name}[/cyan]"')


@visual_app.command("ungroup")
def visual_ungroup(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    group: Annotated[str, typer.Argument(help="Group name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Ungroup a visual group, freeing its children."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        grp = proj.find_visual(pg, group)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        children = proj.ungroup(pg, grp)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    names = ", ".join(f'"{child.name}"' for child in children)
    console.print(f'Ungrouped "[cyan]{grp.name}[/cyan]": freed {names or "no children"}')


@visual_app.command("bind")
def visual_bind(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    role: Annotated[str, typer.Argument(help="Data role (e.g. Category, Y, Values, Rows, Series).")],
    field: Annotated[str, typer.Argument(help="Field reference as Table.Field (e.g. Product.Category).")],
    field_type: Annotated[str, typer.Option("--field-type", help="Field type: auto, column, or measure.")] = "auto",
    project: ProjectOpt = None,
) -> None:
    """Bind a column or measure to a visual's data role."""
    from pbi.roles import get_visual_type_info, normalize_visual_role

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        entity, prop, resolved_field_type = resolve_field_type(proj, field, field_type)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    canonical_role = normalize_visual_role(vis.visual_type, role)
    if canonical_role != role:
        console.print(
            f'[dim]Using canonical role [cyan]{canonical_role}[/cyan] '
            f'for alias "{role}" on {vis.visual_type}.[/dim]'
        )

    info = get_visual_type_info(vis.visual_type)
    if info and info.status == "role-backed":
        supported_roles = {entry["name"] for entry in info.roles}
        if canonical_role not in supported_roles:
            console.print(
                f'[yellow]Warning:[/yellow] Role "{canonical_role}" is not modeled for '
                f'{vis.visual_type}. Supported roles: {", ".join(sorted(supported_roles))}'
            )

    proj.add_binding(vis, canonical_role, entity, prop, field_type=resolved_field_type)
    kind = "measure" if resolved_field_type == "measure" else "column"
    console.print(
        f'Bound [cyan]{entity}.{prop}[/cyan] ({kind}) -> '
        f'{vis.visual_type} role "[bold]{canonical_role}[/bold]"'
    )


@visual_app.command("unbind")
def visual_unbind(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    role: Annotated[str, typer.Argument(help="Data role to unbind from.")],
    field: Annotated[str | None, typer.Argument(help="Specific field to remove (Table.Field). Omit to remove entire role.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Remove data bindings from a visual."""
    from pbi.roles import normalize_visual_role

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    canonical_role = normalize_visual_role(vis.visual_type, role)
    removed = proj.remove_binding(vis, canonical_role, field_ref=field)
    if removed:
        target = f" ({field})" if field else ""
        console.print(f'Removed {removed} binding(s) from role "[bold]{canonical_role}[/bold]"{target}')
    else:
        console.print(f'[yellow]No bindings found for role "{canonical_role}"[/yellow]')


@visual_app.command("bindings")
def visual_bindings(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    project: ProjectOpt = None,
) -> None:
    """List all data bindings on a visual."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    bindings = proj.get_bindings(vis)
    if not bindings:
        console.print("[dim]No data bindings.[/dim]")
        return

    table = Table(title=f"Bindings on {vis.visual_type}", box=box.SIMPLE)
    table.add_column("Role", style="bold")
    table.add_column("Table", style="cyan")
    table.add_column("Field")
    table.add_column("Type", style="dim")

    for role, entity, prop, ftype in bindings:
        table.add_row(role, entity, prop, ftype)

    console.print(table)
