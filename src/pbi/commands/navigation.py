"""First-class navigation and action wiring commands."""

from __future__ import annotations

import copy
import json
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from pbi.properties import VISUAL_PROPERTIES, get_property, set_property

from .common import ProjectOpt, console
from .visuals.helpers import resolve_visual_target

nav_app = typer.Typer(help="Navigation and button action operations.", no_args_is_help=True)
nav_action_app = typer.Typer(help="Inspect or clear the current visual action.", no_args_is_help=True)
nav_page_app = typer.Typer(help="Set page navigation actions.", no_args_is_help=True)
nav_bookmark_app = typer.Typer(help="Set bookmark actions.", no_args_is_help=True)
nav_back_app = typer.Typer(help="Set back actions.", no_args_is_help=True)
nav_url_app = typer.Typer(help="Set URL actions.", no_args_is_help=True)
nav_drillthrough_app = typer.Typer(help="Set drillthrough actions.", no_args_is_help=True)
nav_tooltip_app = typer.Typer(help="Inspect or manage report-page tooltips.", no_args_is_help=True)
nav_app.add_typer(nav_action_app, name="action")
nav_app.add_typer(nav_page_app, name="page")
nav_app.add_typer(nav_bookmark_app, name="bookmark")
nav_app.add_typer(nav_back_app, name="back")
nav_app.add_typer(nav_url_app, name="url")
nav_app.add_typer(nav_drillthrough_app, name="drillthrough")
nav_app.add_typer(nav_tooltip_app, name="tooltip")


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
    drillthrough: str | None = None,
    url: str | None = None,
) -> None:
    _clear_action_state(visual_data)
    set_property(visual_data, "action.show", "true", VISUAL_PROPERTIES)
    set_property(visual_data, "action.type", action_type, VISUAL_PROPERTIES)
    if bookmark is not None:
        set_property(visual_data, "action.bookmark", bookmark, VISUAL_PROPERTIES)
    if page is not None:
        set_property(visual_data, "action.page", page, VISUAL_PROPERTIES)
    if drillthrough is not None:
        set_property(visual_data, "action.drillthrough", drillthrough, VISUAL_PROPERTIES)
    if url is not None:
        set_property(visual_data, "action.url", url, VISUAL_PROPERTIES)
    if tooltip:
        set_property(visual_data, "action.tooltip", tooltip, VISUAL_PROPERTIES)


def _get_visual_tooltip_entry(visual_data: dict, *, create: bool) -> tuple[dict | None, dict | None]:
    visual = visual_data.setdefault("visual", {}) if create else visual_data.get("visual")
    if not isinstance(visual, dict):
        return None, None
    container_objects = visual.setdefault("visualContainerObjects", {}) if create else visual.get("visualContainerObjects")
    if not isinstance(container_objects, dict):
        return None, None
    entries = container_objects.setdefault("visualTooltip", [{}]) if create else container_objects.get("visualTooltip")
    if not isinstance(entries, list):
        return container_objects, None
    if create and not entries:
        entries.append({})
    if not entries or not isinstance(entries[0], dict):
        return container_objects, None
    properties = entries[0].setdefault("properties", {}) if create else entries[0].get("properties")
    if create and not isinstance(properties, dict):
        entries[0]["properties"] = {}
        properties = entries[0]["properties"]
    return container_objects, properties if isinstance(properties, dict) else None


def _set_report_page_tooltip(visual_data: dict, page_name: str) -> None:
    set_property(visual_data, "tooltip.show", "true", VISUAL_PROPERTIES)
    set_property(visual_data, "tooltip.type", "ReportPage", VISUAL_PROPERTIES)
    set_property(visual_data, "tooltip.section", page_name, VISUAL_PROPERTIES)


def _clear_report_page_tooltip(visual_data: dict) -> bool:
    container_objects, properties = _get_visual_tooltip_entry(visual_data, create=False)
    if container_objects is None or properties is None:
        return False
    changed = False
    for key in ("section", "type", "show"):
        if key in properties:
            properties.pop(key, None)
            changed = True
    entries = container_objects.get("visualTooltip")
    if isinstance(entries, list) and entries and isinstance(entries[0], dict):
        if not entries[0].get("properties"):
            container_objects.pop("visualTooltip", None)
            changed = True
    visual = visual_data.get("visual", {})
    if isinstance(visual, dict):
        visual_container_objects = visual.get("visualContainerObjects", {})
        if isinstance(visual_container_objects, dict) and not visual_container_objects:
            visual.pop("visualContainerObjects", None)
    return changed


def _read_action_state(visual_data: dict) -> dict | None:
    action_type = get_property(visual_data, "action.type", VISUAL_PROPERTIES)
    if not action_type:
        return None
    state = {"type": action_type}
    for key in ("page", "bookmark", "drillthrough", "url", "tooltip"):
        value = get_property(visual_data, f"action.{key}", VISUAL_PROPERTIES)
        if value is not None:
            state[key] = value
    return state


def _read_report_page_tooltip_state(visual_data: dict) -> dict | None:
    tooltip_type = get_property(visual_data, "tooltip.type", VISUAL_PROPERTIES)
    tooltip_section = get_property(visual_data, "tooltip.section", VISUAL_PROPERTIES)
    tooltip_show = get_property(visual_data, "tooltip.show", VISUAL_PROPERTIES)
    if tooltip_type is None and tooltip_section is None and tooltip_show is None:
        return None
    state: dict[str, object] = {}
    if tooltip_show is not None:
        state["show"] = tooltip_show
    if tooltip_type is not None:
        state["type"] = tooltip_type
    if tooltip_section is not None:
        state["section"] = tooltip_section
    return state


def _print_state_table(title: str, rows: list[tuple[str, object]]) -> None:
    table = Table(title=title, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    for key, value in rows:
        table.add_row(key, "" if value is None else str(value))
    console.print(table)


def _nav_set_page(
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


def _nav_set_bookmark(
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


def _nav_set_back(
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


def _nav_set_url(
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


def _nav_set_drillthrough(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target_page: Annotated[str, typer.Argument(help="Target drillthrough page name, display name, or index.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to drill through to a drillthrough page."""
    from pbi.drillthrough import is_drillthrough

    proj, _pg, vis = resolve_visual_target(project, page, visual)
    try:
        target = proj.find_page(target_page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if not is_drillthrough(target):
        console.print(f'[red]Error:[/red] Page "{target.display_name}" is not configured as drillthrough.')
        raise typer.Exit(1)

    _set_action(vis.data, action_type="Drillthrough", drillthrough=target.name, tooltip=tooltip)
    vis.save()
    console.print(
        f'Set navigation on "[cyan]{vis.name}[/cyan]" -> drillthrough "[cyan]{target.display_name}[/cyan]"'
    )


def _nav_set_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target_page: Annotated[str, typer.Argument(help="Target tooltip page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Set a visual to use a report-page tooltip."""
    from pbi.drillthrough import is_tooltip_page

    proj, _pg, vis = resolve_visual_target(project, page, visual)
    try:
        target = proj.find_page(target_page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if not is_tooltip_page(target):
        console.print(f'[red]Error:[/red] Page "{target.display_name}" is not configured as a tooltip page.')
        raise typer.Exit(1)

    _set_report_page_tooltip(vis.data, target.name)
    vis.save()
    console.print(
        f'Set tooltip on "[cyan]{vis.name}[/cyan]" -> page "[cyan]{target.display_name}[/cyan]"'
    )


def _nav_clear_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's configured report-page tooltip."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)
    preview = copy.deepcopy(vis.data)
    changed = _clear_report_page_tooltip(preview)
    if not changed:
        console.print(f'[dim]No change:[/dim] [cyan]{vis.name}[/cyan] has no report-page tooltip configured')
        return
    if not force:
        confirm = typer.confirm(f'Clear tooltip on "{vis.name}"?')
        if not confirm:
            raise typer.Abort()
    _clear_report_page_tooltip(vis.data)
    vis.save()
    console.print(f'Cleared tooltip on "[cyan]{vis.name}[/cyan]"')


def _nav_clear_action(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's configured action."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)
    preview = copy.deepcopy(vis.data)
    changed = _clear_action_state(preview)
    if not changed:
        console.print(f'[dim]No change:[/dim] [cyan]{vis.name}[/cyan] has no action configured')
        return
    if not force:
        confirm = typer.confirm(f'Clear navigation on "{vis.name}"?')
        if not confirm:
            raise typer.Abort()
    _clear_action_state(vis.data)
    vis.save()
    console.print(f'Cleared navigation on "[cyan]{vis.name}[/cyan]"')


@nav_action_app.command("get")
def nav_action_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show the current action configured on a visual."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)
    state = _read_action_state(vis.data)
    if state is None:
        console.print(f'[yellow]No action configured on "[cyan]{vis.name}[/cyan]".[/yellow]')
        raise typer.Exit(0)
    if raw:
        console.print_json(json.dumps(state, indent=2))
        return
    rows = [("Type", state.get("type"))]
    for key in ("page", "bookmark", "drillthrough", "url", "tooltip"):
        if key in state:
            rows.append((key.capitalize(), state[key]))
    _print_state_table(vis.name, rows)


@nav_action_app.command("clear")
def nav_action_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's configured action."""
    _nav_clear_action(page, visual, force, project)


@nav_page_app.command("set")
def nav_page_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target_page: Annotated[str, typer.Argument(help="Target page name, display name, or index.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to navigate to another page."""
    _nav_set_page(page, visual, target_page, tooltip, project)


@nav_bookmark_app.command("set")
def nav_bookmark_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    bookmark: Annotated[str, typer.Argument(help="Bookmark name or display name.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to apply a bookmark."""
    _nav_set_bookmark(page, visual, bookmark, tooltip, project)


@nav_back_app.command("set")
def nav_back_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to navigate back."""
    _nav_set_back(page, visual, tooltip, project)


@nav_url_app.command("set")
def nav_url_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    url: Annotated[str, typer.Argument(help="Target URL.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to open a URL."""
    _nav_set_url(page, visual, url, tooltip, project)


@nav_drillthrough_app.command("set")
def nav_drillthrough_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target_page: Annotated[str, typer.Argument(help="Target drillthrough page name, display name, or index.")],
    tooltip: Annotated[str | None, typer.Option("--tooltip", help="Optional button tooltip.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set a visual action to drill through to a drillthrough page."""
    _nav_set_drillthrough(page, visual, target_page, tooltip, project)


@nav_tooltip_app.command("get")
def nav_tooltip_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show the current report-page tooltip configured on a visual."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)
    state = _read_report_page_tooltip_state(vis.data)
    if state is None:
        console.print(f'[yellow]No tooltip configured on "[cyan]{vis.name}[/cyan]".[/yellow]')
        raise typer.Exit(0)
    if raw:
        console.print_json(json.dumps(state, indent=2))
        return
    rows = []
    for key in ("show", "type", "section"):
        if key in state:
            rows.append((key.capitalize(), state[key]))
    _print_state_table(vis.name, rows)


@nav_tooltip_app.command("set")
def nav_tooltip_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target_page: Annotated[str, typer.Argument(help="Target tooltip page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Set a visual to use a report-page tooltip."""
    _nav_set_tooltip(page, visual, target_page, project)


@nav_tooltip_app.command("clear")
def nav_tooltip_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index containing the source visual.")],
    visual: Annotated[str, typer.Argument(help="Source visual name or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's configured report-page tooltip."""
    _nav_clear_tooltip(page, visual, force, project)

