"""Filter management for PBI reports, pages, and visuals."""

from __future__ import annotations

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
) -> dict:
    """Add a categorical filter to a JSON structure. Returns the filter dict."""
    filter_name = f"Filter_{secrets.token_hex(8)}"

    field_key = "Column" if field_type == "column" else "Measure"
    field_ref = {
        field_key: {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }

    # Build the semantic filter expression
    pbi_values = [
        [{"Literal": {"Value": f"'{v}'"}}] for v in values
    ]

    filter_obj = {
        "name": filter_name,
        "type": "Categorical",
        "filter": {
            "Version": 2,
            "From": [{"Name": "f", "Entity": entity, "Type": 0}],
            "Where": [
                {
                    "Condition": {
                        "In": {
                            "Expressions": [
                                {
                                    field_key: {
                                        "Expression": {"SourceRef": {"Source": "f"}},
                                        "Property": prop,
                                    }
                                }
                            ],
                            "Values": pbi_values,
                        }
                    }
                }
            ],
        },
        "field": field_ref,
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
) -> dict:
    """Add a range filter (between min and max). Returns the filter dict."""
    filter_name = f"Filter_{secrets.token_hex(8)}"

    field_key = "Column" if field_type == "column" else "Measure"
    field_ref = {
        field_key: {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }

    # Build conditions
    conditions = []
    col_expr = {
        field_key: {
            "Expression": {"SourceRef": {"Source": "f"}},
            "Property": prop,
        }
    }

    if min_val is not None:
        conditions.append({
            "Condition": {
                "Comparison": {
                    "ComparisonKind": 2,  # GreaterThanOrEqual
                    "Left": col_expr,
                    "Right": {"Literal": {"Value": f"{min_val}D"}},
                }
            }
        })

    if max_val is not None:
        conditions.append({
            "Condition": {
                "Comparison": {
                    "ComparisonKind": 4,  # LessThanOrEqual
                    "Left": col_expr,
                    "Right": {"Literal": {"Value": f"{max_val}D"}},
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
) -> dict:
    """Add a Top N filter. Returns the filter dict.

    Args:
        entity: Target field entity (e.g. "Product")
        prop: Target field property (e.g. "Category")
        n: Number of items to show
        order_entity: Order-by field entity (e.g. "Sales")
        order_prop: Order-by field property (e.g. "Total Revenue")
        order_field_type: "measure" or "column" for the order-by field
        direction: "Top" or "Bottom"
        field_type: "column" or "measure" for the target field
    """
    filter_name = f"Filter_{secrets.token_hex(8)}"

    target_key = "Column" if field_type == "column" else "Measure"
    field_ref = {
        target_key: {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }

    order_key = "Column" if order_field_type == "column" else "Measure"
    order_expr = {
        order_key: {
            "Expression": {"SourceRef": {"Source": "f"}},
            "Property": order_prop,
        }
    }

    target_expr = {
        target_key: {
            "Expression": {"SourceRef": {"Source": "f"}},
            "Property": prop,
        }
    }

    filter_obj = {
        "name": filter_name,
        "type": "TopN",
        "filter": {
            "Version": 2,
            "From": [
                {"Name": "f", "Entity": entity, "Type": 0},
                {"Name": "o", "Entity": order_entity, "Type": 0},
            ],
            "Where": [
                {
                    "Condition": {
                        "Top": {
                            "Expression": target_expr,
                            "Count": n,
                            "OrderBy": [
                                {
                                    "Expression": {
                                        "Aggregation": {
                                            "Expression": order_expr,
                                            "Function": 0,  # Sum
                                        }
                                    },
                                    "Direction": 2 if direction == "Top" else 1,
                                }
                            ],
                        }
                    }
                }
            ],
        },
        "field": field_ref,
        "isHiddenInViewMode": is_hidden,
        "isLockedInViewMode": False,
        "howCreated": "User",
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
    """Add a relative date filter. Returns the filter dict.

    Args:
        entity: Date field entity (e.g. "Calendar")
        prop: Date field property (e.g. "Date")
        operator: "InLast", "InThis", or "InNext"
        time_units_count: Number of time units
        time_unit_type: "Days", "Weeks", "Months", "Quarters", or "Years"
        include_today: Whether to include the current day
    """
    filter_name = f"Filter_{secrets.token_hex(8)}"

    field_key = "Column" if field_type == "column" else "Measure"
    field_ref = {
        field_key: {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }

    filter_obj = {
        "name": filter_name,
        "type": "RelativeDate",
        "filter": {
            "Version": 2,
            "From": [{"Name": "f", "Entity": entity, "Type": 0}],
            "Where": [
                {
                    "Condition": {
                        "RelativeDate": {
                            "Expression": {
                                field_key: {
                                    "Expression": {"SourceRef": {"Source": "f"}},
                                    "Property": prop,
                                }
                            },
                            "Operator": {"InLast": 0, "InThis": 1, "InNext": 2}.get(operator, 0),
                            "TimeUnitsCount": time_units_count,
                            "TimeUnitType": {
                                "Days": 0, "Weeks": 1, "Months": 2,
                                "Quarters": 3, "Years": 4,
                            }.get(time_unit_type, 0),
                            "IncludeToday": include_today,
                        }
                    }
                }
            ],
        },
        "field": field_ref,
        "isHiddenInViewMode": is_hidden,
        "isLockedInViewMode": False,
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

    for clause in where:
        cond = clause.get("Condition", {})

        # Categorical: In condition
        if "In" in cond:
            for val_list in cond["In"].get("Values", []):
                for val in val_list:
                    if "Literal" in val:
                        raw = val["Literal"]["Value"]
                        # Strip quotes and type suffixes
                        if raw.startswith("'") and raw.endswith("'"):
                            values.append(raw[1:-1])
                        elif raw.endswith("D") or raw.endswith("L"):
                            values.append(raw[:-1])
                        else:
                            values.append(raw)

        # Range: Comparison conditions
        if "Comparison" in cond:
            comp = cond["Comparison"]
            kind = comp.get("ComparisonKind", 0)
            right = comp.get("Right", {})
            literal = right.get("Literal", {}).get("Value", "?")
            if literal.endswith("D"):
                literal = literal[:-1]
            op_map = {0: "==", 1: "<", 2: ">=", 3: ">", 4: "<=", 5: "!="}
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
