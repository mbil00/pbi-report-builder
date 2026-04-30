from __future__ import annotations

import tempfile
from pathlib import Path

from pbi.project import _read_json, _write_json
from pbi.report_authoring import ReportAuthoring
from tests.cli_regressions_support import make_project


def test_page_authoring_helpers_preserve_order_and_active_page() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp))
        authoring = ReportAuthoring(project)
        first = authoring.create_page("Overview")
        second = authoring.create_page("Details")

        meta_path = project.definition_folder / "pages" / "pages.json"
        meta = _read_json(meta_path)
        meta["activePageName"] = second.name
        _write_json(meta_path, meta)

        duplicate = authoring.copy_page(first, "Overview Copy")
        authoring.delete_page(second)

        page_names = [page.display_name for page in project.get_pages()]
        pages_meta = project.get_pages_meta()

        assert page_names == ["Overview", "Overview Copy"]
        assert duplicate.display_name == "Overview Copy"
        assert pages_meta["activePageName"] == first.name
        assert second.name not in pages_meta["pageOrder"]


def test_visual_authoring_helpers_cover_copy_and_group_delete_cleanup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp))
        authoring = ReportAuthoring(project)
        page = authoring.create_page("Overview")
        first = authoring.create_visual(page, "textbox", x=10, y=20, width=100, height=40)
        first.data["name"] = "first"
        first.save()
        second = authoring.create_visual(page, "textbox", x=20, y=80, width=100, height=40)
        second.data["name"] = "second"
        second.save()

        copied = authoring.copy_visual(first, page, new_name="first copy")
        assert copied.name == "first-copy"

        group = authoring.create_group(page, [first, second], display_name="header")
        authoring.delete_visual(group)
        project.clear_caches()

        visuals = {visual.name: visual for visual in project.get_visuals(page)}
        assert "header" not in visuals
        assert "first-copy" in visuals
        assert "parentGroupName" not in visuals["first"].data
        assert "parentGroupName" not in visuals["second"].data
