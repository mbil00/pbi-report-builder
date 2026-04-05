from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pbi.project import Project
from pbi.schema_refs import PAGES_METADATA_SCHEMA, REPORT_SCHEMA
from pbi.visual_groups import create_group, create_group_container, ungroup


def _make_project(root: Path) -> Project:
    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    pages_dir = definition / "pages"
    pages_dir.mkdir(parents=True)

    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps({"$schema": REPORT_SCHEMA}) + "\n",
        encoding="utf-8",
    )
    (pages_dir / "pages.json").write_text(
        json.dumps({"$schema": PAGES_METADATA_SCHEMA, "pageOrder": []}) + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip)


def test_visual_group_helpers_create_and_ungroup_children() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _make_project(Path(tmp))
        page = project.create_page("Overview")
        first = project.create_visual(page, "textbox", x=10, y=20, width=100, height=50)
        second = project.create_visual(page, "textbox", x=40, y=70, width=120, height=60)

        group = create_group(project, page, [first, second], display_name="Header")
        reloaded = project.find_visual(page, "Header")

        assert group.name == "Header"
        assert reloaded.data["position"]["x"] == 10
        assert reloaded.data["position"]["y"] == 20
        assert reloaded.data["position"]["width"] == 150
        assert reloaded.data["position"]["height"] == 110

        freed = ungroup(project, page, reloaded)
        assert [visual.name for visual in freed] == [first.name, second.name]
        assert project.find_visual(page, first.name).data.get("parentGroupName") is None


def test_visual_group_container_helper_creates_empty_group() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _make_project(Path(tmp))
        page = project.create_page("Overview")

        group = create_group_container(
            project,
            page,
            name="summary-band",
            display_name="Summary Band",
            x=5,
            y=6,
            width=300,
            height=40,
        )

        assert group.name == "summary-band"
        reloaded = project.find_visual(page, "summary-band")
        assert reloaded.data["visualGroup"]["displayName"] == "Summary Band"
