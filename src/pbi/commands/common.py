"""Shared CLI command helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from pbi.project import Project

console = Console()

ProjectOpt = Annotated[
    Optional[Path],
    typer.Option("--project", "-p", help="Path to PBIP project (default: auto-detect from cwd)."),
]


def get_project(project: Path | None) -> Project:
    """Resolve a PBIP project or exit with a CLI-friendly error."""
    try:
        return Project.find(project)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def normalize_field_type(field_type: str) -> str:
    """Normalize a field type switch used by model/visual/filter commands."""
    valid = {"auto", "column", "measure"}
    if field_type not in valid:
        raise ValueError(f"Invalid field type '{field_type}'. Use one of: auto, column, measure.")
    return field_type


def resolve_field_type(
    proj: Project,
    field: str,
    field_type: str,
) -> tuple[str, str, str]:
    """Resolve Table.Field to entity, prop, and concrete field type."""
    dot = field.find(".")
    if dot == -1:
        raise ValueError("Field must be Table.Field format.")
    entity, prop = field[:dot], field[dot + 1 :]
    mode = normalize_field_type(field_type)
    if mode != "auto":
        return entity, prop, mode
    try:
        from pbi.model import SemanticModel

        model = SemanticModel.load(proj.root)
        entity, prop, mode = model.resolve_field(field)
    except (FileNotFoundError, ValueError):
        mode = "column"
    return entity, prop, mode


def parse_property_assignments(assignments: list[str]) -> list[tuple[str, str]]:
    """Parse canonical prop=value pairs."""
    pairs: list[tuple[str, str]] = []
    for arg in assignments:
        eq = arg.find("=")
        if eq == -1:
            raise ValueError(f"Invalid assignment '{arg}'. Use prop=value format.")
        pairs.append((arg[:eq], arg[eq + 1 :]))
    return pairs
