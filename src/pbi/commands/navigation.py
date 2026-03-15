"""First-class navigation and action wiring commands."""

from __future__ import annotations

from typing import Annotated

import typer

from pbi.properties import VISUAL_PROPERTIES, set_property

from .common import ProjectOpt, console
from .visuals.helpers import resolve_visual_target

nav_app = typer.Typer(help="Navigation and button action operations.", no_args_is_help=True)


def _clear_action_state(visual_data: dict) -> bool:
    visual = visual_data.get("visual")
    if not isinstance(visual, dict):
        return False
    container_objects = visual.get("visualContainerObjects")
    if not isinstance(container_objects, dict):
        return False
    removed = container_objects.pop("visualLink", None) is not None
    if not container_objects:
        visual.pop("visualContainerObjects", None)
    return removed


def _set_action(
    visual_data: dict,
    *,
    action_type: str,
    tooltip: str | None = None,
    bookmark: str | None = None,
    page: str | None = None,
    url: str | None = None,
) -> None:
    _clear_action_state(visual_data)
    set_property(visual_data, "action.show", "true", VISUAL_PROPERTIES)
    set_property(visual_data, "action.type", action_type, VISUAL_PROPERTIES)
    if bookmark is not None:
        set_property(visual_data, "action.bookmark", bookmark, VISUAL_PROPERTIES)
    if page is not None:
        set_property(visual_data, "action.page", page, VISUAL_PROPERTIES)
    if url is not None:
        set_property(visual_data, "action.url", url, VISUAL_PROPERTIES)
    if tooltip:
        set_property(visual_data, "action.tooltip", tooltip, VISUAL_PROPERTIES)


@nav_app.command("set-page")
def nav_set_page(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target_page: Annotated[str, typer.Argument(help="Target page name, display name, or index.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to navigate to another page."""
    proj, _pg, vis = resolve_visual_target(project, page, visual)
    try:
        target = proj.find_page(target_page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    _set_action(vis.data, action_type="PageNavigation", page=target.name, tooltip=tooltip)
    vis.save()
    console.print(
        f'Set navigation on "[cyan]{vis.name}[/cyan]" -> page "[cyan]{target.display_name}[/cyan]"'
    )


@nav_app.command("set-bookmark")
def nav_set_bookmark(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    bookmark: Annotated[str, typer.Argument(help="Bookmark name or display name.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to apply a bookmark."""
    from pbi.bookmarks import get_bookmark

    _proj, _pg, vis = resolve_visual_target(project, page, visual)
    try:
        bookmark_data = get_bookmark(_proj, bookmark)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    bookmark_id = bookmark_data.get("name", "")
    bookmark_name = bookmark_data.get("displayName", bookmark)
    if not bookmark_id:
        console.print(f'[red]Error:[/red] Bookmark "{bookmark}" has no internal identifier.')
        raise typer.Exit(1)

    _set_action(vis.data, action_type="Bookmark", bookmark=bookmark_id, tooltip=tooltip)
    vis.save()
    console.print(
        f'Set navigation on "[cyan]{vis.name}[/cyan]" -> bookmark "[cyan]{bookmark_name}[/cyan]"'
    )


@nav_app.command("set-back")
def nav_set_back(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to navigate back."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)
    _set_action(vis.data, action_type="Back", tooltip=tooltip)
    vis.save()
    console.print(f'Set navigation on "[cyan]{vis.name}[/cyan]" -> [cyan]Back[/cyan]')


@nav_app.command("set-url")
def nav_set_url(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    url: Annotated[str, typer.Argument(help="Target URL.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to open a URL."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)
    _set_action(vis.data, action_type="WebUrl", url=url, tooltip=tooltip)
    vis.save()
    console.print(f'Set navigation on "[cyan]{vis.name}[/cyan]" -> [cyan]{url}[/cyan]')


@nav_app.command("clear")
def nav_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's configured action."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)
    changed = _clear_action_state(vis.data)
    if not changed:
        console.print(f'[dim]No change:[/dim] [cyan]{vis.name}[/cyan] has no action configured')
        return
    vis.save()
    console.print(f'Cleared navigation on "[cyan]{vis.name}[/cyan]"')
