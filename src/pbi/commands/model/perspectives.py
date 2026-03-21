"""Perspective-related semantic-model commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .base import ProjectOpt, console, get_model, get_project, model_perspective_app


def _build_spec(
    *,
    include_all: list[str] | None,
    columns: list[str] | None,
    measures: list[str] | None,
    hierarchies: list[str] | None,
):
    from pbi.model import PerspectiveMemberSpec

    return PerspectiveMemberSpec(
        include_all_tables=list(include_all or []),
        columns=list(columns or []),
        measures=list(measures or []),
        hierarchies=list(hierarchies or []),
    )


@model_perspective_app.command("list")
def model_perspective_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List perspectives in the semantic model."""
    _, model = get_model(project)

    if not model.perspectives:
        console.print("[yellow]No perspectives found in the model. Use `pbi model perspective create` to add one.[/yellow]")
        raise typer.Exit(0)

    rows = [
        {
            "name": perspective.name,
            "tables": len(perspective.tables),
            "columns": sum(len(item.columns) for item in perspective.tables),
            "measures": sum(len(item.measures) for item in perspective.tables),
            "hierarchies": sum(len(item.hierarchies) for item in perspective.tables),
            "includeAll": sum(1 for item in perspective.tables if item.include_all),
        }
        for perspective in model.perspectives
    ]

    if as_json:
        import json

        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title="Perspectives", box=box.SIMPLE)
    table.add_column("Perspective", style="cyan")
    table.add_column("Tables", justify="right")
    table.add_column("Cols", justify="right")
    table.add_column("Measures", justify="right")
    table.add_column("Hierarchies", justify="right")
    table.add_column("All", justify="right", style="dim")
    for row in rows:
        table.add_row(
            row["name"],
            str(row["tables"]),
            str(row["columns"]),
            str(row["measures"]),
            str(row["hierarchies"]),
            str(row["includeAll"]),
        )
    console.print(table)


@model_perspective_app.command("get")
def model_perspective_get(
    perspective_name: Annotated[str, typer.Argument(help="Perspective name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one perspective in detail."""
    _, model = get_model(project)
    try:
        perspective = model.find_perspective(perspective_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rows = [
        {
            "table": item.table,
            "includeAll": item.include_all,
            "columns": item.columns,
            "measures": item.measures,
            "hierarchies": item.hierarchies,
        }
        for item in perspective.tables
    ]

    if as_json:
        import json

        console.print_json(json.dumps({"name": perspective.name, "tables": rows}, indent=2))
        return

    table = Table(title=f'Perspective: "{perspective.name}"', box=box.SIMPLE)
    table.add_column("Table", style="cyan")
    table.add_column("All", style="dim")
    table.add_column("Columns")
    table.add_column("Measures")
    table.add_column("Hierarchies")
    for row in rows:
        table.add_row(
            row["table"],
            "yes" if row["includeAll"] else "",
            ", ".join(row["columns"]),
            ", ".join(row["measures"]),
            ", ".join(row["hierarchies"]),
        )
    console.print(table)


@model_perspective_app.command("create")
def model_perspective_create(
    perspective_name: Annotated[str, typer.Argument(help="Perspective name.")],
    include_all: Annotated[list[str] | None, typer.Option("--include-all", help="Include all fields from a table (repeatable).")] = None,
    column: Annotated[list[str] | None, typer.Option("--column", help="Include a column ref as Table.Column (repeatable).")] = None,
    measure: Annotated[list[str] | None, typer.Option("--measure", help="Include a measure ref as Table.Measure (repeatable).")] = None,
    hierarchy: Annotated[list[str] | None, typer.Option("--hierarchy", help="Include a hierarchy ref as Table.Hierarchy (repeatable).")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a perspective from table/field membership."""
    from pbi.model import create_perspective

    proj = get_project(project)
    spec = _build_spec(include_all=include_all, columns=column, measures=measure, hierarchies=hierarchy)
    try:
        name, _created = create_perspective(
            proj.root,
            perspective_name,
            spec,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Created perspective [cyan]{name}[/cyan]')


@model_perspective_app.command("set")
def model_perspective_set(
    perspective_name: Annotated[str, typer.Argument(help="Perspective name.")],
    include_all: Annotated[list[str] | None, typer.Option("--include-all", help="Include all fields from a table (repeatable).")] = None,
    column: Annotated[list[str] | None, typer.Option("--column", help="Include a column ref as Table.Column (repeatable).")] = None,
    measure: Annotated[list[str] | None, typer.Option("--measure", help="Include a measure ref as Table.Measure (repeatable).")] = None,
    hierarchy: Annotated[list[str] | None, typer.Option("--hierarchy", help="Include a hierarchy ref as Table.Hierarchy (repeatable).")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Replace all membership in a perspective."""
    from pbi.model import set_perspective

    proj = get_project(project)
    spec = _build_spec(include_all=include_all, columns=column, measures=measure, hierarchies=hierarchy)
    try:
        name, changed = set_perspective(
            proj.root,
            perspective_name,
            spec,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Updated perspective [cyan]{name}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] perspective [cyan]{name}[/cyan] already matches the requested membership')


@model_perspective_app.command("delete")
def model_perspective_delete(
    perspective_name: Annotated[str, typer.Argument(help="Perspective name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a perspective."""
    from pbi.model import delete_perspective

    if not force:
        confirm = typer.confirm(f'Delete perspective "{perspective_name}"?')
        if not confirm:
            raise typer.Abort()

    proj = get_project(project)
    try:
        name, deleted = delete_perspective(
            proj.root,
            perspective_name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if deleted:
        console.print(f'{prefix}Deleted perspective [cyan]{name}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] perspective [cyan]{name}[/cyan] does not exist')
