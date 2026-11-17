"""Page and visual authoring helpers on a copy of the Desktop-saved report-01."""

from __future__ import annotations

from collections.abc import Callable

from pbi.project import Project
from pbi.report_authoring import ReportAuthoring
from tests.support import read_json

KITCHEN_SINK = "report-01-kitchen-sink"
NAVIGATION_CHILDREN = {"navToProduct", "navToRegional", "navFocusOnline"}


def test_page_authoring_helpers_preserve_order_and_active_page(
    fixture_project: Callable[[str], Project],
) -> None:
    project = fixture_project(KITCHEN_SINK)
    authoring = ReportAuthoring(project)
    overview = project.find_page("Executive Overview")
    regional = project.find_page("Regional Detail")
    authoring.set_active_page(regional.name)

    duplicate = authoring.copy_page(overview, "Overview Copy")
    authoring.delete_page(regional)

    assert [page.display_name for page in project.get_pages()] == [
        "Executive Overview",
        "Product Detail",
        "Tooltip - Order Context",
        "Hidden QA Page",
        "Overview Copy",
    ]
    meta = project.get_pages_meta()
    # The deleted page was active, so the first page becomes active.
    assert meta["activePageName"] == overview.name
    assert regional.name not in meta["pageOrder"]
    assert meta["pageOrder"][-1] == duplicate.name
    assert not regional.folder.exists()

    assert duplicate.name == duplicate.folder.name != overview.name
    saved = read_json(duplicate.folder / "page.json")
    assert (saved["name"], saved["displayName"]) == (duplicate.folder.name, "Overview Copy")
    # The copy keeps Desktop's friendly visual names and the group, in new folders.
    source = {visual.name: visual for visual in project.get_visuals(overview)}
    copied = {visual.name: visual for visual in project.get_visuals(duplicate)}
    assert copied.keys() == source.keys()
    assert {v.folder.name for v in copied.values()}.isdisjoint(v.folder.name for v in source.values())
    grouped = {name for name, visual in copied.items() if visual.data.get("parentGroupName") == "Navigation"}
    assert grouped == NAVIGATION_CHILDREN


def test_visual_authoring_helpers_cover_copy_and_group_delete_cleanup(
    fixture_project: Callable[[str], Project],
) -> None:
    project = fixture_project(KITCHEN_SINK)
    authoring = ReportAuthoring(project)
    overview = project.find_page("Executive Overview")
    regional = project.find_page("Regional Detail")
    visuals = {visual.name: visual for visual in project.get_visuals(overview)}
    regional_count = len(project.get_visuals(regional))

    copied = authoring.copy_visual(visuals["heroTitle"], regional, new_name="hero title copy")
    assert copied.name == "hero-title-copy"
    assert copied.folder.parent.parent == regional.folder
    assert read_json(copied.folder / "visual.json")["visual"] == visuals["heroTitle"].data["visual"]
    regional_names = [visual.name for visual in project.get_visuals(regional)]
    assert len(regional_names) == regional_count + 1
    assert "hero-title-copy" in regional_names

    group = visuals["Navigation"]
    authoring.delete_visual(group)
    project.clear_caches()

    after = {visual.name: visual for visual in project.get_visuals(overview)}
    assert not group.folder.exists()
    assert after.keys() == visuals.keys() - {"Navigation"}
    for name in NAVIGATION_CHILDREN:
        assert "parentGroupName" not in after[name].data
        assert "parentGroupName" not in read_json(after[name].folder / "visual.json")
