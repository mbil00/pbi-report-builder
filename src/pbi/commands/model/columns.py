"""Column-related semantic-model commands."""

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
    model_column_app,
    parse_property_assignments,
    resolve_model_expression_input,
)


@model_column_app.command("list")
def model_columns(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    show_hidden: Annotated[bool, typer.Option("--hidden", help="Include hidden columns in the listing.")] = False,
    hidden_only: Annotated[bool, typer.Option("--hidden-only", help="Only show hidden columns.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List columns (dimensions) in a table."""
    if show_hidden and hidden_only:
        console.print("[red]Error:[/red] Use either --hidden or --hidden-only, not both.")
        raise typer.Exit(1)

    _, model = get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    columns = sem_table.columns
    if hidden_only:
        columns = [column for column in columns if column.is_hidden]
    elif not show_hidden:
        columns = [column for column in columns if not column.is_hidden]

    if as_json:
        import json

        rows = [
            {
                "name": column.name,
                "kind": column.kind,
                "dataType": column.data_type,
                "format": column.format_string,
                "hidden": column.is_hidden,
                "sourceColumn": column.source_column,
            }
            for column in columns
        ]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title=f'Columns in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Column", style="cyan")
    table.add_column("Kind", style="dim")
    table.add_column("Data Type", style="dim")
    table.add_column("Format", style="dim")
    table.add_column("Hidden", style="dim", justify="center")
    table.add_column("Source Column", style="dim")

    for column in columns:
        kind_label = "calculated" if column.kind == "calculatedColumn" else ""
        table.add_row(
            column.name,
            kind_label,
            column.data_type,
            column.format_string,
            "yes" if column.is_hidden else "",
            column.source_column,
        )

    console.print(table)
    hidden_count = len(sem_table.columns) - len(columns)
    if hidden_count and not hidden_only:
        console.print(f"[dim]({hidden_count} hidden columns, use --hidden to show)[/dim]")


@model_column_app.command("hide")
def model_column_hide(
    fields: Annotated[list[str] | None, typer.Argument(help="Column references as Table.Column.")] = None,
    table_name: Annotated[str | None, typer.Option("--table", help="Target table (use with --pattern).")] = None,
    pattern: Annotated[str | None, typer.Option("--pattern", help="Regex pattern to match column names.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Hide one or more columns in the semantic model."""
    if table_name and pattern:
        _model_set_column_visibility_by_pattern(
            table_name,
            pattern,
            hidden=True,
            dry_run=dry_run,
            project=project,
        )
    elif fields:
        _model_set_column_visibility(fields, hidden=True, dry_run=dry_run, project=project)
    else:
        console.print("[red]Error:[/red] Provide column references or use --table with --pattern.")
        raise typer.Exit(1)


@model_column_app.command("create")
def model_column_create(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    column_name: Annotated[str, typer.Argument(help="Calculated column name.")],
    expression: Annotated[str | None, typer.Argument(help="DAX expression (omit to read from stdin or use --from-file).")] = None,
    data_type: Annotated[str, typer.Option("--type", help="Calculated column data type.")] = "string",
    format_string: Annotated[str | None, typer.Option("--format", help="Optional format string.")] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the DAX expression from a file.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a calculated column in the semantic model."""
    from pbi.model import create_calculated_column

    proj = get_project(project)
    try:
        dax = resolve_model_expression_input(expression, from_file)
        table, name, _changed = create_calculated_column(
            proj.root,
            table_name,
            column_name,
            dax,
            data_type=data_type,
            format_string=format_string,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Created calculated column [cyan]{table}.{name}[/cyan]')


@model_column_app.command("edit")
def model_column_edit(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    column_name: Annotated[str, typer.Argument(help="Calculated column name.")],
    expression: Annotated[str | None, typer.Argument(help="New DAX expression (omit to read from stdin or use --from-file).")] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the DAX expression from a file.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Edit a calculated column expression."""
    from pbi.model import edit_calculated_column_expression

    proj = get_project(project)
    try:
        dax = resolve_model_expression_input(expression, from_file)
        table, name, changed = edit_calculated_column_expression(
            proj.root,
            table_name,
            column_name,
            dax,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Updated calculated column [cyan]{table}.{name}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] [cyan]{table}.{name}[/cyan] expression is unchanged')


@model_column_app.command("unhide")
def model_column_unhide(
    fields: Annotated[list[str] | None, typer.Argument(help="Column references as Table.Column.")] = None,
    table_name: Annotated[str | None, typer.Option("--table", help="Target table (use with --pattern).")] = None,
    pattern: Annotated[str | None, typer.Option("--pattern", help="Regex pattern to match column names.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Unhide one or more previously hidden columns in the semantic model."""
    if table_name and pattern:
        _model_set_column_visibility_by_pattern(
            table_name,
            pattern,
            hidden=False,
            dry_run=dry_run,
            project=project,
        )
    elif fields:
        _model_set_column_visibility(fields, hidden=False, dry_run=dry_run, project=project)
    else:
        console.print("[red]Error:[/red] Provide column references or use --table with --pattern.")
        raise typer.Exit(1)


@model_column_app.command("delete")
def model_column_delete(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    column_name: Annotated[str, typer.Argument(help="Calculated column name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a calculated column from the semantic model."""
    from pbi.model import delete_calculated_column

    if not force:
        confirm = typer.confirm(f'Delete calculated column "{table_name}.{column_name}"?')
        if not confirm:
            raise typer.Abort()

    proj = get_project(project)
    try:
        table, name, _changed = delete_calculated_column(
            proj.root,
            table_name,
            column_name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Deleted calculated column [cyan]{table}.{name}[/cyan]')


@model_column_app.command("get")
def model_column_get(
    field: Annotated[str, typer.Argument(help="Column reference as Table.Column, or table name when column_name is provided.")],
    column_name: Annotated[str | None, typer.Argument(help="Column name (optional, use with table name as first arg).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show the full definition of one column."""
    ref = f"{field}.{column_name}" if column_name else field
    _, model = get_model(project)
    try:
        table_name, column_name_resolved, field_type = model.resolve_field(ref)
        if field_type != "column":
            raise ValueError(f'Field "{ref}" resolves to a {field_type}, not a column.')
        table = model.find_table(table_name)
        column = table.find_column(column_name_resolved)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold]{table.name}.{column.name}[/bold]")
    console.print(f"[dim]Kind:[/dim] {column.kind}")
    console.print(f"[dim]Data Type:[/dim] {column.data_type or '(none)'}")
    console.print(f"[dim]Format:[/dim] {column.format_string or '(none)'}")
    console.print(f"[dim]Summarize By:[/dim] {column.summarize_by or '(none)'}")
    console.print(f"[dim]Hidden:[/dim] {'true' if column.is_hidden else 'false'}")
    console.print(f"[dim]Description:[/dim] {column.description or '(none)'}")
    console.print(f"[dim]Display Folder:[/dim] {column.display_folder or '(none)'}")
    console.print(f"[dim]Sort By Column:[/dim] {column.sort_by_column or '(none)'}")
    console.print(f"[dim]Data Category:[/dim] {column.data_category or '(none)'}")
    console.print(f"[dim]Source Column:[/dim] {column.source_column or '(none)'}")
    console.print(f"[dim]Lineage:[/dim] {column.lineage_tag or '(none)'}")
    if column.expression:
        console.print("[dim]Expression:[/dim]")
        console.print(column.expression, highlight=False)


@model_column_app.command("set")
def model_column_set(
    field: Annotated[str, typer.Argument(help="Column reference as Table.Column.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments as key=value.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set metadata properties on a column (displayFolder, sortByColumn, etc.)."""
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


@model_column_app.command("rename")
def model_column_rename(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    old_name: Annotated[str, typer.Argument(help="Current column name.")],
    new_name: Annotated[str, typer.Argument(help="New column name.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Rename a calculated column and update all DAX + relationship references."""
    from pbi.model import rename_column

    proj = get_project(project)
    try:
        table, old, new, updated_refs = rename_column(
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


def _model_set_column_visibility(
    fields: list[str],
    *,
    hidden: bool,
    dry_run: bool,
    project,
) -> None:
    """Apply a hidden/shown state to one or more semantic-model columns."""
    from pbi.model import SemanticModel, TmdlEditSession, set_column_hidden

    proj = get_project(project)
    action = "Hidden" if hidden else "Shown"
    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    try:
        model = SemanticModel.load(proj.root)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    edit_session = TmdlEditSession()

    for field in fields:
        try:
            table_name, field_name, changed = set_column_hidden(
                proj.root,
                field,
                hidden,
                dry_run=dry_run,
                model=model,
                edit_session=edit_session,
            )
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        if changed:
            console.print(f'{prefix}{action} [cyan]{table_name}.{field_name}[/cyan]')
        else:
            current = "hidden" if hidden else "visible"
            console.print(
                f'{prefix}[dim]No change:[/dim] [cyan]{table_name}.{field_name}[/cyan] '
                f'is already {current}'
            )

    if not dry_run:
        edit_session.flush()


def _model_set_column_visibility_by_pattern(
    table_name: str,
    pattern: str,
    *,
    hidden: bool,
    dry_run: bool,
    project,
) -> None:
    """Hide/unhide columns matching a regex pattern in a table."""
    import re as re_mod

    from pbi.model import SemanticModel, TmdlEditSession, set_column_hidden

    proj = get_project(project)
    try:
        model = SemanticModel.load(proj.root)
        table = model.find_table(table_name)
        regex = re_mod.compile(pattern)
    except (FileNotFoundError, ValueError, re_mod.error) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if hidden:
        matching = [column for column in table.columns if regex.search(column.name) and not column.is_hidden]
    else:
        matching = [column for column in table.columns if regex.search(column.name) and column.is_hidden]

    if not matching:
        state = "visible" if hidden else "hidden"
        console.print(f'[yellow]No {state} columns matching "{pattern}" in "{table.name}".[/yellow]')
        raise typer.Exit(0)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    action = "Hidden" if hidden else "Shown"
    count = 0
    edit_session = TmdlEditSession()
    for column in matching:
        try:
            _, _, changed = set_column_hidden(
                proj.root,
                f"{table.name}.{column.name}",
                hidden,
                dry_run=dry_run,
                model=model,
                edit_session=edit_session,
            )
            if changed:
                console.print(f"{prefix}{action} [cyan]{table.name}.{column.name}[/cyan]")
                count += 1
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")

    if not dry_run:
        edit_session.flush()

    console.print(f"[dim]{count} column(s) {'hidden' if hidden else 'shown'}.[/dim]")
