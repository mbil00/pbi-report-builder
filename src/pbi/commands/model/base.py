"""Shared app instances and helpers for semantic-model commands."""

from __future__ import annotations

from pathlib import Path

import typer

from ..common import ProjectOpt, console, get_project, parse_property_assignments, resolve_yaml_input

model_app = typer.Typer(help="Semantic model operations.", no_args_is_help=True)
model_column_app = typer.Typer(help="Semantic model column operations.", no_args_is_help=True)
model_measure_app = typer.Typer(help="Semantic model measure operations.", no_args_is_help=True)
model_relationship_app = typer.Typer(help="Semantic model relationship operations.", no_args_is_help=True)
model_hierarchy_app = typer.Typer(help="Semantic model hierarchy operations.", no_args_is_help=True)
model_table_app = typer.Typer(help="Semantic model table operations.", no_args_is_help=True)

model_app.add_typer(model_column_app, name="column")
model_app.add_typer(model_measure_app, name="measure")
model_app.add_typer(model_relationship_app, name="relationship")
model_app.add_typer(model_hierarchy_app, name="hierarchy")
model_app.add_typer(model_table_app, name="table")


def get_model(project):
    """Load the semantic model for a project or exit with a CLI error."""
    from pbi.model import SemanticModel

    proj = get_project(project)
    try:
        return proj, SemanticModel.load(proj.root)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def resolve_model_expression_input(
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
