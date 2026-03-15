"""Bookmark CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project

bookmark_app = typer.Typer(help="Bookmark operations.", no_args_is_help=True)


@bookmark_app.command("list")
def bookmark_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List all bookmarks in the project."""
    from pbi.bookmarks import list_bookmarks

    proj = get_project(project)
    bookmarks = list_bookmarks(proj)

    if not bookmarks:
        console.print("[yellow]No bookmarks. Use `pbi bookmark create` to add one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json as json_mod

        rows = []
        for bm in bookmarks:
            rows.append({
                "name": bm.name,
                "displayName": bm.display_name,
                "activeSection": bm.active_section,
                "targets": bm.target_visuals or [],
                "suppressData": bm.suppress_data,
                "suppressDisplay": bm.suppress_display,
            })
        console.print_json(json_mod.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Active Page")
    table.add_column("Targets", style="dim")
    table.add_column("Options", style="dim")

    for bookmark in bookmarks:
        targets = ", ".join(bookmark.target_visuals) if bookmark.target_visuals else "all"
        opts = []
        if bookmark.suppress_data:
            opts.append("no-data")
        if bookmark.suppress_display:
            opts.append("no-display")
        table.add_row(
            bookmark.name[:16] + "..." if len(bookmark.name) > 16 else bookmark.name,
            bookmark.display_name,
            bookmark.active_section[:16] + "..." if len(bookmark.active_section) > 16 else bookmark.active_section,
            targets,
            ", ".join(opts) or "-",
        )

    console.print(table)


@bookmark_app.command("get")
def bookmark_get(
    bookmark: Annotated[str, typer.Argument(help="Bookmark name or display name.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Show raw JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show bookmark details."""
    import json as json_mod

    from pbi.bookmarks import get_bookmark

    proj = get_project(project)
    try:
        data = get_bookmark(proj, bookmark)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        console.print_json(json_mod.dumps(data, indent=2))
        return

    exploration = data.get("explorationState", {})
    options = data.get("options", {})

    table = Table(title=data.get("displayName", ""), box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Name", data.get("name", ""))
    table.add_row("Display Name", data.get("displayName", ""))
    table.add_row("Active Section", exploration.get("activeSection", ""))

    if options:
        table.add_section()
        if options.get("suppressActiveSection"):
            table.add_row("Suppress Active Section", "true")
        if options.get("suppressData"):
            table.add_row("Suppress Data", "true")
        if options.get("suppressDisplay"):
            table.add_row("Suppress Display", "true")
        if options.get("applyOnlyToTargetVisuals"):
            targets = options.get("targetVisualNames", [])
            table.add_row("Target Visuals", ", ".join(targets))

    sections = exploration.get("sections", {})
    for section_name, section_data in sections.items():
        containers = section_data.get("visualContainers", {})
        if containers:
            table.add_section()
            for vis_name, vis_state in containers.items():
                single = vis_state.get("singleVisual", {})
                display_state = single.get("display", {})
                mode = display_state.get("mode", "normal")
                table.add_row(f"[dim]{section_name}[/dim] {vis_name}", mode)

    console.print(table)


@bookmark_app.command("create")
def bookmark_create(
    name: Annotated[str, typer.Argument(help="Display name for the bookmark.")],
    page: Annotated[str, typer.Argument(help="Page to bookmark (name, display name, or index).")],
    hide: Annotated[list[str] | None, typer.Option("--hide", help="Visual names to hide in this bookmark.")] = None,
    target: Annotated[list[str] | None, typer.Option("--target", help="Only apply bookmark to these visuals.")] = None,
    capture_data: Annotated[bool, typer.Option("--capture-data/--no-capture-data", help="Capture data and filter state.")] = True,
    capture_display: Annotated[bool, typer.Option("--capture-display/--no-capture-display", help="Capture display state.")] = True,
    capture_page: Annotated[bool, typer.Option("--capture-page/--no-capture-page", help="Capture the active page.")] = True,
    project: ProjectOpt = None,
) -> None:
    """Create a bookmark capturing page state."""
    from pbi.bookmarks import create_bookmark

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    create_bookmark(
        proj,
        display_name=name,
        page=pg,
        visuals=visuals,
        hidden_visuals=hide,
        target_visuals=target,
        suppress_data=not capture_data,
        suppress_display=not capture_display,
        suppress_active_section=not capture_page,
    )

    hidden_count = len(hide) if hide else 0
    console.print(
        f'Created bookmark "[cyan]{name}[/cyan]" on page "{pg.display_name}"'
        f'{f" ({hidden_count} hidden)" if hidden_count else ""}'
    )


@bookmark_app.command("set")
def bookmark_set(
    bookmark: Annotated[str, typer.Argument(help="Bookmark name or display name.")],
    hide: Annotated[list[str] | None, typer.Option("--hide", help="Visual names to set as hidden.")] = None,
    show: Annotated[list[str] | None, typer.Option("--show", help="Visual names to set as visible.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Update visual visibility in an existing bookmark."""
    from pbi.bookmarks import update_bookmark_visuals

    proj = get_project(project)

    if not hide and not show:
        console.print("[red]Error:[/red] Specify --hide or --show to update visual states.")
        raise typer.Exit(1)

    try:
        data = update_bookmark_visuals(
            proj,
            bookmark,
            hidden_visuals=hide,
            visible_visuals=show,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    changes = []
    if hide:
        changes.append(f"hidden: {', '.join(hide)}")
    if show:
        changes.append(f"visible: {', '.join(show)}")
    console.print(
        f'Updated bookmark "[cyan]{data.get("displayName", bookmark)}[/cyan]": '
        f'{"; ".join(changes)}'
    )


@bookmark_app.command("delete")
def bookmark_delete(
    bookmark: Annotated[str, typer.Argument(help="Bookmark name or display name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a bookmark."""
    from pbi.bookmarks import delete_bookmark

    proj = get_project(project)

    if not force:
        confirm = typer.confirm(f'Delete bookmark "{bookmark}"?')
        if not confirm:
            raise typer.Abort()

    try:
        display_name = delete_bookmark(proj, bookmark)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f'Deleted bookmark "[cyan]{display_name}[/cyan]"')
