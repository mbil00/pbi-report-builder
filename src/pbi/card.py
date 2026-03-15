"""cardVisual KPI shorthand expansion.

Expands a high-level ``kpis:`` YAML block into the full PBIR object
structure required by the Power BI new card visual (cardVisual).
"""

from __future__ import annotations

from typing import Any


# ── Selector helpers ─────────────────────────────────────────────

def _default_selector() -> dict:
    return {"id": "default"}


def _measure_selector(query_ref: str) -> dict:
    return {"metadata": query_ref}


def _ref_label_binding_selector(
    parent_ref: str, field_id: str, order: int,
) -> dict:
    return {
        "data": [{"dataViewWildcard": {"matchingOption": 0}}],
        "metadata": parent_ref,
        "id": field_id,
        "order": order,
    }


def _ref_label_format_selector(field_id: str) -> dict:
    return {"id": field_id}


# ── Expression helpers ───────────────────────────────────────────

def _measure_expr(entity: str, prop: str) -> dict:
    return {
        "Measure": {
            "Expression": {"SourceRef": {"Entity": entity}},
            "Property": prop,
        }
    }


def _split_ref(ref: str) -> tuple[str, str]:
    """Split 'Table.Field' into (entity, prop)."""
    dot = ref.find(".")
    if dot <= 0:
        raise ValueError(f"Invalid measure reference: {ref!r}. Expected Table.Field format.")
    return ref[:dot], ref[dot + 1:]


# ── Object entry builders ───────────────────────────────────────

def _obj_entry(selector: dict, properties: dict) -> dict:
    return {"selector": selector, "properties": properties}


def _ensure_obj(objects: dict, name: str) -> list:
    return objects.setdefault(name, [])


# ── Main expansion ───────────────────────────────────────────────

def expand_kpis(
    visual_data: dict,
    kpis: list[dict],
    *,
    layout: dict | None = None,
    accent_bar: dict | None = None,
    ref_label_layout: dict | None = None,
) -> int:
    """Expand KPI shorthand into full cardVisual PBIR structure.

    Modifies *visual_data* in place.  Returns the number of properties set.

    Parameters
    ----------
    visual_data : dict
        The full visual.json content (contains ``visual``, ``position``, etc.).
    kpis : list[dict]
        Per-KPI definitions.  Each dict may contain:
        ``measure``, ``displayUnits``, ``fontSize``, ``fontColor``, ``bold``,
        ``label``, ``labelPosition``, ``accentColor``, ``tileBackground``,
        ``referenceLabels``.
    layout : dict | None
        Layout block (``columns``, ``calloutSize``, ``alignment``, ``dividers``,
        ``padding``, ``cellPadding``).
    accent_bar : dict | None
        Global accent bar settings (``show``, ``position``, ``width``).
    ref_label_layout : dict | None
        Reference label layout (``position``, ``arrangement``, ``style``,
        ``verticalAlignment``).
    """
    vis = visual_data.setdefault("visual", {})
    objects: dict[str, list] = vis.setdefault("objects", {})
    query_state = (
        vis.setdefault("query", {})
        .setdefault("queryState", {})
    )

    props_set = 0

    # ── 1. Query projections ─────────────────────────────────────
    projections: list[dict] = []
    for kpi in kpis:
        ref = kpi["measure"]
        projections.append({"queryRef": ref, "active": True})

        for rl in kpi.get("referenceLabels", []):
            projections.append({"queryRef": rl["measure"], "active": True})

    query_state["Data"] = {"projections": projections}
    props_set += len(projections)

    # ── 2. Layout object ─────────────────────────────────────────
    if layout:
        layout_entries = _ensure_obj(objects, "layout")
        layout_props: dict[str, Any] = {}
        _map_prop(layout, "columns", layout_props, "columnCount")
        _map_prop(layout, "calloutSize", layout_props, "calloutSize")
        _map_prop(layout, "alignment", layout_props, "alignment")
        _map_prop(layout, "padding", layout_props, "padding")
        _map_prop(layout, "cellPadding", layout_props, "cellPadding")
        _map_prop(layout, "orientation", layout_props, "orientation")
        if layout_props:
            layout_entries.append(_obj_entry({}, layout_props))
            props_set += len(layout_props)

        if layout.get("dividers") is not None:
            divider_entries = _ensure_obj(objects, "divider")
            divider_entries.append(_obj_entry({}, {
                "show": {"expr": {"Literal": {"Value": "true" if layout["dividers"] else "false"}}},
            }))
            props_set += 1

    # ── 3. Global accent bar ─────────────────────────────────────
    if accent_bar:
        ab_entries = _ensure_obj(objects, "accentBar")
        ab_props: dict[str, Any] = {}
        if "show" in accent_bar:
            ab_props["show"] = {"expr": {"Literal": {"Value": "true" if accent_bar["show"] else "false"}}}
        if "position" in accent_bar:
            ab_props["position"] = {"expr": {"Literal": {"Value": f"'{accent_bar['position']}'"}}}
        if "width" in accent_bar:
            ab_props["width"] = {"expr": {"Literal": {"Value": f"{accent_bar['width']}D"}}}
        if ab_props:
            ab_entries.append(_obj_entry(_default_selector(), ab_props))
            props_set += len(ab_props)

    # ── 4. Reference label layout ────────────────────────────────
    if ref_label_layout:
        rll_entries = _ensure_obj(objects, "referenceLabelLayout")
        rll_props: dict[str, Any] = {}
        for key in ("position", "arrangement", "style", "verticalAlignment"):
            if key in ref_label_layout:
                rll_props[key] = {"expr": {"Literal": {"Value": f"'{ref_label_layout[key]}'"}}}
        if rll_props:
            rll_entries.append(_obj_entry(_default_selector(), rll_props))
            props_set += len(rll_props)

    # ── 5. Per-KPI entries ───────────────────────────────────────
    for kpi_idx, kpi in enumerate(kpis):
        ref = kpi["measure"]
        sel = _measure_selector(ref)

        # Value formatting (display units, font size, color, bold)
        value_props: dict[str, Any] = {}
        if "displayUnits" in kpi:
            value_props["labelDisplayUnits"] = {"expr": {"Literal": {"Value": f"{kpi['displayUnits']}D"}}}
        if "fontSize" in kpi:
            value_props["fontSize"] = {"expr": {"Literal": {"Value": f"{kpi['fontSize']}D"}}}
        if "fontColor" in kpi:
            c = kpi["fontColor"]
            value_props["fontColor"] = {"solid": {"color": {"expr": {"Literal": {"Value": f"'{c}'"}}}}}
        if "bold" in kpi:
            value_props["bold"] = {"expr": {"Literal": {"Value": "true" if kpi["bold"] else "false"}}}
        if value_props:
            _ensure_obj(objects, "value").append(_obj_entry(sel, value_props))
            props_set += len(value_props)

        # Custom label
        if "label" in kpi or "labelPosition" in kpi:
            label_props: dict[str, Any] = {}
            if "label" in kpi:
                label_props["titleContentType"] = {"expr": {"Literal": {"Value": "'custom'"}}}
                label_props["text"] = {"expr": {"Literal": {"Value": f"'{kpi['label']}'"}}}
            if "labelPosition" in kpi:
                label_props["position"] = {"expr": {"Literal": {"Value": f"'{kpi['labelPosition']}'"}}}
            _ensure_obj(objects, "label").append(_obj_entry(sel, label_props))
            props_set += len(label_props)

        # Accent bar color (per-KPI)
        if "accentColor" in kpi:
            c = kpi["accentColor"]
            _ensure_obj(objects, "accentBar").append(_obj_entry(sel, {
                "color": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{c}'"}}}}},
            }))
            props_set += 1

        # Tile background (per-KPI)
        if "tileBackground" in kpi:
            c = kpi["tileBackground"]
            _ensure_obj(objects, "cardCalloutArea").append(_obj_entry(sel, {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "backgroundFillColor": {"solid": {"color": {"expr": {"Literal": {"Value": f"'{c}'"}}}}},
            }))
            props_set += 2

        # ── 6. Reference labels ──────────────────────────────────
        for rl_idx, rl in enumerate(kpi.get("referenceLabels", [])):
            rl_ref = rl["measure"]
            rl_entity, rl_prop = _split_ref(rl_ref)
            field_id = f"field-kpi-{kpi_idx}-ref-{rl_idx}"

            # Binding entry (referenceLabel with measure expression)
            binding_sel = _ref_label_binding_selector(ref, field_id, rl_idx)
            _ensure_obj(objects, "referenceLabel").append(_obj_entry(binding_sel, {
                "value": {"expr": _measure_expr(rl_entity, rl_prop)},
            }))
            props_set += 1

            # Title entry
            fmt_sel = _ref_label_format_selector(field_id)
            if "title" in rl:
                _ensure_obj(objects, "referenceLabelTitle").append(_obj_entry(fmt_sel, {
                    "show": {"expr": {"Literal": {"Value": "true"}}},
                    "titleContentType": {"expr": {"Literal": {"Value": "'custom'"}}},
                    "titleText": {"expr": {"Literal": {"Value": f"'{rl['title']}'"}}},
                }))
                props_set += 3

            # Value formatting
            rl_value_props: dict[str, Any] = {}
            if "displayUnits" in rl:
                rl_value_props["valueDisplayUnits"] = {"expr": {"Literal": {"Value": f"{rl['displayUnits']}D"}}}
            if "fontColor" in rl:
                c = rl["fontColor"]
                rl_value_props["valueFontColor"] = {"solid": {"color": {"expr": {"Literal": {"Value": f"'{c}'"}}}}}
            if rl_value_props:
                _ensure_obj(objects, "referenceLabelValue").append(_obj_entry(fmt_sel, rl_value_props))
                props_set += len(rl_value_props)

    return props_set


def _map_prop(source: dict, src_key: str, target: dict, tgt_key: str) -> None:
    """Copy a value from source to target as a PBI Literal expression."""
    if src_key not in source:
        return
    val = source[src_key]
    if isinstance(val, bool):
        target[tgt_key] = {"expr": {"Literal": {"Value": "true" if val else "false"}}}
    elif isinstance(val, (int, float)):
        v = int(val) if val == int(val) else val
        target[tgt_key] = {"expr": {"Literal": {"Value": f"{v}D"}}}
    elif isinstance(val, str):
        target[tgt_key] = {"expr": {"Literal": {"Value": f"'{val}'"}}}
