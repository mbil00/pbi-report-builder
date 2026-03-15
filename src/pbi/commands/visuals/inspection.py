"""Visual inspection and discovery commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from pbi.properties import (
    VISUAL_PROPERTIES,
    get_property,
    get_visual_objects,
    list_properties,
    property_aliases_for,
)

from ..common import ProjectOpt, console
from .app import visual_app
from .helpers import (
    collect_effective_visual_property_rows,
    collect_visual_property_rows,
    flatten_visual_diff_spec,
    resolve_page_target,
    resolve_visual_property_value,
    resolve_visual_target,
)


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
    _proj, _pg, vis = resolve_visual_target(project, page, visual)

    chart_objects = get_visual_objects(vis.data)
    if not chart_objects:
        console.print(f'[dim]No chart objects on {vis.visual_type} "{vis.name}".[/dim]')
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
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List all visuals on a page."""
    proj, pg = resolve_page_target(project, page)
    visuals = proj.get_visuals(pg)

    if as_json:
        import json

        rows = []
        for index, vis in enumerate(visuals, 1):
            pos = vis.position
            rows.append({
                "index": index,
                "name": vis.name,
                "type": vis.visual_type,
                "x": pos.get("x", 0),
                "y": pos.get("y", 0),
                "width": pos.get("width", 0),
                "height": pos.get("height", 0),
                "z": pos.get("z", 0),
                "hidden": bool(vis.data.get("isHidden")),
            })
        console.print_json(json.dumps(rows, indent=2))
        return

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
    proj, _pg, vis = resolve_visual_target(project, page, visual)

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
    proj, pg = resolve_page_target(project, page)
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

    proj, left_pg, left_vis = resolve_visual_target(project, left_page, left_visual)
    try:
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
