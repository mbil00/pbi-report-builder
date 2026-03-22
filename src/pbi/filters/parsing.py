from __future__ import annotations

from .expressions import (
    _decode_literal_expr,
    _extract_expression_ref,
    _is_now_expr,
    _parse_date_add,
    _time_unit_name,
)
from .types import DATE_UNIT_CODES, FilterInfo


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
    entity, prop = _extract_field_ref(f.get("field", {}))
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


def remove_filter(data: dict, identifier: str) -> int:
    """Remove filter(s) by name or field reference. Returns count removed."""
    config = data.get("filterConfig", {})
    filters = config.get("filters", [])
    if not filters:
        return 0

    id_lower = identifier.lower()
    original = len(filters)
    config["filters"] = [f for f in filters if not _filter_matches(f, id_lower)]
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
        inner_cond = condition
        if "Not" in inner_cond:
            inner_cond = inner_cond["Not"].get("Expression", {})
        for node_key in ("Contains", "StartsWith"):
            if node_key in inner_cond:
                entity, prop = _extract_expression_ref(
                    inner_cond[node_key].get("Left", {}),
                    alias_map=alias_map,
                )
                if entity != "?" and prop != "?":
                    refs.append(f"{entity}.{prop}")

    deduped: list[str] = []
    for ref in refs:
        if ref not in deduped:
            deduped.append(ref)
    return deduped


def _decode_advanced_condition(cond: dict) -> str | None:
    """Decode Contains, StartsWith, Not, And, Or conditions into display text."""
    for logic_key, logic_label in (("And", "and"), ("Or", "or")):
        if logic_key in cond:
            left = _decode_advanced_condition(cond[logic_key].get("Left", {}))
            right = _decode_advanced_condition(cond[logic_key].get("Right", {}))
            if left and right:
                return f"{left} {logic_label} {right}"
            return left or right

    negated = False
    inner = cond

    if "Not" in inner:
        negated = True
        inner = inner["Not"].get("Expression", {})

    if "Contains" in inner:
        literal = _decode_literal_expr(inner["Contains"].get("Right", {}))
        op = "does not contain" if negated else "contains"
        return f"{op} {literal}"

    if "StartsWith" in inner:
        literal = _decode_literal_expr(inner["StartsWith"].get("Right", {}))
        op = "does not start with" if negated else "starts with"
        return f"{op} {literal}"

    if "Comparison" in inner:
        comp = inner["Comparison"]
        kind = comp.get("ComparisonKind", 0)
        right = comp.get("Right", {})
        raw_val = right.get("Literal", {}).get("Value")

        if kind == 0:
            if raw_val == "null":
                return "is not blank" if negated else "is blank"
            if raw_val == "''":
                return "is not empty" if negated else "is empty"
            if negated:
                literal = _decode_literal_expr(right)
                return f"is not {literal}"
            return None

        if negated:
            op_map = {1: "not >", 2: "not >=", 3: "not <", 4: "not <="}
            literal = _decode_literal_expr(right)
            return f"{op_map.get(kind, '?')} {literal}"

        return None

    return None


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

        if "In" in cond:
            tuple_values = []
            for val_list in cond["In"].get("Values", []):
                decoded = [_decode_literal_expr(val) for val in val_list]
                if len(decoded) == 1:
                    values.append(decoded[0])
                else:
                    tuple_values.append("(" + ", ".join(decoded) + ")")
            values.extend(tuple_values)

        decoded_adv = _decode_advanced_condition(cond)
        if decoded_adv:
            values.append(decoded_adv)
        elif "Comparison" in cond:
            comp = cond["Comparison"]
            kind = comp.get("ComparisonKind", 0)
            right = comp.get("Right", {})
            literal = _decode_literal_expr(right)
            op_map = {0: "==", 1: ">", 2: ">=", 3: "<", 4: "<="}
            op = op_map.get(kind, "?")
            values.append(f"{op} {literal}")

        if "Top" in cond:
            top = cond["Top"]
            count = top.get("Count", "?")
            order_by = top.get("OrderBy", [{}])
            direction_code = order_by[0].get("Direction", 2) if order_by else 2
            direction = "top" if direction_code == 2 else "bottom"
            values.append(f"{direction} {count}")

        if "RelativeDate" in cond:
            rd = cond["RelativeDate"]
            op_map = {0: "in last", 1: "in this", 2: "in next"}
            unit_map = {
                0: "days",
                1: "weeks",
                2: "calendar weeks",
                3: "months",
                4: "calendar months",
                5: "years",
                6: "calendar years",
            }
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
            subquery = source.get("Expression", {}).get("Subquery", {}).get("Query", {})
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


def _extract_relative_structured(filter_obj: dict) -> dict | None:
    """Extract structured {operator, count, unit, includeToday} from a relative filter.

    Returns a dict suitable for YAML export, or None if the structure is unrecognized.
    """
    filter_type = filter_obj.get("type")
    where = filter_obj.get("filter", {}).get("Where", [])
    if not where:
        return None
    condition = where[0].get("Condition", {})

    if filter_type == "RelativeDate":
        # InThis pattern: Comparison with DateSpan(Now(), unit)
        comparison = condition.get("Comparison")
        if comparison and comparison.get("ComparisonKind") == 0:
            right = comparison.get("Right", {})
            span = right.get("DateSpan", {})
            if _is_now_expr(span.get("Expression", {})):
                unit_name = _time_unit_name(span.get("TimeUnit"))
                if unit_name:
                    return {"operator": "InThis", "count": 1, "unit": unit_name}

        between = condition.get("Between")
        if between:
            lower = between.get("LowerBound", {})
            upper = between.get("UpperBound", {})
            result = _match_relative_date_structured(lower, upper)
            if result:
                return result

    if filter_type == "RelativeTime":
        between = condition.get("Between")
        if between:
            lower_bound = between.get("LowerBound", {})
            upper_bound = between.get("UpperBound", {})
            if _is_now_expr(upper_bound):
                parsed = _parse_date_add(lower_bound)
                if parsed and _is_now_expr(parsed[0]) and parsed[1] < 0:
                    unit_name = _time_unit_name(parsed[2])
                    if unit_name:
                        return {"operator": "InLast", "count": abs(parsed[1]), "unit": unit_name}
            if _is_now_expr(lower_bound):
                parsed = _parse_date_add(upper_bound)
                if parsed and _is_now_expr(parsed[0]) and parsed[1] > 0:
                    unit_name = _time_unit_name(parsed[2])
                    if unit_name:
                        return {"operator": "InNext", "count": parsed[1], "unit": unit_name}

    return None


def _match_relative_date_structured(lower: dict, upper: dict) -> dict | None:
    """Extract structured fields from a RelativeDate Between condition."""
    lower_span = lower.get("DateSpan", {})
    upper_span = upper.get("DateSpan", {})
    lower_expr = lower_span.get("Expression", {}) if lower_span else lower
    upper_expr = upper_span.get("Expression", {}) if upper_span else upper
    lower_span_unit = lower_span.get("TimeUnit") if lower_span else None
    upper_span_unit = upper_span.get("TimeUnit") if upper_span else None

    # InLast with includeToday: DateAdd(DateAdd(Now(), 1, Days), -N, Unit) .. Now()
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
                    return {"operator": "InLast", "count": abs(first[1]), "unit": unit_name, "includeToday": True}

    # InNext with includeToday: Now() .. DateAdd(DateAdd(Now(), -1, Days), N, Unit)
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
                    return {"operator": "InNext", "count": first[1], "unit": unit_name, "includeToday": True}

    # InLast/InNext without includeToday
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
                    return {"operator": "InLast", "count": abs(lower_add[1]), "unit": unit_name, "includeToday": False}
                if lower_add[1] == 1 and upper_add[1] > 0:
                    return {"operator": "InNext", "count": upper_add[1], "unit": unit_name, "includeToday": False}

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
