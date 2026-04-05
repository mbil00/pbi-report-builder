from __future__ import annotations

import tempfile
from pathlib import Path

from pbi.page_metadata import (
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
from pbi.page_sections import create_page_section, list_page_sections
from pbi.properties import PAGE_PROPERTIES, get_property
from tests.cli_regressions_support import make_project


def test_page_listing_reorder_and_active_page() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp))
        first = project.create_page("Overview")
        second = project.create_page("Details")

        rows = list_pages(project)
        assert [row.display_name for row in rows] == ["Overview", "Details"]
        assert rows[0].active is False

        ordered = reorder_pages(project, ["Details"])
        assert [page.display_name for page in ordered] == ["Details", "Overview"]

        active_page, old_name, changed = set_active_page(project, "Details")
        assert active_page.display_name == "Details"
        assert old_name is None
        assert changed is True

        unchanged_page, old_name, changed = set_active_page(project, second.name)
        assert unchanged_page.display_name == "Details"
        assert old_name == "Details"
        assert changed is False

        renamed = rename_page(project, first, "Landing")
        assert renamed is True
        assert project.find_page("Landing").display_name == "Landing"


def test_page_property_helpers_support_single_and_bulk_updates() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp))
        first = project.create_page("Overview")
        second = project.create_page("Hidden Draft")

        changes = set_page_properties(
            first,
            [("displayOption", "FitToWidth"), ("visibility", "HiddenInViewMode")],
        )
        assert [change.prop for change in changes] == ["displayOption", "visibility"]
        assert all(change.changed for change in changes)

        count = set_all_page_properties(
            project,
            [("background.color", "#FFFFFF")],
            exclude="Hidden",
            dry_run=False,
        )
        assert count == 1
        assert get_property(project.find_page("Overview").data, "background.color", PAGE_PROPERTIES) == "#FFFFFF"
        assert project.find_page("Hidden Draft").display_name == "Hidden Draft"


def test_page_binding_helpers_cover_drillthrough_and_tooltip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp), with_model=True)
        page = project.create_page("Detail")
        fields = resolve_page_fields(project, ["Customers.Region"])

        configure_page_drillthrough(page, fields, cross_report=True, hide=True)
        binding = get_page_binding_info(page)
        assert binding is not None
        assert binding.binding_type == "Drillthrough"
        assert binding.cross_report is True
        assert binding.fields == [("Customers", "Region", "column")]
        assert clear_page_drillthrough(page) is True
        assert get_page_binding_info(page) is None

        configure_page_tooltip(page, fields, width=320, height=240)
        binding = get_page_binding_info(page)
        assert binding is not None
        assert binding.binding_type == "Tooltip"
        assert binding.fields == [("Customers", "Region", "column")]
        assert clear_page_tooltip(page) is True
        assert get_page_binding_info(page) is None


def test_page_section_helpers_create_and_list_sections() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp))
        page = project.create_page("Overview")

        result = create_page_section(project, page, "Revenue", x=10, y=20, width=300, height=120)
        assert result.title == "Revenue"
        assert result.background_visual.startswith("section-bg-")
        assert result.title_visual.startswith("section-title-")

        sections = list_page_sections(project, page)
        assert len(sections) == 1
        assert sections[0].name == "Revenue"
        assert sections[0].x == 10
        assert sections[0].y == 20
