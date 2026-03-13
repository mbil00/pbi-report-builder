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
app.add_typer(page_app, name="page")
app.add_typer(visual_app, name="visual")

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


if __name__ == "__main__":
    app()
