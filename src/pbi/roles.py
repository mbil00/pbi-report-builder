"""Visual type role definitions for Power BI visuals.

Maps visual types to their supported data roles.
"""

from __future__ import annotations


def _role(name: str, description: str, multi: bool = False) -> dict:
    return {"name": name, "description": description, "multi": "yes" if multi else ""}


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
    "card": [
        _role("Values", "Displayed value"),
    ],
    "multiRowCard": [
        _role("Values", "Displayed fields", multi=True),
    ],

    # ── KPI ────────────────────────────────────────────────────
    "kpi": [
        _role("Indicator", "KPI value"),
        _role("TrendAxis", "Trend axis (date/time)"),
        _role("Goal", "Target/goal value"),
    ],

    # ── Tables & Matrix ────────────────────────────────────────
    "tableEx": [
        _role("Values", "Table columns", multi=True),
    ],
    "pivotTable": [
        _role("Rows", "Row headers", multi=True),
        _role("Columns", "Column headers", multi=True),
        _role("Values", "Cell values", multi=True),
    ],

    # ── Slicer ─────────────────────────────────────────────────
    "slicer": [
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

    # ── Decorative ─────────────────────────────────────────────
    "textbox": [],
    "shape": [],
    "image": [],
    "actionButton": [],
}
