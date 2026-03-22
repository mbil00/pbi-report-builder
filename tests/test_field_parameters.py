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


from pbi.model import SemanticModel, create_field_parameter


class FieldParameterCreateTests(unittest.TestCase):
    def test_create_field_parameter_basic(self) -> None:
        """Create a field parameter table with measures."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1

\tmeasure Margin = SUM(Sales[Profit])
\t\tlineageTag: m2
""")
            name, path, created = create_field_parameter(
                root, "Metric Selector",
                fields=["Sales.Revenue", "Sales.Margin"],
                labels=["Revenue", "Margin"],
            )
            self.assertTrue(created)
            self.assertTrue(path.exists())

            content = path.read_text(encoding="utf-8")
            self.assertIn("isParameterType", content)
            self.assertIn("sourceColumn: [Name]", content)
            self.assertIn("sourceColumn: [Value]", content)
            self.assertIn("sourceColumn: [Ordinal]", content)
            self.assertIn("NAMEOF('Sales'[Revenue])", content)
            self.assertIn("NAMEOF('Sales'[Margin])", content)

            # Verify it parses back correctly
            model = SemanticModel.load(root)
            table = model.find_table("Metric Selector")
            self.assertTrue(table.is_parameter_type)

    def test_create_field_parameter_auto_labels(self) -> None:
        """Labels default to field property names."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1
""")
            _, path, _ = create_field_parameter(
                root, "Selector",
                fields=["Sales.Revenue"],
                labels=None,
            )
            content = path.read_text(encoding="utf-8")
            self.assertIn('"Revenue"', content)

    def test_create_field_parameter_labels_length_mismatch(self) -> None:
        """Mismatched labels and fields raises ValueError."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1

\tmeasure Margin = SUM(Sales[Profit])
\t\tlineageTag: m2
""")
            with self.assertRaises(ValueError):
                create_field_parameter(
                    root, "Selector",
                    fields=["Sales.Revenue", "Sales.Margin"],
                    labels=["Revenue"],
                )

    def test_create_field_parameter_duplicate_table(self) -> None:
        """Error when table already exists."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1
""")
            create_field_parameter(root, "Selector", fields=["Sales.Revenue"], labels=None)
            with self.assertRaises(ValueError):
                create_field_parameter(root, "Selector", fields=["Sales.Revenue"], labels=None)

    def test_create_field_parameter_dry_run(self) -> None:
        """Dry run doesn't write files."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1
""")
            _, path, _ = create_field_parameter(
                root, "Selector",
                fields=["Sales.Revenue"],
                labels=None,
                dry_run=True,
            )
            self.assertFalse(path.exists())


from typer.testing import CliRunner
from pbi.cli import app

runner = CliRunner()


class FieldParameterCLITests(unittest.TestCase):
    def test_cli_create_field_parameter(self) -> None:
        """CLI creates a field parameter table."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tlineageTag: t1

\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m1

\tmeasure Margin = SUM(Sales[Profit])
\t\tlineageTag: m2
""")
            result = runner.invoke(app, [
                "model", "field-parameter", "create",
                "Metric Selector",
                "--fields", "Sales.Revenue",
                "--fields", "Sales.Margin",
                "--labels", "Revenue",
                "--labels", "Margin",
                "-p", str(root),
            ])
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("Created field parameter", result.output)
            self.assertIn("Revenue", result.output)


if __name__ == "__main__":
    unittest.main()
