"""Shared CLI command helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console

from pbi.fields import normalize_field_type, resolve_field_info, resolve_field_type
from pbi.project import Project
from pbi.project_runtime import register_project_schemas
console = Console()

ProjectOpt = Annotated[
    Optional[Path],
    typer.Option("--project", "-p", help="Path to PBIP project (default: auto-detect from cwd)."),
]


def find_project(project: Path | None) -> Project:
    """Resolve a PBIP project or exit with a CLI-friendly error."""
    try:
        return Project.find(project)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def get_project(project: Path | None) -> Project:
    """Resolve a PBIP project or exit with a CLI-friendly error."""
    proj = find_project(project)
    register_project_schemas(proj)
    return proj


def parse_property_assignments(assignments: list[str]) -> list[tuple[str, str]]:
    """Parse canonical prop=value pairs."""
    pairs: list[tuple[str, str]] = []
    for arg in assignments:
        eq = arg.find("=")
        if eq == -1:
            raise ValueError(f"Invalid assignment '{arg}'. Use prop=value format.")
        pairs.append((arg[:eq], arg[eq + 1 :]))
    return pairs


def resolve_output_path(
    output: Path,
    *,
    confine_to: Path | None = None,
) -> Path:
    """Resolve an output path relative to CWD, optionally confining it to a project root."""
    resolved = output.resolve() if output.is_absolute() else (Path.cwd() / output).resolve()
    if confine_to is not None:
        root = confine_to.resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError(f"Output path must stay within {root}")
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return resolved


def resolve_yaml_input(yaml_source: str | Path | None) -> str:
    """Resolve YAML from a file path, '-' sentinel, or piped stdin."""
    if yaml_source not in (None, "-"):
        yaml_path = yaml_source if isinstance(yaml_source, Path) else Path(yaml_source)
        yaml_path = yaml_path if yaml_path.is_absolute() else Path.cwd() / yaml_path
        if not yaml_path.exists():
            raise ValueError(f"File not found: {yaml_path}")
        yaml_content = yaml_path.read_text(encoding="utf-8")
        if not yaml_content.strip():
            raise ValueError(f"YAML file is empty: {yaml_path}")
        return yaml_content

    if not sys.stdin.isatty():
        yaml_content = sys.stdin.read()
        if yaml_content.strip():
            return yaml_content

    raise ValueError("Provide a YAML file, use '-' to read from stdin, or pipe YAML into the command.")
