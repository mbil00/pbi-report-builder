"""CLI commands for field parameter management."""

from __future__ import annotations

from typing import Annotated

import typer

from ..common import ProjectOpt, console
from .base import get_model, model_field_parameter_app


@model_field_parameter_app.command("create")
def create_field_parameter_cmd(
    name: Annotated[str, typer.Argument(help="Name for the field parameter table.")],
    fields: Annotated[list[str], typer.Argument(help="Table.Field references to include.")],
    labels: Annotated[list[str] | None, typer.Option("--labels", help="Display labels (one per field).")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview without writing.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a field parameter table from model fields."""
    from pbi.modeling.writes_field_parameters import (
        create_field_parameter,
        resolve_field_parameter_fields,
    )

    proj, model = get_model(project)
    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    # Normalize labels: if provided, must match fields count; if empty list from CLI, treat as None
    effective_labels = labels if labels else None

    try:
        param_name, path, created = create_field_parameter(
            proj.root,
            name,
            fields=fields,
            labels=effective_labels,
            dry_run=dry_run,
            model=model,
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rows = resolve_field_parameter_fields(model, fields, effective_labels)
    measures = {
        (table.name, measure.name) for table in model.tables for measure in table.measures
    }

    console.print(f'{prefix}Created field parameter "[cyan]{param_name}[/cyan]" with {len(fields)} fields')
    for row in rows:
        kind = "measure" if (row.table, row.field) in measures else "column"
        console.print(f"  [cyan]{row.label:<16}[/cyan] [dim]->[/dim] {row.ref} [dim]({kind})[/dim]")
    console.print()
    console.print(f'[dim]Bind to a slicer:[/dim] pbi visual bind "Page" slicer Values "{param_name}.{param_name}"')
