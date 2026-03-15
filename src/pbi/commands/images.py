"""Image resource management commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project

image_app = typer.Typer(help="Image resource operations.", no_args_is_help=True)


@image_app.command("add")
def image_add(
    image_path: Annotated[str, typer.Argument(help="Path to the image file to register.")],
    project: ProjectOpt = None,
) -> None:
    """Register an image file in the project's resources."""
    from pbi.images import add_image

    proj = get_project(project)
    source = Path(image_path)
    if not source.is_absolute():
        source = Path.cwd() / source

    try:
        registered_name = add_image(proj, source)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f'Registered [cyan]{source.name}[/cyan] [dim]->[/dim] RegisteredResources/{registered_name}')


@image_app.command("list")
def image_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List registered image resources."""
    from pbi.images import list_images

    proj = get_project(project)
    images = list_images(proj)

    if not images:
        console.print("[yellow]No registered images. Use `pbi image add` to register one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json
        rows = [
            {
                "name": img.name,
                "size": img.size,
                "references": len(img.referenced_by),
                "referencedBy": img.referenced_by,
            }
            for img in images
        ]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Size", style="dim", justify="right")
    table.add_column("References", justify="right")

    for img in images:
        size_str = _format_size(img.size)
        table.add_row(img.name, size_str, str(len(img.referenced_by)))

    console.print(table)


@image_app.command("prune")
def image_prune(
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Remove unreferenced image resources."""
    from pbi.images import list_images, prune_images

    proj = get_project(project)
    images = list_images(proj)
    unreferenced = [img for img in images if not img.referenced_by]

    if not unreferenced:
        console.print("[dim]No unreferenced images to remove.[/dim]")
        return

    if not force:
        for img in unreferenced:
            console.print(f"  [cyan]{img.name}[/cyan] [dim]({_format_size(img.size)})[/dim]")
        confirm = typer.confirm(f"Remove {len(unreferenced)} unreferenced image(s)?")
        if not confirm:
            raise typer.Abort()

    removed = prune_images(proj)
    total_size = sum(img.size for img in unreferenced)
    console.print(f"Removed {len(removed)} unreferenced image(s) [dim](saved {_format_size(total_size)})[/dim]")


def _format_size(size: int) -> str:
    """Format bytes as human-readable."""
    if size < 1024:
        return f"{size}B"
    if size < 1024 * 1024:
        return f"{size // 1024}KB"
    return f"{size // (1024 * 1024)}MB"
