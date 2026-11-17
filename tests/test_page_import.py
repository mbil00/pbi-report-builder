"""``import_page`` from a copy of the Desktop-saved report-01 into other Desktop fixtures."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from pbi.page_import import import_page
from pbi.project import Project
from tests.support import read_json

KITCHEN_SINK = "report-01-kitchen-sink"
LOGO = "logo5431731159809324.png"


def test_import_page_rewrites_visual_ids_and_group_references(
    fixture_project: Callable[[str], Project],
) -> None:
    source = fixture_project(KITCHEN_SINK)
    target = fixture_project("report-02-model-heavy")
    source_page = source.find_page("Executive Overview")
    source_names = {visual.name for visual in source.get_visuals(source_page)}
    pages_before = [page.name for page in target.get_pages()]

    result = import_page(target, from_project=source, page="Executive Overview", name="Imported")

    assert (result.source_page_name, result.target_page_name) == ("Executive Overview", "Imported")
    assert (result.visual_count, result.resource_count) == (15, 0)
    imported_page = target.find_page("Imported")
    assert imported_page.name == imported_page.folder.name != source_page.name
    assert [page.name for page in target.get_pages()] == [*pages_before, imported_page.name]
    assert target.get_pages_meta()["pageOrder"][-1] == imported_page.folder.name
    saved = read_json(imported_page.folder / "page.json")
    assert (saved["name"], saved["displayName"]) == (imported_page.folder.name, "Imported")

    imported = target.get_visuals(imported_page)
    names = {visual.name for visual in imported}
    assert len(imported) == 15
    assert names.isdisjoint(source_names)
    assert all(visual.name == visual.folder.name for visual in imported)
    [group] = [visual for visual in imported if "visualGroup" in visual.data]
    assert group.data["visualGroup"]["displayName"] == "Navigation"
    children = [visual for visual in imported if visual.data.get("parentGroupName")]
    assert len(children) == 3
    assert {visual.data["parentGroupName"] for visual in children} == {group.name}
    assert not (target.report_folder / "StaticResources" / "RegisteredResources").exists()


@pytest.mark.parametrize("target_name", ["report-02-model-heavy", "report-04-desktop-shapes"])
def test_import_page_copies_registered_resources_when_requested(
    fixture_project: Callable[[str], Project],
    target_name: str,
) -> None:
    # report-02 has no RegisteredResources package; report-04 has one with a theme and an image.
    source = fixture_project(KITCHEN_SINK)
    target = fixture_project(target_name)
    resources = target.report_folder / "StaticResources" / "RegisteredResources"
    files_before = sorted(path.name for path in resources.iterdir()) if resources.exists() else []
    packages_before = read_json(target.definition_folder / "report.json")["resourcePackages"]
    items_before = next(
        (package["items"] for package in packages_before if package["name"] == "RegisteredResources"), []
    )

    result = import_page(
        target,
        from_project=source,
        page="Executive Overview",
        name="Imported",
        include_resources=True,
    )

    # Only this page's image is copied; Product Detail's hero image stays behind.
    assert result.resource_count == 1
    assert sorted(path.name for path in resources.iterdir()) == sorted([*files_before, LOGO])
    source_logo = source.report_folder / "StaticResources" / "RegisteredResources" / LOGO
    assert (resources / LOGO).read_bytes() == source_logo.read_bytes()

    packages = read_json(target.definition_folder / "report.json")["resourcePackages"]
    assert [package["name"] for package in packages] == ["SharedResources", "RegisteredResources"]
    [registered] = [package for package in packages if package["name"] == "RegisteredResources"]
    assert registered["type"] == "RegisteredResources"
    assert registered["items"] == [*items_before, {"name": LOGO, "path": LOGO, "type": "Image"}]


@pytest.mark.xfail(strict=True, reason="#103: resource writes drop the BaseThemes/ folder from the base theme path")
def test_import_page_keeps_the_base_theme_path(fixture_project: Callable[[str], Project]) -> None:
    source = fixture_project(KITCHEN_SINK)
    target = fixture_project("report-04-desktop-shapes")
    shared_before = read_json(target.definition_folder / "report.json")["resourcePackages"][0]
    assert shared_before["items"][0]["path"] == "BaseThemes/Fluent2-CY26SU10.json"

    import_page(target, from_project=source, page="Executive Overview", name="Imported", include_resources=True)

    assert read_json(target.definition_folder / "report.json")["resourcePackages"][0] == shared_before
