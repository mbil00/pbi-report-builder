"""Semantic-model CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project, resolve_yaml_input

model_app = typer.Typer(help="Semantic model operations.", no_args_is_help=True)
model_column_app = typer.Typer(help="Semantic model column operations.", no_args_is_help=True)
model_measure_app = typer.Typer(help="Semantic model measure operations.", no_args_is_help=True)
model_app.add_typer(model_column_app, name="column")
model_app.add_typer(model_measure_app, name="measure")


def _get_model(project):
    from pbi.model import SemanticModel

    proj = get_project(project)
    try:
        return proj, SemanticModel.load(proj.root)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@model_app.command("tables")
def model_tables(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List tables in the semantic model."""
    _, model = _get_model(project)

    if as_json:
        import json

        rows = [{"name": t.name, "columns": len(t.columns), "measures": len(t.measures)} for t in model.tables]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title="Semantic Model Tables", box=box.SIMPLE)
    table.add_column("Table", style="cyan")
    table.add_column("Columns", justify="right")
    table.add_column("Measures", justify="right")

    for sem_table in model.tables:
        table.add_row(sem_table.name, str(len(sem_table.columns)), str(len(sem_table.measures)))

    console.print(table)


@model_app.command("columns")
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

    _, model = _get_model(project)
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

        rows = [{
            "name": c.name,
            "kind": c.kind,
            "dataType": c.data_type,
            "format": c.format_string,
            "hidden": c.is_hidden,
            "sourceColumn": c.source_column,
        } for c in columns]
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


@model_app.command("measures")
def model_measures(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    full: Annotated[bool, typer.Option("--full", help="Show complete expressions without truncation.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List measures (facts) in a table."""
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if as_json:
        import json

        rows = [{"name": m.name, "expression": m.expression, "format": m.format_string} for m in sem_table.measures]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title=f'Measures in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Measure", style="cyan")
    if full:
        table.add_column("Expression")
    else:
        table.add_column("Expression", max_width=60)
    table.add_column("Format", style="dim")

    for measure in sem_table.measures:
        if full:
            expr = measure.expression
        else:
            expr = measure.expression[:57] + "..." if len(measure.expression) > 60 else measure.expression
        table.add_row(measure.name, expr, measure.format_string)

    console.print(table)


@model_app.command("search")
def model_search(
    keyword: Annotated[str, typer.Argument(help="Keyword to search for across all tables, columns, and measures.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Search for fields and measures by keyword across all tables."""
    _, model = _get_model(project)
    keyword_lower = keyword.lower()

    matches: list[dict[str, str]] = []
    for sem_table in model.tables:
        if keyword_lower in sem_table.name.lower():
            matches.append({"ref": sem_table.name, "type": "table", "details": f"{len(sem_table.columns)} cols, {len(sem_table.measures)} measures"})
        for column in sem_table.columns:
            if keyword_lower in column.name.lower():
                matches.append({"ref": f"{sem_table.name}.{column.name}", "type": "column", "details": column.data_type})
        for measure in sem_table.measures:
            if keyword_lower in measure.name.lower():
                expr = measure.expression[:40] + "..." if len(measure.expression) > 40 else measure.expression
                matches.append({"ref": f"{sem_table.name}.{measure.name}", "type": "measure", "details": expr})

    if not matches:
        console.print(f'[yellow]No fields matching "{keyword}". Try a broader search.[/yellow]')
        raise typer.Exit(0)

    if as_json:
        import json

        console.print_json(json.dumps(matches, indent=2))
        return

    table = Table(title=f'Search: "{keyword}"', box=box.SIMPLE)
    table.add_column("Reference", style="cyan")
    table.add_column("Type")
    table.add_column("Details", style="dim")
    for match in matches:
        table.add_row(match["ref"], match["type"], match["details"])
    console.print(table)


@model_app.command("apply")
def model_apply(
    yaml_file: Annotated[str | None, typer.Argument(help="YAML file describing model changes. Use '-' or omit to read from stdin.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview model changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Apply declarative YAML changes to the semantic model."""
    from pbi.model_apply import apply_model_yaml

    proj = get_project(project)
    try:
        yaml_content = resolve_yaml_input(yaml_file)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    result = apply_model_yaml(proj.root, yaml_content, dry_run=dry_run)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    for ref in result.measures_created:
        console.print(f"{prefix}Created measure [cyan]{ref}[/cyan]")
    for ref in result.measures_updated:
        console.print(f"{prefix}Updated measure [cyan]{ref}[/cyan]")
    for ref in result.columns_created:
        console.print(f"{prefix}Created calculated column [cyan]{ref}[/cyan]")
    for ref in result.columns_updated:
        console.print(f"{prefix}Updated column [cyan]{ref}[/cyan]")
    for error in result.errors:
        console.print(f"[red]Error:[/red] {error}")

    if result.errors:
        raise typer.Exit(1)
    if not result.has_changes:
        console.print("[dim]No changes detected.[/dim]" if dry_run else "[dim]No changes applied.[/dim]")


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
        dax = _resolve_model_expression_input(expression, from_file)
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
        dax = _resolve_model_expression_input(expression, from_file)
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
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
        measure = sem_table.find_measure(measure_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold]{sem_table.name}.{measure.name}[/bold]")
    console.print(f"[dim]Format:[/dim] {measure.format_string or '(none)'}")
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


@model_app.command("relationships")
def model_relationships(
    from_table: Annotated[str | None, typer.Option("--from", help="Filter by table name.")] = None,
    to_table: Annotated[str | None, typer.Option("--to", help="Filter by table name.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List relationships in the semantic model."""
    _, model = _get_model(project)

    rels = model.find_relationships(from_table=from_table, to_table=to_table)

    if not rels:
        console.print("[yellow]No relationships found.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        rows = [{
            "from": f"{r.from_table}.{r.from_column}",
            "to": f"{r.to_table}.{r.to_column}",
            "properties": r.properties,
        } for r in rels]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title="Model Relationships", box=box.SIMPLE)
    table.add_column("From", style="cyan")
    table.add_column("", style="dim", width=2)
    table.add_column("To", style="cyan")
    table.add_column("Properties", style="dim")

    for r in rels:
        props = ", ".join(f"{k}={v}" for k, v in r.properties.items()) if r.properties else ""
        table.add_row(
            f"{r.from_table}.{r.from_column}",
            "→",
            f"{r.to_table}.{r.to_column}",
            props,
        )
    console.print(table)


@model_app.command("path")
def model_path(
    from_table: Annotated[str, typer.Argument(help="Source table name.")],
    to_table: Annotated[str, typer.Argument(help="Target table name.")],
    project: ProjectOpt = None,
) -> None:
    """Show the relationship path between two tables."""
    _, model = _get_model(project)

    path = model.find_path(from_table, to_table)
    if path is None:
        console.print(f'[yellow]No relationship path found between "{from_table}" and "{to_table}".[/yellow]')
        raise typer.Exit(1)

    if not path:
        console.print(f'[dim]"{from_table}" and "{to_table}" are the same table.[/dim]')
        return

    steps = []
    for rel in path:
        steps.append(f"{rel.from_table}.{rel.from_column} [dim]→[/dim] {rel.to_table}.{rel.to_column}")

    console.print(f"[bold]Path ({len(path)} hop{'s' if len(path) != 1 else ''}):[/bold]")
    for step in steps:
        console.print(f"  {step}")


@model_app.command("fields")
def model_fields(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List all fields (columns + measures) for use with 'visual bind'."""
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if as_json:
        import json

        rows = []
        for column in sem_table.columns:
            if not column.is_hidden:
                rows.append({"ref": f"{sem_table.name}.{column.name}", "type": "column", "details": column.data_type})
        for measure in sem_table.measures:
            rows.append({"ref": f"{sem_table.name}.{measure.name}", "type": "measure", "details": measure.expression})
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title=f'Fields in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Field Reference", style="cyan")
    table.add_column("Type")
    table.add_column("Details", style="dim")

    for column in sem_table.columns:
        if not column.is_hidden:
            table.add_row(f"{sem_table.name}.{column.name}", "column", column.data_type)
    for measure in sem_table.measures:
        expr = measure.expression[:40] + "..." if len(measure.expression) > 40 else measure.expression
        table.add_row(f"{sem_table.name}.{measure.name}", "[bold]measure[/bold]", expr)

    console.print(table)


def _resolve_model_expression_input(
    expression: str | None,
    from_file: Path | None,
) -> str:
    """Resolve a model expression from an arg, file, or piped stdin."""
    import sys

    if expression is not None and from_file is not None:
        raise ValueError("Provide either an inline expression or --from-file, not both.")
    if from_file is not None:
        path = from_file if from_file.is_absolute() else Path.cwd() / from_file
        if not path.exists():
            raise ValueError(f"File not found: {path}")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"Expression file is empty: {path}")
        return text.strip("\n")
    if expression is not None and expression.strip():
        return expression.strip("\n")
    if not sys.stdin.isatty():
        text = sys.stdin.read()
        if text.strip():
            return text.strip("\n")
    raise ValueError("Provide a DAX expression inline, via --from-file, or through stdin.")


@model_app.command("format")
def model_format(
    field: Annotated[str, typer.Argument(help="Field reference as Table.Field.")],
    format_string: Annotated[str, typer.Argument(help="Format string to set.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set the semantic model format string for a column or measure."""
    from pbi.model import set_field_format

    proj = get_project(project)
    try:
        table_name, field_name, field_type, changed = set_field_format(
            proj.root,
            field,
            format_string,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(
            f'{prefix}Set format on [cyan]{table_name}.{field_name}[/cyan] '
            f'([dim]{field_type}[/dim]) -> "{format_string}"'
        )
    else:
        console.print(
            f'{prefix}[dim]No change:[/dim] [cyan]{table_name}.{field_name}[/cyan] '
            f'already uses "{format_string}"'
        )


@model_column_app.command("hide")
def model_column_hide(
    fields: Annotated[list[str], typer.Argument(help="Column references as Table.Column.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Hide one or more columns in the semantic model."""
    _model_set_column_visibility(fields, hidden=True, dry_run=dry_run, project=project)


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
        dax = _resolve_model_expression_input(expression, from_file)
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
        dax = _resolve_model_expression_input(expression, from_file)
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
    fields: Annotated[list[str], typer.Argument(help="Column references as Table.Column.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Unhide one or more previously hidden columns in the semantic model."""
    _model_set_column_visibility(fields, hidden=False, dry_run=dry_run, project=project)


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
    _, model = _get_model(project)
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
    console.print(f"[dim]Source Column:[/dim] {column.source_column or '(none)'}")
    console.print(f"[dim]Lineage:[/dim] {column.lineage_tag or '(none)'}")
    if column.expression:
        console.print("[dim]Expression:[/dim]")
        console.print(column.expression, highlight=False)


def _model_set_column_visibility(
    fields: list[str],
    *,
    hidden: bool,
    dry_run: bool,
    project,
) -> None:
    """Apply a hidden/shown state to one or more semantic-model columns."""
    from pbi.model import set_column_hidden

    proj = get_project(project)
    action = "Hidden" if hidden else "Shown"
    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    for field in fields:
        try:
            table_name, field_name, changed = set_column_hidden(
                proj.root,
                field,
                hidden,
                dry_run=dry_run,
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
