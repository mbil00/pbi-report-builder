"""Visual inspection and discovery commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from rich.tree import Tree

from pbi.properties import (
    VISUAL_PROPERTIES,
    decode_pbi_value,
    get_property,
    get_visual_objects,
    list_properties,
    property_aliases_for,
)

from ..common import ProjectOpt, console, get_project
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
            console.print(f'[red]Error:[/red] Unknown visual type "{visual_type}".')
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

            # Show KPI shorthand documentation for cardVisual
            if info.visual_type == "cardVisual":
                console.print()
                console.print("[bold]KPI Shorthand (CLI extension):[/bold]")
                console.print("[dim]Instead of bindings, cardVisual supports a kpis: shorthand:[/dim]")
                console.print("""
  layout: { columns: N, cellPadding: N }
  accentBar: { show: true, position: Top|Left, width: N }
  kpis:
  - measure: Table.Measure
    label: Display Label
    fontSize: N
    fontColor: "#hex"
    bold: true
    accentColor: "#hex"
    tileBackground: "#hex"
    referenceLabels:
    - measure: Table.OtherMeasure
      title: Label""", highlight=False)
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
        vals = ", ".join(str(v) for v in enum_values) if enum_values else ""
        row = [name, vtype, prop_group or "", desc, vals]
        if show_aliases:
            aliases = property_aliases_for(name, VISUAL_PROPERTIES)
            row.append(", ".join(aliases))
        table.add_row(*row)

    console.print(table)
    schema_count = sum(1 for _, _, desc, *_ in props if "(schema)" in desc)
    if schema_count and visual_type:
        console.print(
            f"\n[dim]{schema_count} properties from PBI schema for {visual_type}. "
            f"Schema properties can be set directly (e.g. 'legend.show') or via 'chart:' prefix.[/dim]"
        )
    else:
        console.print(
            "\n[dim]Use --visual-type <type> to see all schema-derived chart properties for a specific visual type.[/dim]"
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


@visual_app.command("inspect")
def visual_inspect(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    search: Annotated[str | None, typer.Option("--search", "-s", help="Filter output to entries matching keyword.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Deep inspection of every object property on a visual.

    Shows all entries in visual.objects and visualContainerObjects with
    full selector context.  Use --search to find specific properties.
    Useful for reverse-engineering visuals built in Power BI Desktop.
    """
    _proj, _pg, vis = resolve_visual_target(project, page, visual)

    sections = _collect_inspect_sections(vis.data)

    if search:
        kw = search.lower()
        sections = {
            obj: [e for e in entries if _entry_matches(e, kw)]
            for obj, entries in sections.items()
        }
        sections = {k: v for k, v in sections.items() if v}

    if not sections:
        if search:
            console.print(f'[yellow]No properties matching "{search}".[/yellow]')
        else:
            console.print(f'[dim]No object properties on {vis.visual_type} "{vis.name}".[/dim]')
        return

    if as_json:
        import json as json_mod
        console.print_json(json_mod.dumps(sections, indent=2, default=str))
        return

    console.print(f"[bold]{vis.name}[/bold] ({vis.visual_type})\n")

    for obj_name in sorted(sections):
        entries = sections[obj_name]
        console.print(f"[bold cyan]{obj_name}[/bold cyan]")
        for entry in entries:
            sel_str = entry.get("_selector_display", "")
            if sel_str:
                # Escape Rich markup brackets in selector display
                escaped = sel_str.replace("[", "\\[")
                console.print(f"  [dim]{escaped}[/dim]")
            for prop_name, prop_value in sorted(entry.get("properties", {}).items()):
                val_str = str(prop_value).replace("[", "\\[")
                console.print(f"    {prop_name} = [green]{val_str}[/green]")
        console.print()

    total_objects = sum(len(v) for v in sections.values())
    total_props = sum(
        len(e.get("properties", {}))
        for entries in sections.values()
        for e in entries
    )
    console.print(f"[dim]{total_objects} entries across {len(sections)} objects, {total_props} properties total[/dim]")
    console.print(f"[dim]Set with: pbi visual set {page} {visual} chart:<object>.<prop>=<value>[/dim]")


def _collect_inspect_sections(data: dict) -> dict[str, list[dict]]:
    """Collect all object entries from both objects and visualContainerObjects."""
    sections: dict[str, list[dict]] = {}
    vis = data.get("visual", {})

    for source_key, prefix in [("objects", ""), ("visualContainerObjects", "container:")]:
        objects = vis.get(source_key, {})
        for obj_name, entries in objects.items():
            if not isinstance(entries, list):
                continue
            display_name = f"{prefix}{obj_name}" if prefix else obj_name
            parsed: list[dict] = []
            for entry in entries:
                selector = entry.get("selector")
                raw_props = entry.get("properties", {})
                decoded_props = {}
                for prop_name, raw_val in raw_props.items():
                    decoded = decode_pbi_value(raw_val)
                    # For complex values that didn't decode to a scalar, summarize
                    if isinstance(decoded, dict):
                        decoded = _summarize_complex_value(decoded)
                    decoded_props[prop_name] = decoded
                parsed.append({
                    "_selector_display": _format_selector(selector),
                    "selector": selector,
                    "properties": decoded_props,
                })
            if parsed:
                sections[display_name] = parsed

    return sections


def _format_selector(selector: dict | None) -> str:
    """Format a selector into a readable string."""
    if selector is None:
        return ""
    parts = []
    if "id" in selector:
        parts.append(f"id={selector['id']}")
    if "metadata" in selector:
        parts.append(f"metadata={selector['metadata']}")
    if "order" in selector:
        parts.append(f"order={selector['order']}")
    data = selector.get("data", [])
    for d in data:
        if "dataViewWildcard" in d:
            mo = d["dataViewWildcard"].get("matchingOption", 0)
            parts.append(f"wildcard={mo}")
    if not parts:
        return "[no selector]"
    return f"[{', '.join(parts)}]"


def _summarize_complex_value(val: dict) -> str:
    """Summarize a complex decoded value that couldn't be flattened to a scalar."""
    # Measure expression
    if "Measure" in val:
        m = val["Measure"]
        entity = m.get("Expression", {}).get("SourceRef", {}).get("Entity", "?")
        prop = m.get("Property", "?")
        return f"Measure({entity}.{prop})"
    # SelectRef
    if "SelectRef" in val:
        return f"SelectRef({val['SelectRef'].get('ExpressionName', '?')})"
    # FillRule
    if "FillRule" in val:
        return "<FillRule gradient>"
    # Conditional
    if "Conditional" in val:
        n = len(val["Conditional"].get("Cases", []))
        return f"<Conditional {n} rules>"
    # Fallback: abbreviated JSON
    import json
    s = json.dumps(val, separators=(",", ":"))
    if len(s) > 60:
        return s[:57] + "..."
    return s


def _entry_matches(entry: dict, keyword: str) -> bool:
    """Check if any property name or value contains the keyword."""
    for prop_name, prop_value in entry.get("properties", {}).items():
        if keyword in prop_name.lower() or keyword in str(prop_value).lower():
            return True
    sel = entry.get("_selector_display", "")
    if keyword in sel.lower():
        return True
    return False


@visual_app.command("list")
def visual_list(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List all visuals on a page."""
    proj, pg = resolve_page_target(project, page)
    visuals = proj.get_visuals(pg)

    if not visuals and not as_json:
        console.print(f'[yellow]No visuals on "{pg.display_name}". Use `pbi visual create` to add one.[/yellow]')
        raise typer.Exit(0)

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
    full: Annotated[bool, typer.Option("--full", help="Show everything: properties, chart objects, columns, bindings, filters, sort.")] = False,
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

    if full:
        from pbi.columns import get_columns
        from pbi.filters import get_filters, parse_filter

        # Header
        pos = vis.position
        console.print(f"[bold]{vis.name}[/bold] ({vis.visual_type})")
        console.print(f"  [dim]Position:[/dim] {pos.get('x', 0)}, {pos.get('y', 0)}  [dim]Size:[/dim] {pos.get('width', 0)} x {pos.get('height', 0)}  [dim]Z:[/dim] {pos.get('z', 0)}")
        if vis.data.get("isHidden"):
            console.print("  [yellow](hidden)[/yellow]")

        # Properties
        prop_rows = collect_visual_property_rows(vis.data, include_core=False)
        if prop_rows:
            console.print("\n[bold]Properties[/bold]")
            for prop_name, value in prop_rows:
                console.print(f"  [cyan]{prop_name}[/cyan]: {value}")

        # Chart objects
        chart_objects = get_visual_objects(vis.data)
        if chart_objects:
            console.print("\n[bold]Chart Objects[/bold]")
            for obj_key in sorted(chart_objects):
                obj_props = chart_objects[obj_key]
                for p_name, p_value in sorted(obj_props.items()):
                    console.print(f"  [cyan]{obj_key}.{p_name}[/cyan]: {p_value}")

        # Columns/bindings
        columns = get_columns(vis)
        if columns:
            console.print("\n[bold]Columns[/bold]")
            for col in columns:
                display = col.display_name or col.prop
                width_str = f" w={int(col.width)}" if col.width else ""
                console.print(f"  [cyan]{col.entity}.{col.prop}[/cyan] ({col.role}) → {display}{width_str}")

        # Sort
        sorts = proj.get_sort(vis)
        if sorts:
            console.print("\n[bold]Sort[/bold]")
            for entity, sort_prop, ftype, direction in sorts:
                kind = " (measure)" if ftype == "measure" else ""
                console.print(f"  {entity}.{sort_prop}{kind} {direction}")

        # Filters
        filters = get_filters(vis.data)
        if filters:
            console.print("\n[bold]Filters[/bold]")
            for f in filters:
                info = parse_filter(f)
                vals = f" = {', '.join(str(v) for v in info.values)}" if info.values else ""
                console.print(f"  [cyan]{info.field_entity}.{info.field_prop}[/cyan] ({info.filter_type}){vals}")

        return

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
    table.add_row("Hidden", "yes" if vis.data.get("isHidden") else "")

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

    # Filter summary
    from pbi.filters import get_filters, parse_filter

    filters = get_filters(vis.data)
    if filters:
        table.add_section()
        for f in filters:
            info = parse_filter(f)
            vals = f" = {', '.join(str(v) for v in info.values)}" if info.values else ""
            table.add_row("[dim]Filter:[/dim]", f"{info.field_entity}.{info.field_prop} ({info.filter_type}){vals}")

    console.print(table)


@visual_app.command("export")
def visual_export(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    output: Annotated[str | None, typer.Option("-o", "--output", help="Output file (default: stdout).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Export a single visual as YAML (apply-compatible format)."""
    import yaml
    from pbi.export import export_visual_spec

    proj, _pg, vis = resolve_visual_target(project, page, visual)
    spec = export_visual_spec(proj, vis)
    yaml_str = yaml.dump(
        spec,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    if output:
        from pathlib import Path
        Path(output).write_text(yaml_str, encoding="utf-8")
        console.print(f'Exported [cyan]{vis.name}[/cyan] to {output}')
    else:
        console.print(yaml_str, highlight=False)


@visual_app.command("audit")
def visual_audit(
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Only audit visuals of this type.")] = None,
    page: Annotated[str | None, typer.Option("--page", help="Audit a single page instead of all pages.")] = None,
    match: Annotated[str | None, typer.Option("--match", help="Only show properties whose name contains this string.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Audit visual styling consistency across pages.

    Groups visuals by type and reports which properties differ across instances.
    Use --visual-type to focus on a specific type (e.g. slicer, cardVisual).
    """
    import json as json_mod
    from collections import defaultdict

    proj = get_project(project)

    if page:
        try:
            target_pages = [proj.find_page(page)]
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        target_pages = proj.get_pages()

    # Collect: type -> prop -> { value -> [(page, visual)] }
    type_props: dict[str, dict[str, dict[str, list[tuple[str, str]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    type_counts: dict[str, int] = defaultdict(int)

    for pg in target_pages:
        visuals = proj.get_visuals(pg)
        for vis in visuals:
            if "visualGroup" in vis.data:
                continue
            vtype = vis.visual_type
            if visual_type and vtype != visual_type:
                continue
            type_counts[vtype] += 1
            for prop_name, value in collect_visual_property_rows(vis.data, include_core=False):
                if match and match.lower() not in prop_name.lower():
                    continue
                type_props[vtype][prop_name][str(value)].append(
                    (pg.display_name, vis.name)
                )

    if not type_props:
        console.print("[yellow]No visuals matched the filters.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        output = {}
        for vtype in sorted(type_props):
            props = type_props[vtype]
            type_entry: dict[str, dict] = {}
            for prop_name in sorted(props):
                values = props[prop_name]
                type_entry[prop_name] = {
                    "consistent": len(values) == 1,
                    "values": {
                        val: [f"{p}/{v}" for p, v in locs]
                        for val, locs in values.items()
                    },
                }
            output[vtype] = {"count": type_counts[vtype], "properties": type_entry}
        console.print_json(json_mod.dumps(output, indent=2))
        return

    for vtype in sorted(type_props):
        count = type_counts[vtype]
        props = type_props[vtype]

        # Split into consistent vs inconsistent
        inconsistent = {p: v for p, v in props.items() if len(v) > 1}
        consistent = {p: v for p, v in props.items() if len(v) == 1}

        page_label = f' on "{target_pages[0].display_name}"' if len(target_pages) == 1 else f" across {len(target_pages)} pages"
        console.print(f"\n[bold]{vtype}[/bold] [dim]({count} visuals{page_label})[/dim]")

        if inconsistent:
            for prop_name in sorted(inconsistent):
                values = inconsistent[prop_name]
                parts = []
                for val, locs in sorted(values.items(), key=lambda x: -len(x[1])):
                    parts.append(f"{val} ({len(locs)})")
                console.print(f"  [yellow]VARIES[/yellow]  [cyan]{prop_name}[/cyan]: {', '.join(parts)}")

        if consistent:
            for prop_name in sorted(consistent):
                val = next(iter(consistent[prop_name]))
                n = len(consistent[prop_name][val])
                console.print(f"  [green]OK[/green]      [cyan]{prop_name}[/cyan]: {val} [dim]({n})[/dim]")

        if not inconsistent:
            console.print(f"  [dim]All {len(consistent)} properties are consistent.[/dim]")

    # Summary
    total_types = len(type_props)
    total_inconsistent = sum(
        1 for props in type_props.values()
        for v in props.values() if len(v) > 1
    )
    if total_inconsistent:
        console.print(f"\n[yellow]{total_inconsistent} inconsistent properties across {total_types} visual types.[/yellow]")
    else:
        console.print(f"\n[dim]All properties consistent across {total_types} visual types.[/dim]")


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


@visual_app.command("page-diff")
def page_diff(
    left_page: Annotated[str, typer.Argument(help="First page name, display name, or index.")],
    right_page: Annotated[str, typer.Argument(help="Second page name, display name, or index.")],
    all_props: Annotated[bool, typer.Option("--all-props", help="Include core properties like position.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Compare two pages: visual counts, types, and property differences."""
    from pbi.export import export_visual_spec

    proj, left_pg = resolve_page_target(project, left_page)
    try:
        right_pg = proj.find_page(right_page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    left_visuals = proj.get_visuals(left_pg)
    right_visuals = proj.get_visuals(right_pg)

    # Summary
    console.print(f'[bold]{left_pg.display_name}[/bold]: {len(left_visuals)} visuals')
    console.print(f'[bold]{right_pg.display_name}[/bold]: {len(right_visuals)} visuals')

    left_by_name = {v.name: v for v in left_visuals}
    right_by_name = {v.name: v for v in right_visuals}
    all_names = list(dict.fromkeys(list(left_by_name.keys()) + list(right_by_name.keys())))

    only_left = [n for n in all_names if n in left_by_name and n not in right_by_name]
    only_right = [n for n in all_names if n not in left_by_name and n in right_by_name]
    common = [n for n in all_names if n in left_by_name and n in right_by_name]

    if only_left:
        console.print(f'\n[yellow]Only in "{left_pg.display_name}":[/yellow]')
        for n in only_left:
            console.print(f"  [cyan]{n}[/cyan] ({left_by_name[n].visual_type})")
    if only_right:
        console.print(f'\n[yellow]Only in "{right_pg.display_name}":[/yellow]')
        for n in only_right:
            console.print(f"  [cyan]{n}[/cyan] ({right_by_name[n].visual_type})")

    if common:
        diff_count = 0
        for name in common:
            left_spec = flatten_visual_diff_spec(export_visual_spec(proj, left_by_name[name]), include_core=all_props)
            right_spec = flatten_visual_diff_spec(export_visual_spec(proj, right_by_name[name]), include_core=all_props)
            diffs = []
            all_keys = list(dict.fromkeys(list(left_spec.keys()) + list(right_spec.keys())))
            for key in all_keys:
                lv = left_spec.get(key, "")
                rv = right_spec.get(key, "")
                if lv != rv:
                    diffs.append((key, lv, rv))
            if diffs:
                diff_count += 1
                table = Table(title=f"Differences: {name}", box=box.SIMPLE)
                table.add_column("Property", style="cyan")
                table.add_column(left_pg.display_name)
                table.add_column(right_pg.display_name)
                for prop_name, lv, rv in diffs:
                    table.add_row(prop_name, str(lv), str(rv))
                console.print(table)

        if diff_count == 0 and not only_left and not only_right:
            console.print("\n[dim]Pages are identical.[/dim]")
        elif diff_count == 0:
            console.print(f"\n[dim]{len(common)} shared visuals have no property differences.[/dim]")


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


@visual_app.command("tree")
def visual_tree(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show visual hierarchy as a tree with group nesting."""
    proj, pg = resolve_page_target(project, page)
    visuals = proj.get_visuals(pg)

    if not visuals:
        console.print(f'[yellow]No visuals on "{pg.display_name}".[/yellow]')
        raise typer.Exit(0)

    if as_json:
        import json as json_mod
        console.print_json(json_mod.dumps(_build_tree_data(visuals), indent=2))
        return

    from pbi.project import Visual as VisualType

    # Build parent → children mapping
    groups: dict[str, list[VisualType]] = {}
    group_visuals: dict[str, VisualType] = {}
    top_level = []

    for vis in visuals:
        if "visualGroup" in vis.data:
            group_visuals[vis.name] = vis
            groups.setdefault(vis.name, [])
        else:
            parent = vis.data.get("parentGroupName")
            if parent:
                groups.setdefault(parent, []).append(vis)
            else:
                top_level.append(vis)

    # Also add groups that are top-level (not children of another group)
    top_groups = []
    for _gname, gvis in group_visuals.items():
        parent = gvis.data.get("parentGroupName")
        if parent:
            groups.setdefault(parent, []).append(gvis)
        else:
            top_groups.append(gvis)

    total = len(visuals)
    tree = Tree(f'[bold]{pg.display_name}[/bold] [dim]({total} visuals)[/dim]')

    def _add_node(parent_tree, vis):
        pos = vis.position
        pos_str = f'{pos.get("x", 0)},{pos.get("y", 0)} {pos.get("width", 0)}x{pos.get("height", 0)}'
        hidden = " [yellow](hidden)[/yellow]" if vis.data.get("isHidden") else ""

        if "visualGroup" in vis.data:
            display = vis.data.get("visualGroup", {}).get("displayName", vis.name)
            children = groups.get(vis.name, [])
            label = f'[bold][group][/bold] [cyan]{display}[/cyan] [dim]({len(children)} children, {pos_str})[/dim]{hidden}'
            node = parent_tree.add(label)
            for child in children:
                _add_node(node, child)
        else:
            name_label = f'[cyan]{vis.name}[/cyan] ' if vis.name != vis.visual_type else ''
            label = f'{name_label}{vis.visual_type} [dim]{pos_str}[/dim]{hidden}'
            parent_tree.add(label)

    # Render top-level groups first, then ungrouped visuals
    for gvis in top_groups:
        _add_node(tree, gvis)
    for vis in top_level:
        _add_node(tree, vis)

    console.print(tree)


def _build_tree_data(visuals: list) -> list[dict]:
    """Build JSON-serializable tree structure."""
    from pbi.project import Visual as VisualType

    groups: dict[str, list[VisualType]] = {}
    group_visuals: dict[str, VisualType] = {}
    top_level: list[VisualType] = []

    for vis in visuals:
        if "visualGroup" in vis.data:
            group_visuals[vis.name] = vis
            groups.setdefault(vis.name, [])
        else:
            parent = vis.data.get("parentGroupName")
            if parent:
                groups.setdefault(parent, []).append(vis)
            else:
                top_level.append(vis)

    top_groups: list[VisualType] = []
    for _gname, gvis in group_visuals.items():
        parent = gvis.data.get("parentGroupName")
        if parent:
            groups.setdefault(parent, []).append(gvis)
        else:
            top_groups.append(gvis)

    def _node(vis):
        pos = vis.position
        entry = {
            "name": vis.name,
            "type": vis.visual_type if "visualGroup" not in vis.data else "group",
            "x": pos.get("x", 0),
            "y": pos.get("y", 0),
            "width": pos.get("width", 0),
            "height": pos.get("height", 0),
        }
        if "visualGroup" in vis.data:
            entry["displayName"] = vis.data.get("visualGroup", {}).get("displayName", vis.name)
            entry["children"] = [_node(c) for c in groups.get(vis.name, [])]
        if vis.data.get("isHidden"):
            entry["hidden"] = True
        return entry

    result = []
    for gvis in top_groups:
        result.append(_node(gvis))
    for vis in top_level:
        result.append(_node(vis))
    return result
