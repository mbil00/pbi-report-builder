"""Tests for the HTML render module."""

import pytest

from pbi.render import (
    _hex_to_rgba,
    _resolve_color,
    _adjust_color,
    _theme_color_fallback,
    _render_textbox_content,
    _build_group_offsets,
    render_page_html,
)
from pbi.project import Project
from tests.support import KITCHEN_SINK_DIR, SHAPES_DIR


def test_hex_to_rgba():
    assert _hex_to_rgba("#FF0000", 50) == "rgba(255,0,0,0.50)"
    assert _hex_to_rgba("#000000", 0) == "rgba(0,0,0,1.00)"
    assert _hex_to_rgba("#FFFFFF", 100) == "rgba(255,255,255,0.00)"


def test_resolve_color_hex_string():
    assert _resolve_color("#FF0000") == "#FF0000"


def test_resolve_color_theme_data():
    raw = {"expr": {"ThemeDataColor": {"ColorId": 0, "Percent": 0}}}
    result = _resolve_color(raw)
    assert result == "#FFFFFF"


def test_resolve_color_none():
    assert _resolve_color(None) is None


def test_theme_color_fallback():
    assert _theme_color_fallback({"ColorId": 0, "Percent": 0}) == "#FFFFFF"
    assert _theme_color_fallback({"ColorId": 1, "Percent": 0}) == "#252423"
    assert _theme_color_fallback({"ColorId": 2, "Percent": 0}) == "#118DFF"


def test_adjust_color_darken():
    result = _adjust_color("#FFFFFF", -0.1)
    # 255 * 0.9 = 229.5 -> 229 = 0xe5
    assert result == "#e5e5e5"


def test_adjust_color_lighten():
    result = _adjust_color("#000000", 0.5)
    # 0 + (255-0)*0.5 = 127
    assert result == "#7f7f7f"


def test_render_textbox_content():
    data = {
        "visual": {
            "objects": {
                "general": [{
                    "properties": {
                        "paragraphs": [{
                            "textRuns": [{
                                "value": "Hello World",
                                "textStyle": {
                                    "fontFamily": "Arial",
                                    "fontSize": "16pt",
                                    "color": "#000000",
                                }
                            }],
                            "horizontalTextAlignment": "center",
                        }]
                    }
                }]
            }
        }
    }
    result = _render_textbox_content(data)
    assert "Hello World" in result
    assert "font-family:'Arial'" in result
    assert "font-size:16pt" in result
    assert "text-align:center" in result


def test_render_textbox_empty():
    assert _render_textbox_content({}) == ""


def test_build_group_offsets_nested():
    """Nested groups accumulate offsets."""
    from pbi.project import Visual
    from pathlib import Path

    outer = Visual(
        folder=Path("/fake/outer"),
        data={
            "name": "outer",
            "position": {"x": 100, "y": 100, "z": 1000},
            "visualGroup": {"displayName": "Outer"},
        },
    )
    inner = Visual(
        folder=Path("/fake/inner"),
        data={
            "name": "inner",
            "position": {"x": 50, "y": 50, "z": 2000},
            "visualGroup": {"displayName": "Inner"},
            "parentGroupName": "outer",
        },
    )
    leaf = Visual(
        folder=Path("/fake/leaf"),
        data={
            "name": "leaf",
            "position": {"x": 5, "y": 5, "z": 100},
            "parentGroupName": "inner",
        },
    )
    offsets = _build_group_offsets([outer, inner, leaf])
    # leaf offset = inner pos + outer pos
    assert offsets["leaf"] == (150.0, 150.0, 3000)


def _visual_html(page_html: str, name: str) -> str:
    """Return the one rendered element for visual ``name``."""
    [element] = [chunk for chunk in page_html.split("\n\n") if f'data-name="{name}"' in chunk]
    return element


def test_render_page_html_desktop_fixtures():
    """Named facts from rendering Desktop-saved pages (read in place; render writes nothing)."""
    kitchen = Project.find(KITCHEN_SINK_DIR)
    page_html = render_page_html(kitchen, kitchen.find_page("Executive Overview"))
    assert page_html.startswith("<!DOCTYPE html>")
    assert "<title>Executive Overview</title>" in page_html
    assert '<div class="page-canvas">' in page_html
    # Page and visual backgrounds: a solid wrapper around an expr Literal.
    assert "background: #F5F6FA;" in page_html
    assert "background-color:#0078D4" in _visual_html(page_html, "navToProduct")
    # A visual outside any group is drawn at its own position; group containers aren't drawn.
    assert "left:16.0px;top:12.0px;width:500.0px;height:48.0px;z-index:1000;" in _visual_html(page_html, "heroTitle")
    assert 'data-name="Navigation"' not in page_html

    shapes = Project.find(SHAPES_DIR)
    page_html = render_page_html(shapes, shapes.find_page("Overview"))
    heading = _visual_html(page_html, "7d88e913cd74e62b0c83")
    assert (
        "<span style=\"font-family:'Georgia',sans-serif;font-size:24pt;font-weight:bold;color:#1f3a5f\">"
        "Delivery Overview</span>"
    ) in heading
    assert (
        '<span style="font-size:12pt;font-weight:bold;font-style:italic;color:#d64550">2024-2025</span>'
    ) in heading
    # Runs without a text style are plain text.
    assert '<p style="margin:0">Open the project handbook</p>' in _visual_html(page_html, "0edca500e000b9be8bca")


@pytest.mark.xfail(strict=True, reason="#129: grouped visuals are drawn offset by their group's position")
def test_render_draws_grouped_visuals_at_their_page_position():
    kitchen = Project.find(KITCHEN_SINK_DIR)
    page_html = render_page_html(kitchen, kitchen.find_page("Executive Overview"))
    # navToProduct is at x=660, y=540 in its visual.json, inside the Navigation group at the same point.
    assert "left:660.0px;top:540.0px;" in _visual_html(page_html, "navToProduct")
