"""Theme CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project, resolve_output_path

theme_app = typer.Typer(help="Theme operations.", no_args_is_help=True)


@theme_app.command("list")
def theme_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List active themes (base + custom)."""
    from pbi.themes import get_themes

    proj = get_project(project)
    themes = get_themes(proj)

    if not themes:
        console.print("[yellow]No themes configured.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        rows = [{"type": "custom" if t.is_custom else "base", "name": t.name, "source": t.source} for t in themes]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Source")
    for theme in themes:
        label = "custom" if theme.is_custom else "base"
        table.add_row(label, theme.name, theme.source)
    console.print(table)


@theme_app.command("apply")
def theme_apply(
    theme_file: Annotated[str, typer.Argument(help="Path to theme JSON file.")],
    project: ProjectOpt = None,
) -> None:
    """Apply a custom theme JSON file to the project."""
    import json

    from pbi.themes import apply_theme

    proj = get_project(project)
    path = Path(theme_file).resolve()
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        raise typer.Exit(1)

    try:
        name = apply_theme(proj, path)
    except (json.JSONDecodeError, ValueError) as e:
        console.print(f"[red]Error:[/red] Invalid theme file: {e}")
        raise typer.Exit(1)

    console.print(f'Applied theme "[cyan]{name}[/cyan]"')


@theme_app.command("export")
def theme_export(
    output: Annotated[str, typer.Argument(help="Output path for the theme JSON file.")],
    project: ProjectOpt = None,
) -> None:
    """Export the active custom theme to a standalone JSON file."""
    from pbi.themes import export_theme

    proj = get_project(project)
    out_path = resolve_output_path(Path(output), base_dir=Path.cwd())

    try:
        name = export_theme(proj, out_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f'Exported theme "[cyan]{name}[/cyan]" -> {out_path}')


@theme_app.command("delete")
def theme_delete(
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Remove the custom theme from the project (reverts to base theme)."""
    from pbi.themes import remove_theme

    proj = get_project(project)

    if not force:
        confirm = typer.confirm("Delete the custom theme?")
        if not confirm:
            raise typer.Abort()

    try:
        name = remove_theme(proj)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if name:
        console.print(f'Deleted custom theme "[cyan]{name}[/cyan]"')
    else:
        console.print("[yellow]No custom theme to remove.[/yellow]")


@theme_app.command("migrate")
def theme_migrate(
    old_theme: Annotated[str, typer.Argument(help="Path to old theme JSON file.")],
    new_theme: Annotated[str, typer.Argument(help="Path to new theme JSON file.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change without modifying files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Migrate visual property overrides from old theme colors to new theme colors.

    Compares the two theme JSONs to build a color mapping, then scans all
    visuals for per-visual property overrides that match old colors and
    replaces them with the corresponding new colors.
    """
    from pbi.themes import migrate_theme

    proj = get_project(project)
    old_path = Path(old_theme).resolve()
    new_path = Path(new_theme).resolve()

    for label, path in [("Old theme", old_path), ("New theme", new_path)]:
        if not path.exists():
            console.print(f"[red]Error:[/red] {label} not found: {path}")
            raise typer.Exit(1)

    result = migrate_theme(proj, old_path, new_path, dry_run=dry_run)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    if not result.replacements and not result.page_background_changes:
        console.print("[dim]No color differences found between themes.[/dim]")
        return

    for repl in result.replacements:
        if repl.count > 0:
            verb = "Would update" if dry_run else "Updated"
            console.print(
                f"{prefix}{verb} [cyan]{repl.old_color}[/cyan] [dim]->[/dim] "
                f"[cyan]{repl.new_color}[/cyan] on {repl.count} visual(s)"
            )

    if result.page_background_changes:
        verb = "Would update" if dry_run else "Updated"
        console.print(
            f"{prefix}{verb} background.color on "
            f"[cyan]{result.page_background_changes}[/cyan] page(s)"
        )

    if not result.total_changes:
        console.print("[dim]No matching color overrides found in visuals.[/dim]")
