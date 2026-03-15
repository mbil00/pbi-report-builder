"""Render Power BI report pages as HTML mockups.

Reads PBIR visual definitions and produces an HTML document that
approximates the visual layout with accurate positioning, sizing,
backgrounds, borders, titles, and text content. Charts and data visuals
are represented as labeled placeholders.
"""

from __future__ import annotations

import html
from typing import Any

from pbi.project import Project, Page, Visual
from pbi.properties import decode_pbi_value


# ── Visual type display ──────────────────────────────────────────

VISUAL_ICONS: dict[str, str] = {
    "barChart": "\u2590\u2590\u2590",
    "clusteredBarChart": "\u2590\u2590\u2590",
    "hundredPercentStackedBarChart": "\u2590\u2590\u2590",
    "columnChart": "\u2581\u2583\u2585",
    "clusteredColumnChart": "\u2581\u2583\u2585",
    "hundredPercentStackedColumnChart": "\u2581\u2583\u2585",
    "stackedBarChart": "\u2590\u2590\u2590",
    "lineChart": "\u27cb",
    "areaChart": "\u25e2",
    "stackedAreaChart": "\u25e2",
    "hundredPercentStackedAreaChart": "\u25e2",
    "lineStackedColumnComboChart": "\u2581\u2583\u27cb",
    "lineClusteredColumnComboChart": "\u2581\u2583\u27cb",
    "ribbonChart": "\u2261",
    "waterfallChart": "\u2581\u2585\u2583",
    "funnel": "\u25bd",
    "scatterChart": "\u2022\u2022",
    "pieChart": "\u25d5",
    "donutChart": "\u25d4",
    "treemap": "\u25a3",
    "gauge": "\u25d1",
    "cardVisual": "#",
    "card": "#",
    "kpi": "\u2191",
    "multiRowCard": "#\u2261",
    "scorecard": "\u2261",
    "tableEx": "\u2261",
    "pivotTable": "\u2261",
    "slicer": "\u25bc",
    "advancedSlicerVisual": "\u25bc",
    "listSlicer": "\u2261",
    "textSlicer": "T",
    "textbox": "T",
    "image": "\u25a3",
    "shape": "",
    "actionButton": "\u25b6",
    "pageNavigator": "\u2190\u2192",
    "azureMap": "\u2609",
    "map": "\u2609",
    "filledMap": "\u2609",
    "esriVisual": "\u2609",
    "decompositionTreeVisual": "\u2442",
    "keyDriversVisual": "\u26bf",
    "aiNarratives": "AI",
}

VISUAL_LABELS: dict[str, str] = {
    "barChart": "Bar Chart",
    "clusteredBarChart": "Clustered Bar",
    "hundredPercentStackedBarChart": "100% Stacked Bar",
    "stackedBarChart": "Stacked Bar",
    "columnChart": "Column Chart",
    "clusteredColumnChart": "Clustered Column",
    "hundredPercentStackedColumnChart": "100% Stacked Column",
    "lineChart": "Line Chart",
    "areaChart": "Area Chart",
    "stackedAreaChart": "Stacked Area",
    "hundredPercentStackedAreaChart": "100% Stacked Area",
    "lineStackedColumnComboChart": "Line & Stacked Column",
    "lineClusteredColumnComboChart": "Line & Column",
    "ribbonChart": "Ribbon Chart",
    "waterfallChart": "Waterfall",
    "funnel": "Funnel",
    "scatterChart": "Scatter",
    "pieChart": "Pie Chart",
    "donutChart": "Donut Chart",
    "treemap": "Treemap",
    "gauge": "Gauge",
    "cardVisual": "Card",
    "card": "Card",
    "kpi": "KPI",
    "multiRowCard": "Multi-Row Card",
    "scorecard": "Scorecard",
    "tableEx": "Table",
    "pivotTable": "Matrix",
    "slicer": "Slicer",
    "advancedSlicerVisual": "Slicer",
    "listSlicer": "List Slicer",
    "textSlicer": "Text Slicer",
    "textbox": "Text",
    "image": "Image",
    "shape": "Shape",
    "actionButton": "Button",
    "pageNavigator": "Page Navigator",
    "azureMap": "Map",
    "map": "Map",
    "filledMap": "Filled Map",
    "esriVisual": "ArcGIS Map",
    "decompositionTreeVisual": "Decomposition Tree",
    "keyDriversVisual": "Key Influencers",
    "aiNarratives": "Smart Narrative",
    "rdlVisual": "Paginated Report",
    "scriptVisual": "R/Python Visual",
}


# ── Color resolution ─────────────────────────────────────────────

def _resolve_color(raw: Any) -> str | None:
    """Resolve a PBI color value to a CSS color string."""
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        # Solid color wrapper
        if "solid" in raw:
            inner = raw["solid"].get("color")
            return _resolve_color(inner)
        # Expr literal
        if "expr" in raw:
            literal = raw.get("expr", {}).get("Literal", {}).get("Value")
            if literal and isinstance(literal, str):
                val = literal.strip("'")
                if val.startswith("#"):
                    return val
            # ThemeDataColor — can't resolve without theme, use fallback
            theme = raw.get("expr", {}).get("ThemeDataColor")
            if theme:
                return _theme_color_fallback(theme)
        # Direct ThemeDataColor at top level
        if "ThemeDataColor" in raw:
            return _theme_color_fallback(raw["ThemeDataColor"])
    return None


def _theme_color_fallback(theme_data: dict) -> str:
    """Generate a reasonable CSS color from ThemeDataColor metadata."""
    color_id = theme_data.get("ColorId", 0)
    percent = theme_data.get("Percent", 0)
    # Common Power BI theme defaults
    base_colors = {
        0: "#FFFFFF",  # Background (light theme)
        1: "#252423",  # Foreground (dark text)
        2: "#118DFF",  # Primary accent
        3: "#12239E",  # Secondary accent
        4: "#E66C37",  # Tertiary accent
        5: "#6B007B",  # Accent 4
        6: "#E044A7",  # Accent 5
        7: "#744EC2",  # Accent 6
    }
    base = base_colors.get(color_id, "#CCCCCC")
    if percent != 0:
        return _adjust_color(base, percent)
    return base


def _hex_to_rgba(hex_color: str, transparency: float) -> str:
    """Convert a hex color + PBI transparency (0-100) to CSS rgba()."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    else:
        r, g, b = 200, 200, 200
    alpha = 1 - (transparency / 100)
    return f"rgba({r},{g},{b},{alpha:.2f})"


def _adjust_color(hex_color: str, percent: float) -> str:
    """Lighten (positive percent) or darken (negative) a hex color."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    if percent > 0:
        # Lighten toward white
        r = int(r + (255 - r) * percent)
        g = int(g + (255 - g) * percent)
        b = int(b + (255 - b) * percent)
    else:
        # Darken toward black
        factor = 1 + percent
        r = int(r * factor)
        g = int(g * factor)
        b = int(b * factor)
    r, g, b = max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))
    return f"#{r:02x}{g:02x}{b:02x}"


# ── Container property extraction ────────────────────────────────

def _get_container_prop(visual_data: dict, key: str, prop: str) -> Any:
    """Read a property from visualContainerObjects."""
    entries = (
        visual_data
        .get("visual", {})
        .get("visualContainerObjects", {})
        .get(key, [])
    )
    for entry in entries:
        val = entry.get("properties", {}).get(prop)
        if val is not None:
            return decode_pbi_value(val)
    return None


def _get_object_prop(visual_data: dict, key: str, prop: str, selector: str | None = None) -> Any:
    """Read a property from visual.objects."""
    entries = (
        visual_data
        .get("visual", {})
        .get("objects", {})
        .get(key, [])
    )
    for entry in entries:
        if selector is not None:
            entry_sel = entry.get("selector", {}).get("id")
            if entry_sel != selector:
                continue
        val = entry.get("properties", {}).get(prop)
        if val is not None:
            return decode_pbi_value(val)
    return None


# ── Textbox rendering ────────────────────────────────────────────

def _render_textbox_content(visual_data: dict) -> str:
    """Extract rich text from a textbox visual and convert to HTML."""
    paragraphs = (
        visual_data
        .get("visual", {})
        .get("objects", {})
        .get("general", [{}])[0]
        .get("properties", {})
        .get("paragraphs", [])
    )
    if not paragraphs:
        return ""

    parts = []
    for para in paragraphs:
        text_runs = para.get("textRuns", [])
        alignment = para.get("horizontalTextAlignment", "")
        align_css = f"text-align:{alignment};" if alignment else ""

        spans = []
        for run in text_runs:
            value = html.escape(run.get("value", ""))
            style = run.get("textStyle", {})

            css_parts = []
            if style.get("fontFamily"):
                css_parts.append(f"font-family:'{style['fontFamily']}',sans-serif")
            if style.get("fontSize"):
                css_parts.append(f"font-size:{style['fontSize']}")
            if style.get("fontWeight"):
                css_parts.append(f"font-weight:{style['fontWeight']}")
            if style.get("fontStyle"):
                css_parts.append(f"font-style:{style['fontStyle']}")
            if style.get("color"):
                css_parts.append(f"color:{style['color']}")
            if style.get("textDecoration"):
                css_parts.append(f"text-decoration:{style['textDecoration']}")

            style_attr = ";".join(css_parts)
            if style_attr:
                spans.append(f'<span style="{style_attr}">{value}</span>')
            else:
                spans.append(value)

        inner = "".join(spans)
        if align_css:
            parts.append(f'<p style="{align_css}margin:0">{inner}</p>')
        else:
            parts.append(f"<p style=\"margin:0\">{inner}</p>")

    return "\n".join(parts)


# ── Binding extraction for placeholders ──────────────────────────

def _get_binding_labels(visual_data: dict) -> list[str]:
    """Get human-readable binding field names from a visual."""
    query_state = (
        visual_data
        .get("visual", {})
        .get("query", {})
        .get("queryState", {})
    )
    labels = []
    for config in query_state.values():
        for proj in config.get("projections", []):
            display = proj.get("displayName") or proj.get("nativeQueryRef", "")
            if display:
                labels.append(display)
    return labels


def _get_column_headers(visual_data: dict) -> list[str]:
    """Get column names for table visuals."""
    query_state = (
        visual_data
        .get("visual", {})
        .get("query", {})
        .get("queryState", {})
    )
    values = query_state.get("Values", {})
    headers = []
    for proj in values.get("projections", []):
        name = proj.get("displayName") or proj.get("nativeQueryRef", "")
        if name:
            headers.append(name)
    return headers


# ── Button text extraction ───────────────────────────────────────

def _get_button_text(visual_data: dict) -> str:
    """Get text label from an actionButton visual."""
    text_entries = (
        visual_data
        .get("visual", {})
        .get("objects", {})
        .get("text", [])
    )
    for entry in text_entries:
        text_val = entry.get("properties", {}).get("text")
        if text_val is not None:
            decoded = decode_pbi_value(text_val)
            if isinstance(decoded, str):
                return decoded
    return ""


# ── Group hierarchy resolution ───────────────────────────────────

def _build_group_offsets(visuals: list[Visual]) -> dict[str, tuple[float, float, int]]:
    """Build absolute (x, y, z_boost) offsets for each visual by walking the group chain.

    Group containers define a local coordinate system for their children.
    A child's absolute position = sum of all ancestor group positions + own position.
    Z-boost accumulates parent z-indices so grouped children render above sibling
    elements of their ancestors (PBI groups create implicit stacking contexts).

    Returns a dict mapping visual name -> (offset_x, offset_y, z_boost).
    """
    # Map group name -> group visual (groups are identified by their 'name' field)
    groups: dict[str, Visual] = {}
    for v in visuals:
        if "visualGroup" in v.data:
            groups[v.name] = v

    # Cache resolved offsets
    offset_cache: dict[str, tuple[float, float, int]] = {}

    def _resolve_offset(group_name: str) -> tuple[float, float, int]:
        if group_name in offset_cache:
            return offset_cache[group_name]
        group = groups.get(group_name)
        if group is None:
            offset_cache[group_name] = (0.0, 0.0, 0)
            return (0.0, 0.0, 0)
        pos = group.position
        gx = pos.get("x", 0)
        gy = pos.get("y", 0)
        gz = pos.get("z", 0)
        # Recurse if this group is itself in a parent group
        parent = group.data.get("parentGroupName")
        if parent:
            px, py, pz = _resolve_offset(parent)
            gx += px
            gy += py
            gz += pz
        offset_cache[group_name] = (gx, gy, gz)
        return (gx, gy, gz)

    # Build offsets for each visual
    result: dict[str, tuple[float, float, int]] = {}
    for v in visuals:
        parent = v.data.get("parentGroupName")
        if parent:
            result[v.name] = _resolve_offset(parent)
        else:
            result[v.name] = (0.0, 0.0, 0)
    return result


# ── Single visual rendering ──────────────────────────────────────

def _render_visual(visual: Visual, offset: tuple[float, float, int] = (0.0, 0.0, 0)) -> str:
    """Render a single visual as an HTML element."""
    data = visual.data
    pos = visual.position
    vtype = visual.visual_type

    # Skip visual groups (they are structural containers)
    if "visualGroup" in data:
        return ""

    x = pos.get("x", 0) + offset[0]
    y = pos.get("y", 0) + offset[1]
    w = pos.get("width", 0)
    h = pos.get("height", 0)
    z = pos.get("z", 0) + offset[2]

    # Hidden visuals
    if data.get("isHidden"):
        return ""

    # Build CSS styles
    styles: list[str] = [
        "position:absolute",
        f"left:{x:.1f}px",
        f"top:{y:.1f}px",
        f"width:{w:.1f}px",
        f"height:{h:.1f}px",
        f"z-index:{z}",
        "box-sizing:border-box",
        "overflow:hidden",
    ]

    # Background
    bg_show = _get_container_prop(data, "background", "show")
    if bg_show is not False:
        bg_color_raw = _get_container_raw_prop(data, "background", "color")
        bg_color = _resolve_color(bg_color_raw)
        bg_transparency = _get_container_prop(data, "background", "transparency")
        if bg_color:
            if bg_transparency and bg_transparency > 0:
                # Use rgba() so only background is transparent, not children
                styles.append(f"background-color:{_hex_to_rgba(bg_color, bg_transparency)}")
            else:
                styles.append(f"background-color:{bg_color}")
        elif bg_show is True:
            styles.append("background-color:#ffffff")

    # Border
    border_show = _get_container_prop(data, "border", "show")
    if border_show:
        border_color_raw = _get_container_raw_prop(data, "border", "color")
        border_color = _resolve_color(border_color_raw) or "#E0E0E0"
        border_width = _get_container_prop(data, "border", "width") or 1
        border_radius = _get_container_prop(data, "border", "radius") or 0
        styles.append(f"border:{border_width}px solid {border_color}")
        if border_radius:
            styles.append(f"border-radius:{border_radius}px")

    # Shadow
    shadow_show = _get_container_prop(data, "dropShadow", "show")
    if shadow_show:
        shadow_color = "#00000033"
        shadow_blur = _get_container_prop(data, "dropShadow", "shadowBlur") or 10
        shadow_dist = _get_container_prop(data, "dropShadow", "shadowDistance") or 5
        shadow_spread = _get_container_prop(data, "dropShadow", "shadowSpread") or 0
        styles.append(f"box-shadow:0 {shadow_dist}px {shadow_blur}px {shadow_spread}px {shadow_color}")

    # Padding
    pad_top = _get_container_prop(data, "padding", "top") or 0
    pad_bottom = _get_container_prop(data, "padding", "bottom") or 0
    pad_left = _get_container_prop(data, "padding", "left") or 0
    pad_right = _get_container_prop(data, "padding", "right") or 0
    if any([pad_top, pad_bottom, pad_left, pad_right]):
        styles.append(f"padding:{pad_top}px {pad_right}px {pad_bottom}px {pad_left}px")

    css = ";".join(styles)

    # Title — only show when explicitly enabled; skip shapes (design-time labels)
    title_html = ""
    title_show = _get_container_prop(data, "title", "show")
    if title_show is True and vtype != "shape":
        title_text = _get_container_prop(data, "title", "text") or ""
        if title_text:
            title_styles = ["font-size:12px", "font-weight:600", "padding:4px 8px", "margin:0"]
            title_color_raw = _get_container_raw_prop(data, "title", "fontColor")
            title_color = _resolve_color(title_color_raw)
            if title_color:
                title_styles.append(f"color:{title_color}")
            title_align = _get_container_prop(data, "title", "alignment")
            if title_align:
                title_styles.append(f"text-align:{title_align}")
            title_font_size = _get_container_prop(data, "title", "fontSize")
            if title_font_size:
                title_styles.append(f"font-size:{title_font_size}px")
            title_css = ";".join(title_styles)
            title_html = f'<div class="visual-title" style="{title_css}">{html.escape(str(title_text))}</div>'

    # Content based on visual type
    content_html = _render_visual_content(data, vtype)

    # CSS class for the visual type
    type_class = f"visual-{vtype}"

    return (
        f'<div class="visual {type_class}" style="{css}" '
        f'data-type="{html.escape(vtype)}" data-name="{html.escape(visual.name)}">'
        f"{title_html}{content_html}</div>\n"
    )


def _get_container_raw_prop(visual_data: dict, key: str, prop: str) -> Any:
    """Read a raw property value (before decoding) from visualContainerObjects."""
    entries = (
        visual_data
        .get("visual", {})
        .get("visualContainerObjects", {})
        .get(key, [])
    )
    for entry in entries:
        val = entry.get("properties", {}).get(prop)
        if val is not None:
            return val
    return None


def _render_visual_content(data: dict, vtype: str) -> str:
    """Render the inner content of a visual based on its type."""
    if vtype == "textbox":
        content = _render_textbox_content(data)
        if content:
            return f'<div class="textbox-content" style="width:100%;height:100%;overflow:hidden">{content}</div>'
        return ""

    if vtype == "shape":
        # Shape visuals are just background containers, rendered by the outer div
        fill_show = _get_object_prop(data, "fill", "show")
        if fill_show is False:
            return ""
        fill_color_raw = _get_object_raw_prop(data, "fill", "fillColor")
        if fill_color_raw:
            color = _resolve_color(fill_color_raw)
            if color:
                return f'<div style="width:100%;height:100%;background-color:{color}"></div>'
        return ""

    if vtype == "actionButton":
        text = _get_button_text(data)
        return (
            f'<div class="button-content" style="display:flex;align-items:center;'
            f'justify-content:center;width:100%;height:100%;font-size:12px">'
            f'{html.escape(text) if text else "Button"}</div>'
        )

    if vtype in ("tableEx", "pivotTable"):
        headers = _get_column_headers(data)
        if headers:
            cols = "".join(
                f'<th style="padding:4px 8px;font-size:10px;text-align:left;'
                f'border-bottom:1px solid #ddd;white-space:nowrap">{html.escape(h)}</th>'
                for h in headers
            )
            return (
                f'<table style="width:100%;border-collapse:collapse;font-size:10px">'
                f"<tr>{cols}</tr>"
                f'<tr>{"".join("<td style=\"padding:4px 8px;color:#999\">—</td>" for _ in headers)}</tr>'
                f"</table>"
            )

    if vtype in ("slicer", "advancedSlicerVisual", "listSlicer"):
        bindings = _get_binding_labels(data)
        label = bindings[0] if bindings else "Slicer"
        mode = _get_object_prop(data, "data", "mode") or ""
        icon = "\u25bc" if mode == "Dropdown" else "\u2261"
        return (
            f'<div style="display:flex;align-items:center;padding:4px 8px;font-size:11px">'
            f'<span style="margin-right:4px">{icon}</span>{html.escape(label)}</div>'
        )

    if vtype in ("cardVisual", "card"):
        bindings = _get_binding_labels(data)
        label = bindings[0] if bindings else "Value"
        font_size = _get_object_prop(data, "labels", "fontSize") or 24
        return (
            f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'justify-content:center;width:100%;height:100%">'
            f'<div style="font-size:{font_size}px;font-weight:700;color:#118DFF">—</div>'
            f'<div style="font-size:11px;color:#666">{html.escape(label)}</div></div>'
        )

    if vtype == "kpi":
        bindings = _get_binding_labels(data)
        indicator_size = _get_object_prop(data, "indicator", "fontSize") or 20
        label = bindings[0] if bindings else "KPI"
        return (
            f'<div style="display:flex;flex-direction:column;align-items:center;'
            f'justify-content:center;width:100%;height:100%">'
            f'<div style="font-size:{indicator_size}px;font-weight:700;color:#118DFF">—</div>'
            f'<div style="font-size:10px;color:#666">{html.escape(label)}</div>'
            f'<div style="font-size:9px;color:#999;margin-top:2px">Goal: —</div></div>'
        )

    if vtype == "image":
        return (
            '<div style="display:flex;align-items:center;justify-content:center;'
            'width:100%;height:100%;background:#f0f0f0;color:#999;font-size:11px">'
            '\u25a3 Image</div>'
        )

    if vtype == "pageNavigator":
        return (
            '<div style="display:flex;align-items:center;gap:8px;padding:4px 12px;'
            'font-size:11px;color:#666">'
            '\u2190 \u2192 Page Navigator</div>'
        )

    # Generic chart/visual placeholder
    icon = VISUAL_ICONS.get(vtype, "\u25a1")
    label = VISUAL_LABELS.get(vtype, vtype)
    return (
        f'<div class="placeholder" style="display:flex;flex-direction:column;'
        f'align-items:center;justify-content:center;width:100%;height:100%;'
        f'color:#999;font-size:11px">'
        f'<div style="font-size:24px;margin-bottom:4px;opacity:0.5">{icon}</div>'
        f'{html.escape(label)}</div>'
    )


def _get_object_raw_prop(visual_data: dict, key: str, prop: str) -> Any:
    """Read a raw property from visual.objects (before decoding)."""
    entries = (
        visual_data
        .get("visual", {})
        .get("objects", {})
        .get(key, [])
    )
    for entry in entries:
        val = entry.get("properties", {}).get(prop)
        if val is not None:
            return val
    return None


# ── Page rendering ───────────────────────────────────────────────

def _page_background(page: Page) -> str:
    """Get CSS background for a page from its objects."""
    page_objs = page.data.get("objects", {})
    bg_entries = page_objs.get("outspace", [])
    for entry in bg_entries:
        color_val = entry.get("properties", {}).get("color")
        if color_val:
            color = _resolve_color(color_val)
            if color:
                return color

    bg_entries = page_objs.get("background", [])
    for entry in bg_entries:
        color_val = entry.get("properties", {}).get("color")
        if color_val:
            color = _resolve_color(color_val)
            if color:
                return color

    return "#F2F2F2"


def render_page_html(project: Project, page: Page) -> str:
    """Render a full page as a standalone HTML document."""
    visuals = project.get_visuals(page)
    offsets = _build_group_offsets(visuals)
    pw = page.width
    ph = page.height
    bg = _page_background(page)

    visual_elements = []
    for vis in visuals:
        rendered = _render_visual(vis, offsets.get(vis.name, (0.0, 0.0, 0)))
        if rendered:
            visual_elements.append(rendered)

    visuals_html = "\n".join(visual_elements)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(page.display_name)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: #1a1a1a;
    display: flex;
    justify-content: center;
    padding: 20px;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  }}
  .page-canvas {{
    position: relative;
    width: {pw}px;
    height: {ph}px;
    background: {bg};
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
    overflow: hidden;
  }}
  .visual {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  }}
  .visual-title {{
    border-bottom: 1px solid rgba(0,0,0,0.05);
  }}
  .textbox-content p {{
    line-height: 1.4;
  }}
  .placeholder {{
    user-select: none;
  }}
  /* Tooltip on hover */
  .visual[data-type]:hover::after {{
    content: attr(data-type) " — " attr(data-name);
    position: absolute;
    bottom: -20px;
    left: 0;
    background: rgba(0,0,0,0.8);
    color: #fff;
    font-size: 10px;
    padding: 2px 6px;
    border-radius: 3px;
    white-space: nowrap;
    z-index: 999999;
    pointer-events: none;
  }}
</style>
</head>
<body>
<div class="page-canvas">
{visuals_html}
</div>
</body>
</html>"""


def render_page_screenshot_html(project: Project, page: Page) -> str:
    """Render a page as HTML optimized for Puppeteer screenshot (no body padding)."""
    visuals = project.get_visuals(page)
    offsets = _build_group_offsets(visuals)
    pw = page.width
    ph = page.height
    bg = _page_background(page)

    visual_elements = []
    for vis in visuals:
        rendered = _render_visual(vis, offsets.get(vis.name, (0.0, 0.0, 0)))
        if rendered:
            visual_elements.append(rendered)

    visuals_html = "\n".join(visual_elements)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{html.escape(page.display_name)}</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    width: {pw}px;
    height: {ph}px;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  }}
  .page-canvas {{
    position: relative;
    width: {pw}px;
    height: {ph}px;
    background: {bg};
    overflow: hidden;
  }}
  .visual {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  }}
  .textbox-content p {{
    line-height: 1.4;
  }}
</style>
</head>
<body>
<div class="page-canvas">
{visuals_html}
</div>
</body>
</html>"""
