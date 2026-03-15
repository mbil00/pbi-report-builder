"""Visual sort commands."""

from __future__ import annotations

from typing import Annotated

import typer

from ..common import ProjectOpt, console, resolve_field_type
from .app import visual_sort_app
from .helpers import resolve_visual_target


@visual_sort_app.command("get")
def visual_sort_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show a visual's sort definition."""
    proj, _pg, vis = resolve_visual_target(project, page, visual)

    sorts = proj.get_sort(vis)
    if not sorts:
        console.print("[dim]No sort definition.[/dim]")
        return
    for entity, prop, ftype, direction in sorts:
        kind = " (measure)" if ftype == "measure" else ""
        console.print(f"[cyan]{entity}.{prop}[/cyan]{kind} {direction}")


@visual_sort_app.command("set")
def visual_sort_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    field: Annotated[str, typer.Argument(help="Sort field as Table.Field.")],
    direction: Annotated[str, typer.Option("--direction", help="Sort direction: asc or desc.")] = "desc",
    field_type: Annotated[str, typer.Option("--field-type", help="Field type: auto, column, or measure.")] = "auto",
    project: ProjectOpt = None,
) -> None:
    """Set a visual's sort definition."""
    proj, _pg, vis = resolve_visual_target(project, page, visual)

    if direction not in {"asc", "desc"}:
        console.print("[red]Error:[/red] --direction must be 'asc' or 'desc'.")
        raise typer.Exit(1)

    try:
        entity, prop, resolved_field_type = resolve_field_type(proj, field, field_type)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    descending = direction == "desc"
    proj.set_sort(vis, entity, prop, field_type=resolved_field_type, descending=descending)
    console.print(f'Sort set: [cyan]{entity}.{prop}[/cyan] {"Descending" if descending else "Ascending"}')


@visual_sort_app.command("clear")
def visual_sort_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's sort definition."""
    proj, _pg, vis = resolve_visual_target(project, page, visual)

    if proj.clear_sort(vis):
        console.print("Sort definition removed.")
    else:
        console.print("[dim]No sort definition to remove.[/dim]")
