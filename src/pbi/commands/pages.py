"""Page CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.table import Table

from pbi.properties import PAGE_PROPERTIES, get_property, list_properties, set_property

from .common import ProjectOpt, console, get_project, parse_property_assignments, resolve_field_type

page_app = typer.Typer(help="Page operations.", no_args_is_help=True)
page_drillthrough_app = typer.Typer(help="Page drillthrough operations.", no_args_is_help=True)
page_tooltip_app = typer.Typer(help="Page tooltip operations.", no_args_is_help=True)
page_app.add_typer(page_drillthrough_app, name="drillthrough")
page_app.add_typer(page_tooltip_app, name="tooltip")


def _get_page(project: Path | None, page: str):
    proj = get_project(project)
    try:
        return proj, proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _resolve_page_fields(proj, fields: list[str]) -> list[tuple[str, str, str]]:
    parsed: list[tuple[str, str, str]] = []
    for field in fields:
        try:
            parsed.append(resolve_field_type(proj, field, "auto"))
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    return parsed


@page_app.command("list")
def page_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List all pages."""
    proj = get_project(project)
    pages = proj.get_pages()
    meta = proj.get_pages_meta()

    if as_json:
        import json

        rows = []
        for i, pg in enumerate(pages, 1):
            visuals = proj.get_visuals(pg)
            rows.append({
                "index": i,
                "name": pg.display_name,
                "folder": pg.name,
                "width": pg.width,
                "height": pg.height,
                "displayOption": pg.display_option,
                "visibility": pg.visibility,
                "active": meta.get("activePageName") == pg.name,
                "visuals": len(visuals),
            })
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Size", style="dim")
    table.add_column("Display", style="dim")
    table.add_column("Visibility")
    table.add_column("Visuals", justify="right")

    for i, page in enumerate(pages, 1):
        visuals = proj.get_visuals(page)
        active = meta.get("activePageName") == page.name
        vis_text = "AlwaysVisible" if page.visibility == "AlwaysVisible" else "[yellow]Hidden[/yellow]"
        name = f"[bold]{page.display_name}[/bold]" if active else page.display_name
        table.add_row(
            str(i),
            name,
            f"{page.width}x{page.height}",
            page.display_option,
            vis_text,
            str(len(visuals)),
        )

    console.print(table)


@page_app.command("reorder")
def page_reorder(
    pages: Annotated[list[str], typer.Argument(help="Pages in desired order (names, display names, or indices).")],
    project: ProjectOpt = None,
) -> None:
    """Set page order. List all pages in desired order, or a subset to move to front."""
    proj = get_project(project)
    all_pages = proj.get_pages()
    all_ids = [p.name for p in all_pages]

    # Resolve referenced pages
    resolved_ids: list[str] = []
    for ref in pages:
        try:
            pg = proj.find_page(ref)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        if pg.name in resolved_ids:
            console.print(f'[red]Error:[/red] Page "{pg.display_name}" listed more than once.')
            raise typer.Exit(1)
        resolved_ids.append(pg.name)

    # If partial list, append remaining pages in current order
    if len(resolved_ids) < len(all_ids):
        for pid in all_ids:
            if pid not in resolved_ids:
                resolved_ids.append(pid)

    proj.set_page_order(resolved_ids)

    # Display new order
    id_to_page = {p.name: p for p in all_pages}
    for i, pid in enumerate(resolved_ids, 1):
        pg = id_to_page[pid]
        console.print(f"  {i}. [cyan]{pg.display_name}[/cyan]")


@page_app.command("set-active")
def page_set_active(
    page: Annotated[str, typer.Argument(help="Page to set as active (name, display name, or index).")],
    project: ProjectOpt = None,
) -> None:
    """Set which page opens by default when the report is viewed."""
    proj, pg = _get_page(project, page)
    meta = proj.get_pages_meta()
    old_active = meta.get("activePageName")

    if old_active == pg.name:
        console.print(f'[dim]"{pg.display_name}" is already the active page.[/dim]')
        return

    proj.set_active_page(pg.name)

    old_name = None
    if old_active:
        for p in proj.get_pages():
            if p.name == old_active:
                old_name = p.display_name
                break
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

    proj = get_project(project)

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
    visuals = proj.get_visuals(pg)
    table.add_row("Visuals", str(len(visuals)))

    # Drillthrough/tooltip info
    page_binding = pg.data.get("pageBinding")
    if page_binding:
        binding_type = page_binding.get("type", "")
        table.add_row("Binding Type", binding_type)
        data_fields = page_binding.get("dataFields", [])
        if data_fields:
            refs = []
            for df in data_fields:
                col = df.get("Column", {})
                entity = col.get("Entity", "?")
                prop = col.get("Property", "?")
                refs.append(f"{entity}.{prop}")
            table.add_row("Binding Fields", ", ".join(refs))

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

    for prop, value in pairs:
        old = get_property(pg.data, prop, PAGE_PROPERTIES)
        try:
            set_property(pg.data, prop, value, PAGE_PROPERTIES)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {prop}: {e}")
            raise typer.Exit(1)
        new = get_property(pg.data, prop, PAGE_PROPERTIES)
        console.print(f"[dim]{prop}:[/dim] {old} [dim]->[/dim] {new}")

    pg.save()


@page_app.command("set-all")
def page_set_all(
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    exclude: Annotated[str | None, typer.Option("--exclude", help="Exclude pages whose display name contains this string.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change without saving.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set properties on all pages at once."""
    proj = get_project(project)
    pages = proj.get_pages()

    if exclude:
        pages = [p for p in pages if exclude not in p.display_name]

    if not pages:
        console.print("[yellow]No pages match the filter.[/yellow]")
        raise typer.Exit(0)

    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    count_done = 0
    for pg in pages:
        for prop, value in pairs:
            try:
                set_property(pg.data, prop, value, PAGE_PROPERTIES)
            except ValueError as e:
                console.print(f"[red]Error:[/red] {pg.display_name}: {prop}: {e}")
                raise typer.Exit(1)
        if not dry_run:
            pg.save()
        count_done += 1

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
    project: ProjectOpt = None,
) -> None:
    """Create a new page."""
    proj = get_project(project)
    pg = proj.create_page(name, width=width, height=height, display_option=display_option)
    console.print(f'Created page "[cyan]{pg.display_name}[/cyan]" ({pg.name})')

    if from_template:
        from pbi.templates import apply_template

        try:
            created = apply_template(proj, pg, from_template)
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        console.print(
            f'Applied template "[cyan]{from_template}[/cyan]" ({len(created)} visuals created)'
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
        out_path = output if output.is_absolute() else proj.root / output
        out_path.write_text(content, encoding="utf-8")
        console.print(f"Exported to [cyan]{out_path}[/cyan]")
    else:
        typer.echo(content, nl=False)


@page_app.command("save-template")
def page_save_template(
    page: Annotated[str, typer.Argument(help="Page to save as template.")],
    template_name: Annotated[str, typer.Argument(help="Name for the template.")],
    project: ProjectOpt = None,
) -> None:
    """Save a page's layout and formatting as a reusable template."""
    from pbi.templates import save_template

    proj, pg = _get_page(project, page)
    visuals = proj.get_visuals(pg)
    try:
        path = save_template(proj, pg, template_name, visuals)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(
        f'Saved template "[cyan]{template_name}[/cyan]" '
        f"({len(visuals)} visuals) -> {path}"
    )


@page_app.command("apply-template")
def page_apply_template(
    page: Annotated[str, typer.Argument(help="Target page to apply template to.")],
    template_name: Annotated[str, typer.Argument(help="Template name to apply.")],
    project: ProjectOpt = None,
) -> None:
    """Apply a saved template to a page."""
    from pbi.templates import apply_template

    proj, pg = _get_page(project, page)

    try:
        created = apply_template(proj, pg, template_name)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f'Applied template "[cyan]{template_name}[/cyan]" -> '
        f'"{pg.display_name}" ({len(created)} visuals created)'
    )


@page_app.command("templates")
def page_templates(
    project: ProjectOpt = None,
) -> None:
    """List available page templates."""
    from pbi.templates import list_templates

    proj = get_project(project)
    templates = list_templates(proj)

    if not templates:
        console.print("[yellow]No templates saved. Use `pbi page save-template` to create one.[/yellow]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Visuals")
    table.add_column("Page Size")
    table.add_column("File", style="dim")
    for template in templates:
        table.add_row(template["name"], str(template["visuals"]), template["size"], template["file"])
    console.print(table)


@page_app.command("delete-template")
def page_delete_template(
    template_name: Annotated[str, typer.Argument(help="Template name to delete.")],
    project: ProjectOpt = None,
) -> None:
    """Delete a saved page template."""
    from pbi.templates import delete_template

    proj = get_project(project)
    try:
        deleted = delete_template(proj, template_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if deleted:
        console.print(f'Deleted template "[cyan]{template_name}[/cyan]"')
    else:
        console.print(f'[yellow]Template "{template_name}" not found.[/yellow]')


@page_drillthrough_app.command("set")
def page_set_drillthrough(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    fields: Annotated[list[str], typer.Argument(help="Drillthrough fields as Table.Field (e.g. Product.Category).")],
    cross_report: Annotated[bool, typer.Option("--cross-report", help="Enable cross-report drillthrough.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Configure a page as a drillthrough target."""
    from pbi.drillthrough import configure_drillthrough

    proj, pg = _get_page(project, page)
    parsed = _resolve_page_fields(proj, fields)

    configure_drillthrough(pg, parsed, cross_report=cross_report)
    pg.save()

    field_list = ", ".join(fields)
    cross = " (cross-report)" if cross_report else ""
    console.print(
        f'Configured "[cyan]{pg.display_name}[/cyan]" as drillthrough page{cross}: {field_list}'
    )


@page_drillthrough_app.command("clear")
def page_clear_drillthrough(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Remove drillthrough configuration from a page."""
    from pbi.drillthrough import clear_drillthrough

    _proj, pg = _get_page(project, page)

    if clear_drillthrough(pg):
        pg.save()
        console.print(f'Removed drillthrough from "[cyan]{pg.display_name}[/cyan]"')
    else:
        console.print("[yellow]Page is not configured as drillthrough.[/yellow]")


@page_tooltip_app.command("set")
def page_set_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    fields: Annotated[Optional[list[str]], typer.Argument(help="Auto-match fields as Table.Field (optional).")] = None,
    width: Annotated[int, typer.Option("-W", "--width", help="Tooltip page width.")] = 320,
    height: Annotated[int, typer.Option("-H", "--height", help="Tooltip page height.")] = 240,
    project: ProjectOpt = None,
) -> None:
    """Configure a page as a custom tooltip page."""
    from pbi.drillthrough import configure_tooltip_page

    proj, pg = _get_page(project, page)
    parsed = _resolve_page_fields(proj, fields or [])

    configure_tooltip_page(pg, parsed or None, width=width, height=height)
    pg.save()

    console.print(
        f'Configured "[cyan]{pg.display_name}[/cyan]" as tooltip page ({width}x{height})'
    )


@page_tooltip_app.command("clear")
def page_clear_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Remove tooltip configuration from a page."""
    from pbi.drillthrough import clear_tooltip_page

    _proj, pg = _get_page(project, page)

    if clear_tooltip_page(pg):
        pg.save()
        console.print(f'Removed tooltip config from "[cyan]{pg.display_name}[/cyan]"')
    else:
        console.print("[yellow]Page is not configured as a tooltip page.[/yellow]")
