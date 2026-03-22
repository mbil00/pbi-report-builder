"""Tests for field parameter support."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pbi.model import SemanticModel


def _make_project(root: Path) -> None:
    from pbi.schema_refs import REPORT_SCHEMA

    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps({"$schema": REPORT_SCHEMA, "themeCollection": {}, "layoutOptimization": "None"}) + "\n",
        encoding="utf-8",
    )


def _write_table(root: Path, filename: str, content: str) -> Path:
    tables = root / "Sample.SemanticModel" / "definition" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    path = tables / filename
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


class FieldParameterParserTests(unittest.TestCase):
    def test_parse_is_parameter_type_flag(self) -> None:
        """Parser detects isParameterType on a table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Metric_Selector.tmdl", """
table 'Metric Selector'
\tisParameterType
\tlineageTag: abc-123

\tcolumn 'Metric Selector'
\t\tdataType: string
\t\tlineageTag: col-1
\t\tsourceColumn: [Name]

\tpartition 'Metric Selector' = calculated
\t\tmode: import
\t\tsource = {("Revenue", NAMEOF('Sales'[Revenue]), 0)}
""")
            model = SemanticModel.load(root)
            table = model.find_table("Metric Selector")
            self.assertTrue(table.is_parameter_type)

    def test_regular_table_not_parameter_type(self) -> None:
        """Normal tables have is_parameter_type=False."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: xyz-456

\tcolumn Revenue
\t\tdataType: decimal
\t\tlineageTag: col-2
""")
            model = SemanticModel.load(root)
            table = model.find_table("Sales")
            self.assertFalse(table.is_parameter_type)


if __name__ == "__main__":
    unittest.main()
