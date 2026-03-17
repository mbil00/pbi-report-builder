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


DATE_UNIT_CODES = {
    "Days": 0,
    "Weeks": 1,
    "Months": 2,
    "Quarters": 3,
    "Years": 4,
}

TIME_UNIT_CODES = {
    "Minutes": 6,
    "Hours": 7,
}


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


def add_empty_categorical_filter(
    data: dict,
    entity: str,
    prop: str,
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
) -> dict:
    """Add an empty categorical filter (field in filter pane, no pre-selections)."""
    filter_name = f"Filter_{secrets.token_hex(8)}"
    field_ref = _field_expr(entity, prop, field_type, entity)

    filter_obj = {
        "name": filter_name,
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "f", "Entity": entity, "Type": 0}],
            "Where": [],
        },
        "field": field_ref,
        "isHiddenInViewMode": is_hidden,
        "isLockedInViewMode": is_locked,
        "howCreated": "User",
    }

    config = data.setdefault("filterConfig", {})
    config.setdefault("filters", []).append(filter_obj)
    return filter_obj


def add_blank_filter(
    data: dict,
    entity: str,
    prop: str,
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
) -> dict:
    """Add a filter that shows only blank/null values."""
    return _add_null_filter(
        data, entity, prop,
        field_type=field_type,
        is_blank=True,
        is_hidden=is_hidden,
        is_locked=is_locked,
    )


def add_not_blank_filter(
    data: dict,
    entity: str,
    prop: str,
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
) -> dict:
    """Add a filter that hides blank/null values (show only non-blank)."""
    return _add_null_filter(
        data, entity, prop,
        field_type=field_type,
        is_blank=False,
        is_hidden=is_hidden,
        is_locked=is_locked,
    )


def _add_null_filter(
    data: dict,
    entity: str,
    prop: str,
    *,
    field_type: str,
    is_blank: bool,
    is_hidden: bool,
    is_locked: bool,
) -> dict:
    """Build an IsNull or Not/IsNull filter."""
    filter_name = f"Filter_{secrets.token_hex(8)}"
    field_ref = _field_expr(entity, prop, field_type, entity)
    alias = "f"
    col_expr = _field_expr(entity, prop, field_type, alias)

    condition: dict
    if is_blank:
        # Show only nulls: Where IsNull(field)
        condition = {"Comparison": {
            "ComparisonKind": 0,  # Equal
            "Left": col_expr,
            "Right": {"Literal": {"Value": "null"}},
        }}
    else:
        # Hide nulls: Where Not(IsNull(field))
        condition = {"Not": {"Expression": {"Comparison": {
            "ComparisonKind": 0,
            "Left": col_expr,
            "Right": {"Literal": {"Value": "null"}},
        }}}}

    filter_obj = {
        "name": filter_name,
        "type": "Advanced",
        "filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": entity, "Type": 0}],
            "Where": [{"Condition": condition}],
        },
        "field": field_ref,
        "isHiddenInViewMode": is_hidden,
        "isLockedInViewMode": is_locked,
        "howCreated": "User",
    }

    config = data.setdefault("filterConfig", {})
    config.setdefault("filters", []).append(filter_obj)
    return filter_obj


def _build_in_condition(
    field_expr: dict,
    pbi_values: list,
    *,
    exclude: bool = False,
) -> dict:
    """Build an In or Not/In condition for value filters."""
    in_block = {
        "In": {
            "Expressions": [field_expr],
            "Values": pbi_values,
        }
    }
    if exclude:
        return {"Not": {"Expression": in_block}}
    return in_block


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
                    "Condition": _build_in_condition(
                        _field_expr(entity, prop, field_type, alias),
                        pbi_values,
                        exclude=(filter_type == "Exclude"),
                    )
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
    is_locked: bool = False,
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
        "isLockedInViewMode": is_locked,
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
    is_locked: bool = False,
) -> dict:
    """Add a schema-backed Relative Date filter."""
    if field_type != "column":
        raise ValueError("Relative date filters currently require a column target field.")
    if operator not in {"InLast", "InThis", "InNext"}:
        raise ValueError("Relative date operator must be InLast, InThis, or InNext.")
    if time_units_count <= 0:
        raise ValueError("Relative date filters require a positive time unit count.")
    if time_unit_type not in DATE_UNIT_CODES:
        raise ValueError(
            "Relative date filters support Days, Weeks, Months, Quarters, and Years."
        )

    unit_code = DATE_UNIT_CODES[time_unit_type]
    alias = "d"
    field_ref = _field_expr(entity, prop, field_type, entity)
    filter_obj = {
        "name": f"Filter_{secrets.token_hex(8)}",
        "field": field_ref,
        "type": "RelativeDate",
        "filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": entity, "Type": 0}],
            "Where": [
                {
                    "Condition": _relative_date_condition(
                        entity,
                        prop,
                        alias,
                        operator=operator,
                        time_units_count=time_units_count,
                        unit_code=unit_code,
                        include_today=include_today,
                    )
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


def add_relative_time_filter(
    data: dict,
    entity: str,
    prop: str,
    operator: str = "InLast",
    time_units_count: int = 15,
    time_unit_type: str = "Minutes",
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
) -> dict:
    """Add a schema-backed Relative Time filter."""
    if field_type != "column":
        raise ValueError("Relative time filters currently require a column target field.")
    if operator not in {"InLast", "InNext"}:
        raise ValueError("Relative time operator must be InLast or InNext.")
    if time_units_count <= 0:
        raise ValueError("Relative time filters require a positive time unit count.")
    if time_unit_type not in TIME_UNIT_CODES:
        raise ValueError("Relative time filters support Minutes and Hours.")

    unit_code = TIME_UNIT_CODES[time_unit_type]
    alias = "d"
    field_ref = _field_expr(entity, prop, field_type, entity)
    filter_obj = {
        "name": f"Filter_{secrets.token_hex(8)}",
        "field": field_ref,
        "type": "RelativeTime",
        "filter": {
            "Version": 2,
            "From": [{"Name": alias, "Entity": entity, "Type": 0}],
            "Where": [
                {
                    "Condition": _relative_time_condition(
                        entity,
                        prop,
                        alias,
                        operator=operator,
                        time_units_count=time_units_count,
                        unit_code=unit_code,
                    )
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
    return any(field_ref.lower() == identifier for field_ref in filter_field_refs(f))


def _extract_field_ref(field: dict) -> tuple[str, str]:
    """Extract (entity, property) from a PBI field reference."""
    return _extract_expression_ref(field)


def filter_field_refs(filter_obj: dict) -> list[str]:
    """Return all recognizable field refs for a filter."""
    refs: list[str] = []
    alias_map = {
        source.get("Name"): source.get("Entity")
        for source in filter_obj.get("filter", {}).get("From", [])
        if source.get("Name") and source.get("Entity")
    }

    entity, prop = _extract_field_ref(filter_obj.get("field", {}))
    if entity != "?" and prop != "?":
        refs.append(f"{entity}.{prop}")

    for clause in filter_obj.get("filter", {}).get("Where", []):
        condition = clause.get("Condition", {})
        if "In" in condition:
            for expr in condition["In"].get("Expressions", []):
                entity, prop = _extract_expression_ref(expr, alias_map=alias_map)
                if entity != "?" and prop != "?":
                    refs.append(f"{entity}.{prop}")
        if "Comparison" in condition:
            entity, prop = _extract_expression_ref(
                condition["Comparison"].get("Left", {}),
                alias_map=alias_map,
            )
            if entity != "?" and prop != "?":
                refs.append(f"{entity}.{prop}")
        if "Between" in condition:
            entity, prop = _extract_expression_ref(
                condition["Between"].get("Expression", {}),
                alias_map=alias_map,
            )
            if entity != "?" and prop != "?":
                refs.append(f"{entity}.{prop}")

    deduped: list[str] = []
    for ref in refs:
        if ref not in deduped:
            deduped.append(ref)
    return deduped


def _extract_filter_values(f: dict) -> list[str]:
    """Extract human-readable values from a filter."""
    values = []
    filter_data = f.get("filter", {})
    where = filter_data.get("Where", [])

    if f.get("type") == "TopN":
        summary = _extract_topn_summary(filter_data)
        if summary:
            values.append(summary)
    if f.get("type") in {"RelativeDate", "RelativeTime"}:
        summary = _extract_relative_summary(f)
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


def _relative_date_condition(
    entity: str,
    prop: str,
    alias: str,
    *,
    operator: str,
    time_units_count: int,
    unit_code: int,
    include_today: bool,
) -> dict:
    """Build the published relative-date condition shape."""
    field_expr = _field_expr(entity, prop, "column", alias)
    now = _now_expr()

    if operator == "InThis":
        if time_units_count != 1:
            raise ValueError("Relative date 'InThis' filters require a count of 1.")
        return {
            "Comparison": {
                "ComparisonKind": 0,
                "Left": field_expr,
                "Right": _date_span_expr(now, unit_code),
            }
        }

    if operator == "InLast":
        if include_today:
            lower = _date_span_expr(
                _date_add_expr(
                    _date_add_expr(now, 1, DATE_UNIT_CODES["Days"]),
                    -time_units_count,
                    unit_code,
                ),
                DATE_UNIT_CODES["Days"],
            )
            upper = _date_span_expr(now, DATE_UNIT_CODES["Days"])
        else:
            lower = _date_span_expr(_date_add_expr(now, -time_units_count, unit_code), unit_code)
            upper = _date_span_expr(_date_add_expr(now, -1, unit_code), unit_code)
    else:
        if include_today:
            lower = _date_span_expr(now, DATE_UNIT_CODES["Days"])
            upper = _date_span_expr(
                _date_add_expr(
                    _date_add_expr(now, -1, DATE_UNIT_CODES["Days"]),
                    time_units_count,
                    unit_code,
                ),
                DATE_UNIT_CODES["Days"],
            )
        else:
            lower = _date_span_expr(_date_add_expr(now, 1, unit_code), unit_code)
            upper = _date_span_expr(_date_add_expr(now, time_units_count, unit_code), unit_code)

    return {
        "Between": {
            "Expression": field_expr,
            "LowerBound": lower,
            "UpperBound": upper,
        }
    }


def _relative_time_condition(
    entity: str,
    prop: str,
    alias: str,
    *,
    operator: str,
    time_units_count: int,
    unit_code: int,
) -> dict:
    """Build the published relative-time condition shape."""
    field_expr = _field_expr(entity, prop, "column", alias)
    now = _now_expr()

    if operator == "InLast":
        lower = _date_add_expr(now, -time_units_count, unit_code)
        upper = now
    else:
        lower = now
        upper = _date_add_expr(now, time_units_count, unit_code)

    return {
        "Between": {
            "Expression": field_expr,
            "LowerBound": lower,
            "UpperBound": upper,
        }
    }


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


def _extract_relative_summary(filter_obj: dict) -> str | None:
    """Extract a short display summary for schema-backed relative filters."""
    filter_type = filter_obj.get("type")
    where = filter_obj.get("filter", {}).get("Where", [])
    if not where:
        return None
    condition = where[0].get("Condition", {})

    if filter_type == "RelativeDate":
        comparison = condition.get("Comparison")
        if comparison and comparison.get("ComparisonKind") == 0:
            right = comparison.get("Right", {})
            span = right.get("DateSpan", {})
            if _is_now_expr(span.get("Expression", {})):
                unit_name = _time_unit_name(span.get("TimeUnit"))
                if unit_name:
                    return f"in this {unit_name.lower()}"

        between = condition.get("Between")
        if between:
            lower = between.get("LowerBound", {}).get("DateSpan", {})
            upper = between.get("UpperBound", {}).get("DateSpan", {})
            summary = _match_relative_date_between(lower, upper)
            if summary:
                return summary

    if filter_type == "RelativeTime":
        between = condition.get("Between")
        if between:
            lower = between.get("LowerBound", {})
            upper = between.get("UpperBound", {})
            if _is_now_expr(upper):
                parsed = _parse_date_add(lower)
                if parsed and _is_now_expr(parsed[0]) and parsed[1] < 0:
                    unit_name = _time_unit_name(parsed[2])
                    if unit_name:
                        return f"in last {abs(parsed[1])} {unit_name.lower()}"
            if _is_now_expr(lower):
                parsed = _parse_date_add(upper)
                if parsed and _is_now_expr(parsed[0]) and parsed[1] > 0:
                    unit_name = _time_unit_name(parsed[2])
                    if unit_name:
                        return f"in next {parsed[1]} {unit_name.lower()}"

    return None


def _match_relative_date_between(lower: dict, upper: dict) -> str | None:
    """Recognize the published relative-date Between patterns."""
    lower_expr = lower.get("Expression", {})
    upper_expr = upper.get("Expression", {})
    lower_span_unit = lower.get("TimeUnit")
    upper_span_unit = upper.get("TimeUnit")

    if (
        lower_span_unit == DATE_UNIT_CODES["Days"]
        and upper_span_unit == DATE_UNIT_CODES["Days"]
        and _is_now_expr(upper_expr)
    ):
        first = _parse_date_add(lower_expr)
        if first and first[1] < 0:
            second = _parse_date_add(first[0])
            if second and _is_now_expr(second[0]) and second[1] == 1 and second[2] == DATE_UNIT_CODES["Days"]:
                unit_name = _time_unit_name(first[2])
                if unit_name:
                    return f"in last {abs(first[1])} {unit_name.lower()} incl today"

    if (
        lower_span_unit == DATE_UNIT_CODES["Days"]
        and upper_span_unit == DATE_UNIT_CODES["Days"]
        and _is_now_expr(lower_expr)
    ):
        first = _parse_date_add(upper_expr)
        if first and first[1] > 0:
            second = _parse_date_add(first[0])
            if second and _is_now_expr(second[0]) and second[1] == -1 and second[2] == DATE_UNIT_CODES["Days"]:
                unit_name = _time_unit_name(first[2])
                if unit_name:
                    return f"in next {first[1]} {unit_name.lower()} incl today"

    lower_add = _parse_date_add(lower_expr)
    upper_add = _parse_date_add(upper_expr)
    if lower_add and upper_add:
        if (
            _is_now_expr(lower_add[0])
            and _is_now_expr(upper_add[0])
            and lower_add[2] == upper_add[2] == lower_span_unit == upper_span_unit
        ):
            unit_name = _time_unit_name(lower_add[2])
            if unit_name:
                if lower_add[1] < 0 and upper_add[1] == -1:
                    return f"in last {abs(lower_add[1])} {unit_name.lower()}"
                if lower_add[1] == 1 and upper_add[1] > 0:
                    return f"in next {upper_add[1]} {unit_name.lower()}"

    return None


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

    if normalized_type in {"double", "decimal", "currency", "number"}:
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
