"""Visual interaction CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project

interaction_app = typer.Typer(help="Visual interaction operations.", no_args_is_help=True)


@interaction_app.command("list")
def interaction_list(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List visual interactions on a page."""
    from pbi.interactions import get_interactions

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    interactions = get_interactions(pg)
    if not interactions:
        console.print("[yellow]No custom interactions (all using default behavior).[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        console.print_json(json.dumps(interactions, indent=2))
        return

    table = Table(title=f'Interactions on "{pg.display_name}"', box=box.SIMPLE)
    table.add_column("Source", style="cyan")
    table.add_column("Target", style="cyan")
    table.add_column("Type")

    for entry in interactions:
        table.add_row(entry.get("source", ""), entry.get("target", ""), entry.get("type", ""))

    console.print(table)


@interaction_app.command("set")
def interaction_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    source: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target: Annotated[str, typer.Argument(help="Target visual name or index.")],
    mode: Annotated[str, typer.Option("--mode", help="Interaction mode: DataFilter, HighlightFilter, or NoFilter.")],
    project: ProjectOpt = None,
) -> None:
    """Set interaction between two visuals."""
    from pbi.interactions import set_interaction

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        src_vis = proj.find_visual(pg, source)
        tgt_vis = proj.find_visual(pg, target)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if mode not in {"DataFilter", "HighlightFilter", "NoFilter"}:
        console.print("[red]Error:[/red] --mode must be DataFilter, HighlightFilter, or NoFilter.")
        raise typer.Exit(1)

    try:
        set_interaction(pg, src_vis.name, tgt_vis.name, mode)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    pg.save()
    console.print(
        f'Set interaction: [cyan]{src_vis.name}[/cyan] -> '
        f'[cyan]{tgt_vis.name}[/cyan] = [bold]{mode}[/bold]'
    )


@interaction_app.command("clear")
def interaction_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    source: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target: Annotated[str | None, typer.Argument(help="Target visual (omit to remove all from source).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Remove custom interactions from a visual."""
    from pbi.interactions import remove_interaction

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        src_vis = proj.find_visual(pg, source)
        tgt_vis = proj.find_visual(pg, target) if target else None
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    removed = remove_interaction(pg, src_vis.name, tgt_vis.name if tgt_vis else None)
    if removed:
        pg.save()
        scope = f'-> "{tgt_vis.name}"' if tgt_vis else "(all targets)"
        console.print(f'Removed {removed} interaction(s) from [cyan]{src_vis.name}[/cyan] {scope}')
    else:
        console.print("[yellow]No matching interactions found.[/yellow]")
