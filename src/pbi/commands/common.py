"""Shared CLI command helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any, Optional

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
        proj = Project.find(project)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Auto-install custom visual schemas from .pbiviz files, then load all
    try:
        from pbi.custom_visuals import auto_install
        newly_installed = auto_install(proj)
        for cv in newly_installed:
            console.print(
                f'[dim]Auto-installed plugin schema "[cyan]{cv.visual_type}[/cyan]" '
                f"({cv.role_count} roles, {cv.object_count} objects)[/dim]"
            )
    except Exception:
        pass

    try:
        from pbi.visual_schema import register_custom_schemas
        register_custom_schemas(proj.root)
    except Exception:
        pass

    return proj


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
    *,
    strict: bool = False,
) -> tuple[str, str, str]:
    """Resolve Table.Field to entity, prop, and concrete field type."""
    entity, prop, resolved_type, _data_type = resolve_field_info(
        proj,
        field,
        field_type,
        strict=strict,
    )
    return entity, prop, resolved_type


def resolve_field_info(
    proj: Project,
    field: str,
    field_type: str,
    *,
    model: Any | None = None,
    strict: bool = False,
) -> tuple[str, str, str, str | None]:
    """Resolve Table.Field to entity, prop, concrete field type, and data type.

    Resolution rules:
    - explicit `measure` returns the raw field ref as a measure
    - explicit `column` keeps the requested type but still uses the model, when
      available, to resolve the canonical entity/prop and column data type
    - `auto` uses the semantic model when available and otherwise falls back to
      treating the field as a column
    """
    raw_field = field.strip()
    has_measure_marker = raw_field.endswith("(measure)")
    normalized_field = raw_field[:-9].strip() if has_measure_marker else raw_field

    dot = normalized_field.find(".")
    if dot == -1:
        raise ValueError("Field must be Table.Field format.")

    entity, prop = normalized_field[:dot], normalized_field[dot + 1 :]
    mode = normalize_field_type(field_type)
    if has_measure_marker and mode == "auto":
        mode = "measure"

    if model is None:
        try:
            from pbi.model import SemanticModel

            model = SemanticModel.load(proj.root)
        except (FileNotFoundError, ValueError):
            model = None

    if model is None:
        return entity, prop, "column" if mode == "auto" else mode, None

    try:
        resolved_entity, resolved_prop, resolved_field_type = model.resolve_field(normalized_field)
    except (ValueError, KeyError) as exc:
        if strict:
            raise ValueError(str(exc)) from exc
        return entity, prop, "column" if mode == "auto" else mode, None

    effective_type = mode if mode in {"column", "measure"} else resolved_field_type

    data_type = None
    try:
        table = model.find_table(resolved_entity)
        if effective_type == "column":
            for column in table.columns:
                if column.name == resolved_prop:
                    data_type = column.data_type
                    break
        elif effective_type == "measure":
            for measure in table.measures:
                if measure.name == resolved_prop:
                    data_type = _infer_measure_data_type(measure.format_string)
                    break
    except (ValueError, KeyError):
        pass

    return resolved_entity, resolved_prop, effective_type, data_type


def _infer_measure_data_type(format_string: str) -> str | None:
    """Best-effort measure type inference from the format string."""
    fmt = (format_string or "").strip()
    if not fmt:
        return None

    lowered = fmt.lower()
    if any(symbol in fmt for symbol in ("$", "€", "£", "¥")) or "currency" in lowered:
        return "currency"
    if "%" in fmt:
        return "number"
    if "." in fmt:
        return "number"
    return None


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
