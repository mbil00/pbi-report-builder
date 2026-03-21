"""Hierarchy-related semantic-model commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .base import ProjectOpt, console, get_model, get_project, model_hierarchy_app


@model_hierarchy_app.command("create")
def model_hierarchy_create(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    hierarchy_name: Annotated[str, typer.Argument(help="Hierarchy name.")],
    columns: Annotated[list[str], typer.Argument(help="Level columns in order (top to bottom).")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a hierarchy from ordered columns."""
    from pbi.model import create_hierarchy

    proj = get_project(project)
    try:
        table, name, _created = create_hierarchy(
            proj.root,
            table_name,
            hierarchy_name,
            columns,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Created hierarchy [cyan]{table}.{name}[/cyan] ({len(columns)} levels)')


@model_hierarchy_app.command("list")
def model_hierarchy_list(
    table_name: Annotated[str | None, typer.Argument(help="Table name (omit to list across all tables).")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List hierarchies in one table or across the whole model."""
    _, model = get_model(project)
    tables = model.tables
    if table_name is not None:
        try:
            tables = [model.find_table(table_name)]
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    rows = []
    for sem_table in tables:
        for hierarchy in sem_table.hierarchies:
            rows.append(
                {
                    "table": sem_table.name,
                    "name": hierarchy.name,
                    "levels": [{"name": level.name, "column": level.column} for level in hierarchy.levels],
                }
            )

    if not rows:
        if table_name is None:
            console.print("[yellow]No hierarchies found in the model. Use `pbi model hierarchy create` to add one.[/yellow]")
        else:
            console.print(f'[yellow]No hierarchies in "{tables[0].name}". Use `pbi model hierarchy create` to add one.[/yellow]')
        raise typer.Exit(0)

    if as_json:
        import json

        console.print_json(json.dumps(rows, indent=2))
        return

    title = f'Hierarchies in "{tables[0].name}"' if table_name is not None else "Hierarchies"
    table = Table(title=title, box=box.SIMPLE)
    if table_name is None:
        table.add_column("Table", style="dim")
    table.add_column("Hierarchy", style="cyan")
    table.add_column("Levels", style="dim")

    for row in rows:
        levels_str = " > ".join(level["column"] for level in row["levels"])
        values = [row["name"], levels_str]
        if table_name is None:
            values.insert(0, row["table"])
        table.add_row(*values)
    console.print(table)


@model_hierarchy_app.command("delete")
def model_hierarchy_delete(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    hierarchy_name: Annotated[str, typer.Argument(help="Hierarchy name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a hierarchy from a table."""
    from pbi.model import delete_hierarchy

    if not force:
        confirm = typer.confirm(f'Delete hierarchy "{table_name}.{hierarchy_name}"?')
        if not confirm:
            raise typer.Abort()

    proj = get_project(project)
    try:
        table, name, _deleted = delete_hierarchy(
            proj.root,
            table_name,
            hierarchy_name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Deleted hierarchy [cyan]{table}.{name}[/cyan]')
