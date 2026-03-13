"""Table/matrix visual column operations — width, rename, per-column formatting.

Operates on tableEx and pivotTable visuals. Column widths and formatting
use metadata selectors keyed by queryRef. Renaming sets displayName on
query projections.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pbi.project import Visual
from pbi.properties import decode_pbi_value, encode_pbi_value


# ── Data types ────────────────────────────────────────────────────

@dataclass
class ColumnInfo:
    """Parsed column info for display."""
    role: str
    entity: str
    prop: str
    field_type: str  # "column" or "measure"
    query_ref: str
    display_name: str | None  # None means using default field name
    width: float | None
    formatting: dict[str, Any] = field(default_factory=dict)


# ── Read operations ───────────────────────────────────────────────

def get_columns(visual: Visual) -> list[ColumnInfo]:
    """Get all columns from a table/matrix visual with their config."""
    query_state = (
        visual.data
        .get("visual", {})
        .get("query", {})
        .get("queryState", {})
    )
    objects = visual.data.get("visual", {}).get("objects", {})

    # Build width and formatting lookups by queryRef
    widths = _get_widths(objects)
    col_fmt = _get_column_formatting(objects)

    columns = []
    for role, config in query_state.items():
        for proj in config.get("projections", []):
            field_data = proj.get("field", {})
            query_ref = proj.get("queryRef", "")
            display_name = proj.get("displayName")

            entity, prop, field_type = "?", "?", "column"
            for key, ftype in [("Column", "column"), ("Measure", "measure")]:
                if key in field_data:
                    entity = field_data[key]["Expression"]["SourceRef"]["Entity"]
                    prop = field_data[key]["Property"]
                    field_type = ftype
                    break

            columns.append(ColumnInfo(
                role=role,
                entity=entity,
                prop=prop,
                field_type=field_type,
                query_ref=query_ref,
                display_name=display_name,
                width=widths.get(query_ref),
                formatting=col_fmt.get(query_ref, {}),
            ))

    return columns


def find_column(visual: Visual, identifier: str) -> ColumnInfo:
    """Find a column by queryRef, field reference (Table.Field), display name, or index.

    Raises ValueError if not found or ambiguous.
    """
    columns = get_columns(visual)
    if not columns:
        raise ValueError("Visual has no columns (is it a table/matrix?)")

    # Try numeric index (1-based)
    try:
        idx = int(identifier)
        if 1 <= idx <= len(columns):
            return columns[idx - 1]
    except ValueError:
        pass

    id_lower = identifier.lower()
    matches = []
    for col in columns:
        # Exact queryRef match
        if col.query_ref.lower() == id_lower:
            return col
        # Exact field ref match (Table.Field)
        field_ref = f"{col.entity}.{col.prop}".lower()
        if field_ref == id_lower:
            return col
        # Exact display name match
        if col.display_name and col.display_name.lower() == id_lower:
            return col
        # Partial matches
        if (id_lower in col.query_ref.lower()
                or id_lower in field_ref
                or (col.display_name and id_lower in col.display_name.lower())
                or id_lower in col.prop.lower()):
            matches.append(col)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        refs = [f"{m.entity}.{m.prop}" for m in matches]
        raise ValueError(f'Ambiguous column "{identifier}": matches {", ".join(refs)}')
    raise ValueError(f'Column "{identifier}" not found')


# ── Write operations ──────────────────────────────────────────────

def set_column_width(visual: Visual, query_ref: str, width: float) -> None:
    """Set the width of a column by its queryRef."""
    objects = visual.data.setdefault("visual", {}).setdefault("objects", {})
    entries = objects.setdefault("columnWidth", [])

    value = encode_pbi_value(str(width), "number")

    # Find existing entry for this column
    for entry in entries:
        if entry.get("selector", {}).get("metadata") == query_ref:
            entry.setdefault("properties", {})["value"] = value
            return

    # Create new entry
    entries.append({
        "properties": {"value": value},
        "selector": {"metadata": query_ref},
    })


def rename_column(visual: Visual, query_ref: str, display_name: str) -> None:
    """Rename a column's display header by setting displayName on its projection."""
    query_state = (
        visual.data
        .get("visual", {})
        .get("query", {})
        .get("queryState", {})
    )

    for _role, config in query_state.items():
        for proj in config.get("projections", []):
            if proj.get("queryRef") == query_ref:
                proj["displayName"] = display_name
                return

    raise ValueError(f'Column with queryRef "{query_ref}" not found in query')


def set_column_format(
    visual: Visual,
    query_ref: str,
    *,
    alignment: str | None = None,
    font_color: str | None = None,
    back_color: str | None = None,
    display_units: int | None = None,
    precision: int | None = None,
) -> None:
    """Set per-column formatting properties."""
    objects = visual.data.setdefault("visual", {}).setdefault("objects", {})
    entries = objects.setdefault("columnFormatting", [])

    # Find or create entry for this column
    target = None
    for entry in entries:
        if entry.get("selector", {}).get("metadata") == query_ref:
            target = entry
            break

    if target is None:
        target = {
            "properties": {},
            "selector": {"metadata": query_ref},
        }
        entries.append(target)

    props = target.setdefault("properties", {})

    if alignment is not None:
        props["alignment"] = encode_pbi_value(alignment, "enum")
    if font_color is not None:
        props["fontColor"] = encode_pbi_value(font_color, "color")
    if back_color is not None:
        props["backColor"] = encode_pbi_value(back_color, "color")
    if display_units is not None:
        props["labelDisplayUnits"] = encode_pbi_value(str(display_units), "number")
    if precision is not None:
        props["labelPrecision"] = encode_pbi_value(str(precision), "number")

    # Apply to values section by default
    if "styleValues" not in props:
        props["styleValues"] = encode_pbi_value("true", "boolean")


def clear_column_width(visual: Visual, query_ref: str) -> bool:
    """Remove a column width override. Returns True if removed."""
    return _remove_by_selector("columnWidth", visual, query_ref)


def clear_column_format(visual: Visual, query_ref: str) -> bool:
    """Remove per-column formatting. Returns True if removed."""
    return _remove_by_selector("columnFormatting", visual, query_ref)


# ── Internal helpers ──────────────────────────────────────────────

def _get_widths(objects: dict) -> dict[str, float]:
    """Read columnWidth entries into a {queryRef: width} lookup."""
    result = {}
    for entry in objects.get("columnWidth", []):
        qr = entry.get("selector", {}).get("metadata")
        if qr:
            raw = entry.get("properties", {}).get("value")
            if raw is not None:
                decoded = decode_pbi_value(raw)
                if isinstance(decoded, (int, float)):
                    result[qr] = float(decoded)
    return result


def _get_column_formatting(objects: dict) -> dict[str, dict[str, Any]]:
    """Read columnFormatting entries into a {queryRef: {prop: decoded}} lookup."""
    result: dict[str, dict[str, Any]] = {}
    for entry in objects.get("columnFormatting", []):
        qr = entry.get("selector", {}).get("metadata")
        if qr:
            props = entry.get("properties", {})
            decoded = {}
            for k, v in props.items():
                decoded[k] = decode_pbi_value(v) if isinstance(v, dict) else v
            result[qr] = decoded
    return result


def _remove_by_selector(object_name: str, visual: Visual, query_ref: str) -> bool:
    """Remove an entry from visual.objects by selector.metadata match."""
    objects = visual.data.get("visual", {}).get("objects", {})
    entries = objects.get(object_name, [])
    original = len(entries)
    objects[object_name] = [
        e for e in entries
        if e.get("selector", {}).get("metadata") != query_ref
    ]
    if not objects[object_name]:
        objects.pop(object_name, None)
    return len(objects.get(object_name, [])) < original
