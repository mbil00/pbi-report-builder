"""Filter management for PBI reports, pages, and visuals."""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from typing import Any

from pbi.project import Project, _read_json, _write_json


@dataclass
class FilterInfo:
    """Parsed filter for display."""
    name: str
    field_entity: str
    field_prop: str
    filter_type: str
    values: list[str]
    is_hidden: bool
    is_locked: bool
    level: str  # "report", "page", or "visual"


@dataclass(frozen=True)
class TupleField:
    """One field/value pair within a tuple filter row."""

    entity: str
    prop: str
    value: str
    field_type: str = "column"
    data_type: str | None = None


def get_filter_config(data: dict) -> dict:
    """Get the filterConfig from a JSON structure."""
    return data.get("filterConfig", {})


def get_filters(data: dict) -> list[dict]:
    """Get the filters list from a JSON structure."""
    return get_filter_config(data).get("filters", [])


def parse_filter(f: dict, level: str = "") -> FilterInfo:
    """Parse a raw PBI filter dict into a FilterInfo."""
    name = f.get("name", "")
    filter_type = f.get("type", "Unknown")
    is_hidden = f.get("isHiddenInViewMode", False)
    is_locked = f.get("isLockedInViewMode", False)

    # Extract field reference
    field = f.get("field", {})
    entity, prop = _extract_field_ref(field)

    # Extract filter values
    values = _extract_filter_values(f)

    return FilterInfo(
        name=name,
        field_entity=entity,
        field_prop=prop,
        filter_type=filter_type,
        values=values,
        is_hidden=is_hidden,
        is_locked=is_locked,
        level=level,
    )


def add_categorical_filter(
    data: dict,
    entity: str,
    prop: str,
    values: list[str],
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
    data_type: str | None = None,
) -> dict:
    """Add a categorical filter to a JSON structure. Returns the filter dict."""
    return _add_value_filter(
        data,
        entity,
        prop,
        values,
        field_type=field_type,
        filter_type="Categorical",
        how_created="User",
        is_hidden=is_hidden,
        is_locked=is_locked,
        data_type=data_type,
    )


def add_include_filter(
    data: dict,
    entity: str,
    prop: str,
    values: list[str],
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
    data_type: str | None = None,
) -> dict:
    """Add an Include filter to a JSON structure."""
    return _add_value_filter(
        data,
        entity,
        prop,
        values,
        field_type=field_type,
        filter_type="Include",
        how_created="Include",
        is_hidden=is_hidden,
        is_locked=is_locked,
        data_type=data_type,
    )


def add_exclude_filter(
    data: dict,
    entity: str,
    prop: str,
    values: list[str],
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
    data_type: str | None = None,
) -> dict:
    """Add an Exclude filter to a JSON structure."""
    return _add_value_filter(
        data,
        entity,
        prop,
        values,
        field_type=field_type,
        filter_type="Exclude",
        how_created="Exclude",
        is_hidden=is_hidden,
        is_locked=is_locked,
        data_type=data_type,
    )


def _add_value_filter(
    data: dict,
    entity: str,
    prop: str,
    values: list[str],
    *,
    field_type: str,
    filter_type: str,
    how_created: str,
    is_hidden: bool,
    is_locked: bool,
    data_type: str | None = None,
) -> dict:
    """Build a single-field In filter container."""
    filter_name = f"Filter_{secrets.token_hex(8)}"

    field_ref = _field_expr(entity, prop, field_type, entity)
    alias = "f"
    pbi_values = [[_literal_expr(v, data_type=data_type)] for v in values]

    filter_obj = {
        "name": filter_name,
        "type": filter_type,
        "filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": entity, "Type": 0}],
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": [_field_expr(entity, prop, field_type, alias)],
                            "Values": pbi_values,
                        }
                    }
                }
            ],
        },
        "field": field_ref,
        "isHiddenInViewMode": is_hidden,
        "isLockedInViewMode": is_locked,
        "howCreated": how_created,
    }

    config = data.setdefault("filterConfig", {})
    config.setdefault("filters", []).append(filter_obj)
    return filter_obj


def add_tuple_filter(
    data: dict,
    rows: list[list[TupleField]],
    *,
    is_hidden: bool = False,
    is_locked: bool = False,
) -> dict:
    """Add a Tuple filter to a JSON structure."""
    if not rows:
        raise ValueError("Tuple filters require at least one row.")

    first_row = rows[0]
    if not first_row:
        raise ValueError("Tuple filter rows may not be empty.")

    signature = [(f.entity, f.prop, f.field_type) for f in first_row]
    for row in rows[1:]:
        if [(f.entity, f.prop, f.field_type) for f in row] != signature:
            raise ValueError(
                "All tuple rows must reference the same fields in the same order."
            )

    alias_map: dict[str, str] = {}
    sources = []
    for entity, _prop, _field_type in signature:
        if entity not in alias_map:
            alias = f"f{len(alias_map)}"
            alias_map[entity] = alias
            sources.append({"Name": alias, "Entity": entity, "Type": 0})

    expressions = [
        _field_expr(entity, prop, field_type, alias_map[entity])
        for entity, prop, field_type in signature
    ]
    values = [
        [_literal_expr(field.value, data_type=field.data_type) for field in row]
        for row in rows
    ]

    filter_obj = {
        "name": f"Filter_{secrets.token_hex(8)}",
        "type": "Tuple",
        "filter": {
            "Version": 2,
            "From": sources,
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": expressions,
                            "Values": values,
                        }
                    }
                }
            ],
        },
        "isHiddenInViewMode": is_hidden,
        "isLockedInViewMode": is_locked,
        "howCreated": "User",
    }

    config = data.setdefault("filterConfig", {})
    config.setdefault("filters", []).append(filter_obj)
    return filter_obj


def add_range_filter(
    data: dict,
    entity: str,
    prop: str,
    min_val: str | None = None,
    max_val: str | None = None,
    field_type: str = "column",
    is_hidden: bool = False,
    data_type: str | None = None,
) -> dict:
    """Add a range filter (between min and max). Returns the filter dict."""
    filter_name = f"Filter_{secrets.token_hex(8)}"

    field_ref = _field_expr(entity, prop, field_type, entity)

    # Build conditions
    conditions = []
    col_expr = _field_expr(entity, prop, field_type, "f")

    if min_val is not None:
        conditions.append({
            "Condition": {
                "Comparison": {
                    "ComparisonKind": 2,  # GreaterThanOrEqual
                    "Left": col_expr,
                    "Right": _literal_expr(min_val, data_type=data_type),
                }
            }
        })

    if max_val is not None:
        conditions.append({
            "Condition": {
                "Comparison": {
                    "ComparisonKind": 4,  # LessThanOrEqual
                    "Left": col_expr,
                    "Right": _literal_expr(max_val, data_type=data_type),
                }
            }
        })

    filter_obj = {
        "name": filter_name,
        "type": "Advanced",
        "filter": {
            "Version": 2,
            "From": [{"Name": "f", "Entity": entity, "Type": 0}],
            "Where": conditions,
        },
        "field": field_ref,
        "isHiddenInViewMode": is_hidden,
        "isLockedInViewMode": False,
        "howCreated": "User",
    }

    config = data.setdefault("filterConfig", {})
    config.setdefault("filters", []).append(filter_obj)
    return filter_obj


def add_topn_filter(
    data: dict,
    entity: str,
    prop: str,
    n: int,
    order_entity: str,
    order_prop: str,
    order_field_type: str = "measure",
    direction: str = "Top",
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
) -> dict:
    """Add a Top N filter using the schema-backed subquery form."""
    if field_type != "column":
        raise ValueError("Top N filters currently require a column target field.")
    if n <= 0:
        raise ValueError("Top N filters require a positive --topn value.")
    if direction not in {"Top", "Bottom"}:
        raise ValueError("Top N direction must be 'Top' or 'Bottom'.")

    filter_name = f"Filter_{secrets.token_hex(8)}"
    field_ref = _field_expr(entity, prop, field_type, entity)

    target_alias = "c1"
    order_alias = target_alias if order_entity == entity else "o"
    outer_subquery_alias = "subquery"
    sort_direction = 2 if direction == "Top" else 1

    subquery_sources = [{"Name": target_alias, "Entity": entity, "Type": 0}]
    if order_alias != target_alias:
        subquery_sources.append({"Name": order_alias, "Entity": order_entity, "Type": 0})

    subquery = {
        "Version": 2,
        "From": subquery_sources,
        "Select": [
            {
                **_field_expr(entity, prop, field_type, target_alias),
                "Name": "field",
            }
        ],
        "OrderBy": [
            {
                "Direction": sort_direction,
                "Expression": _field_expr(
                    order_entity,
                    order_prop,
                    order_field_type,
                    order_alias,
                ),
            }
        ],
        "Top": n,
    }

    filter_obj = {
        "name": filter_name,
        "field": field_ref,
        "type": "TopN",
        "filter": {
            "Version": 2,
            "From": [
                {
                    "Name": outer_subquery_alias,
                    "Expression": {"Subquery": {"Query": subquery}},
                    "Type": 2,
                },
                {
                    "Name": target_alias,
                    "Entity": entity,
                    "Type": 0,
                },
            ],
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": [
                                _field_expr(entity, prop, field_type, target_alias)
                            ],
                            "Table": {
                                "SourceRef": {
                                    "Source": outer_subquery_alias,
                                }
                            },
                        }
                    }
                }
            ],
        },
        "isHiddenInViewMode": is_hidden,
        "isLockedInViewMode": is_locked,
    }

    config = data.setdefault("filterConfig", {})
    config.setdefault("filters", []).append(filter_obj)
    return filter_obj


def add_relative_date_filter(
    data: dict,
    entity: str,
    prop: str,
    operator: str = "InLast",
    time_units_count: int = 7,
    time_unit_type: str = "Days",
    include_today: bool = True,
    field_type: str = "column",
    is_hidden: bool = False,
) -> dict:
    """Relative date filter creation is intentionally blocked.

    Power BI supports relative date filters, but the current PBIR schema references
    in this project do not expose a schema-valid query expression shape for the
    implementation that used to be emitted here. Refuse to write malformed JSON instead.
    """
    raise NotImplementedError(
        "Relative date filters are not emitted by this CLI because the previous "
        "writer did not match Microsoft’s published PBIR semanticQuery schema."
    )


def remove_filter(data: dict, identifier: str) -> int:
    """Remove filter(s) by name or field reference. Returns count removed."""
    config = data.get("filterConfig", {})
    filters = config.get("filters", [])
    if not filters:
        return 0

    id_lower = identifier.lower()
    original = len(filters)

    config["filters"] = [
        f for f in filters
        if not _filter_matches(f, id_lower)
    ]

    return original - len(config["filters"])


def _filter_matches(f: dict, identifier: str) -> bool:
    """Check if a filter matches the given identifier."""
    if f.get("name", "").lower() == identifier:
        return True
    field = f.get("field", {})
    entity, prop = _extract_field_ref(field)
    field_ref = f"{entity}.{prop}".lower()
    return field_ref == identifier


def _extract_field_ref(field: dict) -> tuple[str, str]:
    """Extract (entity, property) from a PBI field reference."""
    for key in ("Column", "Measure"):
        if key in field:
            entity = field[key].get("Expression", {}).get("SourceRef", {}).get("Entity", "?")
            prop = field[key].get("Property", "?")
            return entity, prop
    return "?", "?"


def _extract_filter_values(f: dict) -> list[str]:
    """Extract human-readable values from a filter."""
    values = []
    filter_data = f.get("filter", {})
    where = filter_data.get("Where", [])

    if f.get("type") == "TopN":
        summary = _extract_topn_summary(filter_data)
        if summary:
            values.append(summary)

    for clause in where:
        cond = clause.get("Condition", {})

        # Categorical: In condition
        if "In" in cond:
            tuple_values = []
            for val_list in cond["In"].get("Values", []):
                decoded = [_decode_literal_expr(val) for val in val_list]
                if len(decoded) == 1:
                    values.append(decoded[0])
                else:
                    tuple_values.append("(" + ", ".join(decoded) + ")")
            values.extend(tuple_values)

        # Range: Comparison conditions
        if "Comparison" in cond:
            comp = cond["Comparison"]
            kind = comp.get("ComparisonKind", 0)
            right = comp.get("Right", {})
            literal = _decode_literal_expr(right)
            op_map = {0: "==", 1: ">", 2: ">=", 3: "<", 4: "<="}
            op = op_map.get(kind, "?")
            values.append(f"{op} {literal}")

        # TopN
        if "Top" in cond:
            top = cond["Top"]
            count = top.get("Count", "?")
            order_by = top.get("OrderBy", [{}])
            direction_code = order_by[0].get("Direction", 2) if order_by else 2
            direction = "top" if direction_code == 2 else "bottom"
            values.append(f"{direction} {count}")

        # RelativeDate
        if "RelativeDate" in cond:
            rd = cond["RelativeDate"]
            op_map = {0: "in last", 1: "in this", 2: "in next"}
            unit_map = {0: "days", 1: "weeks", 2: "months", 3: "quarters", 4: "years"}
            op = op_map.get(rd.get("Operator", 0), "?")
            count = rd.get("TimeUnitsCount", "?")
            unit = unit_map.get(rd.get("TimeUnitType", 0), "?")
            values.append(f"{op} {count} {unit}")

    return values


def _extract_topn_summary(filter_data: dict) -> str | None:
    """Extract a short display summary for a schema-backed Top N filter."""
    subquery = None
    for source in filter_data.get("From", []):
        if source.get("Type") == 2:
            subquery = (
                source.get("Expression", {})
                .get("Subquery", {})
                .get("Query", {})
            )
            if subquery:
                break

    if not subquery:
        return None

    count = subquery.get("Top")
    if count is None:
        return None

    alias_map = {
        source.get("Name"): source.get("Entity")
        for source in subquery.get("From", [])
        if source.get("Name") and source.get("Entity")
    }
    order_items = subquery.get("OrderBy", [])
    direction = "top"
    order_label = None
    if order_items:
        order_item = order_items[0]
        direction = "top" if order_item.get("Direction", 2) == 2 else "bottom"
        order_entity, order_prop = _extract_expression_ref(
            order_item.get("Expression", {}),
            alias_map=alias_map,
        )
        if order_entity != "?" and order_prop != "?":
            order_label = f"{order_entity}.{order_prop}"

    summary = f"{direction} {count}"
    if order_label:
        summary += f" by {order_label}"
    return summary


def _extract_expression_ref(
    expr: dict,
    *,
    alias_map: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Extract an entity/property reference from a query expression."""
    alias_map = alias_map or {}
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

    if normalized_type in {"date", "datetime", "datetimeoffset"} or _looks_like_date(raw):
        if "T" in raw:
            return f"datetime'{raw}'"
        return f"datetime'{raw}T00:00:00'"

    if normalized_type in {"int64", "int32", "integer", "whole", "whole number"}:
        if re.fullmatch(r"-?\d+", raw):
            return f"{raw}L"

    if normalized_type in {"double", "decimal", "currency", "number"} or _looks_like_number(raw):
        return f"{raw}D"

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
    if raw.endswith("D") or raw.endswith("L"):
        return raw[:-1]
    return raw


def _looks_like_date(value: str) -> bool:
    return bool(
        re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?", value)
    )


def _looks_like_number(value: str) -> bool:
    return bool(re.fullmatch(r"-?\d+(?:\.\d+)?", value))


# ── Level-aware load/save ──────────────────────────────────────

def load_level_data(
    project: Project,
    page_name: str | None = None,
    visual_name: str | None = None,
) -> tuple[dict, str, Any]:
    """Load the JSON data for the specified filter level.

    Returns (data_dict, level_label, save_target).
    save_target is the object with a .save() method, or a Path for report.
    """
    if visual_name and page_name:
        page = project.find_page(page_name)
        visual = project.find_visual(page, visual_name)
        return visual.data, "visual", visual
    elif page_name:
        page = project.find_page(page_name)
        return page.data, "page", page
    else:
        path = project.definition_folder / "report.json"
        data = _read_json(path) if path.exists() else {}
        return data, "report", path


def save_level_data(data: dict, save_target: Any) -> None:
    """Save data back to the appropriate level."""
    if hasattr(save_target, "save"):
        save_target.data = data
        save_target.save()
    else:
        # save_target is a Path (report.json)
        _write_json(save_target, data)
