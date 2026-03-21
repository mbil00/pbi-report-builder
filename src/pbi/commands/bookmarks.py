"""Bookmark CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project

bookmark_app = typer.Typer(help="Bookmark operations.", no_args_is_help=True)
bookmark_group_app = typer.Typer(help="Bookmark group operations.", no_args_is_help=True)
bookmark_app.add_typer(bookmark_group_app, name="group")


def _load_json_mapping(path: Path | None) -> dict | None:
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] File not found: {path}")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON in {path}: {e}")
        raise typer.Exit(1)
    if not isinstance(data, dict):
        console.print(f"[red]Error:[/red] {path} must contain a JSON object.")
        raise typer.Exit(1)
    return data


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
                "group": bm.group,
                "hiddenVisuals": bm.hidden_visuals,
                "sortStates": bm.sort_states,
                "filterStates": bm.filter_states,
                "projectionStates": bm.projection_states,
                "objectStates": bm.object_states,
            })
        console.print_json(json_mod.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Active Page")
    table.add_column("Group", style="dim")
    table.add_column("Targets", style="dim")
    table.add_column("State", style="dim")
    table.add_column("Options", style="dim")

    for bookmark in bookmarks:
        targets = ", ".join(bookmark.target_visuals) if bookmark.target_visuals else "all"
        state_parts = []
        if bookmark.hidden_visuals:
            state_parts.append(f"{bookmark.hidden_visuals} hidden")
        if bookmark.sort_states:
            state_parts.append(f"{bookmark.sort_states} sort")
        if bookmark.filter_states:
            state_parts.append(f"{bookmark.filter_states} filter")
        if bookmark.projection_states:
            state_parts.append(f"{bookmark.projection_states} projection")
        if bookmark.object_states:
            state_parts.append(f"{bookmark.object_states} object")
        opts = []
        if bookmark.suppress_data:
            opts.append("no-data")
        if bookmark.suppress_display:
            opts.append("no-display")
        table.add_row(
            bookmark.name[:16] + "..." if len(bookmark.name) > 16 else bookmark.name,
            bookmark.display_name,
            bookmark.active_section[:16] + "..." if len(bookmark.active_section) > 16 else bookmark.active_section,
            bookmark.group or "-",
            targets,
            ", ".join(state_parts) or "-",
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

    from pbi.bookmarks import describe_bookmark_state, get_bookmark, summarize_bookmark_state

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
    group_lookup = None
    try:
        from pbi.bookmarks import _bookmark_group_lookup, _load_meta

        group_lookup = _bookmark_group_lookup(_load_meta(proj))
    except Exception:
        group_lookup = None

    table = Table(title=data.get("displayName", ""), box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Name", data.get("name", ""))
    table.add_row("Display Name", data.get("displayName", ""))
    table.add_row("Active Section", exploration.get("activeSection", ""))
    summary = summarize_bookmark_state(data)
    table.add_row("Hidden Visuals", str(summary["hiddenVisuals"]))
    table.add_row("Sort States", str(summary["sortStates"]))
    table.add_row("Filter States", str(summary["filterStates"]))
    table.add_row("Projection States", str(summary["projectionStates"]))
    table.add_row("Object States", str(summary["objectStates"]))
    if group_lookup is not None:
        group_name = group_lookup.get(data.get("name", ""))
        if group_name:
            table.add_row("Group", group_name)

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

    state_rows = describe_bookmark_state(data)
    if state_rows:
        table.add_section()
        for label, value in state_rows:
            table.add_row(label, value)

    console.print(table)


@bookmark_group_app.command("list")
def bookmark_group_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List bookmark groups."""
    import json as json_mod

    from pbi.bookmarks import list_bookmark_groups

    proj = get_project(project)
    groups = list_bookmark_groups(proj)
    if not groups:
        console.print("[yellow]No bookmark groups. Use `pbi bookmark group create` to add one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        rows = [{"name": group.name, "children": group.children} for group in groups]
        console.print_json(json_mod.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Group", style="cyan")
    table.add_column("Bookmarks")
    table.add_column("Count", style="dim")

    for group in groups:
        table.add_row(group.name, ", ".join(group.children), str(len(group.children)))

    console.print(table)


@bookmark_group_app.command("create")
def bookmark_group_create(
    name: Annotated[str, typer.Argument(help="Display name for the bookmark group.")],
    bookmarks: Annotated[list[str], typer.Argument(help="Bookmarks to include in the group (at least 2).")],
    project: ProjectOpt = None,
) -> None:
    """Create a bookmark group from existing bookmarks."""
    from pbi.bookmarks import create_bookmark_group

    proj = get_project(project)
    try:
        group = create_bookmark_group(proj, name, bookmarks)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f'Created bookmark group "[cyan]{group.name}[/cyan]" '
        f'with [cyan]{len(group.children)}[/cyan] bookmark(s)'
    )


@bookmark_group_app.command("delete")
def bookmark_group_delete(
    group: Annotated[str, typer.Argument(help="Bookmark group display name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a bookmark group and restore its bookmarks as standalone items."""
    from pbi.bookmarks import delete_bookmark_group

    proj = get_project(project)
    if not force:
        confirm = typer.confirm(f'Delete bookmark group "{group}"?')
        if not confirm:
            raise typer.Abort()

    try:
        removed = delete_bookmark_group(proj, group)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f'Deleted bookmark group "[cyan]{removed.name}[/cyan]" '
        f'([cyan]{len(removed.children)}[/cyan] bookmark(s) restored)'
    )


@bookmark_app.command("create")
def bookmark_create(
    name: Annotated[str, typer.Argument(help="Display name for the bookmark.")],
    page: Annotated[str, typer.Argument(help="Page to bookmark (name, display name, or index).")],
    hide: Annotated[list[str] | None, typer.Option("--hide", help="Visual names to hide in this bookmark.")] = None,
    target: Annotated[list[str] | None, typer.Option("--target", help="Only apply bookmark to these visuals.")] = None,
    capture_data: Annotated[bool, typer.Option("--capture-data/--no-capture-data", help="Capture data and filter state.")] = True,
    capture_display: Annotated[bool, typer.Option("--capture-display/--no-capture-display", help="Capture display state.")] = True,
    capture_page: Annotated[bool, typer.Option("--capture-page/--no-capture-page", help="Capture the active page.")] = True,
    state_file: Annotated[Path | None, typer.Option("--state-file", help="Merge bookmark explorationState patch from JSON file.")] = None,
    options_file: Annotated[Path | None, typer.Option("--options-file", help="Merge bookmark options patch from JSON file.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Create a bookmark capturing page state."""
    from pbi.bookmarks import create_bookmark, normalize_bookmark_state

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    state_patch = _load_json_mapping(state_file)
    if state_patch is not None:
        state_patch = normalize_bookmark_state(proj, state_patch)
    options_patch = _load_json_mapping(options_file)
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
        exploration_state_patch=state_patch,
        options_patch=options_patch,
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
    page: Annotated[str | None, typer.Option("--page", help="Set the bookmark's active page.")] = None,
    target: Annotated[list[str] | None, typer.Option("--target", help="Restrict bookmark to these visuals.")] = None,
    clear_targets: Annotated[bool, typer.Option("--clear-targets", help="Remove bookmark target-visual restrictions.")] = False,
    capture_data: Annotated[bool | None, typer.Option("--capture-data/--no-capture-data", help="Toggle data/filter capture.")] = None,
    capture_display: Annotated[bool | None, typer.Option("--capture-display/--no-capture-display", help="Toggle display capture.")] = None,
    capture_page: Annotated[bool | None, typer.Option("--capture-page/--no-capture-page", help="Toggle active-page capture.")] = None,
    state_file: Annotated[Path | None, typer.Option("--state-file", help="Merge bookmark explorationState patch from JSON file.")] = None,
    options_file: Annotated[Path | None, typer.Option("--options-file", help="Merge bookmark options patch from JSON file.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Update an existing bookmark."""
    from pbi.bookmarks import normalize_bookmark_state, update_bookmark

    proj = get_project(project)

    if not any([
        hide,
        show,
        page,
        target is not None,
        clear_targets,
        capture_data is not None,
        capture_display is not None,
        capture_page is not None,
        state_file is not None,
        options_file is not None,
    ]):
        console.print("[red]Error:[/red] Specify bookmark state changes to apply.")
        raise typer.Exit(1)

    page_ref = None
    if page:
        try:
            page_ref = proj.find_page(page)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    state_patch = _load_json_mapping(state_file)
    if state_patch is not None:
        state_patch = normalize_bookmark_state(proj, state_patch)
    options_patch = _load_json_mapping(options_file)
    try:
        data = update_bookmark(
            proj,
            bookmark,
            hidden_visuals=hide,
            visible_visuals=show,
            page=page_ref,
            target_visuals=target,
            clear_targets=clear_targets,
            capture_data=capture_data,
            capture_display=capture_display,
            capture_page=capture_page,
            exploration_state_patch=state_patch,
            options_patch=options_patch,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    changes = []
    if hide:
        changes.append(f"hidden: {', '.join(hide)}")
    if show:
        changes.append(f"visible: {', '.join(show)}")
    if page_ref is not None:
        changes.append(f"page: {page_ref.display_name}")
    if target is not None:
        changes.append(f"targets: {', '.join(target) if target else '(none)'}")
    if clear_targets:
        changes.append("targets cleared")
    if capture_data is not None:
        changes.append(f"captureData: {capture_data}")
    if capture_display is not None:
        changes.append(f"captureDisplay: {capture_display}")
    if capture_page is not None:
        changes.append(f"capturePage: {capture_page}")
    if state_file is not None:
        changes.append(f"state patch: {state_file.name}")
    if options_file is not None:
        changes.append(f"options patch: {options_file.name}")
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
