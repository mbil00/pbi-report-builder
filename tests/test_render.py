"""Tests for the HTML render module."""

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


def test_hex_to_rgba():
    assert _hex_to_rgba("#FF0000", 50) == "rgba(255,0,0,0.50)"
    assert _hex_to_rgba("#000000", 0) == "rgba(0,0,0,1.00)"
    assert _hex_to_rgba("#FFFFFF", 100) == "rgba(255,255,255,0.00)"


def test_resolve_color_hex_string():
    assert _resolve_color("#FF0000") == "#FF0000"


def test_resolve_color_solid_wrapper():
    raw = {"solid": {"color": "#00FF00"}}
    assert _resolve_color(raw) == "#00FF00"


def test_resolve_color_expr_literal():
    raw = {"expr": {"Literal": {"Value": "'#0000FF'"}}}
    assert _resolve_color(raw) == "#0000FF"


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


def test_build_group_offsets_no_groups():
    """Visuals without groups get zero offsets."""
    from pbi.project import Visual
    from pathlib import Path

    v = Visual(folder=Path("/fake/v1"), data={"name": "v1"})
    offsets = _build_group_offsets([v])
    assert offsets["v1"] == (0.0, 0.0, 0)


def test_build_group_offsets_with_group():
    """Child visuals get parent group position as offset."""
    from pbi.project import Visual
    from pathlib import Path

    group = Visual(
        folder=Path("/fake/g1"),
        data={
            "name": "g1",
            "position": {"x": 100, "y": 200, "z": 5000},
            "visualGroup": {"displayName": "Group 1"},
        },
    )
    child = Visual(
        folder=Path("/fake/c1"),
        data={
            "name": "c1",
            "position": {"x": 10, "y": 20, "z": 100},
            "parentGroupName": "g1",
        },
    )
    offsets = _build_group_offsets([group, child])
    assert offsets["c1"] == (100.0, 200.0, 5000)
    assert offsets["g1"] == (0.0, 0.0, 0)


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


def test_render_page_html_sample():
    """Smoke test: render a page from the sample report."""
    proj = Project.find("fixtures/sample-report")
    pages = proj.get_pages()
    assert len(pages) > 0

    html = render_page_html(proj, pages[0])
    assert "<!DOCTYPE html>" in html
    assert pages[0].display_name in html
    assert "page-canvas" in html
