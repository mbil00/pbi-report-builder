"""Semantic-model annotation CLI commands."""

from __future__ import annotations

import difflib
import json
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .base import ProjectOpt, console, get_model, get_project, model_annotation_app


def _find_annotation(annotations: dict[str, str], name: str) -> tuple[str, str]:
    lowered = name.lower()
    for key, value in annotations.items():
        if key.lower() == lowered:
            return key, value
    names = list(annotations.keys())
    matches = difflib.get_close_matches(name, names, n=3, cutoff=0.5)
    if matches:
        raise ValueError(f'Annotation "{name}" not found. Did you mean: {", ".join(matches)}?')
    raise ValueError(f'Annotation "{name}" not found. Available: {", ".join(names) or "(none)"}')


@model_annotation_app.command("list")
def model_annotation_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List model annotations."""
    _, model = get_model(project)
    rows = [{"name": key, "value": value} for key, value in model.annotations.items()]
    if as_json:
        console.print_json(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[yellow]No annotations. Use `pbi model annotation set` to add one.[/yellow]")
        raise typer.Exit(0)
    table = Table(title="Model Annotations", box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Value")
    for row in rows:
        table.add_row(row["name"], row["value"])
    console.print(table)


@model_annotation_app.command("get")
def model_annotation_get(
    name: Annotated[str, typer.Argument(help="Annotation name.")],
    project: ProjectOpt = None,
) -> None:
    """Show one model annotation."""
    _, model = get_model(project)
    try:
        _key, value = _find_annotation(model.annotations, name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(value)


@model_annotation_app.command("set")
def model_annotation_set(
    name: Annotated[str, typer.Argument(help="Annotation name.")],
    value: Annotated[str, typer.Argument(help="Annotation value as raw TMDL literal text.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set a model annotation."""
    from pbi.model import set_model_annotation

    proj = get_project(project)
    try:
        annotation_name, changed = set_model_annotation(
            proj.root,
            name,
            value,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f"{prefix}Updated model annotation [cyan]{annotation_name}[/cyan]")
    else:
        console.print(f'{prefix}[dim]No change:[/dim] annotation [cyan]{annotation_name}[/cyan] is already current')


@model_annotation_app.command("delete")
def model_annotation_delete(
    name: Annotated[str, typer.Argument(help="Annotation name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a model annotation."""
    from pbi.model import delete_model_annotation

    proj = get_project(project)
    if not force:
        confirm = typer.confirm(f'Delete annotation "{name}"?')
        if not confirm:
            raise typer.Abort()
    try:
        annotation_name, changed = delete_model_annotation(
            proj.root,
            name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Deleted model annotation [cyan]{annotation_name}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] annotation [cyan]{annotation_name}[/cyan] is already absent')
