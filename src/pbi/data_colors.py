"""Fixed data colours per category value or measure series (``seriesColors``).

The shapes come from the Desktop-built report-04 fixture (see its SPEC.md,
"What The Build Showed", #41):

- A category or legend value is a ``dataPoint`` entry whose selector is
  ``data[0].scopeId.Comparison`` (``ComparisonKind: 0``) of the column against
  a literal typed by the column: text ``'Completed'``, boolean ``true``,
  whole number ``13L``.
- A measure series is a ``dataPoint`` entry with ``selector.metadata`` set to
  the measure's queryRef.
- The colour is ``fill.solid.color`` as a quoted uppercase hex literal.

YAML form, keyed by field::

    seriesColors:
      Task.Status:
        Completed: "#20A741"
        In progress: "#F2A900"
      Measures Table.Estimate Hours: "#A0C4FF"

A ``null`` colour removes the entry.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

# Column data types Desktop has shown a scope literal for.
SUPPORTED_COLUMN_TYPES = ("string", "boolean", "int64")

_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")
_INTEGER = re.compile(r"-?\d+")
_INTEGER_LITERAL = re.compile(r"-?\d+L")

FieldResolver = Callable[[str], tuple[str, str, str, str | None]]
"""Resolve ``Table.Field`` to ``(entity, prop, "column" | "measure", data_type)``."""


def apply_series_colors(
    visual_data: dict,
    spec: Any,
    *,
    resolve_field: FieldResolver,
) -> tuple[int, list[str]]:
    """Write ``seriesColors`` into ``visual.objects.dataPoint``.

    Returns the number of colours written or removed and a list of warnings.
    Raises ``ValueError`` on an invalid spec before changing anything.
    """
    if not isinstance(spec, Mapping):
        raise ValueError("seriesColors must be a mapping of Table.Field to colours.")

    planned: list[tuple[dict, str | None]] = []
    resolved_refs: dict[str, str] = {}
    for field_ref, value in spec.items():
        if not isinstance(field_ref, str) or "." not in field_ref:
            raise ValueError(f"seriesColors key {field_ref!r} must be a Table.Field reference.")
        entity, prop, field_type, data_type = resolve_field(field_ref)
        resolved_refs[field_ref] = f"{entity}.{prop}"
        if field_type == "measure":
            if isinstance(value, Mapping):
                raise ValueError(
                    f"seriesColors.{field_ref} is a measure; give it one colour, not a mapping of values."
                )
            planned.append(({"metadata": f"{entity}.{prop}"}, _normalize_color(value, field_ref)))
            continue

        if not isinstance(value, Mapping):
            raise ValueError(
                f"seriesColors.{field_ref} is a column; give it a mapping of value to colour."
            )
        column_type = _column_literal_type(data_type, value, field_ref)
        for raw_value, color in value.items():
            literal = _scope_literal(raw_value, column_type, field_ref)
            selector = {"data": [{"scopeId": _scope_comparison(entity, prop, literal)}]}
            planned.append((selector, _normalize_color(color, f"{field_ref}[{raw_value}]")))

    entries = visual_data.setdefault("visual", {}).setdefault("objects", {}).setdefault("dataPoint", [])
    changes = 0
    for selector, color in planned:
        index = _find_entry(entries, selector)
        if color is None:
            if index is None:
                continue
            properties = entries[index].get("properties", {})
            properties.pop("fill", None)
            if not properties:
                entries.pop(index)
            changes += 1
            continue
        fill = {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}}
        if index is None:
            entries.append({"properties": {"fill": fill}, "selector": selector})
        else:
            entries[index].setdefault("properties", {})["fill"] = fill
        changes += 1

    objects = visual_data["visual"]["objects"]
    if not objects["dataPoint"]:
        objects.pop("dataPoint")

    return changes, _unbound_field_warnings(visual_data, resolved_refs)


def export_series_colors(visual_data: Mapping[str, Any]) -> tuple[dict[str, Any], list[int]]:
    """Read value-scoped ``dataPoint`` fills back into ``seriesColors`` form.

    Returns the YAML mapping and the indexes of the ``dataPoint`` entries it
    represents. Only entries holding nothing but a hex ``fill`` with a
    Desktop-sampled selector are taken; everything else stays in ``pbir:``.
    Measure-series entries are left to the generic ``chart:dataPoint.fill [..]``
    export, which already round-trips them.
    """
    entries = visual_data.get("visual", {}).get("objects", {}).get("dataPoint", [])
    result: dict[str, Any] = {}
    taken: list[int] = []
    if not isinstance(entries, list):
        return result, taken

    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            continue
        properties = entry.get("properties")
        if not isinstance(properties, Mapping) or set(properties) != {"fill"}:
            continue
        color = _decode_fill(properties["fill"])
        scope = _decode_scope_selector(entry.get("selector"))
        if color is None or scope is None:
            continue
        field_ref, value = scope
        values = result.setdefault(field_ref, {})
        if value in values:
            continue  # a duplicate selector can't be expressed in a mapping
        values[value] = color
        taken.append(index)

    return result, taken


def _column_literal_type(data_type: str | None, values: Mapping, field_ref: str) -> str:
    if data_type is None:
        # No model to read the column type from: infer it from the YAML keys.
        keys = list(values)
        if keys and all(isinstance(key, bool) for key in keys):
            return "boolean"
        if keys and all(isinstance(key, int) and not isinstance(key, bool) for key in keys):
            return "int64"
        return "string"
    normalized = data_type.lower()
    if normalized not in SUPPORTED_COLUMN_TYPES:
        raise ValueError(
            f"seriesColors.{field_ref}: columns of type {data_type} aren't supported yet "
            f"(supported: {', '.join(SUPPORTED_COLUMN_TYPES)}). Use a pbir: passthrough for now."
        )
    return normalized


def _scope_literal(value: Any, column_type: str, field_ref: str) -> str:
    if column_type == "string":
        if isinstance(value, bool):
            text = "true" if value else "false"
        else:
            text = str(value)
        return "'" + text.replace("'", "''") + "'"
    if column_type == "boolean":
        if isinstance(value, bool):
            return "true" if value else "false"
        text = str(value).strip().lower()
        if text in {"true", "false"}:
            return text
        raise ValueError(f"seriesColors.{field_ref}: {value!r} is not a boolean value (true or false).")
    # int64
    if isinstance(value, int) and not isinstance(value, bool):
        return f"{value}L"
    text = str(value).strip()
    if _INTEGER.fullmatch(text):
        return f"{text}L"
    raise ValueError(f"seriesColors.{field_ref}: {value!r} is not a whole number.")


def _scope_comparison(entity: str, prop: str, literal: str) -> dict:
    return {
        "Comparison": {
            "ComparisonKind": 0,
            "Left": {
                "Column": {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop,
                }
            },
            "Right": {"Literal": {"Value": literal}},
        }
    }


def _normalize_color(value: Any, where: str) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not _HEX_COLOR.fullmatch(text):
        raise ValueError(f"seriesColors.{where}: {value!r} is not a #RRGGBB colour.")
    return text.upper()


def _find_entry(entries: list, selector: dict) -> int | None:
    for index, entry in enumerate(entries):
        if isinstance(entry, Mapping) and entry.get("selector") == selector:
            return index
    return None


def _decode_fill(fill: Any) -> str | None:
    try:
        raw = fill["solid"]["color"]["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    if not isinstance(raw, str) or len(raw) < 2 or raw[0] != "'" or raw[-1] != "'":
        return None
    color = raw[1:-1]
    return color.upper() if _HEX_COLOR.fullmatch(color) else None


def _decode_scope_selector(selector: Any) -> tuple[str, Any] | None:
    """Return ``(Table.Column, value)`` for a single-column equality scope."""
    if not isinstance(selector, Mapping) or set(selector) != {"data"}:
        return None
    data = selector["data"]
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], Mapping):
        return None
    if set(data[0]) != {"scopeId"}:
        return None
    comparison = data[0]["scopeId"].get("Comparison") if isinstance(data[0]["scopeId"], Mapping) else None
    if not isinstance(comparison, Mapping) or comparison.get("ComparisonKind") != 0:
        return None
    try:
        column = comparison["Left"]["Column"]
        entity = column["Expression"]["SourceRef"]["Entity"]
        prop = column["Property"]
        raw = comparison["Right"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    if not all(isinstance(part, str) for part in (entity, prop, raw)):
        return None
    value = _decode_scope_literal(raw)
    if value is None:
        return None
    return f"{entity}.{prop}", value


def _decode_scope_literal(raw: str) -> Any:
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if raw in {"true", "false"}:
        return raw == "true"
    if _INTEGER_LITERAL.fullmatch(raw):
        return int(raw[:-1])
    return None


def _unbound_field_warnings(visual_data: Mapping[str, Any], resolved_refs: Mapping[str, str]) -> list[str]:
    bound: set[str] = set()
    query_state = visual_data.get("visual", {}).get("query", {}).get("queryState", {})
    if isinstance(query_state, Mapping):
        for role in query_state.values():
            for projection in role.get("projections", []) if isinstance(role, Mapping) else []:
                for key in ("Column", "Measure"):
                    node = projection.get("field", {}).get(key) if isinstance(projection, Mapping) else None
                    if isinstance(node, Mapping):
                        entity = node.get("Expression", {}).get("SourceRef", {}).get("Entity")
                        bound.add(f"{entity}.{node.get('Property')}")
    warnings = []
    for field_ref, resolved in resolved_refs.items():
        if resolved not in bound:
            warnings.append(
                f"seriesColors.{field_ref}: field isn't bound to this visual, so the colours have no effect."
            )
    return warnings
