"""Semantic-model partition CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .base import ProjectOpt, console, get_model, get_project, model_partition_app, parse_property_assignments, resolve_model_expression_input


def _partition_row(partition) -> dict:
    return {
        "table": partition.table,
        "name": partition.name,
        "sourceType": partition.source_type,
        "mode": partition.mode,
        "source": partition.source_expression,
    }


@model_partition_app.command("list")
def model_partition_list(
    table_name: Annotated[str | None, typer.Argument(help="Optional table name to narrow the list.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List semantic-model partitions."""
    _, model = get_model(project)
    tables = model.tables
    if table_name:
        try:
            tables = [model.find_table(table_name)]
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    rows = [_partition_row(partition) for table in tables for partition in table.partitions]
    if not rows:
        console.print("[yellow]No partitions. Use `pbi model partition create` to add one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Table", style="cyan")
    table.add_column("Partition", style="cyan")
    table.add_column("Source Type")
    table.add_column("Mode")
    table.add_column("Source", style="dim")
    for row in rows:
        preview = row["source"].splitlines()[0] if row["source"] else ""
        if len(preview) > 60:
            preview = preview[:57] + "..."
        table.add_row(row["table"], row["name"], row["sourceType"], row["mode"], preview)
    console.print(table)


@model_partition_app.command("get")
def model_partition_get(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    partition_name: Annotated[str, typer.Argument(help="Partition name.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one partition definition."""
    _, model = get_model(project)
    try:
        table = model.find_table(table_name)
        partition = table.find_partition(partition_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    payload = _partition_row(partition)
    if raw:
        console.print_json(json.dumps(payload, indent=2))
        return

    result = Table(title=f'{table.name}.{partition.name}', box=box.SIMPLE)
    result.add_column("Property", style="cyan")
    result.add_column("Value")
    result.add_row("Source Type", partition.source_type)
    result.add_row("Mode", partition.mode)
    result.add_row("Source", partition.source_expression)
    console.print(result)


@model_partition_app.command("create")
def model_partition_create(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    partition_name: Annotated[str, typer.Argument(help="Partition name.")],
    expression: Annotated[str | None, typer.Argument(help="Partition source expression. Omit when using --from-file or stdin.")] = None,
    source_type: Annotated[str, typer.Option("--source-type", help="Partition source type: m or calculated.")] = "m",
    mode: Annotated[str, typer.Option("--mode", help="Partition mode.")] = "import",
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the source expression from a file.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create one partition."""
    from pbi.model import create_partition

    proj = get_project(project)
    try:
        resolved = resolve_model_expression_input(expression, from_file)
        table, partition, changed = create_partition(
            proj.root,
            table_name,
            partition_name,
            resolved,
            source_type=source_type,
            mode=mode,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Created partition [cyan]{table}.{partition}[/cyan]')


@model_partition_app.command("set")
def model_partition_set(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    partition_name: Annotated[str, typer.Argument(help="Partition name.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments as key=value.")],
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read `source` from a file.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set writable partition properties."""
    from pbi.model import set_partition

    proj = get_project(project)
    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    values: dict[str, str] = {}
    for prop, value in pairs:
        if prop not in {"mode", "sourceType", "source"}:
            console.print('[red]Error:[/red] Property "{}" is not writable. Allowed: mode, sourceType, source'.format(prop))
            raise typer.Exit(1)
        values[prop] = value
    if from_file is not None:
        if "source" in values:
            console.print("[red]Error:[/red] Provide source inline or via --from-file, not both.")
            raise typer.Exit(1)
        try:
            values["source"] = resolve_model_expression_input(None, from_file)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    try:
        table, partition, changed = set_partition(
            proj.root,
            table_name,
            partition_name,
            source_expression=values.get("source"),
            source_type=values.get("sourceType"),
            mode=values.get("mode"),
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Updated partition [cyan]{table}.{partition}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] partition [cyan]{table}.{partition}[/cyan] is already current')


@model_partition_app.command("delete")
def model_partition_delete(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    partition_name: Annotated[str, typer.Argument(help="Partition name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete one partition."""
    from pbi.model import delete_partition

    proj = get_project(project)
    if not force:
        confirm = typer.confirm(f'Delete partition "{table_name}.{partition_name}"?')
        if not confirm:
            raise typer.Abort()
    try:
        table, partition, changed = delete_partition(
            proj.root,
            table_name,
            partition_name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Deleted partition [cyan]{table}.{partition}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] partition [cyan]{table}.{partition}[/cyan] is already absent')
