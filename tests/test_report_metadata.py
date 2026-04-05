from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pbi.project import Project
from pbi.report_metadata import (
    clear_report_data_source_variables,
    clear_report_object,
    delete_report_annotation,
    get_report_annotation,
    get_report_data_source_variables,
    get_report_object,
    list_report_annotations,
    list_report_objects,
    set_report_annotation,
    set_report_data_source_variables,
    set_report_object,
    set_report_properties,
)
from pbi.schema_refs import REPORT_SCHEMA


def _make_report_project(root: Path) -> tuple[Project, Path]:
    pbip_path = root / "Sample.pbip"
    report_folder = root / "Sample.Report"
    definition = report_folder / "definition"
    definition.mkdir(parents=True)

    pbip_path.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    report_path = definition / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "$schema": REPORT_SCHEMA,
                "layoutOptimization": "None",
                "themeCollection": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip_path), report_path


def test_set_report_properties_returns_changes_and_persists() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project, report_path = _make_report_project(Path(tmp))

        changes = set_report_properties(
            project,
            [
                ("settings.useEnhancedTooltips", "true"),
                ("settings.pagesPosition", "Bottom"),
            ],
        )

        assert [change.prop for change in changes] == [
            "settings.useEnhancedTooltips",
            "settings.pagesPosition",
        ]
        assert all(change.changed for change in changes)

        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        assert report["settings"]["useEnhancedTooltips"] is True
        assert report["settings"]["pagesPosition"] == "Bottom"


def test_report_annotation_helpers_cover_crud() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project, report_path = _make_report_project(Path(tmp))

        created = set_report_annotation(project, "README", "Owned by BI")
        assert created.created is True
        assert created.changed is True
        assert created.annotation.name == "README"

        unchanged = set_report_annotation(project, "README", "Owned by BI")
        assert unchanged.created is False
        assert unchanged.changed is False

        rows = list_report_annotations(project)
        assert rows == [created.annotation]
        assert get_report_annotation(project, "README") == created.annotation

        deleted = delete_report_annotation(project, "README")
        assert deleted == created.annotation

        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        assert "annotations" not in report


def test_report_object_helpers_normalize_and_clear() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project, report_path = _make_report_project(Path(tmp))

        payload = [
            {
                "resourcePackage": {
                    "name": "RegisteredResources",
                    "type": 1,
                    "items": [
                        {"name": "logo.png", "path": "RegisteredResources/logo.png", "type": 202}
                    ],
                }
            }
        ]

        key, changed = set_report_object(project, "resourcePackages", payload)
        assert key == "resourcePackages"
        assert changed is True

        rows = list_report_objects(project)
        resource_row = next(row for row in rows if row.name == "resourcePackages")
        assert resource_row.present is True
        assert resource_row.value_type == "array"

        loaded_key, value = get_report_object(project, "resourcePackages")
        assert loaded_key == "resourcePackages"
        assert value == [
            {
                "name": "RegisteredResources",
                "type": "RegisteredResources",
                "items": [{"name": "logo.png", "path": "logo.png", "type": "Image"}],
            }
        ]

        cleared_key, removed = clear_report_object(project, "resourcePackages")
        assert cleared_key == "resourcePackages"
        assert removed is True

        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        assert "resourcePackages" not in report


def test_report_data_source_variable_helpers_round_trip() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project, report_path = _make_report_project(Path(tmp))

        assert get_report_data_source_variables(project) is None
        assert set_report_data_source_variables(project, '{"region":"EMEA"}') is True
        assert set_report_data_source_variables(project, '{"region":"EMEA"}') is False
        assert get_report_data_source_variables(project) == '{"region":"EMEA"}'
        assert clear_report_data_source_variables(project) is True
        assert clear_report_data_source_variables(project) is False

        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        assert "dataSourceVariables" not in report
