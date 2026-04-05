"""Shared field resolution helpers used across CLI and apply paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pbi.project import Project


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
        model = _load_model_from_project(proj)

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


def resolve_binding_ref(
    project_root: Path,
    field_ref: str,
    *,
    model: Any = None,
) -> tuple[str, str, str]:
    """Resolve a shorthand binding field ref to entity/prop/type."""
    entity, prop, field_type, _data_type = resolve_field_info_from_root(
        project_root,
        field_ref,
        "auto",
        model=model,
    )
    return entity, prop, field_type


def resolve_field_info_from_root(
    project_root: Path,
    field: str,
    field_type: str,
    *,
    model: Any | None = None,
    strict: bool = False,
) -> tuple[str, str, str, str | None]:
    """Resolve Table.Field using a project root instead of a Project object."""
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

    loaded_model = model
    if loaded_model is None:
        loaded_model = _load_model_from_root(project_root)

    if loaded_model is None:
        return entity, prop, "column" if mode == "auto" else mode, None

    try:
        resolved_entity, resolved_prop, resolved_field_type = loaded_model.resolve_field(normalized_field)
    except (ValueError, KeyError) as exc:
        if strict:
            raise ValueError(str(exc)) from exc
        return entity, prop, "column" if mode == "auto" else mode, None

    effective_type = mode if mode in {"column", "measure"} else resolved_field_type

    data_type = None
    try:
        table = loaded_model.find_table(resolved_entity)
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


def _load_model_from_project(proj: Project) -> Any | None:
    try:
        from pbi.model import SemanticModel

        return SemanticModel.load(proj.root)
    except (FileNotFoundError, ValueError):
        return None


def _load_model_from_root(project_root: Path) -> Any | None:
    try:
        from pbi.model import SemanticModel

        return SemanticModel.load(project_root)
    except (FileNotFoundError, ValueError, TypeError):
        return None


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
