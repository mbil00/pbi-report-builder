"""Visual sort commands."""

from __future__ import annotations

from typing import Annotated

import typer

from pbi.visual_builders import apply_initial_sort
from pbi.visual_queries import clear_sort, get_sort

from ..common import ProjectOpt, console
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

    sorts = get_sort(vis)
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
        entity, prop, _resolved_field_type, direction_label = apply_initial_sort(
            proj,
            vis,
            field,
            field_type=field_type,
            descending=direction == "desc",
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"Set sort: [cyan]{entity}.{prop}[/cyan] {direction_label}")


@visual_sort_app.command("clear")
def visual_sort_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's sort definition."""
    proj, _pg, vis = resolve_visual_target(project, page, visual)

    if not get_sort(vis):
        console.print("[dim]No sort definition to clear.[/dim]")
        return

    if not force:
        confirm = typer.confirm(f'Clear sort definition from "{vis.name}"?')
        if not confirm:
            raise typer.Abort()

    clear_sort(vis)
    console.print("Cleared sort definition.")
