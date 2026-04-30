from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pbi.project import Project
from pbi.schema_refs import REPORT_SCHEMA
from pbi.report_authoring import ReportAuthoring


def _make_project(root: Path) -> Project:
    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition" / "pages"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (report / "definition" / "report.json").write_text(
        json.dumps(
            {
                "$schema": REPORT_SCHEMA,
                "themeCollection": {},
                "layoutOptimization": "None",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip)


def test_visual_query_helpers_manage_bindings_and_sort() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _make_project(Path(tmp))
        authoring = ReportAuthoring(project)
        page = authoring.create_page("Overview")
        visual = authoring.create_visual(page, "cardVisual")

        authoring.add_binding(visual, "Data", "Sales", "Revenue", field_type="measure")
        authoring.add_binding(visual, "Category", "Date", "Month")
        assert authoring.get_bindings(visual) == [
            ("Data", "Sales", "Revenue", "measure"),
            ("Category", "Date", "Month", "column"),
        ]

        removed = authoring.remove_binding(visual, "Category", field_ref="Date.Month")
        assert removed == 1
        assert authoring.get_bindings(visual) == [("Data", "Sales", "Revenue", "measure")]

        authoring.set_sort(visual, "Date", "Month", descending=False)
        assert authoring.get_sort(visual) == [("Date", "Month", "column", "Ascending")]
        assert authoring.clear_sort(visual) is True
        assert authoring.get_sort(visual) == []
