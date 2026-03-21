from __future__ import annotations

import re

from .types import DATE_UNIT_CODES, TIME_UNIT_CODES


def _extract_expression_ref(
    expr: dict,
    *,
    alias_map: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Extract an entity/property reference from a query expression."""
    alias_map = alias_map or {}
    if "Aggregation" in expr:
        return _extract_expression_ref(expr["Aggregation"].get("Expression", {}), alias_map=alias_map)
    for key in ("Column", "Measure"):
        if key not in expr:
            continue
        source_ref = expr[key].get("Expression", {}).get("SourceRef", {})
        entity = source_ref.get("Entity")
        if entity is None:
            entity = alias_map.get(source_ref.get("Source", ""), "?")
        prop = expr[key].get("Property", "?")
        return entity, prop
    return "?", "?"


def _now_expr() -> dict:
    return {"Now": {}}


def _date_add_expr(expression: dict, amount: int, time_unit: int) -> dict:
    return {
        "DateAdd": {
            "Expression": expression,
            "Amount": amount,
            "TimeUnit": time_unit,
        }
    }


def _date_span_expr(expression: dict, time_unit: int) -> dict:
    return {
        "DateSpan": {
            "Expression": expression,
            "TimeUnit": time_unit,
        }
    }


def _is_now_expr(node: dict) -> bool:
    return node == {"Now": {}}


def _parse_date_add(node: dict) -> tuple[dict, int, int] | None:
    date_add = node.get("DateAdd")
    if not isinstance(date_add, dict):
        return None
    return (
        date_add.get("Expression", {}),
        date_add.get("Amount"),
        date_add.get("TimeUnit"),
    )


def _time_unit_name(unit_code: int | None) -> str | None:
    for name, code in {**DATE_UNIT_CODES, **TIME_UNIT_CODES}.items():
        if code == unit_code:
            return name
    return None


def _field_expr(entity: str, prop: str, field_type: str, source_name: str) -> dict:
    """Build a semantic query field expression container."""
    field_key = "Column" if field_type == "column" else "Measure"
    source_key = "Entity" if source_name == entity else "Source"
    return {
        field_key: {
            "Expression": {"SourceRef": {source_key: source_name}},
            "Property": prop,
        }
    }


def _literal_expr(value: str, data_type: str | None = None) -> dict:
    """Build a semantic query literal expression from CLI text."""
    return {"Literal": {"Value": _format_literal(value, data_type=data_type)}}


def _format_literal(value: str, data_type: str | None = None) -> str:
    """Format a CLI literal for semanticQuery."""
    raw = value.strip()
    normalized_type = (data_type or "").lower()

    if raw.lower() == "true":
        return "true"
    if raw.lower() == "false":
        return "false"
    if raw.lower() == "null":
        return "null"

    if normalized_type in {"date", "datetime", "datetimeoffset"}:
        if "T" in raw:
            return f"datetime'{raw}'"
        return f"datetime'{raw}T00:00:00'"

    if normalized_type in {"int64", "int32", "integer", "whole", "whole number"}:
        if re.fullmatch(r"-?\d+", raw):
            return f"{raw}L"

    if normalized_type in {"decimal", "currency"}:
        if re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
            return _format_double_literal(raw, force_fraction=True)

    if normalized_type in {"double", "number"}:
        if re.fullmatch(r"-?\d+(?:\.\d+)?", raw):
            return _format_double_literal(raw)

    escaped = raw.replace("'", "''")
    return f"'{escaped}'"


def _decode_literal_expr(node: dict) -> str:
    """Decode a semantic query literal node into display text."""
    if "Literal" not in node:
        return str(node)
    raw = node["Literal"].get("Value", "?")
    if raw.startswith("datetime'") and raw.endswith("'"):
        return raw[len("datetime'"):-1]
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1].replace("''", "'")
    if raw.endswith(("D", "L", "M")):
        return raw[:-1]
    return raw


def _looks_like_date(value: str) -> bool:
    return bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", value)
    )


def _looks_like_number(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", value))


def _format_double_literal(raw: str, *, force_fraction: bool = False) -> str:
    if force_fraction and "." not in raw:
        raw = f"{raw}.0"
    return f"{raw}D"
