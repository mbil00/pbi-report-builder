"""Visual property and geometry mutation commands."""

from __future__ import annotations

from typing import Annotated

import typer

from ..common import ProjectOpt, console, parse_property_assignments
from .app import visual_app
from .helpers import prepare_visual_property_updates, resolve_page_target, resolve_visual_target


@visual_app.command("set")
def visual_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    project: ProjectOpt = None,
    for_measure: Annotated[str | None, typer.Option("--for-measure", help="Target a specific measure queryRef for per-measure formatting.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show what would change without saving.")] = False,
) -> None:
    """Set visual properties."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)

    try:
        pairs = parse_property_assignments(assignments)
        updated, changes = prepare_visual_property_updates(vis.data, pairs, measure_ref=for_measure)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for prop, old, new in changes:
        label = f"{prop} ({for_measure})" if for_measure else prop
        if dry_run:
            console.print(f"Would set {label}: {old} [dim]->[/dim] {new}")
        else:
            console.print(f"[dim]{label}:[/dim] {old} [dim]->[/dim] {new}")

    if dry_run:
        return

    vis.data = updated
    vis.save()


@visual_app.command("set-all")
def visual_set_all(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value ...")],
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Only apply to visuals of this type (e.g. slicer, cardVisual, tableEx).")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show what would change without saving.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set properties on multiple visuals at once."""
    proj, pg = resolve_page_target(project, page)
    visuals = proj.get_visuals(pg)
    if visual_type:
        visuals = [vis for vis in visuals if vis.visual_type == visual_type]
        if not visuals:
            console.print(f'[yellow]No visuals of type "{visual_type}" on page "{pg.display_name}".[/yellow]')
            raise typer.Exit(0)

    visuals = [vis for vis in visuals if "visualGroup" not in vis.data]

    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    prepared: list[tuple[object, dict, list[tuple[str, object, object]]]] = []
    for vis in visuals:
        try:
            updated, changes = prepare_visual_property_updates(vis.data, pairs)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {vis.name}: {e}")
            raise typer.Exit(1)
        prepared.append((vis, updated, changes))

    if dry_run:
        totals: dict[str, int] = {}
        for _vis, _updated, changes in prepared:
            for prop, old, new in changes:
                if old != new:
                    totals[prop] = totals.get(prop, 0) + 1
        if not totals:
            console.print("[dim]No changes would be applied.[/dim]")
            return
        for prop, count in totals.items():
            console.print(f"Would set {prop} on [cyan]{count}[/cyan] visual(s)")
        return

    count_done = 0
    for vis, updated, _changes in prepared:
        vis.data = updated
        vis.save()
        count_done += 1

    scope = f"visual-type={visual_type}" if visual_type else "all"
    props_str = " ".join(f"{prop}={value}" for prop, value in pairs)
    console.print(f'Applied {props_str} to [cyan]{count_done}[/cyan] visuals ({scope})')


@visual_app.command("move")
def visual_move(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    x: Annotated[int, typer.Option("--x", help="X position.")],
    y: Annotated[int, typer.Option("--y", help="Y position.")],
    project: ProjectOpt = None,
) -> None:
    """Move a visual to a new position."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)

    old_x = vis.position.get("x", 0)
    old_y = vis.position.get("y", 0)
    vis.data.setdefault("position", {})["x"] = x
    vis.data["position"]["y"] = y
    vis.save()
    console.print(f"[dim]Moved:[/dim] {old_x},{old_y} [dim]->[/dim] {x},{y}")


@visual_app.command("resize")
def visual_resize(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    width: Annotated[int, typer.Option("-W", "--width", help="Width.")],
    height: Annotated[int, typer.Option("-H", "--height", help="Height.")],
    project: ProjectOpt = None,
) -> None:
    """Resize a visual."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)

    old_w = vis.position.get("width", 0)
    old_h = vis.position.get("height", 0)
    vis.data.setdefault("position", {})["width"] = width
    vis.data["position"]["height"] = height
    vis.save()
    console.print(f"[dim]Resized:[/dim] {old_w}x{old_h} [dim]->[/dim] {width}x{height}")
