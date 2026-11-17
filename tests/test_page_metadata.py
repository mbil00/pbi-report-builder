"""Page metadata, binding and section helpers on a copy of the Desktop-saved report-01."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pbi.page_metadata import (
    PageBindingInfo,
    clear_page_drillthrough,
    clear_page_tooltip,
    configure_page_drillthrough,
    configure_page_tooltip,
    get_page_binding_info,
    list_pages,
    rename_page,
    reorder_pages,
    resolve_page_fields,
    set_active_page,
    set_all_page_properties,
    set_page_properties,
)
from pbi.page_sections import PageSectionInfo, create_page_section, list_page_sections
from pbi.project import Page, Project
from pbi.properties import PAGE_PROPERTIES, VISUAL_PROPERTIES, get_property
from tests.support import read_json

KITCHEN_SINK = "report-01-kitchen-sink"


def _reload(project: Project, name: str) -> Page:
    """Re-read a page from disk, so assertions see what was saved."""
    project.clear_caches()
    return project.find_page(name)


def test_page_listing_reorder_and_active_page(fixture_project: Callable[[str], Project]) -> None:
    project = fixture_project(KITCHEN_SINK)

    rows = list_pages(project)
    assert [(row.index, row.display_name, row.active, row.visual_count, row.visibility) for row in rows] == [
        (1, "Executive Overview", True, 15, "AlwaysVisible"),
        (2, "Product Detail", False, 7, "HiddenInViewMode"),
        (3, "Regional Detail", False, 8, "AlwaysVisible"),
        (4, "Tooltip - Order Context", False, 1, "HiddenInViewMode"),
        (5, "Hidden QA Page", False, 3, "HiddenInViewMode"),
    ]
    assert (rows[0].folder, rows[3].width, rows[3].height) == ("eb6cb5c033bc16fa450d", 320, 240)

    ordered = reorder_pages(project, ["Regional Detail", "Hidden QA Page"])
    expected = ["Regional Detail", "Hidden QA Page", "Executive Overview", "Product Detail", "Tooltip - Order Context"]
    assert [page.display_name for page in ordered] == expected
    project.clear_caches()
    assert [page.display_name for page in project.get_pages()] == expected
    with pytest.raises(ValueError, match="listed more than once"):
        reorder_pages(project, ["Regional Detail", "regional detail"])

    page, old_name, changed = set_active_page(project, "Regional Detail")
    assert (page.display_name, old_name, changed) == ("Regional Detail", "Executive Overview", True)
    assert project.get_pages_meta()["activePageName"] == page.name
    page, old_name, changed = set_active_page(project, page.name)
    assert (page.display_name, old_name, changed) == ("Regional Detail", "Regional Detail", False)

    overview = project.find_page("Executive Overview")
    assert rename_page(project, overview, "Landing") is True
    assert read_json(overview.folder / "page.json")["displayName"] == "Landing"
    assert rename_page(project, project.find_page("Landing"), "Landing") is False


def test_page_property_helpers_support_single_and_bulk_updates(fixture_project: Callable[[str], Project]) -> None:
    project = fixture_project(KITCHEN_SINK)
    overview = project.find_page("Executive Overview")

    changes = set_page_properties(overview, [("displayOption", "FitToWidth"), ("visibility", "HiddenInViewMode")])
    assert [(change.prop, change.old, change.new, change.changed) for change in changes] == [
        ("displayOption", "FitToPage", "FitToWidth", True),
        ("visibility", None, "HiddenInViewMode", True),
    ]
    saved = read_json(overview.folder / "page.json")
    assert (saved["displayOption"], saved["visibility"]) == ("FitToWidth", "HiddenInViewMode")

    # A no-op change leaves the Desktop-saved file's bytes alone.
    regional = project.find_page("Regional Detail")
    page_json = regional.folder / "page.json"
    before = page_json.read_bytes()
    [change] = set_page_properties(regional, [("displayOption", "FitToPage")])
    assert change.changed is False
    assert page_json.read_bytes() == before

    count = set_all_page_properties(project, [("background.color", "#FFFFFF")], exclude="Hidden", dry_run=False)
    assert count == 4
    assert get_property(_reload(project, "Executive Overview").data, "background.color", PAGE_PROPERTIES) == "#FFFFFF"
    assert get_property(_reload(project, "Tooltip - Order Context").data, "background.color", PAGE_PROPERTIES) == "#FFFFFF"
    assert get_property(_reload(project, "Hidden QA Page").data, "background.color", PAGE_PROPERTIES) is None

    assert set_all_page_properties(project, [("background.color", "#000000")], dry_run=True) == 5
    assert get_property(_reload(project, "Executive Overview").data, "background.color", PAGE_PROPERTIES) == "#FFFFFF"


def test_page_binding_helpers_cover_drillthrough_and_tooltip(fixture_project: Callable[[str], Project]) -> None:
    project = fixture_project(KITCHEN_SINK)

    # Desktop's drillthrough page keeps its parameters, but their drillFilter filters are gone.
    assert get_page_binding_info(project.find_page("Product Detail")) == PageBindingInfo("Drillthrough", [])
    assert get_page_binding_info(project.find_page("Tooltip - Order Context")) == PageBindingInfo("Tooltip", [])
    assert get_page_binding_info(project.find_page("Regional Detail")) is None

    detail = project.find_page("Product Detail")
    assert clear_page_drillthrough(detail) is True
    assert get_page_binding_info(_reload(project, "Product Detail")) is None
    assert clear_page_drillthrough(project.find_page("Product Detail")) is False

    tooltip = project.find_page("Tooltip - Order Context")
    assert clear_page_tooltip(tooltip) is True
    assert get_page_binding_info(_reload(project, "Tooltip - Order Context")) is None
    assert clear_page_tooltip(project.find_page("Tooltip - Order Context")) is False

    fields = resolve_page_fields(project, ["Customer.Region"])
    assert fields == [("Customer", "Region", "column")]

    # Guessed shape: no Desktop sample has a CrossReport drillthrough page.
    configure_page_drillthrough(project.find_page("Regional Detail"), fields, cross_report=True, hide=True)
    regional = _reload(project, "Regional Detail")
    assert get_page_binding_info(regional) == PageBindingInfo("Drillthrough", fields, cross_report=True)
    assert regional.visibility == "HiddenInViewMode"

    configure_page_tooltip(project.find_page("Hidden QA Page"), fields, width=400, height=300)
    qa = _reload(project, "Hidden QA Page")
    assert get_page_binding_info(qa) == PageBindingInfo("Tooltip", fields)
    assert (qa.width, qa.height) == (400, 300)


def test_page_section_helpers_create_and_list_sections(fixture_project: Callable[[str], Project]) -> None:
    project = fixture_project(KITCHEN_SINK)
    page = project.find_page("Executive Overview")
    min_z = min(visual.position["z"] for visual in project.get_visuals(page))

    # Desktop's "Navigation" group is not a section.
    assert list_page_sections(project, page) == []

    result = create_page_section(project, page, "Revenue", x=10, y=20, width=300, height=120)
    assert (result.title, result.background_visual, result.title_visual) == (
        "Revenue",
        "section-bg-revenue",
        "section-title-revenue",
    )

    project.clear_caches()
    assert list_page_sections(project, page) == [PageSectionInfo("Revenue", 10, 20, 300, 120)]
    visuals = {visual.name: visual for visual in project.get_visuals(page)}
    background = visuals["section-bg-revenue"]
    title = visuals["section-title-revenue"]
    assert background.data["parentGroupName"] == title.data["parentGroupName"] == result.group_visual
    assert background.position["z"] < min_z
    assert get_property(background.data, "border.radius", VISUAL_PROPERTIES) == 10
    assert (title.position["x"], title.position["y"]) == (18, 24)
    [run] = title.data["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"]
    assert run["value"] == "Revenue"
