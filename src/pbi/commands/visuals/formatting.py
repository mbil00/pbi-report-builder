"""Visual formatting commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from ..common import ProjectOpt, console, get_project
from .app import visual_app, visual_format_app
from .helpers import resolve_visual_target


@visual_format_app.command("get")
def visual_format_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show conditional formatting on a visual."""
    from pbi.formatting import get_conditional_formats

    _proj, _pg, vis = resolve_visual_target(project, page, visual)

    formats = get_conditional_formats(vis.data)
    if not formats:
        console.print("[dim]No conditional formatting on this visual.[/dim]")
        return
    table = Table(title="Conditional Formatting", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Mode")
    table.add_column("Source", style="bold")
    table.add_column("Column", style="dim")
    table.add_column("Details", style="dim")
    for fmt in formats:
        table.add_row(f"{fmt.object_name}.{fmt.property_name}", fmt.format_type, fmt.field_ref, fmt.column or "(all)", fmt.details)
    console.print(table)


@visual_format_app.command("set")
def visual_format_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    prop: Annotated[str, typer.Argument(help="Property as object.prop (e.g. dataPoint.fill).")],
    mode: Annotated[str, typer.Option("--mode", help="Formatting mode: measure, gradient, or rules.")],
    source: Annotated[str, typer.Option("--source", help="Source field: Table.Measure for measure mode, Table.Field for gradient mode.")],
    min_color: Annotated[str | None, typer.Option("--min-color", help="Gradient minimum color (#hex).")] = None,
    min_value: Annotated[float | None, typer.Option("--min-value", help="Gradient minimum value.")] = None,
    mid_color: Annotated[str | None, typer.Option("--mid-color", help="Gradient midpoint color (#hex).")] = None,
    mid_value: Annotated[float | None, typer.Option("--mid-value", help="Gradient midpoint value.")] = None,
    max_color: Annotated[str | None, typer.Option("--max-color", help="Gradient maximum color (#hex).")] = None,
    max_value: Annotated[float | None, typer.Option("--max-value", help="Gradient maximum value.")] = None,
    rule: Annotated[list[str] | None, typer.Option("--rule", help="Rules mode: value=color pair (repeatable). E.g. --rule Compliant=#2B7A4B")] = None,
    else_color: Annotated[str | None, typer.Option("--else-color", help="Rules mode: fallback color when no rule matches.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set conditional formatting on a visual property."""
    from pbi.formatting import GradientStop, build_gradient_format, build_measure_format, build_rules_format, set_conditional_format
    from ..common import resolve_field_type

    proj, _pg, vis = resolve_visual_target(project, page, visual)

    dot = prop.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Property must be object.prop format (e.g. dataPoint.fill).")
        raise typer.Exit(1)
    obj_name, prop_name = prop[:dot], prop[dot + 1 :]

    if mode not in {"measure", "gradient", "rules"}:
        console.print("[red]Error:[/red] --mode must be 'measure', 'gradient', or 'rules'.")
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

    # Resolve source field for gradient and rules modes
    src_dot = source.find(".")
    if src_dot == -1:
        console.print("[red]Error:[/red] --source must be Table.Field format.")
        raise typer.Exit(1)
    src_entity, src_prop, src_field_type = resolve_field_type(proj, source, "auto")

    if mode == "rules":
        if not rule:
            console.print("[red]Error:[/red] Rules mode requires at least one --rule value=color pair.")
            raise typer.Exit(1)
        parsed_rules = []
        for r in rule:
            eq = r.find("=")
            if eq == -1:
                console.print(f'[red]Error:[/red] Invalid rule "{r}". Use value=color format (e.g. Compliant=#2B7A4B).')
                raise typer.Exit(1)
            parsed_rules.append({"value": r[:eq], "color": r[eq + 1:]})

        value = build_rules_format(
            src_entity, src_prop, parsed_rules,
            else_color=else_color,
            field_type=src_field_type,
        )
        set_conditional_format(vis.data, obj_name, prop_name, value)
        vis.save()
        console.print(f"Set [cyan]{prop}[/cyan] = rules by [bold]{src_entity}.{src_prop}[/bold] ({len(parsed_rules)} rules)")
        return

    # Gradient mode
    if min_color is None or min_value is None or max_color is None or max_value is None:
        console.print("[red]Error:[/red] Gradient mode requires --min-color, --min-value, --max-color, and --max-value.")
        raise typer.Exit(1)

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
        field_type=src_field_type,
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

    _proj, _pg, vis = resolve_visual_target(project, page, visual)

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
    all_pages: Annotated[bool, typer.Option("--all-pages", help="Apply across all pages (requires --rename or --width with a column field).")] = False,
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

    if all_pages:
        if not column:
            console.print("[red]Error:[/red] --all-pages requires a column field reference.")
            raise typer.Exit(1)
        if not rename and width is None:
            console.print("[red]Error:[/red] --all-pages requires --rename or --width.")
            raise typer.Exit(1)

        proj = get_project(project)
        total = 0
        for pg in proj.get_pages():
            for vis in proj.get_visuals(pg):
                try:
                    col = find_column(vis, column)
                except ValueError:
                    continue
                if rename is not None:
                    rename_column(vis, col.query_ref, rename)
                if width is not None:
                    set_column_width(vis, col.query_ref, width)
                vis.save()
                total += 1
                parts = []
                if rename:
                    parts.append(f"rename={rename}")
                if width is not None:
                    parts.append(f"width={int(width)}")
                console.print(f'[dim]{pg.display_name}/{vis.name}:[/dim] {col.entity}.{col.prop} → {", ".join(parts)}')

        if total == 0:
            console.print(f'[yellow]Column "{column}" not found on any visual.[/yellow]')
        else:
            console.print(f"Updated [cyan]{total}[/cyan] visual(s) across all pages.")
        return

    _proj, _pg, vis = resolve_visual_target(project, page, visual)

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
