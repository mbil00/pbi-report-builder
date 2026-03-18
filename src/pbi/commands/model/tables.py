"""Table-related semantic-model commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .base import ProjectOpt, console, get_model, get_project, model_table_app, resolve_model_expression_input


@model_table_app.command("list")
def model_tables(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List tables in the semantic model."""
    _, model = get_model(project)

    if as_json:
        import json

        rows = [{"name": table.name, "columns": len(table.columns), "measures": len(table.measures)} for table in model.tables]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title="Semantic Model Tables", box=box.SIMPLE)
    table.add_column("Table", style="cyan")
    table.add_column("Columns", justify="right")
    table.add_column("Measures", justify="right")

    for sem_table in model.tables:
        table.add_row(sem_table.name, str(len(sem_table.columns)), str(len(sem_table.measures)))

    console.print(table)


@model_table_app.command("create")
def model_table_create(
    table_name: Annotated[str, typer.Argument(help="New table name.")],
    expression: Annotated[str | None, typer.Argument(help="DAX expression (omit to read from stdin or use --from-file).")] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the DAX expression from a file.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a calculated table with a DAX expression."""
    from pbi.model import create_calculated_table

    proj = get_project(project)
    try:
        dax = resolve_model_expression_input(expression, from_file)
        name, _path, _created = create_calculated_table(
            proj.root,
            table_name,
            dax,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Created calculated table [cyan]{name}[/cyan]')
