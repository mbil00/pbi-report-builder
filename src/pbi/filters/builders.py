from __future__ import annotations

import secrets

from .expressions import _date_add_expr, _date_span_expr, _field_expr, _literal_expr, _now_expr
from .types import ADVANCED_OPERATORS, DATE_UNIT_CODES, TIME_UNIT_CODES, TupleField


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
        data,
        entity,
        prop,
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
        data,
        entity,
        prop,
        field_type=field_type,
        is_blank=False,
        is_hidden=is_hidden,
        is_locked=is_locked,
    )


def _build_advanced_condition(
    operator: str,
    col_expr: dict,
    value: str | None,
    data_type: str | None,
) -> dict:
    """Build a single advanced condition node from an operator."""
    if operator not in ADVANCED_OPERATORS:
        raise ValueError(
            f"Unknown operator '{operator}'. "
            f"Use one of: {', '.join(sorted(ADVANCED_OPERATORS))}."
        )

    json_node, comparison_kind, negated, needs_value = ADVANCED_OPERATORS[operator]

    if needs_value and value is None:
        raise ValueError(f"Operator '{operator}' requires a value.")

    if json_node == "Comparison":
        if operator in ("is-blank", "is-not-blank"):
            right: dict = {"Literal": {"Value": "null"}}
        elif operator in ("is-empty", "is-not-empty"):
            right = {"Literal": {"Value": "''"}}
        else:
            right = _literal_expr(value, data_type=data_type)  # type: ignore[arg-type]
        condition: dict = {
            "Comparison": {
                "ComparisonKind": comparison_kind,
                "Left": col_expr,
                "Right": right,
            }
        }
    elif json_node == "Contains":
        condition = {
            "Contains": {
                "Left": col_expr,
                "Right": _literal_expr(value, data_type=data_type),  # type: ignore[arg-type]
            }
        }
    elif json_node == "StartsWith":
        condition = {
            "StartsWith": {
                "Left": col_expr,
                "Right": _literal_expr(value, data_type=data_type),  # type: ignore[arg-type]
            }
        }
    else:
        raise ValueError(f"Unsupported JSON node type '{json_node}'.")

    if negated:
        condition = {"Not": {"Expression": condition}}

    return condition


def add_advanced_filter(
    data: dict,
    entity: str,
    prop: str,
    operator: str,
    value: str | None = None,
    field_type: str = "column",
    is_hidden: bool = False,
    is_locked: bool = False,
    data_type: str | None = None,
    operator2: str | None = None,
    value2: str | None = None,
    logic: str = "and",
) -> dict:
    """Add an advanced filter with a schema-backed operator."""
    filter_name = f"Filter_{secrets.token_hex(8)}"
    field_ref = _field_expr(entity, prop, field_type, entity)
    alias = "f"
    col_expr = _field_expr(entity, prop, field_type, alias)

    condition = _build_advanced_condition(operator, col_expr, value, data_type)

    if operator2 is not None:
        if logic not in ("and", "or"):
            raise ValueError("Compound logic must be 'and' or 'or'.")
        condition2 = _build_advanced_condition(operator2, col_expr, value2, data_type)
        logic_key = "And" if logic == "and" else "Or"
        condition = {logic_key: {"Left": condition, "Right": condition2}}

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

    if is_blank:
        condition: dict = {
            "Comparison": {
                "ComparisonKind": 0,
                "Left": col_expr,
                "Right": {"Literal": {"Value": "null"}},
            }
        }
    else:
        condition = {
            "Not": {
                "Expression": {
                    "Comparison": {
                        "ComparisonKind": 0,
                        "Left": col_expr,
                        "Right": {"Literal": {"Value": "null"}},
                    }
                }
            }
        }

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
    conditions = []
    col_expr = _field_expr(entity, prop, field_type, "f")

    if min_val is not None:
        conditions.append(
            {
                "Condition": {
                    "Comparison": {
                        "ComparisonKind": 2,
                        "Left": col_expr,
                        "Right": _literal_expr(min_val, data_type=data_type),
                    }
                }
            }
        )

    if max_val is not None:
        conditions.append(
            {
                "Condition": {
                    "Comparison": {
                        "ComparisonKind": 4,
                        "Left": col_expr,
                        "Right": _literal_expr(max_val, data_type=data_type),
                    }
                }
            }
        )

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
                            "Expressions": [_field_expr(entity, prop, field_type, target_alias)],
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
            "Relative date filters support Days, Weeks, CalendarWeeks, Months, CalendarMonths, Years, and CalendarYears."
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
