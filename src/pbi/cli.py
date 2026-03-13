"""PBI Report Builder CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich import box

from pbi.project import Project
from pbi.properties import (
    VISUAL_PROPERTIES,
    PAGE_PROPERTIES,
    get_property,
    set_property,
    list_properties,
)

app = typer.Typer(
    name="pbi",
    help="CLI tool for editing Power BI PBIP project files.",
    no_args_is_help=True,
)
page_app = typer.Typer(help="Page operations.", no_args_is_help=True)
visual_app = typer.Typer(help="Visual operations.", no_args_is_help=True)
model_app = typer.Typer(help="Semantic model operations.", no_args_is_help=True)
app.add_typer(page_app, name="page")
app.add_typer(visual_app, name="visual")
app.add_typer(model_app, name="model")

console = Console()

ProjectOpt = Annotated[
    Optional[Path],
    typer.Option("--project", "-p", help="Path to PBIP project (default: auto-detect from cwd)."),
]


def _get_project(project: Path | None) -> Project:
    try:
        return Project.find(project)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# ── Project info ───────────────────────────────────────────────────

@app.command()
def info(project: ProjectOpt = None) -> None:
    """Show project overview."""
    proj = _get_project(project)
    pages = proj.get_pages()
    meta = proj.get_pages_meta()

    tree = Tree(f"[bold]{proj.project_name}[/bold]")
    tree.add(f"[dim]Root:[/dim] {proj.root}")
    tree.add(f"[dim]Report:[/dim] {proj.report_folder.name}")

    pages_branch = tree.add(f"[bold]Pages[/bold] ({len(pages)})")
    for page in pages:
        visuals = proj.get_visuals(page)
        active = " [green](active)[/green]" if meta.get("activePageName") == page.name else ""
        hidden = " [yellow](hidden)[/yellow]" if page.visibility == "HiddenInViewMode" else ""
        page_node = pages_branch.add(
            f'[cyan]{page.display_name}[/cyan]{active}{hidden} '
            f'[dim]{page.width}x{page.height}[/dim]'
        )
        for v in visuals:
            pos = v.position
            page_node.add(
                f'{v.visual_type} [dim]@ {pos.get("x", 0)},{pos.get("y", 0)} '
                f'{pos.get("width", 0)}x{pos.get("height", 0)}[/dim]'
            )

    console.print(tree)


# ── Page commands ──────────────────────────────────────────────────

@page_app.command("list")
def page_list(project: ProjectOpt = None) -> None:
    """List all pages."""
    proj = _get_project(project)
    pages = proj.get_pages()
    meta = proj.get_pages_meta()

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


@page_app.command("get")
def page_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    prop: Annotated[Optional[str], typer.Argument(help="Property to read (omit for all).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show page details or a specific property."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if prop:
        value = get_property(pg.data, prop, PAGE_PROPERTIES)
        console.print(value)
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

    console.print(table)


@page_app.command("set")
def page_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    prop: Annotated[str, typer.Argument(help="Property path (e.g. 'width', 'displayName').")],
    value: Annotated[str, typer.Argument(help="New value.")],
    project: ProjectOpt = None,
) -> None:
    """Set a page property."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old = get_property(pg.data, prop, PAGE_PROPERTIES)
    try:
        set_property(pg.data, prop, value, PAGE_PROPERTIES)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    pg.save()
    new = get_property(pg.data, prop, PAGE_PROPERTIES)
    console.print(f"[dim]{prop}:[/dim] {old} [dim]→[/dim] {new}")


@page_app.command("props")
def page_props() -> None:
    """List available page properties."""
    table = Table(title="Page Properties", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for name, vtype, desc in list_properties(PAGE_PROPERTIES):
        table.add_row(name, vtype, desc)

    console.print(table)


@page_app.command("create")
def page_create(
    name: Annotated[str, typer.Argument(help="Display name for the new page.")],
    width: Annotated[int, typer.Option(help="Page width in pixels.")] = 1280,
    height: Annotated[int, typer.Option(help="Page height in pixels.")] = 720,
    display_option: Annotated[str, typer.Option("--display", help="FitToPage, FitToWidth, or ActualSize.")] = "FitToPage",
    project: ProjectOpt = None,
) -> None:
    """Create a new page."""
    proj = _get_project(project)
    pg = proj.create_page(name, width=width, height=height, display_option=display_option)
    console.print(f'Created page "[cyan]{pg.display_name}[/cyan]" ({pg.name})')


@page_app.command("copy")
def page_copy(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    name: Annotated[str, typer.Argument(help="Display name for the copy.")],
    project: ProjectOpt = None,
) -> None:
    """Copy/duplicate a page with all its visuals."""
    proj = _get_project(project)
    try:
        source = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    new_page = proj.copy_page(source, name)
    visuals = proj.get_visuals(new_page)
    console.print(
        f'Copied "[cyan]{source.display_name}[/cyan]" → '
        f'"[cyan]{new_page.display_name}[/cyan]" ({len(visuals)} visuals)'
    )


@page_app.command("delete")
def page_delete(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a page and all its visuals."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    if not force:
        confirm = typer.confirm(
            f'Delete page "{pg.display_name}" with {len(visuals)} visual(s)?'
        )
        if not confirm:
            raise typer.Abort()

    proj.delete_page(pg)
    console.print(f'Deleted page "[cyan]{pg.display_name}[/cyan]"')


# ── Visual commands ────────────────────────────────────────────────

@visual_app.command("list")
def visual_list(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """List all visuals on a page."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)

    table = Table(title=f"Visuals on \"{pg.display_name}\"", box=box.SIMPLE)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan", max_width=24)
    table.add_column("Type")
    table.add_column("Position", style="dim")
    table.add_column("Size", style="dim")
    table.add_column("Z", style="dim", justify="right")

    for i, v in enumerate(visuals, 1):
        pos = v.position
        hidden = " [yellow](hidden)[/yellow]" if v.data.get("isHidden") else ""
        table.add_row(
            str(i),
            f"{v.name[:24]}{hidden}",
            v.visual_type,
            f'{pos.get("x", 0)}, {pos.get("y", 0)}',
            f'{pos.get("width", 0)}x{pos.get("height", 0)}',
            str(pos.get("z", 0)),
        )

    console.print(table)


@visual_app.command("get")
def visual_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    prop: Annotated[Optional[str], typer.Argument(help="Property to read (omit for overview).")] = None,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Show raw JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show visual details or a specific property."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        import json
        console.print_json(json.dumps(vis.data, indent=2))
        return

    if prop:
        value = get_property(vis.data, prop, VISUAL_PROPERTIES)
        console.print(value)
        return

    # Overview
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

    # Show container formatting if present
    container_objects = vis.data.get("visual", {}).get("visualContainerObjects", {})
    if container_objects:
        table.add_section()
        for obj_name, entries in container_objects.items():
            if entries and isinstance(entries, list) and entries[0].get("properties"):
                for pname, pval in entries[0]["properties"].items():
                    from pbi.properties import decode_pbi_value
                    decoded = decode_pbi_value(pval)
                    table.add_row(f"{obj_name}.{pname}", str(decoded))

    # Show data bindings summary
    query = vis.data.get("visual", {}).get("query", {}).get("queryState", {})
    if query:
        table.add_section()
        for role, config in query.items():
            projections = config.get("projections", [])
            fields = []
            for p in projections:
                ref = p.get("queryRef", p.get("nativeQueryRef", "?"))
                fields.append(ref)
            table.add_row(f"[dim]Data:[/dim] {role}", ", ".join(fields))

    console.print(table)


@visual_app.command("set")
def visual_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    prop: Annotated[str, typer.Argument(help="Property path (e.g. 'position.x', 'background.color').")],
    value: Annotated[str, typer.Argument(help="New value.")],
    project: ProjectOpt = None,
) -> None:
    """Set a visual property."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old = get_property(vis.data, prop, VISUAL_PROPERTIES)
    try:
        set_property(vis.data, prop, value, VISUAL_PROPERTIES)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    vis.save()
    new = get_property(vis.data, prop, VISUAL_PROPERTIES)
    console.print(f"[dim]{prop}:[/dim] {old} [dim]→[/dim] {new}")


@visual_app.command("move")
def visual_move(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    x: Annotated[int, typer.Argument(help="X coordinate.")],
    y: Annotated[int, typer.Argument(help="Y coordinate.")],
    project: ProjectOpt = None,
) -> None:
    """Move a visual to a new position."""
    proj = _get_project(project)
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
    console.print(f"[dim]Moved:[/dim] {old_x},{old_y} [dim]→[/dim] {x},{y}")


@visual_app.command("resize")
def visual_resize(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    width: Annotated[int, typer.Argument(help="Width.")],
    height: Annotated[int, typer.Argument(help="Height.")],
    project: ProjectOpt = None,
) -> None:
    """Resize a visual."""
    proj = _get_project(project)
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
    console.print(f"[dim]Resized:[/dim] {old_w}x{old_h} [dim]→[/dim] {width}x{height}")


@visual_app.command("create")
def visual_create(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual_type: Annotated[str, typer.Argument(help="Visual type (e.g. clusteredColumnChart, card, table, slicer).")],
    x: Annotated[int, typer.Option(help="X position.")] = 0,
    y: Annotated[int, typer.Option(help="Y position.")] = 0,
    width: Annotated[int, typer.Option("-W", "--width", help="Width.")] = 300,
    height: Annotated[int, typer.Option("-H", "--height", help="Height.")] = 200,
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Friendly name for the visual.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Create a new visual on a page."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    vis = proj.create_visual(pg, visual_type, x=x, y=y, width=width, height=height)
    if name:
        vis.data["name"] = name
        vis.save()
    display = name or vis.name
    console.print(
        f'Created [cyan]{visual_type}[/cyan] "{display}" on "{pg.display_name}" '
        f"@ {x},{y} {width}x{height}"
    )


@visual_app.command("copy")
def visual_copy(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Source visual name, type, or index.")],
    to_page: Annotated[Optional[str], typer.Option("--to-page", help="Target page (default: same page).")] = None,
    name: Annotated[Optional[str], typer.Option("--name", help="Name for the copy.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Copy/duplicate a visual, optionally to a different page."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
        target = proj.find_page(to_page) if to_page else pg
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    new_vis = proj.copy_visual(vis, target, new_name=name)
    dest = f' to "{target.display_name}"' if to_page else ""
    console.print(
        f'Copied [cyan]{vis.visual_type}[/cyan] "{vis.name}"{dest} → "{new_vis.name}"'
    )


@visual_app.command("rename")
def visual_rename(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    name: Annotated[str, typer.Argument(help="New friendly name for the visual.")],
    project: ProjectOpt = None,
) -> None:
    """Give a visual a friendly name for easier CLI reference."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old_name = vis.name
    vis.data["name"] = name
    vis.save()
    console.print(f'Renamed "{old_name}" → "[cyan]{name}[/cyan]"')


@visual_app.command("delete")
def visual_delete(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a visual."""
    proj = _get_project(project)
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


@visual_app.command("bind")
def visual_bind(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    role: Annotated[str, typer.Argument(help="Data role (e.g. Category, Y, Values, Rows, Series).")],
    field: Annotated[str, typer.Argument(help="Field reference as Table.Field (e.g. Product.Category).")],
    measure: Annotated[bool, typer.Option("--measure", "-m", help="Treat field as a measure (fact) instead of column (dimension).")] = False,
    project: ProjectOpt = None,
) -> None:
    """Bind a column (dimension) or measure (fact) to a visual's data role."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Parse Table.Field
    dot = field.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Field must be in Table.Field format (e.g. Product.Category)")
        raise typer.Exit(1)
    entity, prop = field[:dot], field[dot + 1:]

    # Auto-detect field type from semantic model if not forced
    field_type = "measure" if measure else "column"
    if not measure:
        try:
            from pbi.model import SemanticModel
            model = SemanticModel.load(proj.root)
            _, resolved_prop, resolved_type = model.resolve_field(field)
            field_type = resolved_type
            prop = resolved_prop  # Use canonical name from model
        except (FileNotFoundError, ValueError):
            pass  # No model available, use user's specification

    proj.add_binding(vis, role, entity, prop, field_type=field_type)
    kind = "measure" if field_type == "measure" else "column"
    console.print(
        f'Bound [cyan]{entity}.{prop}[/cyan] ({kind}) → '
        f'{vis.visual_type} role "[bold]{role}[/bold]"'
    )


@visual_app.command("unbind")
def visual_unbind(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    role: Annotated[str, typer.Argument(help="Data role to unbind from.")],
    field: Annotated[Optional[str], typer.Argument(help="Specific field to remove (Table.Field). Omit to remove entire role.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Remove data bindings from a visual."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    removed = proj.remove_binding(vis, role, field_ref=field)
    if removed:
        target = f" ({field})" if field else ""
        console.print(f'Removed {removed} binding(s) from role "[bold]{role}[/bold]"{target}')
    else:
        console.print(f'[yellow]No bindings found for role "{role}"[/yellow]')


@visual_app.command("bindings")
def visual_bindings(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    project: ProjectOpt = None,
) -> None:
    """List all data bindings on a visual."""
    proj = _get_project(project)
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


@visual_app.command("types")
def visual_types(
    visual_type: Annotated[Optional[str], typer.Argument(help="Show roles for a specific visual type.")] = None,
) -> None:
    """List known visual types and their data roles."""
    from pbi.roles import VISUAL_ROLES

    if visual_type:
        vtype_lower = visual_type.lower()
        matches = {k: v for k, v in VISUAL_ROLES.items() if vtype_lower in k.lower()}
        if not matches:
            console.print(f'[red]Unknown visual type "{visual_type}".[/red]')
            console.print("[dim]Use 'pbi visual types' to see all known types.[/dim]")
            raise typer.Exit(1)
        for vtype, roles in matches.items():
            table = Table(title=vtype, box=box.SIMPLE)
            table.add_column("Role", style="bold cyan")
            table.add_column("Description")
            table.add_column("Multi", style="dim", justify="center")
            for role in roles:
                table.add_row(role["name"], role["description"], role["multi"])
            console.print(table)
        return

    table = Table(title="Visual Types & Data Roles", box=box.SIMPLE)
    table.add_column("Visual Type", style="cyan")
    table.add_column("Roles")

    for vtype, roles in sorted(VISUAL_ROLES.items()):
        role_names = ", ".join(r["name"] for r in roles)
        table.add_row(vtype, role_names)

    console.print(table)
    console.print("\n[dim]Use 'pbi visual types <type>' for detailed role info.[/dim]")


@visual_app.command("props")
def visual_props() -> None:
    """List available visual properties."""
    table = Table(title="Visual Properties", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for name, vtype, desc in list_properties(VISUAL_PROPERTIES):
        table.add_row(name, vtype, desc)

    console.print(table)
    console.print(
        "\n[dim]You can also use raw JSON paths "
        "(e.g. 'visual.objects.legend[0].properties.show')[/dim]"
    )


# ── Model commands ─────────────────────────────────────────────────

def _get_model(project: Path | None):
    from pbi.model import SemanticModel
    proj = _get_project(project)
    try:
        return proj, SemanticModel.load(proj.root)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@model_app.command("tables")
def model_tables(project: ProjectOpt = None) -> None:
    """List tables in the semantic model."""
    _, model = _get_model(project)

    table = Table(title="Semantic Model Tables", box=box.SIMPLE)
    table.add_column("Table", style="cyan")
    table.add_column("Columns", justify="right")
    table.add_column("Measures", justify="right")

    for t in model.tables:
        table.add_row(t.name, str(len(t.columns)), str(len(t.measures)))

    console.print(table)


@model_app.command("columns")
def model_columns(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    show_hidden: Annotated[bool, typer.Option("--hidden", help="Show hidden columns.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List columns (dimensions) in a table."""
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    cols = sem_table.columns
    if not show_hidden:
        cols = [c for c in cols if not c.is_hidden]

    table = Table(title=f'Columns in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Column", style="cyan")
    table.add_column("Data Type", style="dim")
    table.add_column("Source Column", style="dim")

    for c in cols:
        table.add_row(c.name, c.data_type, c.source_column)

    console.print(table)
    hidden_count = len(sem_table.columns) - len(cols)
    if hidden_count:
        console.print(f"[dim]({hidden_count} hidden columns, use --hidden to show)[/dim]")


@model_app.command("measures")
def model_measures(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    project: ProjectOpt = None,
) -> None:
    """List measures (facts) in a table."""
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    table = Table(title=f'Measures in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Measure", style="cyan")
    table.add_column("Expression", max_width=60)
    table.add_column("Format", style="dim")

    for m in sem_table.measures:
        expr = m.expression[:57] + "..." if len(m.expression) > 60 else m.expression
        table.add_row(m.name, expr, m.format_string)

    console.print(table)


@model_app.command("fields")
def model_fields(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    project: ProjectOpt = None,
) -> None:
    """List all fields (columns + measures) for use with 'visual bind'."""
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    table = Table(title=f'Fields in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Field Reference", style="cyan")
    table.add_column("Type")
    table.add_column("Details", style="dim")

    for c in sem_table.columns:
        if not c.is_hidden:
            table.add_row(
                f"{sem_table.name}.{c.name}",
                "column",
                c.data_type,
            )
    for m in sem_table.measures:
        expr = m.expression[:40] + "..." if len(m.expression) > 40 else m.expression
        table.add_row(
            f"{sem_table.name}.{m.name}",
            "[bold]measure[/bold]",
            expr,
        )

    console.print(table)


if __name__ == "__main__":
    app()
