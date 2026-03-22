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
    from pbi.model import create_field_parameter

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

    # Resolve display info for output
    display_labels = effective_labels if effective_labels else [f.split(".", 1)[1] if "." in f else f for f in fields]
    field_types = []
    for field_ref in fields:
        dot = field_ref.find(".")
        if dot == -1:
            field_types.append("field")
            continue
        table_name = field_ref[:dot]
        field_name = field_ref[dot + 1:]
        ftype = "column"
        try:
            sem_table = model.find_table(table_name)
            for m in sem_table.measures:
                if m.name.lower() == field_name.lower():
                    ftype = "measure"
                    break
        except ValueError:
            pass
        field_types.append(ftype)

    console.print(f'{prefix}Created field parameter "[cyan]{param_name}[/cyan]" with {len(fields)} fields')
    for label, field_ref, ftype in zip(display_labels, fields, field_types):
        console.print(f"  [cyan]{label:<16}[/cyan] [dim]->[/dim] {field_ref} [dim]({ftype})[/dim]")
    console.print()
    console.print(f'[dim]Bind to a slicer:[/dim] pbi visual bind "Page" slicer Values "{param_name}.{param_name}"')
