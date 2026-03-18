from __future__ import annotations

import json
import tempfile
from pathlib import Path

from pbi.commands.common import resolve_field_info, resolve_field_type
from pbi.project import Project
from pbi.schema_refs import REPORT_SCHEMA


def _make_project(root: Path, *, with_model: bool = False) -> Project:
    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
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
    if with_model:
        tables = root / "Sample.SemanticModel" / "definition" / "tables"
        tables.mkdir(parents=True)
        (tables / "Customers.tmdl").write_text(
            "\n".join(
                [
                    "table 'Customers'",
                    "    column 'Region'",
                    "        dataType: string",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return Project.find(pbip)


def test_resolve_field_type_falls_back_to_column_without_model() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _make_project(Path(tmp), with_model=False)

        assert resolve_field_type(project, "Sales.Amount", "auto") == ("Sales", "Amount", "column")


def test_resolve_field_info_uses_model_to_return_column_data_type() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _make_project(Path(tmp), with_model=True)

        assert resolve_field_info(project, "Customers.Region", "auto") == (
            "Customers",
            "Region",
            "column",
            "string",
        )


def test_resolve_field_info_preserves_explicit_measure_mode() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        project = _make_project(Path(tmp), with_model=True)

        assert resolve_field_info(project, "Metrics.Total Revenue", "measure") == (
            "Metrics",
            "Total Revenue",
            "measure",
            None,
        )
