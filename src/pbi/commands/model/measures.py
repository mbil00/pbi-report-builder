"""Measure-related semantic-model commands."""

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
    model_measure_app,
    parse_property_assignments,
    resolve_model_expression_input,
)


@model_measure_app.command("list")
def model_measures(
    table_name: Annotated[str | None, typer.Argument(help="Table name (omit to list across all tables).")] = None,
    full: Annotated[bool, typer.Option("--full", help="Show complete expressions without truncation.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List measures in one table or across the whole model."""
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
        for measure in sem_table.measures:
            rows.append(
                {
                    "table": sem_table.name,
                    "name": measure.name,
                    "expression": measure.expression,
                    "format": measure.format_string,
                    "displayFolder": measure.display_folder,
                }
            )

    if not rows:
        if table_name is None:
            console.print("[yellow]No measures found in the model. Use `pbi model measure create` to add one.[/yellow]")
        else:
            console.print(f'[yellow]No measures in "{tables[0].name}". Use `pbi model measure create` to add one.[/yellow]')
        raise typer.Exit(0)

    if as_json:
        import json

        console.print_json(json.dumps(rows, indent=2))
        return

    title = f'Measures in "{tables[0].name}"' if table_name is not None else "Measures"
    table = Table(title=title, box=box.SIMPLE)
    if table_name is None:
        table.add_column("Table", style="dim")
    table.add_column("Measure", style="cyan")
    if full:
        table.add_column("Expression")
    else:
        table.add_column("Expression", max_width=60)
    table.add_column("Format", style="dim")
    table.add_column("Folder", style="dim")

    for row in rows:
        expr_value = row["expression"]
        expr = expr_value if full else (
            expr_value[:57] + "..." if len(expr_value) > 60 else expr_value
        )
        values = [row["name"], expr, row["format"], row["displayFolder"] or ""]
        if table_name is None:
            values.insert(0, row["table"])
        table.add_row(*values)

    console.print(table)


@model_measure_app.command("create")
def model_measure_create(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    measure_name: Annotated[str, typer.Argument(help="Measure name.")],
    expression: Annotated[str | None, typer.Argument(help="DAX expression (omit to read from stdin or use --from-file).")] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the DAX expression from a file.")] = None,
    format_string: Annotated[str | None, typer.Option("--format", help="Optional format string.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a measure in the semantic model."""
    from pbi.model import create_measure

    proj = get_project(project)
    try:
        dax = resolve_model_expression_input(expression, from_file)
        table, name, _changed = create_measure(
            proj.root,
            table_name,
            measure_name,
            dax,
            format_string=format_string,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Created measure [cyan]{table}.{name}[/cyan]')


@model_measure_app.command("edit")
def model_measure_edit(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    measure_name: Annotated[str, typer.Argument(help="Measure name.")],
    expression: Annotated[str | None, typer.Argument(help="New DAX expression (omit to read from stdin or use --from-file).")] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the DAX expression from a file.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Edit an existing measure expression."""
    from pbi.model import edit_measure_expression

    proj = get_project(project)
    try:
        dax = resolve_model_expression_input(expression, from_file)
        table, name, changed = edit_measure_expression(
            proj.root,
            table_name,
            measure_name,
            dax,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Updated measure [cyan]{table}.{name}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] [cyan]{table}.{name}[/cyan] expression is unchanged')


@model_measure_app.command("get")
def model_measure_get(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    measure_name: Annotated[str, typer.Argument(help="Measure name.")],
    project: ProjectOpt = None,
) -> None:
    """Show the full definition of one measure."""
    _, model = get_model(project)
    try:
        sem_table = model.find_table(table_name)
        measure = sem_table.find_measure(measure_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold]{sem_table.name}.{measure.name}[/bold]")
    console.print(f"[dim]Format:[/dim] {measure.format_string or '(none)'}")
    console.print(f"[dim]Description:[/dim] {measure.description or '(none)'}")
    console.print(f"[dim]Display Folder:[/dim] {measure.display_folder or '(none)'}")
    console.print(f"[dim]Lineage:[/dim] {measure.lineage_tag or '(none)'}")
    console.print("[dim]Expression:[/dim]")
    console.print(measure.expression, highlight=False)


@model_measure_app.command("delete")
def model_measure_delete(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    measure_name: Annotated[str, typer.Argument(help="Measure name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a measure from the semantic model."""
    from pbi.model import delete_measure

    if not force:
        confirm = typer.confirm(f'Delete measure "{table_name}.{measure_name}"?')
        if not confirm:
            raise typer.Abort()

    proj = get_project(project)
    try:
        table, name, _changed = delete_measure(
            proj.root,
            table_name,
            measure_name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Deleted measure [cyan]{table}.{name}[/cyan]')


@model_measure_app.command("set")
def model_measure_set(
    field: Annotated[str, typer.Argument(help="Measure reference as Table.Measure.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments as key=value.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set metadata properties on a measure (displayFolder, formatString, etc.)."""
    from pbi.model import set_member_property

    proj = get_project(project)
    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    for prop_name, prop_value in pairs:
        try:
            table_name, field_name, _field_type, changed = set_member_property(
                proj.root,
                field,
                prop_name,
                prop_value,
                dry_run=dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        if changed:
            console.print(
                f'{prefix}[dim]{prop_name}:[/dim] [cyan]{table_name}.{field_name}[/cyan] '
                f'[dim]->[/dim] "{prop_value}"'
            )
        else:
            console.print(
                f'{prefix}[dim]No change:[/dim] [cyan]{table_name}.{field_name}[/cyan] '
                f'{prop_name} is already "{prop_value}"'
            )


@model_measure_app.command("rename")
def model_measure_rename(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    old_name: Annotated[str, typer.Argument(help="Current measure name.")],
    new_name: Annotated[str, typer.Argument(help="New measure name.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Rename a measure and update all DAX references across the model."""
    from pbi.model import rename_measure

    proj = get_project(project)
    try:
        table, old, new, updated_refs = rename_measure(
            proj.root,
            table_name,
            old_name,
            new_name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Renamed [cyan]{table}.{old}[/cyan] [dim]->[/dim] [cyan]{table}.{new}[/cyan]')
    if updated_refs:
        console.print(f"[dim]Updated {len(updated_refs)} reference(s):[/dim]")
        for ref in updated_refs:
            console.print(f"  [dim]{ref}[/dim]")
