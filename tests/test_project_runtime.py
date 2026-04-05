from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

from pbi.project import Project
from pbi.project_runtime import prepare_project_runtime
from pbi.schema_refs import PAGE_SCHEMA, PAGES_METADATA_SCHEMA, REPORT_SCHEMA
from pbi.visual_schema import clear_custom_schemas, get_visual_schema


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


def _add_visual(project: Project, page_name: str, visual_name: str, visual_type: str) -> None:
    pages_dir = project.definition_folder / "pages"
    page_dir = pages_dir / page_name
    if not page_dir.exists():
        page_dir.mkdir(parents=True)
        (page_dir / "page.json").write_text(
            json.dumps(
                {
                    "$schema": PAGE_SCHEMA,
                    "name": page_name,
                    "displayName": page_name,
                    "width": 1280,
                    "height": 720,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        meta_path = pages_dir / "pages.json"
        meta = json.loads(meta_path.read_text())
        meta.setdefault("pageOrder", []).append(page_name)
        meta_path.write_text(json.dumps(meta) + "\n", encoding="utf-8")

    visual_dir = page_dir / "visuals" / visual_name
    visual_dir.mkdir(parents=True, exist_ok=True)
    (visual_dir / "visual.json").write_text(
        json.dumps(
            {
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.7.0/schema.json",
                "name": visual_name,
                "position": {"x": 0, "y": 0, "width": 200, "height": 200},
                "visual": {"visualType": visual_type},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    project.clear_caches()


def _make_pbiviz(path: Path, visual_type: str = "MyCustomChart") -> None:
    capabilities = {
        "visual": {
            "name": visual_type,
            "displayName": "My Custom Chart",
            "visualClassName": visual_type,
            "capabilities": {
                "dataRoles": [
                    {"name": "Category", "displayName": "Category", "kind": 0},
                    {"name": "Values", "displayName": "Values", "kind": 1},
                ],
                "objects": {
                    "legend": {
                        "displayName": "Legend",
                        "properties": {
                            "show": {"type": {"bool": True}},
                        },
                    },
                },
            },
        }
    }
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("resources/test.pbiviz.json", json.dumps(capabilities))


def test_prepare_project_runtime_installs_and_registers_custom_visuals() -> None:
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            _add_visual(proj, "page1", "cv1", "MyCustomChart")
            cv_dir = proj.report_folder / "CustomVisuals"
            cv_dir.mkdir(parents=True)
            _make_pbiviz(cv_dir / "MyChart.pbiviz")

            state = prepare_project_runtime(proj)

            assert len(state.newly_installed_visuals) == 1
            assert state.registered_schema_count == 1
            assert get_visual_schema("MyCustomChart") is not None
    finally:
        clear_custom_schemas()


def test_prepare_project_runtime_is_idempotent_for_existing_schema_files() -> None:
    clear_custom_schemas()
    try:
        with tempfile.TemporaryDirectory() as tmp:
            proj = _make_project(Path(tmp))
            cv_dir = proj.report_folder / "CustomVisuals"
            cv_dir.mkdir(parents=True)
            _make_pbiviz(cv_dir / "MyChart.pbiviz")

            first = prepare_project_runtime(proj)
            second = prepare_project_runtime(proj)

            assert len(first.newly_installed_visuals) == 1
            assert second.newly_installed_visuals == []
            assert second.registered_schema_count == 1
    finally:
        clear_custom_schemas()
