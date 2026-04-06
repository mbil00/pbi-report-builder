"""Page CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.table import Table

from pbi.page_metadata import (
    clear_page_drillthrough,
    clear_page_tooltip,
    configure_page_drillthrough,
    configure_page_tooltip,
    get_page_binding_info,
    list_pages as list_page_rows,
    rename_page as rename_page_service,
    reorder_pages,
    resolve_page_fields,
    set_active_page as set_active_page_service,
    set_all_page_properties,
    set_page_properties,
)
from pbi.page_sections import create_page_section, list_page_sections
from pbi.properties import PAGE_PROPERTIES, get_property, list_properties

from .common import (
    ProjectOpt,
    console,
    get_project,
    parse_property_assignments,
    resolve_output_path,
)

page_app = typer.Typer(help="Page operations.", no_args_is_help=True)
page_drillthrough_app = typer.Typer(help="Page drillthrough operations.", no_args_is_help=True)
page_tooltip_app = typer.Typer(help="Page tooltip operations.", no_args_is_help=True)
page_section_app = typer.Typer(help="Page section operations.", no_args_is_help=True)
page_app.add_typer(page_drillthrough_app, name="drillthrough")
page_app.add_typer(page_tooltip_app, name="tooltip")
page_app.add_typer(page_section_app, name="section")


def _get_page(project: Path | None, page: str):
    proj = get_project(project)
    try:
        return proj, proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@page_app.command("list")
def page_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List all pages."""
    proj = get_project(project)
    rows = list_page_rows(proj)

    if as_json:
        import json

        console.print_json(
            json.dumps(
                [
                    {
                        "index": row.index,
                        "name": row.display_name,
                        "folder": row.folder,
                        "width": row.width,
                        "height": row.height,
                        "displayOption": row.display_option,
                        "visibility": row.visibility,
                        "active": row.active,
                        "visuals": row.visual_count,
                    }
                    for row in rows
                ],
                indent=2,
            )
        )
        return

    table = Table(box=box.SIMPLE)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Size", style="dim")
    table.add_column("Display", style="dim")
    table.add_column("Visibility")
    table.add_column("Visuals", justify="right")

    for row in rows:
        vis_text = "AlwaysVisible" if row.visibility == "AlwaysVisible" else "[yellow]Hidden[/yellow]"
        name = f"[bold]{row.display_name}[/bold]" if row.active else row.display_name
        table.add_row(
            str(row.index),
            name,
            f"{row.width}x{row.height}",
            row.display_option,
            vis_text,
            str(row.visual_count),
        )

    console.print(table)


@page_app.command("reorder")
def page_reorder(
    pages: Annotated[list[str], typer.Argument(help="Pages in desired order (names, display names, or indices).")],
    project: ProjectOpt = None,
) -> None:
    """Set page order. List all pages in desired order, or a subset to move to front."""
    proj = get_project(project)
    try:
        ordered_pages = reorder_pages(proj, pages)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for i, pg in enumerate(ordered_pages, 1):
        console.print(f"  {i}. [cyan]{pg.display_name}[/cyan]")


@page_app.command("set-active")
def page_set_active(
    page: Annotated[str, typer.Argument(help="Page to set as active (name, display name, or index).")],
    project: ProjectOpt = None,
) -> None:
    """Set which page opens by default when the report is viewed."""
    proj = get_project(project)
    try:
        pg, old_name, changed = set_active_page_service(proj, page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not changed:
        console.print(f'[dim]"{pg.display_name}" is already the active page.[/dim]')
        return
    if old_name:
        console.print(f'Active page: "{old_name}" [dim]->[/dim] "[cyan]{pg.display_name}[/cyan]"')
    else:
        console.print(f'Active page set to "[cyan]{pg.display_name}[/cyan]"')


@page_app.command("get")
def page_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    props: Annotated[list[str] | None, typer.Argument(help="Property or properties to read (omit for overview).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show page details or one or more specific properties."""
    _proj, pg = _get_page(project, page)

    if props:
        if len(props) == 1:
            value = get_property(pg.data, props[0], PAGE_PROPERTIES)
            console.print(value)
            return

        table = Table(title=pg.display_name, box=box.SIMPLE)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        for prop in props:
            value = get_property(pg.data, prop, PAGE_PROPERTIES)
            table.add_row(prop, "" if value is None else str(value))
        console.print(table)
        return

    table = Table(title=pg.display_name, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Folder", pg.name)
    table.add_row("Display Name", pg.display_name)
    table.add_row("Width", str(pg.width))
    table.add_row("Height", str(pg.height))
    table.add_row("Display Option", pg.display_option)
    table.add_row("Visibility", pg.visibility)

    if pg.data.get("type"):
        table.add_row("Type", pg.data["type"])

    # Background color
    bg_color = get_property(pg.data, "background.color", PAGE_PROPERTIES)
    if bg_color:
        table.add_row("Background", str(bg_color))

    # Visual count
    proj = get_project(project)
    visuals = proj.get_visuals(pg)
    table.add_row("Visuals", str(len(visuals)))

    binding = get_page_binding_info(pg)
    if binding is not None:
        table.add_row("Binding Type", binding.binding_type)
        if binding.fields:
            table.add_row(
                "Binding Fields",
                ", ".join(
                    f"{entity}.{prop}{' (measure)' if field_type == 'measure' else ''}"
                    for entity, prop, field_type in binding.fields
                ),
            )
        if binding.binding_type == "Drillthrough":
            table.add_row("Cross Report", "yes" if binding.cross_report else "")

    console.print(table)


@page_app.command("set")
def page_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    project: ProjectOpt = None,
) -> None:
    """Set page properties."""
    _proj, pg = _get_page(project, page)

    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        changes = set_page_properties(pg, pairs)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for change in changes:
        if not change.changed:
            console.print(f"[dim]No change:[/dim] [cyan]{change.prop}[/cyan] is already {change.new}")
        else:
            console.print(f"[dim]{change.prop}:[/dim] {change.old} [dim]->[/dim] {change.new}")


@page_app.command("set-all")
def page_set_all(
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    exclude: Annotated[str | None, typer.Option("--exclude", help="Exclude pages whose display name contains this string.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change without saving.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set properties on all pages at once."""
    proj = get_project(project)
    filtered_pages = proj.get_pages()
    if exclude:
        filtered_pages = [page_obj for page_obj in filtered_pages if exclude not in page_obj.display_name]

    if not filtered_pages:
        console.print("[yellow]No pages match the filter.[/yellow]")
        raise typer.Exit(0)

    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        count_done = set_all_page_properties(proj, pairs, exclude=exclude, dry_run=dry_run)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    props_str = " ".join(f"{prop}={value}" for prop, value in pairs)
    if dry_run:
        console.print(f"Would set {props_str} on [cyan]{count_done}[/cyan] page(s)")
    else:
        console.print(f"Applied {props_str} to [cyan]{count_done}[/cyan] page(s)")


@page_app.command("properties")
def page_props() -> None:
    """List available page properties."""
    table = Table(title="Page Properties", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for name, vtype, desc, _group, _enums in list_properties(PAGE_PROPERTIES):
        table.add_row(name, vtype, desc)

    console.print(table)


@page_app.command("create")
def page_create(
    name: Annotated[str, typer.Argument(help="Display name for the new page.")],
    width: Annotated[int, typer.Option(help="Page width in pixels.")] = 1280,
    height: Annotated[int, typer.Option(help="Page height in pixels.")] = 720,
    display_option: Annotated[str, typer.Option("--display-option", help="FitToPage, FitToWidth, or ActualSize.")] = "FitToPage",
    from_template: Annotated[str | None, typer.Option("--from-template", help="Apply a saved template after creating the page.")] = None,
    template_global: Annotated[bool, typer.Option("--template-global", help="Resolve --from-template from global templates only.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a new page."""
    proj = get_project(project)
    pg = proj.create_page(name, width=width, height=height, display_option=display_option)
    console.print(f'Created page "[cyan]{pg.display_name}[/cyan]" ({pg.name})')

    if from_template:
        from pbi.templates import apply_template

        try:
            result = apply_template(proj, pg, from_template, global_scope=template_global)
        except (FileExistsError, FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        if result.errors:
            for error in result.errors:
                console.print(f"[red]Error:[/red] {error}")
            raise typer.Exit(1)
        created_count = len(result.visuals_created)
        console.print(
            f'Applied template "[cyan]{from_template}[/cyan]" ({created_count} visuals created)'
        )


@page_app.command("copy")
def page_copy(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    name: Annotated[str, typer.Argument(help="Display name for the copy.")],
    project: ProjectOpt = None,
) -> None:
    """Copy/duplicate a page with all its visuals."""
    proj, source = _get_page(project, page)
    new_page = proj.copy_page(source, name)
    visuals = proj.get_visuals(new_page)
    console.print(
        f'Copied "[cyan]{source.display_name}[/cyan]" -> '
        f'"[cyan]{new_page.display_name}[/cyan]" ({len(visuals)} visuals)'
    )


@page_app.command("rename")
def page_rename(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    new_name: Annotated[str, typer.Argument(help="New display name.")],
    project: ProjectOpt = None,
) -> None:
    """Rename a page by updating its display name."""
    _proj, pg = _get_page(project, page)
    old_name = pg.display_name
    if not rename_page_service(_proj, pg, new_name):
        console.print(f'[dim]No change:[/dim] [cyan]{old_name}[/cyan] is already named "{new_name}"')
        return
    console.print(f'Renamed page "[cyan]{old_name}[/cyan]" [dim]->[/dim] "[cyan]{new_name}[/cyan]"')


@page_app.command("delete")
def page_delete(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a page and all its visuals."""
    proj, pg = _get_page(project, page)
    visuals = proj.get_visuals(pg)
    if not force:
        confirm = typer.confirm(
            f'Delete page "{pg.display_name}" with {len(visuals)} visual(s)?'
        )
        if not confirm:
            raise typer.Abort()

    proj.delete_page(pg)
    console.print(f'Deleted page "[cyan]{pg.display_name}[/cyan]"')


@page_app.command("export")
def page_export(
    page: Annotated[Optional[str], typer.Argument(help="Page name (omit to export all pages).")] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output file (default: stdout).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Export page(s) as detailed YAML for use with 'pbi apply'."""
    from pbi.export import export_yaml

    proj = get_project(project)

    if page:
        try:
            proj.find_page(page)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    content = export_yaml(proj, page_filter=page)

    if output:
        out_path = resolve_output_path(output)
        out_path.write_text(content, encoding="utf-8")
        console.print(f"Exported to [cyan]{out_path}[/cyan]")
    else:
        typer.echo(content, nl=False)
@page_drillthrough_app.command("set")
def page_set_drillthrough(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    fields: Annotated[list[str], typer.Argument(help="Drillthrough fields as Table.Field (e.g. Product.Category).")],
    cross_report: Annotated[bool, typer.Option("--cross-report", help="Enable cross-report drillthrough.")] = False,
    hide: Annotated[bool, typer.Option("--hide/--no-hide", help="Hide the page in view mode after configuring drillthrough.")] = True,
    project: ProjectOpt = None,
) -> None:
    """Configure a page as a drillthrough target."""
    from pbi.drillthrough import configure_drillthrough

    proj, pg = _get_page(project, page)
    try:
        parsed = resolve_page_fields(proj, fields)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    configure_page_drillthrough(pg, parsed, cross_report=cross_report, hide=hide)

    field_list = ", ".join(fields)
    cross = " (cross-report)" if cross_report else ""
    hidden_note = " [dim](hidden)[/dim]" if hide else ""
    console.print(f'Configured "[cyan]{pg.display_name}[/cyan]" as drillthrough page{cross}{hidden_note}: {field_list}')


@page_drillthrough_app.command("get")
def page_get_drillthrough(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show drillthrough configuration for a page."""
    _proj, pg = _get_page(project, page)
    binding = get_page_binding_info(pg)
    if binding is None or binding.binding_type != "Drillthrough":
        console.print("[yellow]Page is not configured as drillthrough.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=pg.display_name, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Type", "Drillthrough")
    table.add_row("Cross Report", "yes" if binding.cross_report else "")
    table.add_row(
        "Fields",
        ", ".join(
            f"{entity}.{prop}{' (measure)' if field_type == 'measure' else ''}"
            for entity, prop, field_type in binding.fields
        ) or "(none)",
    )
    console.print(table)


@page_drillthrough_app.command("clear")
def page_clear_drillthrough(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear drillthrough configuration from a page."""
    _proj, pg = _get_page(project, page)
    binding = get_page_binding_info(pg)
    if binding is None or binding.binding_type != "Drillthrough":
        console.print("[yellow]Page is not configured as drillthrough.[/yellow]")
        return

    if not force:
        confirm = typer.confirm(f'Clear drillthrough from "{pg.display_name}"?')
        if not confirm:
            raise typer.Abort()

    clear_page_drillthrough(pg)
    console.print(f'Cleared drillthrough from "[cyan]{pg.display_name}[/cyan]"')


@page_tooltip_app.command("set")
def page_set_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    fields: Annotated[Optional[list[str]], typer.Argument(help="Auto-match fields as Table.Field (optional).")] = None,
    width: Annotated[int, typer.Option("-W", "--width", help="Tooltip page width.")] = 320,
    height: Annotated[int, typer.Option("-H", "--height", help="Tooltip page height.")] = 240,
    project: ProjectOpt = None,
) -> None:
    """Configure a page as a custom tooltip page."""
    proj, pg = _get_page(project, page)
    try:
        parsed = resolve_page_fields(proj, fields or [])
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    configure_page_tooltip(pg, parsed or None, width=width, height=height)

    console.print(
        f'Set "[cyan]{pg.display_name}[/cyan]" as tooltip page ({width}x{height})'
    )


@page_tooltip_app.command("get")
def page_get_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show tooltip configuration for a page."""
    _proj, pg = _get_page(project, page)
    binding = get_page_binding_info(pg)
    if binding is None or binding.binding_type != "Tooltip":
        console.print("[yellow]Page is not configured as a tooltip page.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=pg.display_name, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Type", "Tooltip")
    table.add_row("Width", str(pg.width))
    table.add_row("Height", str(pg.height))
    table.add_row(
        "Fields",
        ", ".join(
            f"{entity}.{prop}{' (measure)' if field_type == 'measure' else ''}"
            for entity, prop, field_type in binding.fields
        ) or "(none)",
    )
    console.print(table)


@page_tooltip_app.command("clear")
def page_clear_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear tooltip configuration from a page."""
    _proj, pg = _get_page(project, page)
    binding = get_page_binding_info(pg)
    if binding is None or binding.binding_type != "Tooltip":
        console.print("[yellow]Page is not configured as a tooltip page.[/yellow]")
        return

    if not force:
        confirm = typer.confirm(f'Clear tooltip configuration from "{pg.display_name}"?')
        if not confirm:
            raise typer.Abort()

    clear_page_tooltip(pg)
    console.print(f'Cleared tooltip config from "[cyan]{pg.display_name}[/cyan]"')


# ── Page import ──────────────────────────────────────────────

@page_app.command("import")
def page_import(
    from_project: Annotated[str, typer.Option("--from-project", help="Path to source PBIP project.")],
    page: Annotated[str, typer.Option("--page", help="Source page name, display name, or index.")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Display name in target project (default: same as source).")] = None,
    include_resources: Annotated[bool, typer.Option("--include-resources", help="Also copy image resources.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Import a page from another project.

    Copies all visuals and page structure. Use --include-resources to also
    copy image files from the source project's RegisteredResources.
    """
    from pbi.page_import import import_page as import_page_service

    target_proj = get_project(project)
    try:
        result = import_page_service(
            target_proj,
            from_project=from_project,
            page=page,
            name=name,
            include_resources=include_resources,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f'Imported "[cyan]{result.source_page_name}[/cyan]" from {result.source_project_name} '
        f'as "[cyan]{result.target_page_name}[/cyan]" ({result.visual_count} visuals)'
    )
    if result.resource_count:
        console.print(f"[dim]Copied {result.resource_count} image resource(s)[/dim]")


# ── Page sections ──────────────────────────────────────────────

@page_section_app.command("create")
def page_section_create(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    title: Annotated[str, typer.Argument(help="Section title text.")],
    x: Annotated[int, typer.Option(help="X position.")] = 0,
    y: Annotated[int, typer.Option(help="Y position.")] = 0,
    width: Annotated[int, typer.Option("-W", "--width", help="Section width.")] = 512,
    height: Annotated[int, typer.Option("-H", "--height", help="Section height.")] = 220,
    background: Annotated[str, typer.Option("--background", help="Background fill color.")] = "#F5F5F5",
    radius: Annotated[int, typer.Option("--radius", help="Border radius.")] = 10,
    title_color: Annotated[str, typer.Option("--title-color", help="Title text color.")] = "#002C77",
    title_font: Annotated[str, typer.Option("--title-font", help="Title font family.")] = "Segoe UI Semibold",
    title_size: Annotated[int, typer.Option("--title-size", help="Title font size.")] = 14,
    project: ProjectOpt = None,
) -> None:
    """Create a page section with background shape and title textbox."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    result = create_page_section(
        proj,
        pg,
        title,
        x=x,
        y=y,
        width=width,
        height=height,
        background=background,
        radius=radius,
        title_color=title_color,
        title_font=title_font,
        title_size=title_size,
    )

    console.print(
        f'Created section "[cyan]{title}[/cyan]" on "{pg.display_name}" '
        f"at ({x}, {y}) {width}x{height}"
    )
    console.print(f"  [dim]Background: {result.background_visual}[/dim]")
    console.print(f"  [dim]Title: {result.title_visual}[/dim]")
    console.print(f"  [dim]Group: {result.group_visual}[/dim]")


@page_section_app.command("list")
def page_section_list(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """List sections on a page (groups with 'Section:' prefix or section-bg visuals)."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    sections = list_page_sections(proj, pg)

    if not sections:
        console.print("[yellow]No sections found. Use `pbi page section create` to add one.[/yellow]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE)
    table.add_column("Section", style="cyan")
    table.add_column("Position", style="dim")
    table.add_column("Size", style="dim")

    for sec in sections:
        table.add_row(
            sec.name,
            f"{sec.x}, {sec.y}",
            f"{sec.width}x{sec.height}",
        )
    console.print(table)
