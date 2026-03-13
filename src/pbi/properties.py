"""Property resolution and editing for PBI visual and page JSON files.

Handles mapping between human-friendly property names (like "background.color")
and the actual PBI JSON structure (nested visualContainerObjects with expr literals).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class PropertyDef:
    json_path: str | None  # Dot path into the JSON, or None for object-style properties
    value_type: str  # "number", "string", "boolean", "color", "page_color", "enum"
    description: str
    enum_values: tuple[str, ...] | None = None
    # For object-style properties (both visualContainerObjects and visual.objects)
    container_key: str | None = None
    container_prop: str | None = None
    objects_path: str = "visualContainerObjects"  # or "objects" for chart formatting
    top_level: bool = False  # True for page-level objects (data.objects vs data.visual.objects)
    selector: str | None = None  # "default" for {"id": "default"} selector entry


# ── Visual properties ──────────────────────────────────────────────

VISUAL_PROPERTIES: dict[str, PropertyDef] = {
    # Position
    "position.x": PropertyDef("position.x", "number", "X coordinate"),
    "position.y": PropertyDef("position.y", "number", "Y coordinate"),
    "position.width": PropertyDef("position.width", "number", "Width"),
    "position.height": PropertyDef("position.height", "number", "Height"),
    "position.z": PropertyDef("position.z", "number", "Z-order"),
    "position.tabOrder": PropertyDef("position.tabOrder", "number", "Tab order"),
    "position.angle": PropertyDef("position.angle", "number", "Rotation angle"),
    # Core
    "visualType": PropertyDef("visual.visualType", "string", "Visual chart type"),
    "isHidden": PropertyDef("isHidden", "boolean", "Hidden in view mode"),
    # ── visualContainerObjects ─────────────────────────────────
    # Background
    "background.show": PropertyDef(
        None, "boolean", "Show background",
        container_key="background", container_prop="show",
    ),
    "background.color": PropertyDef(
        None, "color", "Background color",
        container_key="background", container_prop="color",
    ),
    "background.transparency": PropertyDef(
        None, "number", "Background transparency (0-100)",
        container_key="background", container_prop="transparency",
    ),
    # Border
    "border.show": PropertyDef(
        None, "boolean", "Show border",
        container_key="border", container_prop="show",
    ),
    "border.color": PropertyDef(
        None, "color", "Border color",
        container_key="border", container_prop="color",
    ),
    "border.width": PropertyDef(
        None, "number", "Border width",
        container_key="border", container_prop="width",
    ),
    "border.radius": PropertyDef(
        None, "number", "Border radius",
        container_key="border", container_prop="radius",
    ),
    # Title
    "title.show": PropertyDef(
        None, "boolean", "Show title",
        container_key="title", container_prop="show",
    ),
    "title.text": PropertyDef(
        None, "string", "Title text",
        container_key="title", container_prop="text",
    ),
    "title.heading": PropertyDef(
        None, "string", "Title heading level",
        container_key="title", container_prop="heading",
    ),
    "title.wrap": PropertyDef(
        None, "boolean", "Wrap title text",
        container_key="title", container_prop="titleWrap",
    ),
    "title.color": PropertyDef(
        None, "color", "Title font color",
        container_key="title", container_prop="fontColor",
    ),
    "title.background": PropertyDef(
        None, "color", "Title background color",
        container_key="title", container_prop="background",
    ),
    "title.alignment": PropertyDef(
        None, "enum", "Title alignment",
        container_key="title", container_prop="alignment",
        enum_values=("left", "center", "right"),
    ),
    "title.fontSize": PropertyDef(
        None, "number", "Title font size",
        container_key="title", container_prop="fontSize",
    ),
    "title.bold": PropertyDef(
        None, "boolean", "Title bold",
        container_key="title", container_prop="bold",
    ),
    "title.italic": PropertyDef(
        None, "boolean", "Title italic",
        container_key="title", container_prop="italic",
    ),
    "title.underline": PropertyDef(
        None, "boolean", "Title underline",
        container_key="title", container_prop="underline",
    ),
    "title.fontFamily": PropertyDef(
        None, "string", "Title font family",
        container_key="title", container_prop="fontFamily",
    ),
    # Subtitle
    "subtitle.show": PropertyDef(
        None, "boolean", "Show subtitle",
        container_key="subTitle", container_prop="show",
    ),
    "subtitle.text": PropertyDef(
        None, "string", "Subtitle text",
        container_key="subTitle", container_prop="text",
    ),
    "subtitle.heading": PropertyDef(
        None, "string", "Subtitle heading level",
        container_key="subTitle", container_prop="heading",
    ),
    "subtitle.wrap": PropertyDef(
        None, "boolean", "Wrap subtitle text",
        container_key="subTitle", container_prop="titleWrap",
    ),
    "subtitle.color": PropertyDef(
        None, "color", "Subtitle font color",
        container_key="subTitle", container_prop="fontColor",
    ),
    "subtitle.alignment": PropertyDef(
        None, "enum", "Subtitle alignment",
        container_key="subTitle", container_prop="alignment",
        enum_values=("left", "center", "right"),
    ),
    "subtitle.fontSize": PropertyDef(
        None, "number", "Subtitle font size",
        container_key="subTitle", container_prop="fontSize",
    ),
    "subtitle.bold": PropertyDef(
        None, "boolean", "Subtitle bold",
        container_key="subTitle", container_prop="bold",
    ),
    "subtitle.italic": PropertyDef(
        None, "boolean", "Subtitle italic",
        container_key="subTitle", container_prop="italic",
    ),
    "subtitle.underline": PropertyDef(
        None, "boolean", "Subtitle underline",
        container_key="subTitle", container_prop="underline",
    ),
    "subtitle.fontFamily": PropertyDef(
        None, "string", "Subtitle font family",
        container_key="subTitle", container_prop="fontFamily",
    ),
    # Divider
    "divider.show": PropertyDef(
        None, "boolean", "Show divider between title and visual",
        container_key="divider", container_prop="show",
    ),
    "divider.color": PropertyDef(
        None, "color", "Divider color",
        container_key="divider", container_prop="color",
    ),
    "divider.width": PropertyDef(
        None, "number", "Divider width",
        container_key="divider", container_prop="width",
    ),
    "divider.style": PropertyDef(
        None, "string", "Divider style",
        container_key="divider", container_prop="style",
    ),
    "divider.ignorePadding": PropertyDef(
        None, "boolean", "Divider ignores padding",
        container_key="divider", container_prop="ignorePadding",
    ),
    # Spacing
    "spacing.customize": PropertyDef(
        None, "boolean", "Enable custom spacing",
        container_key="spacing", container_prop="customizeSpacing",
    ),
    "spacing.vertical": PropertyDef(
        None, "number", "Vertical spacing",
        container_key="spacing", container_prop="verticalSpacing",
    ),
    "spacing.belowTitle": PropertyDef(
        None, "number", "Space below title",
        container_key="spacing", container_prop="spaceBelowTitle",
    ),
    "spacing.belowSubtitle": PropertyDef(
        None, "number", "Space below subtitle",
        container_key="spacing", container_prop="spaceBelowSubTitle",
    ),
    "spacing.belowTitleArea": PropertyDef(
        None, "number", "Space below title area",
        container_key="spacing", container_prop="spaceBelowTitleArea",
    ),
    # Padding
    "padding.top": PropertyDef(
        None, "number", "Top padding",
        container_key="padding", container_prop="top",
    ),
    "padding.bottom": PropertyDef(
        None, "number", "Bottom padding",
        container_key="padding", container_prop="bottom",
    ),
    "padding.left": PropertyDef(
        None, "number", "Left padding",
        container_key="padding", container_prop="left",
    ),
    "padding.right": PropertyDef(
        None, "number", "Right padding",
        container_key="padding", container_prop="right",
    ),
    # Drop shadow
    "shadow.show": PropertyDef(
        None, "boolean", "Show drop shadow",
        container_key="dropShadow", container_prop="show",
    ),
    "shadow.preset": PropertyDef(
        None, "string", "Shadow preset",
        container_key="dropShadow", container_prop="preset",
    ),
    "shadow.position": PropertyDef(
        None, "string", "Shadow position",
        container_key="dropShadow", container_prop="position",
    ),
    "shadow.color": PropertyDef(
        None, "color", "Drop shadow color",
        container_key="dropShadow", container_prop="color",
    ),
    "shadow.transparency": PropertyDef(
        None, "number", "Shadow transparency",
        container_key="dropShadow", container_prop="transparency",
    ),
    "shadow.spread": PropertyDef(
        None, "number", "Shadow spread",
        container_key="dropShadow", container_prop="shadowSpread",
    ),
    "shadow.blur": PropertyDef(
        None, "number", "Shadow blur",
        container_key="dropShadow", container_prop="shadowBlur",
    ),
    "shadow.angle": PropertyDef(
        None, "number", "Shadow angle",
        container_key="dropShadow", container_prop="angle",
    ),
    "shadow.distance": PropertyDef(
        None, "number", "Shadow distance",
        container_key="dropShadow", container_prop="shadowDistance",
    ),
    # Lock aspect ratio
    "lockAspect": PropertyDef(
        None, "boolean", "Lock aspect ratio",
        container_key="lockAspect", container_prop="show",
    ),
    # Alt text
    "altText": PropertyDef(
        None, "string", "Accessibility alt text",
        container_key="general", container_prop="altText",
    ),
    # Visual header
    "header.show": PropertyDef(
        None, "boolean", "Show visual header",
        container_key="visualHeader", container_prop="show",
    ),
    "header.background": PropertyDef(
        None, "color", "Visual header background",
        container_key="visualHeader", container_prop="background",
    ),
    "header.border": PropertyDef(
        None, "color", "Visual header border color",
        container_key="visualHeader", container_prop="border",
    ),
    "header.transparency": PropertyDef(
        None, "number", "Visual header transparency",
        container_key="visualHeader", container_prop="transparency",
    ),
    "header.foreground": PropertyDef(
        None, "color", "Visual header icon color",
        container_key="visualHeader", container_prop="foreground",
    ),
    # Visual tooltip
    "tooltip.show": PropertyDef(
        None, "boolean", "Show tooltip",
        container_key="visualTooltip", container_prop="show",
    ),
    "tooltip.type": PropertyDef(
        None, "string", "Tooltip type (Default or ReportPage)",
        container_key="visualTooltip", container_prop="type",
    ),
    "tooltip.section": PropertyDef(
        None, "string", "Tooltip report page name",
        container_key="visualTooltip", container_prop="section",
    ),
    "tooltip.titleColor": PropertyDef(
        None, "color", "Tooltip title font color",
        container_key="visualTooltip", container_prop="titleFontColor",
    ),
    "tooltip.valueColor": PropertyDef(
        None, "color", "Tooltip value font color",
        container_key="visualTooltip", container_prop="valueFontColor",
    ),
    "tooltip.fontSize": PropertyDef(
        None, "number", "Tooltip font size",
        container_key="visualTooltip", container_prop="fontSize",
    ),
    "tooltip.fontFamily": PropertyDef(
        None, "string", "Tooltip font family",
        container_key="visualTooltip", container_prop="fontFamily",
    ),
    "tooltip.background": PropertyDef(
        None, "color", "Tooltip background color",
        container_key="visualTooltip", container_prop="background",
    ),
    "tooltip.transparency": PropertyDef(
        None, "number", "Tooltip transparency",
        container_key="visualTooltip", container_prop="transparency",
    ),
    # Button actions (visualLink)
    "action.show": PropertyDef(
        None, "boolean", "Enable button action",
        container_key="visualLink", container_prop="show",
    ),
    "action.type": PropertyDef(
        None, "string", "Action type (Back, Bookmark, Drillthrough, PageNavigation, QnA, WebUrl)",
        container_key="visualLink", container_prop="type",
    ),
    "action.bookmark": PropertyDef(
        None, "string", "Target bookmark name (for Bookmark action)",
        container_key="visualLink", container_prop="bookmark",
    ),
    "action.page": PropertyDef(
        None, "string", "Target page name (for PageNavigation action)",
        container_key="visualLink", container_prop="navigationSection",
    ),
    "action.drillthrough": PropertyDef(
        None, "string", "Target drillthrough page (for Drillthrough action)",
        container_key="visualLink", container_prop="drillthroughSection",
    ),
    "action.url": PropertyDef(
        None, "string", "Target URL (for WebUrl action)",
        container_key="visualLink", container_prop="webUrl",
    ),
    "action.tooltip": PropertyDef(
        None, "string", "Button tooltip text",
        container_key="visualLink", container_prop="tooltip",
    ),
    # Style preset
    "stylePreset": PropertyDef(
        None, "string", "Style preset name",
        container_key="stylePreset", container_prop="name",
    ),
    # ── Chart formatting (visual.objects) ──────────────────────
    # Legend
    "legend.show": PropertyDef(
        None, "boolean", "Show legend",
        container_key="legend", container_prop="show", objects_path="objects",
    ),
    "legend.position": PropertyDef(
        None, "enum", "Legend position",
        container_key="legend", container_prop="position", objects_path="objects",
        enum_values=("Top", "Bottom", "Left", "Right", "TopCenter", "BottomCenter", "LeftCenter", "RightCenter"),
    ),
    "legend.color": PropertyDef(
        None, "color", "Legend text color",
        container_key="legend", container_prop="labelColor", objects_path="objects",
    ),
    "legend.fontSize": PropertyDef(
        None, "number", "Legend font size",
        container_key="legend", container_prop="fontSize", objects_path="objects",
    ),
    "legend.fontFamily": PropertyDef(
        None, "string", "Legend font family",
        container_key="legend", container_prop="fontFamily", objects_path="objects",
    ),
    "legend.bold": PropertyDef(
        None, "boolean", "Legend bold",
        container_key="legend", container_prop="bold", objects_path="objects",
    ),
    "legend.italic": PropertyDef(
        None, "boolean", "Legend italic",
        container_key="legend", container_prop="italic", objects_path="objects",
    ),
    "legend.showTitle": PropertyDef(
        None, "boolean", "Show legend title",
        container_key="legend", container_prop="showTitle", objects_path="objects",
    ),
    "legend.titleText": PropertyDef(
        None, "string", "Legend title text",
        container_key="legend", container_prop="titleText", objects_path="objects",
    ),
    # ── Category axis (X axis) ────────────────────────────────
    "xAxis.show": PropertyDef(
        None, "boolean", "Show category axis",
        container_key="categoryAxis", container_prop="show", objects_path="objects",
    ),
    "xAxis.position": PropertyDef(
        None, "enum", "Category axis position",
        container_key="categoryAxis", container_prop="position", objects_path="objects",
        enum_values=("Left", "Right"),
    ),
    "xAxis.axisScale": PropertyDef(
        None, "enum", "Category axis scale",
        container_key="categoryAxis", container_prop="axisScale", objects_path="objects",
        enum_values=("linear", "log"),
    ),
    "xAxis.axisType": PropertyDef(
        None, "enum", "Category axis type",
        container_key="categoryAxis", container_prop="axisType", objects_path="objects",
        enum_values=("Scalar", "Categorical"),
    ),
    "xAxis.start": PropertyDef(
        None, "number", "Category axis range start",
        container_key="categoryAxis", container_prop="start", objects_path="objects",
    ),
    "xAxis.end": PropertyDef(
        None, "number", "Category axis range end",
        container_key="categoryAxis", container_prop="end", objects_path="objects",
    ),
    # Labels
    "xAxis.color": PropertyDef(
        None, "color", "Category axis label color",
        container_key="categoryAxis", container_prop="labelColor", objects_path="objects",
    ),
    "xAxis.fontSize": PropertyDef(
        None, "number", "Category axis font size",
        container_key="categoryAxis", container_prop="fontSize", objects_path="objects",
    ),
    "xAxis.fontFamily": PropertyDef(
        None, "string", "Category axis font family",
        container_key="categoryAxis", container_prop="fontFamily", objects_path="objects",
    ),
    "xAxis.bold": PropertyDef(
        None, "boolean", "Category axis labels bold",
        container_key="categoryAxis", container_prop="bold", objects_path="objects",
    ),
    "xAxis.italic": PropertyDef(
        None, "boolean", "Category axis labels italic",
        container_key="categoryAxis", container_prop="italic", objects_path="objects",
    ),
    "xAxis.displayUnits": PropertyDef(
        None, "string", "Category axis display units (0=Auto, 1=None, 1000=K, 1000000=M)",
        container_key="categoryAxis", container_prop="labelDisplayUnits", objects_path="objects",
    ),
    "xAxis.precision": PropertyDef(
        None, "number", "Category axis decimal places",
        container_key="categoryAxis", container_prop="labelPrecision", objects_path="objects",
    ),
    "xAxis.concatenateLabels": PropertyDef(
        None, "boolean", "Concatenate category labels",
        container_key="categoryAxis", container_prop="concatenateLabels", objects_path="objects",
    ),
    "xAxis.innerPadding": PropertyDef(
        None, "number", "Inner padding between columns/bars",
        container_key="categoryAxis", container_prop="innerPadding", objects_path="objects",
    ),
    # Title
    "xAxis.title": PropertyDef(
        None, "boolean", "Show category axis title",
        container_key="categoryAxis", container_prop="showAxisTitle", objects_path="objects",
    ),
    "xAxis.titleText": PropertyDef(
        None, "string", "Category axis title text",
        container_key="categoryAxis", container_prop="axisTitle", objects_path="objects",
    ),
    "xAxis.titleColor": PropertyDef(
        None, "color", "Category axis title color",
        container_key="categoryAxis", container_prop="titleColor", objects_path="objects",
    ),
    "xAxis.titleFontSize": PropertyDef(
        None, "number", "Category axis title font size",
        container_key="categoryAxis", container_prop="titleFontSize", objects_path="objects",
    ),
    "xAxis.titleFontFamily": PropertyDef(
        None, "string", "Category axis title font family",
        container_key="categoryAxis", container_prop="titleFontFamily", objects_path="objects",
    ),
    "xAxis.axisStyle": PropertyDef(
        None, "enum", "Category axis style",
        container_key="categoryAxis", container_prop="axisStyle", objects_path="objects",
        enum_values=("showTitleOnly", "showUnitOnly", "showBoth"),
    ),
    # Gridlines
    "xAxis.gridlines": PropertyDef(
        None, "boolean", "Show category axis gridlines",
        container_key="categoryAxis", container_prop="gridlineShow", objects_path="objects",
    ),
    "xAxis.gridlineColor": PropertyDef(
        None, "color", "Category axis gridline color",
        container_key="categoryAxis", container_prop="gridlineColor", objects_path="objects",
    ),
    "xAxis.gridlineThickness": PropertyDef(
        None, "number", "Category axis gridline thickness",
        container_key="categoryAxis", container_prop="gridlineThickness", objects_path="objects",
    ),
    "xAxis.gridlineStyle": PropertyDef(
        None, "enum", "Category axis gridline style",
        container_key="categoryAxis", container_prop="gridlineStyle", objects_path="objects",
        enum_values=("dashed", "solid", "dotted"),
    ),
    "xAxis.invertAxis": PropertyDef(
        None, "boolean", "Invert category axis order",
        container_key="categoryAxis", container_prop="invertAxis", objects_path="objects",
    ),
    # ── Value axis (Y axis) ───────────────────────────────────
    "yAxis.show": PropertyDef(
        None, "boolean", "Show value axis",
        container_key="valueAxis", container_prop="show", objects_path="objects",
    ),
    "yAxis.position": PropertyDef(
        None, "enum", "Value axis position",
        container_key="valueAxis", container_prop="position", objects_path="objects",
        enum_values=("Left", "Right"),
    ),
    "yAxis.axisScale": PropertyDef(
        None, "enum", "Value axis scale",
        container_key="valueAxis", container_prop="axisScale", objects_path="objects",
        enum_values=("linear", "log"),
    ),
    "yAxis.start": PropertyDef(
        None, "number", "Value axis range start",
        container_key="valueAxis", container_prop="start", objects_path="objects",
    ),
    "yAxis.end": PropertyDef(
        None, "number", "Value axis range end",
        container_key="valueAxis", container_prop="end", objects_path="objects",
    ),
    # Labels
    "yAxis.color": PropertyDef(
        None, "color", "Value axis label color",
        container_key="valueAxis", container_prop="labelColor", objects_path="objects",
    ),
    "yAxis.fontSize": PropertyDef(
        None, "number", "Value axis font size",
        container_key="valueAxis", container_prop="fontSize", objects_path="objects",
    ),
    "yAxis.fontFamily": PropertyDef(
        None, "string", "Value axis font family",
        container_key="valueAxis", container_prop="fontFamily", objects_path="objects",
    ),
    "yAxis.bold": PropertyDef(
        None, "boolean", "Value axis labels bold",
        container_key="valueAxis", container_prop="bold", objects_path="objects",
    ),
    "yAxis.italic": PropertyDef(
        None, "boolean", "Value axis labels italic",
        container_key="valueAxis", container_prop="italic", objects_path="objects",
    ),
    "yAxis.displayUnits": PropertyDef(
        None, "string", "Value axis display units (0=Auto, 1=None, 1000=K, 1000000=M)",
        container_key="valueAxis", container_prop="labelDisplayUnits", objects_path="objects",
    ),
    "yAxis.precision": PropertyDef(
        None, "number", "Value axis decimal places",
        container_key="valueAxis", container_prop="labelPrecision", objects_path="objects",
    ),
    # Title
    "yAxis.title": PropertyDef(
        None, "boolean", "Show value axis title",
        container_key="valueAxis", container_prop="showAxisTitle", objects_path="objects",
    ),
    "yAxis.titleText": PropertyDef(
        None, "string", "Value axis title text",
        container_key="valueAxis", container_prop="axisTitle", objects_path="objects",
    ),
    "yAxis.titleColor": PropertyDef(
        None, "color", "Value axis title color",
        container_key="valueAxis", container_prop="titleColor", objects_path="objects",
    ),
    "yAxis.titleFontSize": PropertyDef(
        None, "number", "Value axis title font size",
        container_key="valueAxis", container_prop="titleFontSize", objects_path="objects",
    ),
    "yAxis.titleFontFamily": PropertyDef(
        None, "string", "Value axis title font family",
        container_key="valueAxis", container_prop="titleFontFamily", objects_path="objects",
    ),
    "yAxis.axisStyle": PropertyDef(
        None, "enum", "Value axis style",
        container_key="valueAxis", container_prop="axisStyle", objects_path="objects",
        enum_values=("showTitleOnly", "showUnitOnly", "showBoth"),
    ),
    # Gridlines
    "yAxis.gridlines": PropertyDef(
        None, "boolean", "Show value axis gridlines",
        container_key="valueAxis", container_prop="gridlineShow", objects_path="objects",
    ),
    "yAxis.gridlineColor": PropertyDef(
        None, "color", "Value axis gridline color",
        container_key="valueAxis", container_prop="gridlineColor", objects_path="objects",
    ),
    "yAxis.gridlineThickness": PropertyDef(
        None, "number", "Value axis gridline thickness",
        container_key="valueAxis", container_prop="gridlineThickness", objects_path="objects",
    ),
    "yAxis.gridlineStyle": PropertyDef(
        None, "enum", "Value axis gridline style",
        container_key="valueAxis", container_prop="gridlineStyle", objects_path="objects",
        enum_values=("dashed", "solid", "dotted"),
    ),
    "yAxis.invertAxis": PropertyDef(
        None, "boolean", "Invert value axis",
        container_key="valueAxis", container_prop="invertAxis", objects_path="objects",
    ),
    # ── Secondary axis (Y2) ──────────────────────────────────
    "y2Axis.show": PropertyDef(
        None, "boolean", "Show secondary value axis",
        container_key="y2Axis", container_prop="show", objects_path="objects",
    ),
    "y2Axis.position": PropertyDef(
        None, "enum", "Secondary axis position",
        container_key="y2Axis", container_prop="position", objects_path="objects",
        enum_values=("Left", "Right"),
    ),
    "y2Axis.axisScale": PropertyDef(
        None, "enum", "Secondary axis scale",
        container_key="y2Axis", container_prop="axisScale", objects_path="objects",
        enum_values=("linear", "log"),
    ),
    "y2Axis.start": PropertyDef(
        None, "number", "Secondary axis range start",
        container_key="y2Axis", container_prop="start", objects_path="objects",
    ),
    "y2Axis.end": PropertyDef(
        None, "number", "Secondary axis range end",
        container_key="y2Axis", container_prop="end", objects_path="objects",
    ),
    "y2Axis.color": PropertyDef(
        None, "color", "Secondary axis label color",
        container_key="y2Axis", container_prop="labelColor", objects_path="objects",
    ),
    "y2Axis.fontSize": PropertyDef(
        None, "number", "Secondary axis font size",
        container_key="y2Axis", container_prop="fontSize", objects_path="objects",
    ),
    "y2Axis.fontFamily": PropertyDef(
        None, "string", "Secondary axis font family",
        container_key="y2Axis", container_prop="fontFamily", objects_path="objects",
    ),
    "y2Axis.displayUnits": PropertyDef(
        None, "string", "Secondary axis display units",
        container_key="y2Axis", container_prop="labelDisplayUnits", objects_path="objects",
    ),
    "y2Axis.precision": PropertyDef(
        None, "number", "Secondary axis decimal places",
        container_key="y2Axis", container_prop="labelPrecision", objects_path="objects",
    ),
    "y2Axis.title": PropertyDef(
        None, "boolean", "Show secondary axis title",
        container_key="y2Axis", container_prop="showAxisTitle", objects_path="objects",
    ),
    "y2Axis.titleText": PropertyDef(
        None, "string", "Secondary axis title text",
        container_key="y2Axis", container_prop="axisTitle", objects_path="objects",
    ),
    "y2Axis.titleColor": PropertyDef(
        None, "color", "Secondary axis title color",
        container_key="y2Axis", container_prop="titleColor", objects_path="objects",
    ),
    "y2Axis.titleFontSize": PropertyDef(
        None, "number", "Secondary axis title font size",
        container_key="y2Axis", container_prop="titleFontSize", objects_path="objects",
    ),
    "y2Axis.gridlines": PropertyDef(
        None, "boolean", "Show secondary axis gridlines",
        container_key="y2Axis", container_prop="gridlineShow", objects_path="objects",
    ),
    "y2Axis.gridlineColor": PropertyDef(
        None, "color", "Secondary axis gridline color",
        container_key="y2Axis", container_prop="gridlineColor", objects_path="objects",
    ),
    # ── Data labels ───────────────────────────────────────────
    "labels.show": PropertyDef(
        None, "boolean", "Show data labels",
        container_key="labels", container_prop="show", objects_path="objects",
    ),
    "labels.color": PropertyDef(
        None, "color", "Data label color",
        container_key="labels", container_prop="color", objects_path="objects",
    ),
    "labels.fontSize": PropertyDef(
        None, "number", "Data label font size",
        container_key="labels", container_prop="fontSize", objects_path="objects",
    ),
    "labels.fontFamily": PropertyDef(
        None, "string", "Data label font family",
        container_key="labels", container_prop="fontFamily", objects_path="objects",
    ),
    "labels.bold": PropertyDef(
        None, "boolean", "Data label bold",
        container_key="labels", container_prop="bold", objects_path="objects",
    ),
    "labels.italic": PropertyDef(
        None, "boolean", "Data label italic",
        container_key="labels", container_prop="italic", objects_path="objects",
    ),
    "labels.position": PropertyDef(
        None, "enum", "Data label position",
        container_key="labels", container_prop="labelPosition", objects_path="objects",
        enum_values=("Auto", "InsideEnd", "OutsideEnd", "InsideCenter", "InsideBase"),
    ),
    "labels.format": PropertyDef(
        None, "string", "Data label display units (0=Auto, 1000=K, 1000000=M)",
        container_key="labels", container_prop="labelDisplayUnits", objects_path="objects",
    ),
    "labels.precision": PropertyDef(
        None, "number", "Data label decimal places",
        container_key="labels", container_prop="labelPrecision", objects_path="objects",
    ),
    "labels.enableBackground": PropertyDef(
        None, "boolean", "Enable label background",
        container_key="labels", container_prop="enableBackground", objects_path="objects",
    ),
    "labels.backgroundColor": PropertyDef(
        None, "color", "Label background color",
        container_key="labels", container_prop="backgroundColor", objects_path="objects",
    ),
    "labels.backgroundTransparency": PropertyDef(
        None, "number", "Label background transparency",
        container_key="labels", container_prop="backgroundTransparency", objects_path="objects",
    ),
    "labels.labelDensity": PropertyDef(
        None, "number", "Label density (how many labels to show)",
        container_key="labels", container_prop="labelDensity", objects_path="objects",
    ),
    "labels.labelStyle": PropertyDef(
        None, "enum", "Label style (pie/donut)",
        container_key="labels", container_prop="labelStyle", objects_path="objects",
        enum_values=("Data", "Category", "Percent of total", "All detail labels"),
    ),
    # ── Plot area ─────────────────────────────────────────────
    "plotArea.transparency": PropertyDef(
        None, "number", "Plot area transparency",
        container_key="plotArea", container_prop="transparency", objects_path="objects",
    ),
    "plotArea.color": PropertyDef(
        None, "color", "Plot area background color",
        container_key="plotArea", container_prop="color", objects_path="objects",
    ),
    # ── Data colors ───────────────────────────────────────────
    "dataColors.default": PropertyDef(
        None, "color", "Default data color",
        container_key="dataPoint", container_prop="defaultColor", objects_path="objects",
    ),
    "dataColors.showAll": PropertyDef(
        None, "boolean", "Show all data colors",
        container_key="dataPoint", container_prop="showAllDataPoints", objects_path="objects",
    ),
    # ── Line formatting (line/area charts) ────────────────────
    "line.show": PropertyDef(
        None, "boolean", "Show line markers",
        container_key="lineStyles", container_prop="showMarker", objects_path="objects",
    ),
    "line.style": PropertyDef(
        None, "enum", "Line style",
        container_key="lineStyles", container_prop="lineStyle", objects_path="objects",
        enum_values=("solid", "dashed", "dotted"),
    ),
    "line.width": PropertyDef(
        None, "number", "Line stroke width",
        container_key="lineStyles", container_prop="strokeWidth", objects_path="objects",
    ),
    "line.stepped": PropertyDef(
        None, "boolean", "Stepped line (step chart)",
        container_key="lineStyles", container_prop="stepped", objects_path="objects",
    ),
    "line.shadeArea": PropertyDef(
        None, "boolean", "Shade area under line",
        container_key="lineStyles", container_prop="shadeArea", objects_path="objects",
    ),
    # Shape formatting
    "shapes.showMarkers": PropertyDef(
        None, "boolean", "Show data point markers",
        container_key="shapes", container_prop="showMarkers", objects_path="objects",
    ),
    "shapes.markerShape": PropertyDef(
        None, "string", "Marker shape",
        container_key="shapes", container_prop="markerShape", objects_path="objects",
    ),
    "shapes.markerSize": PropertyDef(
        None, "number", "Marker size",
        container_key="shapes", container_prop="markerSize", objects_path="objects",
    ),
    # ── Pie/donut ─────────────────────────────────────────────
    "slices.innerRadius": PropertyDef(
        None, "number", "Donut inner radius (0 = pie, higher = larger hole)",
        container_key="slices", container_prop="innerRadiusRatio", objects_path="objects",
    ),
    # ── Card visual ───────────────────────────────────────────
    "categoryLabels.show": PropertyDef(
        None, "boolean", "Show category label (card)",
        container_key="categoryLabels", container_prop="show", objects_path="objects",
    ),
    "categoryLabels.color": PropertyDef(
        None, "color", "Category label color (card)",
        container_key="categoryLabels", container_prop="color", objects_path="objects",
    ),
    "categoryLabels.fontSize": PropertyDef(
        None, "number", "Category label font size (card)",
        container_key="categoryLabels", container_prop="fontSize", objects_path="objects",
    ),
    "categoryLabels.fontFamily": PropertyDef(
        None, "string", "Category label font family (card)",
        container_key="categoryLabels", container_prop="fontFamily", objects_path="objects",
    ),
    "wordWrap.show": PropertyDef(
        None, "boolean", "Enable word wrap (card)",
        container_key="wordWrap", container_prop="show", objects_path="objects",
    ),
    # ── New card visual (cardVisual) ──────────────────────────
    # Layout — global entry (no selector)
    "layout.style": PropertyDef(
        None, "string", "Card layout style (Cards or Callout)",
        container_key="layout", container_prop="style", objects_path="objects",
    ),
    "layout.columnCount": PropertyDef(
        None, "long", "Number of columns in card layout",
        container_key="layout", container_prop="columnCount", objects_path="objects",
    ),
    "layout.calloutSize": PropertyDef(
        None, "number", "Callout font size",
        container_key="layout", container_prop="calloutSize", objects_path="objects",
    ),
    "layout.autoGrid": PropertyDef(
        None, "boolean", "Auto-size grid",
        container_key="layout", container_prop="autoGrid", objects_path="objects",
    ),
    "layout.alignment": PropertyDef(
        None, "string", "Vertical alignment (top, middle, bottom)",
        container_key="layout", container_prop="alignment", objects_path="objects",
    ),
    "layout.contentOrder": PropertyDef(
        None, "long", "Content order",
        container_key="layout", container_prop="contentOrder", objects_path="objects",
    ),
    "layout.orientation": PropertyDef(
        None, "number", "Card orientation (0=horizontal, 2=vertical)",
        container_key="layout", container_prop="orientation", objects_path="objects",
    ),
    "layout.cellPadding": PropertyDef(
        None, "long", "Cell padding between cards",
        container_key="layout", container_prop="cellPadding", objects_path="objects",
    ),
    # Layout — per-card entry (selector: default)
    "layout.padding": PropertyDef(
        None, "long", "Card internal padding",
        container_key="layout", container_prop="paddingUniform", objects_path="objects",
        selector="default",
    ),
    "layout.backgroundShow": PropertyDef(
        None, "boolean", "Show card background",
        container_key="layout", container_prop="backgroundShow", objects_path="objects",
        selector="default",
    ),
    # Accent bar
    "accentBar.show": PropertyDef(
        None, "boolean", "Show accent bar",
        container_key="accentBar", container_prop="show", objects_path="objects",
    ),
    "accentBar.color": PropertyDef(
        None, "color", "Accent bar color",
        container_key="accentBar", container_prop="color", objects_path="objects",
    ),
    # Card value — show entry (no selector)
    "cardValue.show": PropertyDef(
        None, "boolean", "Show card values",
        container_key="value", container_prop="show", objects_path="objects",
    ),
    # Card value — formatting entry (selector: default)
    "cardValue.fontSize": PropertyDef(
        None, "number", "Card value font size",
        container_key="value", container_prop="fontSize", objects_path="objects",
        selector="default",
    ),
    "cardValue.fontFamily": PropertyDef(
        None, "string", "Card value font family",
        container_key="value", container_prop="fontFamily", objects_path="objects",
        selector="default",
    ),
    "cardValue.bold": PropertyDef(
        None, "boolean", "Card value bold",
        container_key="value", container_prop="bold", objects_path="objects",
        selector="default",
    ),
    "cardValue.italic": PropertyDef(
        None, "boolean", "Card value italic",
        container_key="value", container_prop="italic", objects_path="objects",
        selector="default",
    ),
    "cardValue.color": PropertyDef(
        None, "color", "Card value font color",
        container_key="value", container_prop="fontColor", objects_path="objects",
        selector="default",
    ),
    "cardValue.alignment": PropertyDef(
        None, "enum", "Card value horizontal alignment",
        container_key="value", container_prop="horizontalAlignment", objects_path="objects",
        enum_values=("left", "center", "right"), selector="default",
    ),
    # Card value — per-measure (use --measure flag)
    "cardValue.displayUnits": PropertyDef(
        None, "number", "Card value display units (0=Auto, 1=None, 1000=K, 1000000=M)",
        container_key="value", container_prop="labelDisplayUnits", objects_path="objects",
    ),
    "cardValue.precision": PropertyDef(
        None, "number", "Card value decimal places",
        container_key="value", container_prop="labelPrecision", objects_path="objects",
    ),
    # Card label (selector: default)
    "cardLabel.show": PropertyDef(
        None, "boolean", "Show card label",
        container_key="label", container_prop="show", objects_path="objects",
        selector="default",
    ),
    "cardLabel.color": PropertyDef(
        None, "color", "Card label font color",
        container_key="label", container_prop="fontColor", objects_path="objects",
        selector="default",
    ),
    "cardLabel.fontSize": PropertyDef(
        None, "number", "Card label font size",
        container_key="label", container_prop="fontSize", objects_path="objects",
        selector="default",
    ),
    "cardLabel.fontFamily": PropertyDef(
        None, "string", "Card label font family",
        container_key="label", container_prop="fontFamily", objects_path="objects",
        selector="default",
    ),
    "cardLabel.bold": PropertyDef(
        None, "boolean", "Card label bold",
        container_key="label", container_prop="bold", objects_path="objects",
        selector="default",
    ),
    "cardLabel.italic": PropertyDef(
        None, "boolean", "Card label italic",
        container_key="label", container_prop="italic", objects_path="objects",
        selector="default",
    ),
    # Card shape (background rectangle, selector: default)
    "cardShape.color": PropertyDef(
        None, "color", "Card background color",
        container_key="shapeCustomRectangle", container_prop="color", objects_path="objects",
        selector="default",
    ),
    "cardShape.radius": PropertyDef(
        None, "long", "Card corner radius",
        container_key="shapeCustomRectangle", container_prop="rectangleRoundedCurve",
        objects_path="objects", selector="default",
    ),
    "cardShape.transparency": PropertyDef(
        None, "number", "Card background transparency",
        container_key="shapeCustomRectangle", container_prop="transparency",
        objects_path="objects", selector="default",
    ),
    "cardShape.tileShape": PropertyDef(
        None, "boolean", "Use tile shape",
        container_key="shapeCustomRectangle", container_prop="tileShape",
        objects_path="objects", selector="default",
    ),
    # Card overflow
    "cardOverflow.style": PropertyDef(
        None, "number", "Overflow style (1=overflow visible)",
        container_key="overFlow", container_prop="overFlowStyle", objects_path="objects",
    ),
    "cardOverflow.direction": PropertyDef(
        None, "number", "Overflow direction (0=default)",
        container_key="overFlow", container_prop="overFlowDirection", objects_path="objects",
    ),
    # Card internal padding (selector: default)
    "cardPadding.uniform": PropertyDef(
        None, "long", "Card uniform internal padding",
        container_key="padding", container_prop="paddingUniform", objects_path="objects",
        selector="default",
    ),
    "cardPadding.top": PropertyDef(
        None, "number", "Card internal top padding",
        container_key="padding", container_prop="top", objects_path="objects",
        selector="default",
    ),
    "cardPadding.bottom": PropertyDef(
        None, "number", "Card internal bottom padding",
        container_key="padding", container_prop="bottom", objects_path="objects",
        selector="default",
    ),
    "cardPadding.left": PropertyDef(
        None, "number", "Card internal left padding",
        container_key="padding", container_prop="left", objects_path="objects",
        selector="default",
    ),
    "cardPadding.right": PropertyDef(
        None, "number", "Card internal right padding",
        container_key="padding", container_prop="right", objects_path="objects",
        selector="default",
    ),
    # Card divider (selector: default)
    "cardDivider.show": PropertyDef(
        None, "boolean", "Show card divider",
        container_key="divider", container_prop="show", objects_path="objects",
        selector="default",
    ),
    "cardDivider.color": PropertyDef(
        None, "color", "Card divider color",
        container_key="divider", container_prop="color", objects_path="objects",
        selector="default",
    ),
    "cardDivider.width": PropertyDef(
        None, "number", "Card divider width",
        container_key="divider", container_prop="width", objects_path="objects",
        selector="default",
    ),
    # Card-level border (inside objects, selector: default)
    "cardBorder.show": PropertyDef(
        None, "boolean", "Show card-level border",
        container_key="border", container_prop="show", objects_path="objects",
        selector="default",
    ),
    # Card-level shadow (inside objects, selector: default)
    "cardShadow.show": PropertyDef(
        None, "boolean", "Show card-level shadow",
        container_key="shadowCustom", container_prop="show", objects_path="objects",
        selector="default",
    ),
    # ── Slicer visual ────────────────────────────────────────
    "slicerHeader.show": PropertyDef(
        None, "boolean", "Show slicer header",
        container_key="header", container_prop="show", objects_path="objects",
    ),
    "slicerHeader.fontColor": PropertyDef(
        None, "color", "Slicer header font color",
        container_key="header", container_prop="fontColor", objects_path="objects",
    ),
    "slicerHeader.background": PropertyDef(
        None, "color", "Slicer header background",
        container_key="header", container_prop="background", objects_path="objects",
    ),
    "slicerHeader.fontSize": PropertyDef(
        None, "number", "Slicer header font size",
        container_key="header", container_prop="textSize", objects_path="objects",
    ),
    "slicerHeader.fontFamily": PropertyDef(
        None, "string", "Slicer header font family",
        container_key="header", container_prop="fontFamily", objects_path="objects",
    ),
    "slicerHeader.bold": PropertyDef(
        None, "boolean", "Slicer header bold",
        container_key="header", container_prop="bold", objects_path="objects",
    ),
    "slicerItems.fontColor": PropertyDef(
        None, "color", "Slicer items font color",
        container_key="items", container_prop="fontColor", objects_path="objects",
    ),
    "slicerItems.background": PropertyDef(
        None, "color", "Slicer items background",
        container_key="items", container_prop="background", objects_path="objects",
    ),
    "slicerItems.fontSize": PropertyDef(
        None, "number", "Slicer items font size",
        container_key="items", container_prop="textSize", objects_path="objects",
    ),
    "slicerItems.fontFamily": PropertyDef(
        None, "string", "Slicer items font family",
        container_key="items", container_prop="fontFamily", objects_path="objects",
    ),
    "slicer.selectAll": PropertyDef(
        None, "boolean", "Enable select all checkbox",
        container_key="selection", container_prop="selectAllCheckboxEnabled", objects_path="objects",
    ),
    "slicer.singleSelect": PropertyDef(
        None, "boolean", "Single selection mode",
        container_key="selection", container_prop="singleSelect", objects_path="objects",
    ),
    # ── KPI visual ───────────────────────────────────────────
    "kpi.showIcon": PropertyDef(
        None, "boolean", "Show KPI status icon",
        container_key="indicator", container_prop="showIcon", objects_path="objects",
    ),
    "kpi.displayUnits": PropertyDef(
        None, "string", "KPI display units",
        container_key="indicator", container_prop="indicatorDisplayUnits", objects_path="objects",
    ),
    "kpi.precision": PropertyDef(
        None, "number", "KPI decimal places",
        container_key="indicator", container_prop="indicatorPrecision", objects_path="objects",
    ),
    "kpi.direction": PropertyDef(
        None, "enum", "KPI direction (high is good or bad)",
        container_key="status", container_prop="direction", objects_path="objects",
        enum_values=("Positive", "Negative"),
    ),
    "kpi.goodColor": PropertyDef(
        None, "color", "KPI good status color",
        container_key="status", container_prop="goodColor", objects_path="objects",
    ),
    "kpi.neutralColor": PropertyDef(
        None, "color", "KPI neutral status color",
        container_key="status", container_prop="neutralColor", objects_path="objects",
    ),
    "kpi.badColor": PropertyDef(
        None, "color", "KPI bad status color",
        container_key="status", container_prop="badColor", objects_path="objects",
    ),
    "kpi.showTrendline": PropertyDef(
        None, "boolean", "Show KPI trendline",
        container_key="trendline", container_prop="show", objects_path="objects",
    ),
    "kpi.showGoal": PropertyDef(
        None, "boolean", "Show KPI goal",
        container_key="goals", container_prop="showGoal", objects_path="objects",
    ),
    "kpi.showDistance": PropertyDef(
        None, "boolean", "Show KPI distance to goal",
        container_key="goals", container_prop="showDistance", objects_path="objects",
    ),
    # ── Gauge visual ─────────────────────────────────────────
    "gauge.max": PropertyDef(
        None, "number", "Gauge maximum value",
        container_key="axis", container_prop="max", objects_path="objects",
    ),
    "gauge.target": PropertyDef(
        None, "number", "Gauge target value",
        container_key="axis", container_prop="target", objects_path="objects",
    ),
    "gauge.targetColor": PropertyDef(
        None, "color", "Gauge target line color",
        container_key="target", container_prop="color", objects_path="objects",
    ),
    "gauge.targetShow": PropertyDef(
        None, "boolean", "Show gauge target label",
        container_key="target", container_prop="show", objects_path="objects",
    ),
    "gauge.calloutShow": PropertyDef(
        None, "boolean", "Show gauge callout value",
        container_key="calloutValue", container_prop="show", objects_path="objects",
    ),
    "gauge.calloutColor": PropertyDef(
        None, "color", "Gauge callout value color",
        container_key="calloutValue", container_prop="color", objects_path="objects",
    ),
    "gauge.calloutDisplayUnits": PropertyDef(
        None, "string", "Gauge callout display units",
        container_key="calloutValue", container_prop="labelDisplayUnits", objects_path="objects",
    ),
    "gauge.calloutPrecision": PropertyDef(
        None, "number", "Gauge callout decimal places",
        container_key="calloutValue", container_prop="labelPrecision", objects_path="objects",
    ),
    # ── Waterfall ─────────────────────────────────────────────
    "waterfall.increaseColor": PropertyDef(
        None, "color", "Waterfall increase color",
        container_key="sentimentColors", container_prop="increaseFill", objects_path="objects",
    ),
    "waterfall.decreaseColor": PropertyDef(
        None, "color", "Waterfall decrease color",
        container_key="sentimentColors", container_prop="decreaseFill", objects_path="objects",
    ),
    "waterfall.totalColor": PropertyDef(
        None, "color", "Waterfall total color",
        container_key="sentimentColors", container_prop="totalFill", objects_path="objects",
    ),
    # ── Shape visual ──────────────────────────────────────────
    "shape.type": PropertyDef(
        None, "enum", "Shape type",
        container_key="general", container_prop="shapeType", objects_path="objects",
        enum_values=(
            "rectangle", "roundedRectangle", "oval", "triangle",
            "pentagon", "hexagon", "octagon",
            "arrow", "arrowUp", "arrowDown", "arrowLeft", "arrowRight",
            "star5", "star6", "star8", "heart", "diamond",
            "parallelogram", "trapezoid", "homePlate",
            "speechBubble", "callout", "cloud",
        ),
    ),
    "shape.fill": PropertyDef(
        None, "color", "Shape fill color",
        container_key="fill", container_prop="fillColor", objects_path="objects",
    ),
    "shape.fillShow": PropertyDef(
        None, "boolean", "Show shape fill",
        container_key="fill", container_prop="show", objects_path="objects",
    ),
    "shape.fillTransparency": PropertyDef(
        None, "number", "Shape fill transparency (0-100)",
        container_key="fill", container_prop="transparency", objects_path="objects",
    ),
    "shape.lineColor": PropertyDef(
        None, "color", "Shape line/border color",
        container_key="line", container_prop="lineColor", objects_path="objects",
    ),
    "shape.lineShow": PropertyDef(
        None, "boolean", "Show shape line/border",
        container_key="line", container_prop="show", objects_path="objects",
    ),
    "shape.lineWeight": PropertyDef(
        None, "number", "Shape line weight",
        container_key="line", container_prop="weight", objects_path="objects",
    ),
    "shape.lineTransparency": PropertyDef(
        None, "number", "Shape line transparency (0-100)",
        container_key="line", container_prop="transparency", objects_path="objects",
    ),
    "shape.roundEdge": PropertyDef(
        None, "number", "Shape corner rounding",
        container_key="line", container_prop="roundEdge", objects_path="objects",
    ),
    "shape.rotation": PropertyDef(
        None, "number", "Shape rotation angle",
        container_key="rotation", container_prop="angle", objects_path="objects",
    ),
    # ── Image visual ──────────────────────────────────────────
    "image.url": PropertyDef(
        None, "string", "Image URL",
        container_key="imageUrl", container_prop="imageUrl", objects_path="objects",
    ),
    "image.scaling": PropertyDef(
        None, "enum", "Image scaling mode",
        container_key="imageScaling", container_prop="imageScalingType", objects_path="objects",
        enum_values=("Fit", "Fill", "Normal"),
    ),
    # ── Table/matrix global formatting (visual.objects) ───────
    # Column headers (global)
    "columnHeaders.fontColor": PropertyDef(
        None, "color", "Column header font color",
        container_key="columnHeaders", container_prop="fontColor", objects_path="objects",
    ),
    "columnHeaders.backColor": PropertyDef(
        None, "color", "Column header background color",
        container_key="columnHeaders", container_prop="backColor", objects_path="objects",
    ),
    "columnHeaders.fontSize": PropertyDef(
        None, "number", "Column header font size",
        container_key="columnHeaders", container_prop="fontSize", objects_path="objects",
    ),
    "columnHeaders.fontFamily": PropertyDef(
        None, "string", "Column header font family",
        container_key="columnHeaders", container_prop="fontFamily", objects_path="objects",
    ),
    "columnHeaders.bold": PropertyDef(
        None, "boolean", "Column header bold",
        container_key="columnHeaders", container_prop="bold", objects_path="objects",
    ),
    "columnHeaders.italic": PropertyDef(
        None, "boolean", "Column header italic",
        container_key="columnHeaders", container_prop="italic", objects_path="objects",
    ),
    "columnHeaders.alignment": PropertyDef(
        None, "enum", "Column header alignment",
        container_key="columnHeaders", container_prop="alignment", objects_path="objects",
        enum_values=("Left", "Center", "Right"),
    ),
    "columnHeaders.wordWrap": PropertyDef(
        None, "boolean", "Column header word wrap",
        container_key="columnHeaders", container_prop="wordWrap", objects_path="objects",
    ),
    "columnHeaders.autoSize": PropertyDef(
        None, "boolean", "Auto-size column widths",
        container_key="columnHeaders", container_prop="autoSizeColumnWidth", objects_path="objects",
    ),
    # Values (global data cells)
    "values.fontColor": PropertyDef(
        None, "color", "Data cell font color",
        container_key="values", container_prop="fontColorPrimary", objects_path="objects",
    ),
    "values.backColor": PropertyDef(
        None, "color", "Data cell primary background",
        container_key="values", container_prop="backColorPrimary", objects_path="objects",
    ),
    "values.altBackColor": PropertyDef(
        None, "color", "Data cell alternate row background",
        container_key="values", container_prop="backColorSecondary", objects_path="objects",
    ),
    "values.fontSize": PropertyDef(
        None, "number", "Data cell font size",
        container_key="values", container_prop="fontSize", objects_path="objects",
    ),
    "values.fontFamily": PropertyDef(
        None, "string", "Data cell font family",
        container_key="values", container_prop="fontFamily", objects_path="objects",
    ),
    "values.wordWrap": PropertyDef(
        None, "boolean", "Data cell word wrap",
        container_key="values", container_prop="wordWrap", objects_path="objects",
    ),
    "values.urlIcon": PropertyDef(
        None, "boolean", "Show URL icon for web URLs",
        container_key="values", container_prop="urlIcon", objects_path="objects",
    ),
    # Grid
    "grid.vertical": PropertyDef(
        None, "boolean", "Show vertical gridlines",
        container_key="grid", container_prop="gridVertical", objects_path="objects",
    ),
    "grid.verticalColor": PropertyDef(
        None, "color", "Vertical gridline color",
        container_key="grid", container_prop="gridVerticalColor", objects_path="objects",
    ),
    "grid.verticalWeight": PropertyDef(
        None, "number", "Vertical gridline weight",
        container_key="grid", container_prop="gridVerticalWeight", objects_path="objects",
    ),
    "grid.horizontal": PropertyDef(
        None, "boolean", "Show horizontal gridlines",
        container_key="grid", container_prop="gridHorizontal", objects_path="objects",
    ),
    "grid.horizontalColor": PropertyDef(
        None, "color", "Horizontal gridline color",
        container_key="grid", container_prop="gridHorizontalColor", objects_path="objects",
    ),
    "grid.horizontalWeight": PropertyDef(
        None, "number", "Horizontal gridline weight",
        container_key="grid", container_prop="gridHorizontalWeight", objects_path="objects",
    ),
    "grid.rowPadding": PropertyDef(
        None, "number", "Row padding",
        container_key="grid", container_prop="rowPadding", objects_path="objects",
    ),
    "grid.imageHeight": PropertyDef(
        None, "number", "Image height in cells",
        container_key="grid", container_prop="imageHeight", objects_path="objects",
    ),
    "grid.textSize": PropertyDef(
        None, "number", "Grid text size",
        container_key="grid", container_prop="textSize", objects_path="objects",
    ),
    # Total row
    "total.show": PropertyDef(
        None, "boolean", "Show totals row",
        container_key="total", container_prop="totals", objects_path="objects",
    ),
    "total.label": PropertyDef(
        None, "string", "Totals row label",
        container_key="total", container_prop="label", objects_path="objects",
    ),
    "total.fontColor": PropertyDef(
        None, "color", "Totals font color",
        container_key="total", container_prop="fontColor", objects_path="objects",
    ),
    "total.backColor": PropertyDef(
        None, "color", "Totals background color",
        container_key="total", container_prop="backColor", objects_path="objects",
    ),
    "total.fontSize": PropertyDef(
        None, "number", "Totals font size",
        container_key="total", container_prop="fontSize", objects_path="objects",
    ),
    "total.fontFamily": PropertyDef(
        None, "string", "Totals font family",
        container_key="total", container_prop="fontFamily", objects_path="objects",
    ),
    "total.bold": PropertyDef(
        None, "boolean", "Totals bold",
        container_key="total", container_prop="bold", objects_path="objects",
    ),
    # ── Matrix-specific formatting (visual.objects) ───────────
    # Row headers (matrix)
    "rowHeaders.fontColor": PropertyDef(
        None, "color", "Row header font color",
        container_key="rowHeaders", container_prop="fontColor", objects_path="objects",
    ),
    "rowHeaders.backColor": PropertyDef(
        None, "color", "Row header background",
        container_key="rowHeaders", container_prop="backColor", objects_path="objects",
    ),
    "rowHeaders.fontSize": PropertyDef(
        None, "number", "Row header font size",
        container_key="rowHeaders", container_prop="fontSize", objects_path="objects",
    ),
    "rowHeaders.fontFamily": PropertyDef(
        None, "string", "Row header font family",
        container_key="rowHeaders", container_prop="fontFamily", objects_path="objects",
    ),
    "rowHeaders.bold": PropertyDef(
        None, "boolean", "Row header bold",
        container_key="rowHeaders", container_prop="bold", objects_path="objects",
    ),
    "rowHeaders.italic": PropertyDef(
        None, "boolean", "Row header italic",
        container_key="rowHeaders", container_prop="italic", objects_path="objects",
    ),
    "rowHeaders.alignment": PropertyDef(
        None, "enum", "Row header alignment",
        container_key="rowHeaders", container_prop="alignment", objects_path="objects",
        enum_values=("Left", "Center", "Right"),
    ),
    "rowHeaders.wordWrap": PropertyDef(
        None, "boolean", "Row header word wrap",
        container_key="rowHeaders", container_prop="wordWrap", objects_path="objects",
    ),
    "rowHeaders.steppedLayout": PropertyDef(
        None, "boolean", "Enable stepped layout for row headers",
        container_key="rowHeaders", container_prop="stepped", objects_path="objects",
    ),
    "rowHeaders.steppedIndent": PropertyDef(
        None, "number", "Stepped layout indentation (pixels)",
        container_key="rowHeaders", container_prop="steppedLayoutIndentation", objects_path="objects",
    ),
    "rowHeaders.showExpandCollapse": PropertyDef(
        None, "boolean", "Show expand/collapse buttons",
        container_key="rowHeaders", container_prop="showExpandCollapseButtons", objects_path="objects",
    ),
    # Subtotals (matrix)
    "subTotals.rowSubtotals": PropertyDef(
        None, "boolean", "Show row subtotals",
        container_key="subTotals", container_prop="rowSubtotals", objects_path="objects",
    ),
    "subTotals.columnSubtotals": PropertyDef(
        None, "boolean", "Show column subtotals",
        container_key="subTotals", container_prop="columnSubtotals", objects_path="objects",
    ),
    "subTotals.rowSubtotalsPosition": PropertyDef(
        None, "enum", "Row subtotals position",
        container_key="subTotals", container_prop="rowSubtotalsPosition", objects_path="objects",
        enum_values=("Top", "Bottom"),
    ),
    "subTotals.perRowLevel": PropertyDef(
        None, "boolean", "Per row-level subtotals",
        container_key="subTotals", container_prop="perRowLevel", objects_path="objects",
    ),
    "subTotals.perColumnLevel": PropertyDef(
        None, "boolean", "Per column-level subtotals",
        container_key="subTotals", container_prop="perColumnLevel", objects_path="objects",
    ),
}

# ── Page properties ────────────────────────────────────────────────

PAGE_PROPERTIES: dict[str, PropertyDef] = {
    "displayName": PropertyDef("displayName", "string", "Page display name"),
    "width": PropertyDef("width", "number", "Page width in pixels"),
    "height": PropertyDef("height", "number", "Page height in pixels"),
    "displayOption": PropertyDef(
        "displayOption", "enum", "Display option",
        enum_values=("FitToPage", "FitToWidth", "ActualSize"),
    ),
    "visibility": PropertyDef(
        "visibility", "enum", "Page visibility",
        enum_values=("AlwaysVisible", "HiddenInViewMode"),
    ),
    # Page background (page.objects.background)
    "background.color": PropertyDef(
        None, "page_color", "Page background color",
        container_key="background", container_prop="color",
        objects_path="objects", top_level=True,
    ),
    "background.transparency": PropertyDef(
        None, "number", "Page background transparency (0-100)",
        container_key="background", container_prop="transparency",
        objects_path="objects", top_level=True,
    ),
    # Page outspace (area outside the page canvas)
    "outspace.color": PropertyDef(
        None, "page_color", "Outspace background color",
        container_key="outspace", container_prop="backgroundColor",
        objects_path="objects", top_level=True,
    ),
    "outspace.transparency": PropertyDef(
        None, "number", "Outspace transparency",
        container_key="outspace", container_prop="transparency",
        objects_path="objects", top_level=True,
    ),
}


# ── Value encoding/decoding ────────────────────────────────────────

def encode_pbi_value(value: str, value_type: str) -> Any:
    """Encode a CLI string value into PBI JSON format."""
    if value_type in ("color", "page_color"):
        color = value if value.startswith("#") else f"#{value}"
        return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}}
    elif value_type == "number":
        num = float(value)
        return {"expr": {"Literal": {"Value": f"{num}D"}}}
    elif value_type == "long":
        num = int(float(value))
        return {"expr": {"Literal": {"Value": f"{num}L"}}}
    elif value_type == "boolean":
        b = value.lower() in ("true", "1", "yes", "on")
        return {"expr": {"Literal": {"Value": str(b).lower()}}}
    elif value_type == "string":
        return {"expr": {"Literal": {"Value": f"'{value}'"}}}
    elif value_type == "enum":
        return {"expr": {"Literal": {"Value": f"'{value}'"}}}
    return value


def decode_pbi_value(raw: Any) -> Any:
    """Decode a PBI JSON value into a human-readable form."""
    if isinstance(raw, dict):
        # Color: {"solid": {"color": "#hex"}} or {"solid": {"color": {expr...}}}
        if "solid" in raw:
            color = raw["solid"].get("color", raw)
            # Recurse for page-level colors where color is an expr dict
            return decode_pbi_value(color) if isinstance(color, dict) else color
        # Expr literal: {"expr": {"Literal": {"Value": "..."}}}
        if "expr" in raw:
            literal = raw.get("expr", {}).get("Literal", {}).get("Value")
            if literal is not None:
                return _decode_literal(literal)
        return raw
    return raw


def _decode_literal(value: str) -> Any:
    """Decode a PBI literal string like '42D', 'true', or \"'text'\"."""
    if value.endswith("D") or value.endswith("d"):
        try:
            return float(value[:-1])
        except ValueError:
            pass
    if value.endswith("L") or value.endswith("l"):
        try:
            return int(value[:-1])
        except ValueError:
            pass
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    # Quoted string
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


# ── Property get/set operations ────────────────────────────────────

def get_property(
    data: dict, prop_name: str, registry: dict[str, PropertyDef],
    *, measure_ref: str | None = None,
) -> Any:
    """Get a property value from a JSON structure.

    If measure_ref is given, reads from the selector-bearing entry for that
    measure instead of the default (index 0) entry.
    """
    prop_def = registry.get(prop_name)

    if prop_def and prop_def.container_key:
        return _get_container_prop(data, prop_def, measure_ref=measure_ref)
    elif prop_def and prop_def.json_path:
        return _get_by_path(data, prop_def.json_path)
    else:
        # Raw path fallback
        return _get_by_path(data, prop_name)


def set_property(
    data: dict, prop_name: str, value: str, registry: dict[str, PropertyDef],
    *, measure_ref: str | None = None,
) -> None:
    """Set a property value in a JSON structure.

    If measure_ref is given, writes to a per-measure selector entry instead
    of the default (index 0) entry. This enables per-measure formatting in
    multi-measure visuals (e.g. cardVisual accent bars).
    """
    prop_def = registry.get(prop_name)

    if prop_def and prop_def.enum_values:
        # Validate enum value
        if value not in prop_def.enum_values:
            raise ValueError(
                f'Invalid value "{value}" for {prop_name}. '
                f"Valid: {', '.join(prop_def.enum_values)}"
            )

    if prop_def and prop_def.container_key:
        _set_container_prop(data, prop_def, value, measure_ref=measure_ref)
    elif prop_def and prop_def.json_path:
        coerced = _coerce_simple(value, prop_def.value_type)
        _set_by_path(data, prop_def.json_path, coerced)
    elif prop_def is None:
        raise ValueError(
            f'Unknown property "{prop_name}". '
            f"Use 'pbi visual props' or 'pbi page props' to see available properties."
        )


def _find_entry(entries: list[dict], selector: str | None) -> dict | None:
    """Find an entry matching a selector in an object array.

    selector=None → entry with no selector (first selectorless entry)
    selector="default" → entry with {"id": "default"}
    """
    if selector == "default":
        for entry in entries:
            if entry.get("selector", {}).get("id") == "default":
                return entry
        return None
    # No selector → first entry without a selector key
    for entry in entries:
        if "selector" not in entry:
            return entry
    # Fallback to first entry
    return entries[0] if entries else None


def _get_container_prop(
    data: dict, prop_def: PropertyDef,
    *, measure_ref: str | None = None,
) -> Any:
    """Read from object collections (visual-level or page-level)."""
    root = data if prop_def.top_level else data.get("visual", {})
    objects = root.get(prop_def.objects_path, {})
    entries = objects.get(prop_def.container_key, [])
    if not entries:
        return None

    if measure_ref:
        for entry in entries:
            if entry.get("selector", {}).get("metadata") == measure_ref:
                raw = entry.get("properties", {}).get(prop_def.container_prop)
                return decode_pbi_value(raw) if raw is not None else None
        return None

    target = _find_entry(entries, prop_def.selector)
    if target is None:
        return None
    raw = target.get("properties", {}).get(prop_def.container_prop)
    if raw is None:
        return None
    return decode_pbi_value(raw)


def _set_container_prop(
    data: dict, prop_def: PropertyDef, value: str,
    *, measure_ref: str | None = None,
) -> None:
    """Write to object collections, creating structure as needed.

    Selector routing:
      measure_ref → entry with {"metadata": "<measure_ref>"}
      prop_def.selector="default" → entry with {"id": "default"}
      prop_def.selector=None → first selectorless entry (index 0)
    """
    root = data if prop_def.top_level else data.setdefault("visual", {})
    objects = root.setdefault(prop_def.objects_path, {})
    entries = objects.setdefault(prop_def.container_key, [])

    encoded = encode_pbi_value(value, prop_def.value_type)

    if measure_ref:
        target = None
        for entry in entries:
            if entry.get("selector", {}).get("metadata") == measure_ref:
                target = entry
                break
        if target is None:
            target = {
                "properties": {},
                "selector": {"metadata": measure_ref},
            }
            entries.append(target)
        target.setdefault("properties", {})[prop_def.container_prop] = encoded
        return

    # Use prop_def.selector to find the right entry
    target = _find_entry(entries, prop_def.selector)
    if target is None:
        # Create new entry with appropriate selector
        target = {"properties": {}}
        if prop_def.selector == "default":
            target["selector"] = {"id": "default"}
        entries.append(target)
    target.setdefault("properties", {})[prop_def.container_prop] = encoded


def _get_by_path(data: dict, path: str) -> Any:
    """Navigate a dot-separated path into a dict."""
    current = data
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _set_by_path(data: dict, path: str, value: Any) -> None:
    """Set a value at a dot-separated path, creating dicts as needed."""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def _coerce_simple(value: str, value_type: str) -> Any:
    """Coerce a string to the appropriate Python type for direct JSON properties."""
    if value_type == "number":
        try:
            return int(value)
        except ValueError:
            return float(value)
    elif value_type == "boolean":
        return value.lower() in ("true", "1", "yes", "on")
    return value


def list_properties(registry: dict[str, PropertyDef]) -> list[tuple[str, str, str]]:
    """Return (name, type, description) for all properties in a registry."""
    # Display page_color as "color" — the encoding difference is internal
    display_type = lambda t: "color" if t == "page_color" else t
    return [
        (name, display_type(p.value_type), p.description)
        for name, p in sorted(registry.items())
    ]
