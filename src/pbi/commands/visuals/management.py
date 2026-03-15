"""Visual lifecycle and grouping commands."""

from __future__ import annotations

from typing import Annotated

import typer

from ..common import ProjectOpt, console, get_project
from .app import visual_app
from .helpers import resolve_visual_target


@visual_app.command("create")
def visual_create(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual_type: Annotated[str, typer.Argument(help="Visual type (e.g. clusteredColumnChart, card, table, slicer).")],
    x: Annotated[int, typer.Option(help="X position.")] = 0,
    y: Annotated[int, typer.Option(help="Y position.")] = 0,
    width: Annotated[int, typer.Option("-W", "--width", help="Width.")] = 300,
    height: Annotated[int, typer.Option("-H", "--height", help="Height.")] = 200,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Friendly name for the visual.")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Set title text (also enables title.show).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Create a new visual on a page."""
    from pbi.roles import get_visual_roles, is_known_visual_type, normalize_visual_type

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    canonical_visual_type = normalize_visual_type(visual_type)
    if visual_type != canonical_visual_type:
        console.print(
            f'[dim]Using canonical visual type [cyan]{canonical_visual_type}[/cyan] '
            f'for alias "{visual_type}".[/dim]'
        )
    elif not is_known_visual_type(visual_type):
        console.print(
            f'[yellow]Warning:[/yellow] "{visual_type}" is not in the CLI visual catalog. '
            "Creating a raw visual container."
        )

    vis = proj.create_visual(pg, canonical_visual_type, x=x, y=y, width=width, height=height)
    if name:
        vis.data["name"] = name

    if title:
        from pbi.properties import VISUAL_PROPERTIES, set_property

        set_property(vis.data, "title.show", "true", VISUAL_PROPERTIES)
        set_property(vis.data, "title.text", title, VISUAL_PROPERTIES)

    if name or title:
        vis.save()

    display = name or vis.name
    console.print(
        f'Created [cyan]{canonical_visual_type}[/cyan] "{display}" on "{pg.display_name}" '
        f"@ {x},{y} {width}x{height}"
    )

    # Show scaffolded roles so the agent knows what to bind
    roles = get_visual_roles(canonical_visual_type)
    if roles:
        role_names = [r["name"] + (" (multi)" if r["multi"] else "") for r in roles]
        console.print(f'[dim]Roles: {", ".join(role_names)}[/dim]')


@visual_app.command("copy")
def visual_copy(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Source visual name, type, or index.")],
    to_page: Annotated[str | None, typer.Option("--to-page", help="Target page (default: same page).")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Name for the copy.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Copy/duplicate a visual, optionally to a different page."""
    proj, pg, vis = resolve_visual_target(project, page, visual)
    try:
        target = proj.find_page(to_page) if to_page else pg
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    new_vis = proj.copy_visual(vis, target, new_name=name)
    dest = f' to "{target.display_name}"' if to_page else ""
    console.print(f'Copied [cyan]{vis.visual_type}[/cyan] "{vis.name}"{dest} -> "{new_vis.name}"')


@visual_app.command("rename")
def visual_rename(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    name: Annotated[str, typer.Argument(help="New friendly name for the visual.")],
    project: ProjectOpt = None,
) -> None:
    """Give a visual a friendly name for easier CLI reference."""
    _proj, _pg, vis = resolve_visual_target(project, page, visual)

    old_name = vis.name
    vis.data["name"] = name
    vis.save()
    console.print(f'Renamed "{old_name}" -> "[cyan]{name}[/cyan]"')


@visual_app.command("delete")
def visual_delete(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a visual."""
    proj, _pg, vis = resolve_visual_target(project, page, visual)

    if not force:
        confirm = typer.confirm(f'Delete {vis.visual_type} "{vis.name}"?')
        if not confirm:
            raise typer.Abort()

    proj.delete_visual(vis)
    console.print(f'Deleted [cyan]{vis.visual_type}[/cyan] "{vis.name}"')


@visual_app.command("group")
def visual_group(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to group (at least 2).")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Group display name.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Group visuals together into a visual group."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis_list = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        group = proj.create_group(pg, vis_list, display_name=name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    names = ", ".join(f'"{vis.name}"' for vis in vis_list)
    console.print(f'Grouped {names} -> "[cyan]{group.name}[/cyan]"')


@visual_app.command("ungroup")
def visual_ungroup(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    group: Annotated[str, typer.Argument(help="Group name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Ungroup a visual group, freeing its children."""
    proj, pg, grp = resolve_visual_target(project, page, group)

    try:
        children = proj.ungroup(pg, grp)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    names = ", ".join(f'"{child.name}"' for child in children)
    console.print(f'Ungrouped "[cyan]{grp.name}[/cyan]": freed {names or "no children"}')
