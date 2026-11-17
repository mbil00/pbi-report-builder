"""Named facts from the read-only theme commands on report-04's Desktop theme.

The fixture harness runs ``theme get`` on every fixture only to check it
doesn't crash or write. These tests check what the theme commands print,
against ``Desktop_Shapes_Theme*.json``, the custom theme Desktop saved in
report-04. That theme has no ``visualStyles``; the visual-style commands are
checked on hand-built themes in ``test_themes``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support import SHAPES_DIR, cli, copy_fixture, read_json, tables

THEME_NAME = "Desktop Shapes Theme"


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    # Every command here leaves the project unchanged, so the module shares one copy.
    return copy_fixture(SHAPES_DIR.name, tmp_path_factory.mktemp("theme"))


@pytest.fixture(scope="module")
def theme_file(root: Path) -> Path:
    resources = root / "04-desktop-shapes.Report" / "StaticResources" / "RegisteredResources"
    (path,) = resources.glob("Desktop_Shapes_Theme*.json")
    return path


@pytest.fixture(scope="module")
def theme(theme_file: Path) -> dict:
    return read_json(theme_file)


def pbi(root: Path, *args: str) -> str:
    result = cli(*args, project=root)
    assert result.exit_code == 0, result.output
    return result.output


def test_theme_get_overview_lists_palette_data_colours_and_text_classes(root: Path, theme: dict) -> None:
    output = pbi(root, "theme", "get")
    # The title wraps, so compare it with whitespace collapsed.
    assert f"Theme: {THEME_NAME}" in " ".join(output.split())

    palette, text_classes = tables(output)
    # Only the palette keys the theme sets, in the command's order.
    assert [(row["Property"], row["Value"]) for row in palette] == [
        ("foreground", "#252423"),
        ("background", "#FFFFFF"),
        ("tableAccent", "#118DFF"),
        ("good", "#20A741"),
        ("neutral", "#F2A900"),
        ("bad", "#D64550"),
        ("maximum", "#1F3A5F"),
        ("center", "#F2A900"),
        ("minimum", "#DEEFFF"),
    ]

    colours = theme["dataColors"]
    assert f"Data Colors ({len(colours)}): {', '.join(colours[:8])}..." in output

    assert text_classes == [
        {
            "Class": "title",
            "Font": "'Segoe UI Semibold', wf_segoe-ui_semibold, helvetica, arial, sans-serif",
            "Size": "13",
            "Color": "#1F3A5F",
        },
        {"Class": "header", "Font": "", "Size": "", "Color": "#605E5C"},
        {"Class": "callout", "Font": "", "Size": "30", "Color": "#118DFF"},
        {"Class": "label", "Font": "", "Size": "10", "Color": "#3B3A39"},
    ]
    assert "Visual Styles" not in output


def test_theme_get_json_overview_carries_palette_data_colours_and_text_classes(root: Path, theme: dict) -> None:
    overview = json.loads(pbi(root, "theme", "get", "--json"))
    assert overview["foreground"] == "#252423"
    assert overview["bad"] == "#D64550"
    assert overview["backgroundLight"] is None
    assert overview["dataColors"] == theme["dataColors"]
    assert overview["textClasses"]["callout"] == {"fontSize": 30, "color": "#118DFF"}
    assert overview["textClasses"] == theme["textClasses"]


def test_theme_get_raw_dumps_the_theme_file(root: Path, theme: dict) -> None:
    assert json.loads(pbi(root, "theme", "get", "--raw")) == theme


def test_theme_get_reads_listed_properties(root: Path) -> None:
    # One scalar prints bare, one object prints as JSON, a missing key prints (none).
    assert pbi(root, "theme", "get", "foreground").strip() == "#252423"
    assert json.loads(pbi(root, "theme", "get", "textClasses.callout")) == {"fontSize": 30, "color": "#118DFF"}
    assert pbi(root, "theme", "get", "hyperlink").strip() == "(none)"

    (rows,) = tables(pbi(root, "theme", "get", "foreground", "textClasses.title.fontSize", "hyperlink"))
    assert [(row["Property"], row["Value"]) for row in rows] == [
        ("foreground", "#252423"),
        ("textClasses.title.fontSize", "13"),
        ("hyperlink", ""),
    ]
    assert json.loads(pbi(root, "theme", "get", "foreground", "hyperlink", "--json")) == {
        "foreground": "#252423",
        "hyperlink": None,
    }


def test_visual_style_commands_on_a_theme_without_visual_styles(root: Path, theme_file: Path) -> None:
    before = theme_file.read_bytes()
    assert pbi(root, "theme", "style", "list").strip() == "No visual style overrides in this theme."
    assert pbi(root, "theme", "style", "get").strip() == "No visual style overrides in this theme."
    assert (
        pbi(root, "theme", "style", "delete", "columnChart", "--force").strip()
        == 'No visual style overrides for "columnChart".'
    )
    assert theme_file.read_bytes() == before
