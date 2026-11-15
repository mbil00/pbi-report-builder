"""Shared field resolution helpers used across CLI and apply paths."""

from __future__ import annotations

import re
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
                    data_type = infer_measure_data_type(model, measure)
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
                    data_type = infer_measure_data_type(loaded_model, measure)
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


# Result types of the DAX aggregations that settle a measure's type on their own.
_INTEGER_FUNCTIONS = frozenset({
    "COUNT", "COUNTA", "COUNTAX", "COUNTBLANK", "COUNTROWS", "COUNTX",
    "DISTINCTCOUNT", "DISTINCTCOUNTNOBLANK",
})
_DOUBLE_FUNCTIONS = frozenset({"AVERAGE", "AVERAGEA", "AVERAGEX", "DIVIDE"})
# Aggregations whose result keeps the type of the column they read.
_COLUMN_TYPED_FUNCTIONS = frozenset({"SUM", "MIN", "MAX"})
_NUMERIC_COLUMN_TYPES = frozenset({"int64", "double", "decimal"})

_DAX_CALL = re.compile(r"([A-Za-z][A-Za-z0-9.]*)\s*\((.*)\)", re.DOTALL)
_DAX_MEASURE_REF = re.compile(r"\[([^\]]+)\]")


def infer_measure_data_type(model: Any, measure: Any) -> str:
    """Best-effort result type of a measure, used to type filter literals.

    TMDL stores no data type for measures, so read it from simple DAX shapes
    (``COUNTROWS`` is a whole number, ``DIVIDE`` a decimal, ``SUM(T[C])`` the
    column's type) and then from the format string. When neither settles it,
    return ``"numeric"`` so literals are typed by their value instead of quoted.
    """
    from_expression = _infer_dax_type(model, getattr(measure, "expression", "") or "", set())
    if from_expression:
        return from_expression
    return _infer_type_from_format(getattr(measure, "format_string", "") or "") or "numeric"


def _infer_dax_type(model: Any, expression: str, seen: set[str]) -> str | None:
    from pbi.modeling.dax_refs import extract_refs

    text = _strip_dax_comments(expression).strip()
    ref = _DAX_MEASURE_REF.fullmatch(text)
    if ref:
        name = ref.group(1).strip().lower()
        if name in seen:
            return None
        seen.add(name)
        for table in getattr(model, "tables", []):
            for other in table.measures:
                if other.name.lower() == name:
                    return _infer_dax_type(model, other.expression or "", seen)
        return None

    call = _DAX_CALL.fullmatch(text)
    if not call:
        return None
    function = call.group(1).upper()
    args = _split_dax_args(call.group(2))
    if args is None:
        return None
    if function in _INTEGER_FUNCTIONS:
        return "int64"
    if function in _DOUBLE_FUNCTIONS:
        return "double"
    if function == "CALCULATE" and args:
        return _infer_dax_type(model, args[0], seen)
    if function in _COLUMN_TYPED_FUNCTIONS and len(args) == 1:
        refs = extract_refs(args[0])
        if len(refs) == 1 and refs[0].qualified and args[0].strip()[-1:] == "]":
            return _column_data_type(model, refs[0].table, refs[0].name)
    return None


def _column_data_type(model: Any, table_name: str, column_name: str) -> str | None:
    for table in getattr(model, "tables", []):
        if table.name.lower() != table_name.lower():
            continue
        for column in table.columns:
            if column.name.lower() == column_name.lower():
                data_type = (column.data_type or "").lower()
                return data_type if data_type in _NUMERIC_COLUMN_TYPES else None
    return None


def _strip_dax_comments(expression: str) -> str:
    return re.sub(r'"(?:[^"]|"")*"|//[^\n]*|--[^\n]*|/\*.*?\*/',
                  lambda m: m.group(0) if m.group(0).startswith('"') else " ",
                  expression, flags=re.DOTALL)


def _split_dax_args(body: str) -> list[str] | None:
    """Split a DAX argument list at top-level commas; None if brackets don't balance."""
    args: list[str] = []
    depth = 0
    current: list[str] = []
    quote: str | None = None
    bracket = False
    for char in body:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if bracket:
            current.append(char)
            if char == "]":
                bracket = False
            continue
        if char in "\"'":
            quote = char
        elif char == "[":
            bracket = True
        elif char in "({":
            depth += 1
        elif char in ")}":
            depth -= 1
            if depth < 0:
                return None
        elif char == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if depth != 0 or quote or bracket:
        return None
    args.append("".join(current).strip())
    return args


def _infer_type_from_format(format_string: str) -> str | None:
    """Fallback measure type from the format string alone.

    A currency format says nothing about whether the measure returns a fixed
    decimal, so it maps to ``double`` (a ``D`` literal); ``M`` is only written
    when the DAX reads a fixed decimal column.
    """
    fmt = format_string.strip()
    if not fmt:
        return None
    if any(symbol in fmt for symbol in ("$", "€", "£", "¥")) or "currency" in fmt.lower():
        return "double"
    if "%" in fmt or "." in fmt:
        return "double"
    return None
