"""Slicer sync groups (``sync``) and saved default selections (``selected``).

The shapes come from the Desktop-built report-04 fixture (see its SPEC.md,
"What The Build Showed", #42):

- A synced slicer carries ``visual.syncGroup`` with ``groupName``,
  ``fieldChanges`` and ``filterChanges``. A slicer synced to a page where it
  isn't visible is an ordinary slicer with ``isHidden: true`` in the same group.
- A saved selection lives in ``objects.general[0].properties.filter.filter`` as
  a Version 2 query over the slicer's field, aliased by the entity's first
  letter:

  - single and multi select: ``In``;
  - "all except": ``Not(In)`` plus ``data.isInvertedSelectionMode: true``;
  - a date range: ``>= start`` ``And`` ``< end + 1 day``, with
    ``data.startDate`` / ``data.endDate`` / ``data.mode: 'Between'``.

YAML form::

    sync: PortfolioSync            # field and filter changes both synced
    sync: {group: PortfolioSync, fields: true, filters: false}

    selected: [In progress, Blocked]
    selected: {except: [Design]}
    selected: {from: 2024-03-01, to: 2025-06-30}
    selected: null                 # clear the saved selection
"""

from __future__ import annotations

import copy
import datetime as dt
import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

# Visual types Desktop has shown sync groups and saved selections for.
SLICER_TYPES = ("slicer",)

# ``data`` properties a saved selection owns.
SELECTION_DATA_PROPS = ("isInvertedSelectionMode", "startDate", "endDate")

_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DATETIME_LITERAL = re.compile(r"datetime'(\d{4}-\d{2}-\d{2})T00:00:00'")
_INTEGER_LITERAL = re.compile(r"-?\d+L")
_DECIMAL_LITERAL = re.compile(r"-?\d+(?:\.\d+)?[DM]")
_DATE_TYPES = frozenset({"date", "datetime", "datetimeoffset"})
# Model data types a selection literal is typed by. Anything else (a calculated
# column Desktop saved without a dataType is "unknown") is typed by the value.
_KNOWN_TYPES = frozenset({"string", "boolean", "int64", "double", "decimal", "currency"}) | _DATE_TYPES
_NUMBER_TEXT = re.compile(r"-?\d+(?:\.\d+)?")
_COMPARISON_GE = 2
_COMPARISON_LT = 3


# --- sync groups --------------------------------------------------------------


def parse_sync_spec(spec: Any) -> dict[str, Any] | None:
    """Turn a ``sync`` value into a ``syncGroup`` dict (``None`` removes it).

    Raises ``ValueError`` on an invalid spec.
    """
    if spec is None:
        return None
    if isinstance(spec, str):
        group, fields, filters = spec, True, True
    elif isinstance(spec, Mapping):
        unknown = set(spec) - {"group", "fields", "filters"}
        if unknown:
            raise ValueError(
                f"sync: unknown key(s) {', '.join(sorted(map(str, unknown)))} (expected group, fields, filters)."
            )
        group = spec.get("group")
        fields = spec.get("fields", True)
        filters = spec.get("filters", True)
        for key, value in (("fields", fields), ("filters", filters)):
            if not isinstance(value, bool):
                raise ValueError(f"sync.{key} must be true or false, not {value!r}.")
    else:
        raise ValueError("sync must be a group name or a mapping with group, fields and filters.")
    if not isinstance(group, str) or not group.strip():
        raise ValueError("sync needs a non-empty group name.")
    return {"groupName": group.strip(), "fieldChanges": fields, "filterChanges": filters}


def apply_sync_group(visual_data: dict, spec: Any) -> bool:
    """Write or remove ``visual.syncGroup``. Returns whether anything changed."""
    group = parse_sync_spec(spec)
    visual = visual_data.setdefault("visual", {})
    if group is None:
        return visual.pop("syncGroup", None) is not None
    if visual.get("syncGroup") == group:
        return False
    visual["syncGroup"] = group
    return True


def export_sync_group(visual_data: Mapping[str, Any]) -> Any:
    """Return the ``sync`` YAML value for a visual, or ``None``.

    ``None`` also covers a ``syncGroup`` this module can't express (extra keys,
    non-boolean flags); that one stays in the ``pbir`` passthrough.
    """
    if visual_data.get("visual", {}).get("visualType") not in SLICER_TYPES:
        return None  # apply would reject `sync` here, so keep it in pbir
    return _sync_yaml(visual_data.get("visual", {}).get("syncGroup"))


def _sync_yaml(group: Any) -> Any:
    """``sync`` YAML for a ``syncGroup`` dict, or ``None`` if it can't be expressed."""
    if not isinstance(group, Mapping) or set(group) != {"groupName", "fieldChanges", "filterChanges"}:
        return None
    name = group["groupName"]
    fields = group["fieldChanges"]
    filters = group["filterChanges"]
    if not isinstance(name, str) or not name or not isinstance(fields, bool) or not isinstance(filters, bool):
        return None
    if fields and filters:
        return name
    return {"group": name, "fields": fields, "filters": filters}


def normalize_sync_spec(spec: Any) -> Any:
    """Canonical ``sync`` value for comparison (``pbi diff``)."""
    try:
        group = parse_sync_spec(spec)
    except ValueError:
        return spec
    if group is None:
        return None
    return _sync_yaml(group)


# --- saved selections ---------------------------------------------------------


def slicer_field(visual_data: Mapping[str, Any]) -> tuple[str, str] | None:
    """Return ``(entity, column)`` of the slicer's single bound column, if any."""
    projections = (
        visual_data.get("visual", {}).get("query", {}).get("queryState", {}).get("Values", {}).get("projections", [])
    )
    columns = []
    for projection in projections if isinstance(projections, list) else []:
        node = projection.get("field", {}).get("Column") if isinstance(projection, Mapping) else None
        if not isinstance(node, Mapping):
            return None  # a measure, hierarchy or aggregation: not a plain column slicer
        entity = node.get("Expression", {}).get("SourceRef", {}).get("Entity")
        prop = node.get("Property")
        if isinstance(entity, str) and isinstance(prop, str):
            columns.append((entity, prop))
    return columns[0] if len(columns) == 1 else None


def apply_slicer_selection(
    visual_data: dict,
    spec: Any,
    *,
    data_type: str | None,
) -> tuple[bool, list[str]]:
    """Write or clear the saved selection of a slicer.

    ``data_type`` is the bound column's model data type (``None`` without a
    model, in which case values are typed by their YAML type). Returns whether
    anything changed and a list of warnings. Raises ``ValueError`` before
    changing anything.
    """
    kind, payload = _parse_selection_spec(spec)
    if data_type is not None and data_type.lower() not in _KNOWN_TYPES:
        data_type = None
    field = slicer_field(visual_data)
    if field is None and kind != "clear":
        raise ValueError("selected: the slicer needs exactly one bound column (Values) to save a selection.")

    before = copy.deepcopy(visual_data.get("visual", {}).get("objects"))
    # Read-only until everything is validated; the real dict is fetched to write.
    objects = visual_data.get("visual", {}).get("objects") or {}
    warnings: list[str] = []

    if kind == "clear":
        general = _plain_entry(objects, "general", create=False)
        if general is not None:
            general.get("properties", {}).pop("filter", None)
        data = _plain_entry(objects, "data", create=False)
        if data is not None:
            for name in SELECTION_DATA_PROPS:
                data.get("properties", {}).pop(name, None)
        return objects != (before or {}), warnings

    entity, prop = field  # type: ignore[misc]
    alias = _alias(entity)
    column = {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}}
    # Data properties to set (a value) or remove (None).
    data_updates: dict[str, dict | None]

    if kind == "range":
        if data_type is not None and data_type.lower() not in _DATE_TYPES:
            raise ValueError(f"selected: from/to needs a date column; {entity}.{prop} is {data_type}.")
        start, end = payload
        condition: dict[str, Any] = {
            "And": {
                "Left": _comparison(column, _COMPARISON_GE, _date_literal(start)),
                "Right": _comparison(column, _COMPARISON_LT, _date_literal(end + dt.timedelta(days=1))),
            }
        }
        data_updates = {
            "isInvertedSelectionMode": None,
            "startDate": _literal_expr(_date_literal(start)),
            "endDate": _literal_expr(_date_literal(end)),
            "mode": _literal_expr("'Between'"),
        }
    else:
        values = [[{"Literal": {"Value": _value_literal(value, data_type, entity, prop)}}] for value in payload]
        condition = {"In": {"Expressions": [column], "Values": values}}
        data_updates = {"startDate": None, "endDate": None, "isInvertedSelectionMode": None}
        if kind == "except":
            condition = {"Not": {"Expression": condition}}
            data_updates["isInvertedSelectionMode"] = _literal_expr("true")
        data = _plain_entry(objects, "data", create=False)
        mode = _literal_value(data.get("properties", {}).get("mode")) if data else None
        if mode in {"'Between'", "'Before'", "'After'", "'Relative'", "'RelativeTime'"}:
            warnings.append(
                f"selected: the slicer is in {mode.strip(chr(39))} mode; set data.mode to Basic or Dropdown "
                "for a list selection to show."
            )
        if _literal_value(_selection_property(objects, "strictSingleSelect")) == "true" and (
            kind == "except" or len(payload) > 1
        ):
            warnings.append("selected: the slicer is single select, so Desktop keeps only one value.")

    objects = visual_data.setdefault("visual", {}).setdefault("objects", {})
    data_props = _plain_entry(objects, "data", create=True).setdefault("properties", {})
    for name, value in data_updates.items():
        if value is None:
            data_props.pop(name, None)
        else:
            data_props[name] = value
    query = {
        "Version": 2,
        "From": [{"Name": alias, "Entity": entity, "Type": 0}],
        "Where": [{"Condition": condition}],
    }
    general_props = _plain_entry(objects, "general", create=True).setdefault("properties", {})
    general_props["filter"] = {"filter": query}
    return objects != (before or {}), warnings


def export_slicer_selection(visual_data: Mapping[str, Any]) -> tuple[bool, Any]:
    """Read a saved selection back into ``selected`` form.

    Returns ``(found, value)``. ``found`` is False when there is no saved
    selection or when its shape isn't one Desktop was seen to write (that one
    stays in the ``pbir`` passthrough).
    """
    if visual_data.get("visual", {}).get("visualType") not in SLICER_TYPES:
        return False, None  # apply would reject `selected` here, so keep it in pbir
    field = slicer_field(visual_data)
    objects = visual_data.get("visual", {}).get("objects", {})
    if field is None or not isinstance(objects, Mapping):
        return False, None
    general = _plain_entry(objects, "general", create=False)
    wrapper = general.get("properties", {}).get("filter") if general else None
    if not isinstance(wrapper, Mapping) or set(wrapper) != {"filter"}:
        return False, None
    query = wrapper["filter"]
    if not isinstance(query, Mapping) or query.get("Version") != 2:
        return False, None
    sources = query.get("From")
    where = query.get("Where")
    if not (isinstance(sources, list) and len(sources) == 1 and isinstance(where, list) and len(where) == 1):
        return False, None
    source = sources[0]
    entity, prop = field
    if not isinstance(source, Mapping) or source.get("Entity") != entity or source.get("Type") != 0:
        return False, None
    alias = source.get("Name")
    condition = where[0].get("Condition") if isinstance(where[0], Mapping) else None
    if not isinstance(condition, Mapping) or not isinstance(alias, str):
        return False, None

    data = _plain_entry(objects, "data", create=False)
    data_props = data.get("properties", {}) if data else {}
    inverted = _literal_value(data_props.get("isInvertedSelectionMode")) == "true"
    column = {"Column": {"Expression": {"SourceRef": {"Source": alias}}, "Property": prop}}

    if set(condition) == {"And"}:
        bounds = _decode_range(condition["And"], column)
        # Apply sets mode Between with a range, so only a Between slicer's range
        # is representable; any other mode keeps its filter in pbir.
        if bounds is None or inverted or _literal_value(data_props.get("mode")) != "'Between'":
            return False, None
        start, end = bounds
        for name, expected in (("startDate", start), ("endDate", end)):
            stored = _literal_value(data_props.get(name))
            if stored is not None and stored != _date_literal(expected):
                return False, None
        return True, {"from": start, "to": end}

    if set(condition) == {"Not"}:
        inner = condition["Not"].get("Expression") if isinstance(condition["Not"], Mapping) else None
        values = _decode_in(inner, column)
        if values is None or not inverted:
            return False, None
        return True, {"except": values}

    values = _decode_in(condition, column)
    if values is None or inverted or data_props.get("startDate") or data_props.get("endDate"):
        return False, None
    return True, values


def without_selection_props(objects: Mapping[str, Any]) -> dict[str, Any]:
    """Copy ``objects`` without what an exported ``selected`` represents.

    That is the saved ``general`` filter and the ``data`` selection properties;
    entries left empty are dropped.
    """
    result = copy.deepcopy(dict(objects))
    for name, props in (("general", ("filter",)), ("data", SELECTION_DATA_PROPS)):
        entry = _plain_entry(result, name, create=False)
        if entry is None:
            continue
        properties = entry.get("properties", {})
        for prop in props:
            properties.pop(prop, None)
        if not properties and set(entry) <= {"properties"}:
            result[name] = [e for e in result[name] if e is not entry]
            if not result[name]:
                result.pop(name)
    return result


def normalize_selection_spec(spec: Any) -> Any:
    """Canonical ``selected`` value for comparison (``pbi diff``).

    Diff has no column types, so number and boolean text is folded to its value
    (``'13'`` and ``13`` compare equal, as apply writes both as ``13L`` on a
    whole-number column). On a text column that folding is diff-only; apply is
    unaffected.
    """
    try:
        kind, payload = _parse_selection_spec(spec)
    except ValueError:
        return spec
    if kind == "clear":
        return None
    if kind == "range":
        return {"from": payload[0].isoformat(), "to": payload[1].isoformat()}
    values = [_diff_value(value) for value in payload]
    return {"except": values} if kind == "except" else values


def _diff_value(value: Any) -> Any:
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if not isinstance(value, str):
        return value
    text = value.strip()
    if text.lower() in {"true", "false"}:
        return text.lower() == "true"
    if _NUMBER_TEXT.fullmatch(text):
        number = Decimal(text)
        return int(number) if number == number.to_integral_value() else float(number)
    return value


# --- helpers ------------------------------------------------------------------


def _parse_selection_spec(spec: Any) -> tuple[str, Any]:
    if spec is None or spec == []:
        return "clear", None
    if isinstance(spec, list):
        return "in", _check_values(spec, "selected")
    if isinstance(spec, Mapping):
        keys = set(spec)
        if keys == {"except"}:
            values = spec["except"]
            if not isinstance(values, list) or not values:
                raise ValueError("selected.except must be a non-empty list of values.")
            return "except", _check_values(values, "selected.except")
        if keys == {"from", "to"}:
            start = _parse_date(spec["from"], "selected.from")
            end = _parse_date(spec["to"], "selected.to")
            if end < start:
                raise ValueError("selected: 'to' is before 'from'.")
            return "range", (start, end)
        raise ValueError("selected must be a list of values, {except: [...]}, or {from: date, to: date}.")
    return "in", _check_values([spec], "selected")


def _check_values(values: list, where: str) -> list:
    for value in values:
        if value is None or isinstance(value, (list, dict)):
            raise ValueError(f"{where}: {value!r} is not a single value.")
    return values


def _parse_date(value: Any, where: str) -> dt.date:
    if isinstance(value, dt.datetime):
        if value.time() != dt.time(0):
            raise ValueError(f"{where}: {value!r} has a time; give a date (YYYY-MM-DD).")
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str) and _DATE.fullmatch(value.strip()):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            pass
    raise ValueError(f"{where}: {value!r} is not a date (YYYY-MM-DD).")


def _alias(entity: str) -> str:
    first = entity[:1].lower()
    return first if first.isalpha() else "s"


def _date_literal(value: dt.date) -> str:
    return f"datetime'{value.isoformat()}T00:00:00'"


def _literal_expr(value: str) -> dict:
    return {"expr": {"Literal": {"Value": value}}}


def _literal_value(node: Any) -> str | None:
    try:
        value = node["expr"]["Literal"]["Value"]
    except (KeyError, TypeError):
        return None
    return value if isinstance(value, str) else None


def _comparison(column: dict, kind: int, literal: str) -> dict:
    return {"Comparison": {"ComparisonKind": kind, "Left": copy.deepcopy(column), "Right": {"Literal": {"Value": literal}}}}


def _value_literal(value: Any, data_type: str | None, entity: str, prop: str) -> str:
    from pbi.filters.expressions import _format_literal

    where = f"selected ({entity}.{prop})"
    column_type = (data_type or _infer_type(value)).lower()
    if column_type == "string":
        text = ("true" if value else "false") if isinstance(value, bool) else str(value)
        return "'" + text.replace("'", "''") + "'"
    if column_type == "boolean":
        text = str(value).strip().lower()
        if text not in {"true", "false"}:
            raise ValueError(f"{where}: {value!r} is not true or false.")
        return text
    if column_type in _DATE_TYPES:
        return _date_literal(_parse_date(value, where))
    text = _number_text(value)
    if text is None:
        raise ValueError(f"{where}: {value!r} is not a number.")
    if column_type == "int64" and "." in text:
        raise ValueError(f"{where}: {value!r} is not a whole number.")
    return _format_literal(text, data_type=column_type)


def _number_text(value: Any) -> str | None:
    """Plain decimal text for a number (never exponent form), or None."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        text = format(Decimal(repr(value)), "f")
    else:
        text = str(value).strip()
    return text if _NUMBER_TEXT.fullmatch(text) else None


def _infer_type(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "int64"
    if isinstance(value, float):
        return "double"
    if isinstance(value, dt.date):
        return "datetime"
    return "string"


def _decode_value(raw: Any) -> Any:
    if not isinstance(raw, str):
        return None
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    if raw in {"true", "false"}:
        return raw == "true"
    if _INTEGER_LITERAL.fullmatch(raw):
        return int(raw[:-1])
    if _DECIMAL_LITERAL.fullmatch(raw):
        digits = raw[:-1]
        if "." not in digits:
            return int(digits)
        number = float(digits)
        try:
            exact = Decimal(repr(number)) == Decimal(digits)
        except InvalidOperation:
            exact = False
        # A value a float can't hold exactly (a long fixed decimal) would change
        # on the way back, so it isn't representable and stays in pbir.
        return number if exact else None
    match = _DATETIME_LITERAL.fullmatch(raw)
    if match:
        return dt.date.fromisoformat(match.group(1))
    return None


def _decode_in(node: Any, column: dict) -> list | None:
    if not isinstance(node, Mapping) or set(node) != {"In"} or not isinstance(node["In"], Mapping):
        return None
    block = node["In"]
    if block.get("Expressions") != [column] or set(block) != {"Expressions", "Values"}:
        return None
    rows = block["Values"]
    if not isinstance(rows, list) or not rows:
        return None
    values = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 1 or not isinstance(row[0], Mapping):
            return None
        value = _decode_value(row[0].get("Literal", {}).get("Value") if set(row[0]) == {"Literal"} else None)
        if value is None:
            return None
        values.append(value)
    return values


def _decode_range(node: Any, column: dict) -> tuple[dt.date, dt.date] | None:
    if not isinstance(node, Mapping) or set(node) != {"Left", "Right"}:
        return None
    bounds = []
    for side, kind in (("Left", _COMPARISON_GE), ("Right", _COMPARISON_LT)):
        comparison = node[side].get("Comparison") if isinstance(node[side], Mapping) else None
        if not isinstance(comparison, Mapping) or comparison.get("ComparisonKind") != kind:
            return None
        if comparison.get("Left") != column:
            return None
        right = comparison.get("Right")
        raw = right.get("Literal", {}).get("Value") if isinstance(right, Mapping) else None
        match = _DATETIME_LITERAL.fullmatch(raw) if isinstance(raw, str) else None
        if match is None:
            return None
        bounds.append(dt.date.fromisoformat(match.group(1)))
    start, end_exclusive = bounds
    end = end_exclusive - dt.timedelta(days=1)
    if end < start:
        return None
    return start, end


def _plain_entry(objects: dict | Mapping, name: str, *, create: bool) -> dict | None:
    """Return the first selector-less entry of an object list."""
    entries = objects.get(name)
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and "selector" not in entry:
                return entry
    if not create:
        return None
    entry: dict = {"properties": {}}
    if isinstance(entries, list):
        entries.insert(0, entry)
    else:
        objects[name] = [entry]  # type: ignore[index]
    return entry


def _selection_property(objects: Mapping[str, Any], name: str) -> Any:
    entry = _plain_entry(objects, "selection", create=False)
    return entry.get("properties", {}).get(name) if entry else None
