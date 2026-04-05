"""Visual query helpers for bindings and sort definitions."""

from __future__ import annotations

from pbi.project import Visual


def add_binding(
    visual: Visual,
    role: str,
    entity: str,
    prop: str,
    field_type: str = "column",
    display_name: str | None = None,
) -> None:
    """Add a data binding (column or measure) to a visual's query."""
    field_key = "Column" if field_type == "column" else "Measure"
    projection = {
        "field": {
            field_key: {
                "Expression": {"SourceRef": {"Entity": entity}},
                "Property": prop,
            }
        },
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }
    if display_name:
        projection["displayName"] = display_name

    query_state = (
        visual.data
        .setdefault("visual", {})
        .setdefault("query", {})
        .setdefault("queryState", {})
    )
    role_config = query_state.setdefault(role, {"projections": []})
    role_config["projections"].append(projection)
    visual.save()


def remove_binding(
    visual: Visual,
    role: str,
    field_ref: str | None = None,
) -> int:
    """Remove bindings from a visual. Returns count of removed bindings."""
    query_state = (
        visual.data
        .get("visual", {})
        .get("query", {})
        .get("queryState", {})
    )
    if role not in query_state:
        return 0

    if field_ref is None:
        removed = len(query_state[role].get("projections", []))
        del query_state[role]
        visual.save()
        return removed

    projections = query_state[role].get("projections", [])
    original_count = len(projections)
    removed_refs = [
        p.get("queryRef", "")
        for p in projections
        if p.get("queryRef", "").lower() == field_ref.lower()
    ]
    query_state[role]["projections"] = [
        p for p in projections
        if p.get("queryRef", "").lower() != field_ref.lower()
    ]
    removed = original_count - len(query_state[role]["projections"])
    if not query_state[role]["projections"]:
        del query_state[role]
    if removed_refs:
        from pbi.columns import clear_column_format, clear_column_width

        for ref in removed_refs:
            clear_column_width(visual, ref)
            clear_column_format(visual, ref)
    visual.save()
    return removed


def get_bindings(visual: Visual) -> list[tuple[str, str, str, str]]:
    """Get all bindings as (role, entity, property, field_type) tuples."""
    query_state = (
        visual.data
        .get("visual", {})
        .get("query", {})
        .get("queryState", {})
    )
    bindings = []
    for role, config in query_state.items():
        for proj in config.get("projections", []):
            field_data = proj.get("field", {})
            entity, prop, field_type = resolve_projection_field(field_data)
            if entity != "?":
                bindings.append((role, entity, prop, field_type))
    return bindings


def set_sort(
    visual: Visual,
    entity: str,
    prop: str,
    field_type: str = "column",
    descending: bool = True,
) -> None:
    """Set the sort definition on a visual."""
    field_key = "Column" if field_type == "column" else "Measure"
    sort_entry = {
        "field": {
            field_key: {
                "Expression": {"SourceRef": {"Entity": entity}},
                "Property": prop,
            }
        },
        "direction": "Descending" if descending else "Ascending",
    }

    query = (
        visual.data
        .setdefault("visual", {})
        .setdefault("query", {})
    )
    query["sortDefinition"] = {
        "sort": [sort_entry],
        "isDefaultSort": False,
    }
    visual.save()


def clear_sort(visual: Visual) -> bool:
    """Remove sort definition from a visual. Returns True if one was removed."""
    query = visual.data.get("visual", {}).get("query", {})
    if "sortDefinition" in query:
        del query["sortDefinition"]
        visual.save()
        return True
    return False


def get_sort(visual: Visual) -> list[tuple[str, str, str, str]]:
    """Get sort definitions as (entity, property, field_type, direction) tuples."""
    sort_def = (
        visual.data
        .get("visual", {})
        .get("query", {})
        .get("sortDefinition", {})
    )
    result = []
    for entry in sort_def.get("sort", []):
        field_data = entry.get("field", {})
        direction = entry.get("direction", "Ascending")
        entity, prop, ftype = resolve_projection_field(field_data)
        if entity != "?":
            result.append((entity, prop, ftype, direction))
    return result


def resolve_projection_field(field_data: dict) -> tuple[str, str, str]:
    """Extract (entity, property, field_type) from a query projection field."""
    for key, ftype in [("Column", "column"), ("Measure", "measure")]:
        if key in field_data:
            entity = field_data[key]["Expression"]["SourceRef"]["Entity"]
            prop = field_data[key]["Property"]
            return entity, prop, ftype

    if "Aggregation" in field_data:
        inner = field_data["Aggregation"].get("Expression", {})
        for key in ("Column", "Measure"):
            if key in inner:
                entity = inner[key]["Expression"]["SourceRef"]["Entity"]
                prop = inner[key]["Property"]
                return entity, prop, "aggregation"

    return "?", "?", "column"
