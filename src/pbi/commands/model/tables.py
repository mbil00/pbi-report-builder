"""Table-related semantic-model commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .base import (
    ProjectOpt,
    console,
    get_model,
    get_project,
    model_table_app,
    parse_property_assignments,
    resolve_model_expression_input,
)


@model_table_app.command("list")
def model_tables(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List tables in the semantic model."""
    _, model = get_model(project)

    if as_json:
        import json

        rows = [{
            "name": table.name,
            "columns": len(table.columns),
            "measures": len(table.measures),
            "dataCategory": table.data_category,
            "dateTable": table.date_table_column,
        } for table in model.tables]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title="Semantic Model Tables", box=box.SIMPLE)
    table.add_column("Table", style="cyan")
    table.add_column("Columns", justify="right")
    table.add_column("Measures", justify="right")
    table.add_column("Date Table")
    table.add_column("Category", style="dim")

    for sem_table in model.tables:
        table.add_row(
            sem_table.name,
            str(len(sem_table.columns)),
            str(len(sem_table.measures)),
            sem_table.date_table_column or "",
            sem_table.data_category or "",
        )

    console.print(table)


@model_table_app.command("get")
def model_table_get(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    project: ProjectOpt = None,
) -> None:
    """Show metadata for one semantic-model table."""
    _, model = get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold]{sem_table.name}[/bold]")
    console.print(f"[dim]Columns:[/dim] {len(sem_table.columns)}")
    console.print(f"[dim]Measures:[/dim] {len(sem_table.measures)}")
    console.print(f"[dim]Data Category:[/dim] {sem_table.data_category or '(none)'}")
    console.print(f"[dim]Date Table:[/dim] {'yes' if sem_table.date_table_column else 'no'}")
    console.print(f"[dim]Date Column:[/dim] {sem_table.date_table_column or '(none)'}")


@model_table_app.command("set")
def model_table_set(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments as key=value.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set table metadata such as dataCategory or dateTable=<column>."""
    from pbi.model import mark_as_date_table, set_table_property

    proj = get_project(project)
    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    for prop_name, prop_value in pairs:
        try:
            if prop_name == "dateTable":
                table, column, changed = mark_as_date_table(
                    proj.root,
                    table_name,
                    prop_value,
                    dry_run=dry_run,
                )
                if changed:
                    console.print(
                        f"{prefix}[dim]dateTable:[/dim] [cyan]{table}[/cyan] [dim]->[/dim] [cyan]{column}[/cyan]"
                    )
                else:
                    console.print(
                        f"{prefix}[dim]No change:[/dim] [cyan]{table}[/cyan] is already marked as a date table using [cyan]{column}[/cyan]"
                    )
                continue

            table, changed = set_table_property(
                proj.root,
                table_name,
                prop_name,
                prop_value,
                dry_run=dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        if changed:
            console.print(
                f'{prefix}[dim]{prop_name}:[/dim] [cyan]{table}[/cyan] [dim]->[/dim] "{prop_value}"'
            )
        else:
            console.print(
                f'{prefix}[dim]No change:[/dim] [cyan]{table}[/cyan] {prop_name} is already "{prop_value}"'
            )


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


@model_table_app.command("rename")
def model_table_rename(
    old_name: Annotated[str, typer.Argument(help="Current table name.")],
    new_name: Annotated[str, typer.Argument(help="New table name.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Rename a table and cascade through model/report references."""
    from pbi.model import rename_table

    proj = get_project(project)
    try:
        old, new, updated_refs = rename_table(
            proj.root,
            old_name,
            new_name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Renamed table [cyan]{old}[/cyan] [dim]->[/dim] [cyan]{new}[/cyan]')
    if updated_refs:
        console.print(f"[dim]Updated {len(updated_refs)} reference(s):[/dim]")
        for ref in updated_refs:
            console.print(f"  [dim]{ref}[/dim]")
