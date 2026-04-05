from __future__ import annotations

import tempfile
from pathlib import Path

from pbi.page_authoring import copy_page, create_page, delete_page
from pbi.project import _read_json, _write_json
from pbi.visual_authoring import copy_visual, create_visual, delete_visual
from tests.cli_regressions_support import make_project


def test_page_authoring_helpers_preserve_order_and_active_page() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp))
        first = create_page(project, "Overview")
        second = create_page(project, "Details")

        meta_path = project.definition_folder / "pages" / "pages.json"
        meta = _read_json(meta_path)
        meta["activePageName"] = second.name
        _write_json(meta_path, meta)

        duplicate = copy_page(project, first, "Overview Copy")
        delete_page(project, second)

        page_names = [page.display_name for page in project.get_pages()]
        pages_meta = project.get_pages_meta()

        assert page_names == ["Overview", "Overview Copy"]
        assert duplicate.display_name == "Overview Copy"
        assert pages_meta["activePageName"] == first.name
        assert second.name not in pages_meta["pageOrder"]


def test_visual_authoring_helpers_cover_copy_and_group_delete_cleanup() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = make_project(Path(tmp))
        page = create_page(project, "Overview")
        first = create_visual(project, page, "textbox", x=10, y=20, width=100, height=40)
        first.data["name"] = "first"
        first.save()
        second = create_visual(project, page, "textbox", x=20, y=80, width=100, height=40)
        second.data["name"] = "second"
        second.save()

        copied = copy_visual(project, first, page, new_name="first copy")
        assert copied.name == "first-copy"

        group = project.create_group(page, [first, second], display_name="header")
        delete_visual(project, group)
        project.clear_caches()

        visuals = {visual.name: visual for visual in project.get_visuals(page)}
        assert "header" not in visuals
        assert "first-copy" in visuals
        assert "parentGroupName" not in visuals["first"].data
        assert "parentGroupName" not in visuals["second"].data
