"""Visual type catalog and role definitions for Power BI visuals."""

from __future__ import annotations

from dataclasses import dataclass


def _role(name: str, description: str, multi: bool = False) -> dict:
    return {"name": name, "description": description, "multi": "yes" if multi else ""}


VISUAL_TYPE_ALIASES: dict[str, str] = {
    "table": "tableEx",
    "matrix": "pivotTable",
    "card": "cardVisual",
    "button": "actionButton",
}

VISUAL_ROLE_ALIASES: dict[str, dict[str, str]] = {
    "cardVisual": {
        "Values": "Data",
        "Value": "Data",
    },
    "slicer": {"Field": "Values"},
    "advancedSlicerVisual": {"Field": "Values"},
    "listSlicer": {"Field": "Values"},
    "textSlicer": {"Field": "Values"},
    "treemap": {"Y": "Values"},
    "kpi": {"TrendAxis": "TrendLine"},
}


VISUAL_ROLES: dict[str, list[dict]] = {
    # ── Bar & Column charts ────────────────────────────────────
    "clusteredBarChart": [
        _role("Category", "Y axis categories"),
        _role("Y", "X axis values (bars)", multi=True),
        _role("Series", "Legend / color grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "clusteredColumnChart": [
        _role("Category", "X axis categories"),
        _role("Y", "Y axis values (columns)", multi=True),
        _role("Series", "Legend / color grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "stackedBarChart": [
        _role("Category", "Y axis categories"),
        _role("Y", "X axis values (stacked)", multi=True),
        _role("Series", "Legend / stack grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "stackedColumnChart": [
        _role("Category", "X axis categories"),
        _role("Y", "Y axis values (stacked)", multi=True),
        _role("Series", "Legend / stack grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "hundredPercentStackedBarChart": [
        _role("Category", "Y axis categories"),
        _role("Y", "X axis values (100% stacked)", multi=True),
        _role("Series", "Legend / stack grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "hundredPercentStackedColumnChart": [
        _role("Category", "X axis categories"),
        _role("Y", "Y axis values (100% stacked)", multi=True),
        _role("Series", "Legend / stack grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    # ── Line & Area charts ─────────────────────────────────────
    "lineChart": [
        _role("Category", "X axis categories"),
        _role("Y", "Y axis values (lines)", multi=True),
        _role("Series", "Legend / line grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "areaChart": [
        _role("Category", "X axis categories"),
        _role("Y", "Y axis values (areas)", multi=True),
        _role("Series", "Legend / area grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "stackedAreaChart": [
        _role("Category", "X axis categories"),
        _role("Y", "Y axis values (stacked areas)", multi=True),
        _role("Series", "Legend / area grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "hundredPercentStackedAreaChart": [
        _role("Category", "X axis categories"),
        _role("Y", "Y axis values (100% stacked areas)", multi=True),
        _role("Series", "Legend / area grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    # ── Combo charts ───────────────────────────────────────────
    "lineStackedColumnComboChart": [
        _role("Category", "Shared X axis"),
        _role("Y", "Column values", multi=True),
        _role("Y2", "Line values", multi=True),
        _role("Series", "Legend grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "lineClusteredColumnComboChart": [
        _role("Category", "Shared X axis"),
        _role("Y", "Column values", multi=True),
        _role("Y2", "Line values", multi=True),
        _role("Series", "Legend grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    # ── Pie & Donut ────────────────────────────────────────────
    "pieChart": [
        _role("Category", "Slices"),
        _role("Y", "Values"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "donutChart": [
        _role("Category", "Slices"),
        _role("Y", "Values"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    # ── Cards ──────────────────────────────────────────────────
    "cardVisual": [
        _role("Data", "Displayed measures", multi=True),
        _role("Rows", "Grouping field"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "multiRowCard": [
        _role("Values", "Displayed fields", multi=True),
    ],
    "kpi": [
        _role("Indicator", "KPI value"),
        _role("TrendLine", "Trend axis (date/time)"),
        _role("Goal", "Target/goal value"),
    ],
    "scorecard": [],
    # ── Tables & Slicers ───────────────────────────────────────
    "tableEx": [
        _role("Values", "Table columns", multi=True),
    ],
    "pivotTable": [
        _role("Rows", "Row headers", multi=True),
        _role("Columns", "Column headers", multi=True),
        _role("Values", "Cell values", multi=True),
    ],
    "slicer": [
        _role("Values", "Filter field"),
    ],
    "advancedSlicerVisual": [
        _role("Values", "Filter field"),
    ],
    "listSlicer": [
        _role("Values", "Filter field"),
    ],
    "textSlicer": [
        _role("Values", "Filter field"),
    ],
    # ── Scatter & Bubble ───────────────────────────────────────
    "scatterChart": [
        _role("Category", "Details / data points"),
        _role("X", "X axis value"),
        _role("Y", "Y axis value"),
        _role("Size", "Bubble size"),
        _role("Series", "Legend / color grouping"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    # ── Map visuals ────────────────────────────────────────────
    "azureMap": [
        _role("Category", "Location"),
        _role("Size", "Bubble size"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "esriVisual": [],
    "map": [
        _role("Category", "Location"),
        _role("Series", "Legend"),
        _role("Size", "Bubble size"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "filledMap": [
        _role("Category", "Location"),
        _role("Series", "Legend"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    # ── Other chart types ──────────────────────────────────────
    "barChart": [
        _role("Category", "Primary axis categories"),
        _role("Rows", "Secondary grouping field"),
        _role("Y", "Values", multi=True),
    ],
    "columnChart": [
        _role("Category", "Primary axis categories"),
        _role("Rows", "Secondary grouping field"),
        _role("Series", "Legend grouping"),
        _role("Y", "Values", multi=True),
    ],
    "waterfallChart": [
        _role("Category", "Categories"),
        _role("Y", "Values"),
        _role("Breakdown", "Breakdown field"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "funnel": [
        _role("Category", "Group"),
        _role("Y", "Values"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "gauge": [
        _role("Y", "Value"),
        _role("MinValue", "Minimum value"),
        _role("MaxValue", "Maximum value"),
        _role("TargetValue", "Target value"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "treemap": [
        _role("Group", "Group hierarchy", multi=True),
        _role("Values", "Values"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "ribbonChart": [
        _role("Category", "X axis"),
        _role("Y", "Values", multi=True),
        _role("Series", "Legend"),
        _role("Tooltips", "Additional tooltip fields", multi=True),
    ],
    "decompositionTreeVisual": [
        _role("Analyze", "Primary measure to analyze", multi=True),
        _role("ExplainBy", "Fields used to split the measure", multi=True),
    ],
    "keyDriversVisual": [
        _role("Details", "Details or segment field"),
        _role("ExplainBy", "Fields used to explain the target", multi=True),
        _role("Target", "Target measure"),
    ],
    "aiNarratives": [],
    "qnaVisual": [],
    "rdlVisual": [],
    "scriptVisual": [],
    # ── Decorative & navigation ────────────────────────────────
    "image": [],
    "actionButton": [],
    "bookmarkNavigator": [],
    "pageNavigator": [],
    "shape": [],
    "textbox": [],
}


SAMPLE_BACKED_VISUAL_TYPES: set[str] = {
    "advancedSlicerVisual",
    "aiNarratives",
    "areaChart",
    "azureMap",
    "barChart",
    "cardVisual",
    "clusteredBarChart",
    "clusteredColumnChart",
    "columnChart",
    "decompositionTreeVisual",
    "donutChart",
    "esriVisual",
    "funnel",
    "gauge",
    "hundredPercentStackedAreaChart",
    "hundredPercentStackedBarChart",
    "hundredPercentStackedColumnChart",
    "image",
    "keyDriversVisual",
    "kpi",
    "lineChart",
    "lineClusteredColumnComboChart",
    "lineStackedColumnComboChart",
    "listSlicer",
    "pieChart",
    "pivotTable",
    "qnaVisual",
    "rdlVisual",
    "ribbonChart",
    "scatterChart",
    "scorecard",
    "scriptVisual",
    "slicer",
    "stackedAreaChart",
    "tableEx",
    "textSlicer",
    "treemap",
    "waterfallChart",
}


KNOWN_VISUAL_TYPES: set[str] = set(VISUAL_ROLES) | SAMPLE_BACKED_VISUAL_TYPES


@dataclass(frozen=True)
class VisualTypeInfo:
    visual_type: str
    roles: list[dict]
    status: str
    note: str


def _schema_roles(visual_type: str) -> list[dict]:
    """Build role list from schema data for a visual type.

    Returns roles in _role() format with descriptions derived from
    schema displayName and kind metadata.
    """
    try:
        from pbi.visual_schema import get_data_roles
    except Exception:
        return []

    schema = get_data_roles(visual_type)
    if not schema:
        return []

    kind_desc = {0: "Grouping field", 1: "Measure field", 2: "Any field"}
    roles = []
    for name, info in schema.items():
        display = info.get("displayName", name)
        # Clean up localization keys (e.g. "Role_DisplayName_KPI_Indicator" → "Indicator")
        if display.startswith("Role_"):
            display = name
        kind = info.get("kind", 2)
        desc = f"{display} ({kind_desc.get(kind, 'field')})"
        multi = kind == 1  # Measure roles typically accept multiple fields
        roles.append(_role(name, desc, multi=multi))
    return roles


def _merge_roles(handcrafted: list[dict], schema: list[dict]) -> list[dict]:
    """Merge handcrafted roles with schema roles, adding any missing ones."""
    existing = {r["name"] for r in handcrafted}
    merged = list(handcrafted)
    for role in schema:
        if role["name"] not in existing:
            merged.append(role)
    return merged


def normalize_visual_type(name: str) -> str:
    """Normalize user-facing aliases to canonical PBIR visualType values."""
    return VISUAL_TYPE_ALIASES.get(name, name)


def is_known_visual_type(name: str) -> bool:
    """Return whether the visual type is known to the CLI catalog or schema."""
    canonical = normalize_visual_type(name)
    if canonical in KNOWN_VISUAL_TYPES:
        return True
    # Check schema as fallback
    try:
        from pbi.visual_schema import get_visual_schema
        return get_visual_schema(canonical) is not None
    except Exception:
        return False


def get_visual_roles(visual_type: str) -> list[dict]:
    """Return role metadata for a visual type.

    Uses handcrafted roles when available, supplemented with any missing
    roles from the schema. Falls back entirely to schema for types not
    in the handcrafted catalog.
    """
    canonical = normalize_visual_type(visual_type)
    handcrafted = VISUAL_ROLES.get(canonical, [])
    schema = _schema_roles(canonical)

    if handcrafted and schema:
        return _merge_roles(handcrafted, schema)
    if handcrafted:
        return handcrafted
    return schema


def normalize_visual_role(visual_type: str, role: str) -> str:
    """Normalize a user-facing role name to the exported PBIR role name."""
    canonical_type = normalize_visual_type(visual_type)
    all_roles = get_visual_roles(canonical_type)
    known_roles = [entry["name"] for entry in all_roles]

    for known_role in known_roles:
        if known_role.lower() == role.lower():
            return known_role

    alias_map = VISUAL_ROLE_ALIASES.get(canonical_type, {})
    for alias, canonical_role in alias_map.items():
        if alias.lower() == role.lower():
            return canonical_role

    return role


def get_visual_type_info(visual_type: str) -> VisualTypeInfo | None:
    """Return catalog info for a known visual type."""
    canonical = normalize_visual_type(visual_type)
    roles = get_visual_roles(canonical)
    in_catalog = canonical in KNOWN_VISUAL_TYPES
    in_schema = bool(_schema_roles(canonical))

    if not in_catalog and not in_schema:
        return None

    if roles:
        if canonical in VISUAL_ROLES:
            status = "role-backed"
            note = "Roles are modeled and can be used with visual binding commands."
        else:
            status = "schema-backed"
            note = "Roles derived from PBI Desktop schema."
        return VisualTypeInfo(
            visual_type=canonical, roles=roles, status=status, note=note,
        )
    return VisualTypeInfo(
        visual_type=canonical,
        roles=[],
        status="sample-backed",
        note="Observed in exported PBIR sample data, but role/query metadata is not modeled yet.",
    )


def list_visual_type_info() -> list[VisualTypeInfo]:
    """Return known visual types with support metadata."""
    try:
        from pbi.visual_schema import get_visual_types
        schema_types = set(get_visual_types())
    except Exception:
        schema_types = set()
    all_types = KNOWN_VISUAL_TYPES | schema_types
    result = []
    for vt in sorted(all_types):
        info = get_visual_type_info(vt)
        if info is not None:
            result.append(info)
    return result
