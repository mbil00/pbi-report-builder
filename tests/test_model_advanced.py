"""Tests for advanced TMDL features: DAX scanner, deps, rename, bulk hide, calculated tables, validation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.model import (
    SemanticModel,
    create_calculated_table,
    create_relationship,
    find_field_dependents,
    find_field_references,
    rename_column,
    rename_measure,
    set_column_hidden,
    validate_relationships,
)
from pbi.modeling.dax_refs import DaxRef, extract_refs, replace_refs


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


def _write_relationships(root: Path, content: str) -> Path:
    defn = root / "Sample.SemanticModel" / "definition"
    defn.mkdir(parents=True, exist_ok=True)
    path = defn / "relationships.tmdl"
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


# ── DAX Reference Scanner ───────────────────────────────────────


class DaxRefScannerTests(unittest.TestCase):
    def test_extract_unqualified_measure(self):
        refs = extract_refs("DIVIDE ( [Total Revenue], [Order Count] )")
        self.assertEqual(len(refs), 2)
        self.assertEqual(refs[0].name, "Total Revenue")
        self.assertFalse(refs[0].qualified)
        self.assertEqual(refs[1].name, "Order Count")

    def test_extract_qualified_column(self):
        refs = extract_refs("SUM ( Sales[Revenue] )")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].table, "Sales")
        self.assertEqual(refs[0].name, "Revenue")
        self.assertTrue(refs[0].qualified)

    def test_extract_quoted_table(self):
        refs = extract_refs("SUM ( 'My Table'[Amount] )")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].table, "My Table")
        self.assertEqual(refs[0].name, "Amount")

    def test_skip_string_literals(self):
        refs = extract_refs('"Total [Revenue]" & [Actual]')
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].name, "Actual")

    def test_skip_comments(self):
        refs = extract_refs("[Real] + 1 // this is [Comment]")
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].name, "Real")

    def test_multiple_refs(self):
        expr = "IF ( Sales[Qty] > 0, [Revenue] / Sales[Qty], BLANK() )"
        refs = extract_refs(expr)
        names = [(r.table, r.name) for r in refs]
        self.assertIn(("Sales", "Qty"), names)
        self.assertIn(("", "Revenue"), names)

    def test_replace_unqualified(self):
        result = replace_refs(
            "DIVIDE ( [Old Name], [Other] )",
            old_table=None, old_name="Old Name", new_name="New Name",
        )
        self.assertIn("[New Name]", result)
        self.assertIn("[Other]", result)
        self.assertNotIn("[Old Name]", result)

    def test_replace_qualified(self):
        result = replace_refs(
            "SUM ( Sales[OldCol] ) + Sales[OtherCol]",
            old_table="Sales", old_name="OldCol", new_name="NewCol",
        )
        self.assertIn("Sales[NewCol]", result)
        self.assertIn("Sales[OtherCol]", result)
        self.assertNotIn("OldCol", result)

    def test_replace_qualified_only(self):
        result = replace_refs(
            "[Qty] + Sales[Qty]",
            old_table="Sales", old_name="Qty", new_name="Quantity",
            qualified_only=True,
        )
        # Only Sales[Qty] should be replaced, not [Qty]
        self.assertIn("Sales[Quantity]", result)
        self.assertTrue(result.startswith("[Qty]"))

    def test_replace_preserves_strings(self):
        result = replace_refs(
            '"[Revenue]" & [Revenue]',
            old_table=None, old_name="Revenue", new_name="Sales Amount",
        )
        self.assertIn('"[Revenue]"', result)
        self.assertIn("[Sales Amount]", result)


# ── Dependency Analysis ─────────────────────────────────────────


class DependencyAnalysisTests(unittest.TestCase):
    def test_find_measure_dependents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tmeasure 'Avg Revenue' = DIVIDE([Revenue], [Count])
\t\tlineageTag: m-2

\tmeasure Count = COUNTROWS(Sales)
\t\tlineageTag: m-3

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            deps = find_field_dependents(root, "Sales.Revenue")
            dep_names = [f"{t}.{n}" for t, n, _ in deps]
            self.assertIn("Sales.Avg Revenue", dep_names)

    def test_find_column_dependents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Total = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            deps = find_field_dependents(root, "Sales.Amount")
            self.assertEqual(len(deps), 1)
            self.assertEqual(deps[0][1], "Total")

    def test_find_forward_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tmeasure 'Avg Revenue' = DIVIDE([Revenue], [Count])
\t\tlineageTag: m-2

\tmeasure Count = COUNTROWS(Sales)
\t\tlineageTag: m-3

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            refs = find_field_references(root, "Sales.Avg Revenue")
            ref_names = [f"{t}.{n}" for t, n, _ in refs]
            self.assertIn("Sales.Revenue", ref_names)
            self.assertIn("Sales.Count", ref_names)

    def test_deps_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tmeasure 'Avg Revenue' = DIVIDE([Revenue], [Count])
\t\tlineageTag: m-2

\tmeasure Count = COUNTROWS(Sales)
\t\tlineageTag: m-3

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            result = runner.invoke(app, [
                "model", "deps", "Sales.Revenue",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Avg Revenue", result.stdout)
            self.assertIn("Amount", result.stdout)


# ── Measure Rename ──────────────────────────────────────────────


class MeasureRenameTests(unittest.TestCase):
    def test_rename_measure_updates_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure 'Old Name' = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            table, old, new, refs = rename_measure(root, "Sales", "Old Name", "New Name")
            self.assertEqual(old, "Old Name")
            self.assertEqual(new, "New Name")

            model = SemanticModel.load(root)
            measures = [m.name for m in model.find_table("Sales").measures]
            self.assertIn("New Name", measures)
            self.assertNotIn("Old Name", measures)

    def test_rename_measure_cascades_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tmeasure 'Avg Rev' = DIVIDE([Revenue], [Count])
\t\tlineageTag: m-2

\tmeasure Count = COUNTROWS(Sales)
\t\tlineageTag: m-3

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            _, _, _, updated = rename_measure(root, "Sales", "Revenue", "Total Revenue")

            # Verify the expression was updated
            model = SemanticModel.load(root)
            avg = model.find_table("Sales").find_measure("Avg Rev")
            self.assertIn("[Total Revenue]", avg.expression)
            self.assertNotIn("[Revenue]", avg.expression)

    def test_rename_measure_rejects_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tmeasure Count = COUNTROWS(Sales)
\t\tlineageTag: m-2

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            with self.assertRaises(ValueError, msg="already exists"):
                rename_measure(root, "Sales", "Revenue", "Count")

    def test_rename_measure_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            result = runner.invoke(app, [
                "model", "measure", "rename", "Sales", "Revenue", "Total Revenue",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Renamed", result.stdout)
            self.assertIn("Total Revenue", result.stdout)

    def test_rename_measure_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            path = _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            original = path.read_text()
            rename_measure(root, "Sales", "Revenue", "Total Revenue", dry_run=True)
            self.assertEqual(path.read_text(), original)

    def test_rename_measure_batches_same_file_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1

\tmeasure 'Avg Rev' = DIVIDE([Revenue], [Count])
\t\tlineageTag: m-2

\tmeasure Count = COUNTROWS(Sales)
\t\tlineageTag: m-3

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            from pbi.modeling import writes as modeling_writes

            original_write = modeling_writes._write_tmdl_lines
            with mock.patch("pbi.modeling.writes._write_tmdl_lines", wraps=original_write) as write_lines:
                rename_measure(root, "Sales", "Revenue", "Total Revenue")

            self.assertEqual(write_lines.call_count, 1)


# ── Column Rename ───────────────────────────────────────────────


class ColumnRenameTests(unittest.TestCase):
    def test_rename_column_updates_declaration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year = YEAR([DateKey])
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none

\tcolumn DateKey
\t\tdataType: dateTime
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: DateKey
""")
            table, old, new, refs = rename_column(root, "Date", "Year", "CalendarYear")

            model = SemanticModel.load(root)
            col_names = [c.name for c in model.find_table("Date").columns]
            self.assertIn("CalendarYear", col_names)
            self.assertNotIn("Year", col_names)

    def test_rename_column_cascades_dax(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year = YEAR([DateKey])
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none

\tcolumn DateKey
\t\tdataType: dateTime
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: DateKey
""")
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure 'By Year' = COUNTROWS(FILTER(Sales, Date[Year] > 2020))
\t\tlineageTag: m-1

\tcolumn OrderDate
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
""")
            _, _, _, updated = rename_column(root, "Date", "Year", "CalendarYear")

            model = SemanticModel.load(root)
            m = model.find_table("Sales").find_measure("By Year")
            self.assertIn("Date[CalendarYear]", m.expression)
            self.assertNotIn("Date[Year]", m.expression)

    def test_rename_column_updates_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn YearKey = YEAR([DateCol])
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none

\tcolumn DateCol
\t\tdataType: dateTime
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: DateCol
""")
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn YearKey
\t\tdataType: int64
\t\tlineageTag: c-3
\t\tsummarizeBy: none
\t\tsourceColumn: YearKey
""")
            _write_relationships(root, """
relationship abc-123
\tfromColumn: Sales.YearKey
\ttoColumn: Date.YearKey
""")
            rename_column(root, "Date", "YearKey", "CalYear")

            model = SemanticModel.load(root)
            rel = model.relationships[0]
            self.assertEqual(rel.to_column, "CalYear")

    def test_rename_column_updates_relationships_with_spaced_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn YearKey = YEAR([DateCol])
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none

\tcolumn DateCol
\t\tdataType: dateTime
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: DateCol
""")
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn YearKey
\t\tdataType: int64
\t\tlineageTag: c-3
\t\tsummarizeBy: none
\t\tsourceColumn: YearKey
""")
            _write_relationships(root, """
relationship abc-123
\tfromColumn: Sales.YearKey
\ttoColumn: Date.YearKey
""")
            rename_column(root, "Date", "YearKey", "Fiscal Year Key")

            model = SemanticModel.load(root)
            rel = model.relationships[0]
            self.assertEqual(rel.to_column, "Fiscal Year Key")

    def test_rename_source_column_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
""")
            with self.assertRaises(ValueError, msg="source column"):
                rename_column(root, "Sales", "OrderDate", "NewDate")

    def test_rename_column_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year = YEAR([DateKey])
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none

\tcolumn DateKey
\t\tdataType: dateTime
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: DateKey
""")
            result = runner.invoke(app, [
                "model", "column", "rename", "Date", "Year", "CalendarYear",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Renamed", result.stdout)

    def test_rename_column_batches_per_file_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn YearKey = YEAR([DateCol])
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none

\tcolumn Label
\t\tdataType: string
\t\tsortByColumn: YearKey
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: Label

\tcolumn DateCol
\t\tdataType: dateTime
\t\tlineageTag: c-3
\t\tsummarizeBy: none
\t\tsourceColumn: DateCol
""")
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure 'By Year' = COUNTROWS(FILTER(Sales, Date[YearKey] > 2020))
\t\tlineageTag: m-1

\tcolumn YearKey
\t\tdataType: int64
\t\tlineageTag: c-4
\t\tsummarizeBy: none
\t\tsourceColumn: YearKey
""")
            _write_relationships(root, """
relationship abc-123
\tfromColumn: Sales.YearKey
\ttoColumn: Date.YearKey
""")
            from pbi.modeling import writes as modeling_writes

            original_write = modeling_writes._write_tmdl_lines
            with mock.patch("pbi.modeling.writes._write_tmdl_lines", wraps=original_write) as write_lines:
                rename_column(root, "Date", "YearKey", "CalYear")

            self.assertEqual(write_lines.call_count, 3)


# ── Bulk Hide/Unhide ────────────────────────────────────────────


class BulkHideTests(unittest.TestCase):
    def test_hide_matching_pattern(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID

\tcolumn ProductID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: ProductID

\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-3
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
""")
            result = runner.invoke(app, [
                "model", "column", "hide", "--table", "Sales", "--pattern", "ID$",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Hidden", result.stdout)
            self.assertIn("2 column(s) hidden", result.stdout)

            model = SemanticModel.load(root)
            t = model.find_table("Sales")
            cid = t.find_column("CustomerID")
            pid = t.find_column("ProductID")
            rev = t.find_column("Revenue")
            self.assertTrue(cid.is_hidden)
            self.assertTrue(pid.is_hidden)
            self.assertFalse(rev.is_hidden)

    def test_unhide_matching_pattern(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustomerID
\t\tdataType: string
\t\tisHidden
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID

\tcolumn ProductID
\t\tdataType: string
\t\tisHidden
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: ProductID
""")
            result = runner.invoke(app, [
                "model", "column", "unhide", "--table", "Sales", "--pattern", "Customer",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("1 column(s) shown", result.stdout)

    def test_hide_matching_no_results(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
""")
            result = runner.invoke(app, [
                "model", "column", "hide", "--table", "Sales", "--pattern", "ZZZZZ",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("No visible columns", result.stdout)

    def test_hide_matching_pattern_writes_table_once(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID

\tcolumn ProductID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: ProductID
""")
            from pbi.modeling import writes as modeling_writes

            original_write = modeling_writes._write_tmdl_lines
            with mock.patch("pbi.modeling.writes._write_tmdl_lines", wraps=original_write) as write_lines:
                result = runner.invoke(app, [
                    "model", "column", "hide", "--table", "Sales", "--pattern", "ID$",
                    "--project", str(root / "Sample.pbip"),
                ])

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertEqual(write_lines.call_count, 1)


# ── Calculated Table Creation ────────────────────────────────────


class CalculatedTableTests(unittest.TestCase):
    def test_create_calculated_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            # Need at least one table for SemanticModel.load
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            name, path, created = create_calculated_table(
                root, "DateBridge",
                'CALENDAR(DATE(2020,1,1), DATE(2025,12,31))',
            )
            self.assertTrue(created)
            self.assertEqual(name, "DateBridge")
            self.assertTrue(path.exists())

            content = path.read_text()
            self.assertIn("table DateBridge", content)
            self.assertIn("\tcolumn Date", content)
            self.assertIn("partition DateBridge = calculated", content)
            self.assertIn("CALENDAR", content)

            model = SemanticModel.load(root)
            table = model.find_table("DateBridge")
            self.assertEqual([column.name for column in table.columns], ["Date"])

    def test_create_calculated_table_multiline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            expr = """ADDCOLUMNS(
    GENERATESERIES(1, 10, 1),
    "Label", "Row " & [Value]
)"""
            name, path, _ = create_calculated_table(root, "Numbers", expr)
            content = path.read_text()
            self.assertIn("\tcolumn Value", content)
            self.assertIn("ADDCOLUMNS", content)
            self.assertIn("GENERATESERIES", content)

    def test_create_calculated_table_row_infers_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            create_calculated_table(root, "DimDivision", 'ROW("Contractual Division", "Corporate")')

            model = SemanticModel.load(root)
            table = model.find_table("DimDivision")
            self.assertEqual([column.name for column in table.columns], ["Contractual Division"])

    def test_create_duplicate_table_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            with self.assertRaises(ValueError, msg="already exists"):
                create_calculated_table(root, "Sales", "CALENDAR(DATE(2020,1,1), DATE(2025,12,31))")

    def test_create_calculated_table_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            result = runner.invoke(app, [
                "model", "table", "create", "DateBridge",
                "CALENDAR(DATE(2020,1,1), DATE(2025,12,31))",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Created calculated table", result.stdout)
            self.assertIn("DateBridge", result.stdout)

    def test_create_calculated_table_dry_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            _, path, _ = create_calculated_table(
                root, "DateBridge",
                "CALENDAR(DATE(2020,1,1), DATE(2025,12,31))",
                dry_run=True,
            )
            self.assertFalse(path.exists())


# ── Relationship Validation ──────────────────────────────────────


class RelationshipValidationTests(unittest.TestCase):
    def test_warns_on_bidirectional(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustID
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustID
""")
            create_relationship(
                root, "Sales.CustID", "Customers.CustID",
                properties={"crossFilteringBehavior": "bothDirections"},
            )
            findings = validate_relationships(root)
            warnings = [f for f in findings if f["severity"] == "warning"]
            self.assertTrue(any("Bidirectional" in f["message"] for f in warnings))

    def test_warns_on_auto_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustID
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustID
""")
            _write_relationships(root, """
relationship AutoDetected_abc-123
\tfromColumn: Sales.CustID
\ttoColumn: Customers.CustID
""")
            findings = validate_relationships(root)
            warnings = [f for f in findings if f["severity"] == "warning"]
            self.assertTrue(any("Auto-detected" in f["message"] for f in warnings))

    def test_suggests_missing_relationships(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn ProductID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: ProductID
""")
            _write_table(root, "Products.tmdl", """
table Products
\tcolumn ProductID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: ProductID
""")
            findings = validate_relationships(root)
            infos = [f for f in findings if f["severity"] == "info"]
            self.assertTrue(any("shared columns" in f["message"] for f in infos))

    def test_validate_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustID
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustID
""")
            _write_relationships(root, """
relationship AutoDetected_abc-123
\tcrossFilteringBehavior: bothDirections
\tfromColumn: Sales.CustID
\ttoColumn: Customers.CustID
""")
            result = runner.invoke(app, [
                "model", "check",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Bidirectional", result.stdout)
            self.assertIn("Auto-detected", result.stdout)

    def test_validate_no_issues(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
""")
            result = runner.invoke(app, [
                "model", "check",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("No issues", result.stdout)

    def test_validate_prefers_shorter_direct_active_path(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            for name in ("A", "B", "C"):
                _write_table(root, f"{name}.tmdl", f"""
table {name}
\tcolumn ID
\t\tdataType: string
\t\tlineageTag: {name.lower()}-1
\t\tsummarizeBy: none
\t\tsourceColumn: ID
""")
            create_relationship(root, "A.ID", "B.ID")
            create_relationship(root, "A.ID", "C.ID")
            create_relationship(root, "C.ID", "B.ID")

            validate_result = runner.invoke(app, ["validate", "--project", str(root / "Sample.pbip")])
            self.assertEqual(validate_result.exit_code, 0, validate_result.stdout)
            self.assertNotIn("Ambiguous active", validate_result.stdout)

            check_result = runner.invoke(app, ["model", "check", "--project", str(root / "Sample.pbip")])
            self.assertEqual(check_result.exit_code, 0, check_result.stdout)
            self.assertNotIn("Ambiguous active relationship paths", check_result.stdout)

    def test_validate_reports_equal_length_ambiguous_active_paths(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            for name in ("A", "B", "C", "D"):
                _write_table(root, f"{name}.tmdl", f"""
table {name}
\tcolumn ID
\t\tdataType: string
\t\tlineageTag: {name.lower()}-1
\t\tsummarizeBy: none
\t\tsourceColumn: ID
""")
            create_relationship(root, "A.ID", "B.ID")
            create_relationship(root, "A.ID", "C.ID")
            create_relationship(root, "B.ID", "D.ID")
            create_relationship(root, "C.ID", "D.ID")

            validate_result = runner.invoke(app, ["validate", "--project", str(root / "Sample.pbip")])
            self.assertEqual(validate_result.exit_code, 1, validate_result.stdout)
            self.assertIn("Ambiguous active", validate_result.stdout)
            self.assertIn("D -> B -> A", validate_result.stdout)
            self.assertIn("D -> C -> A", validate_result.stdout)

            check_result = runner.invoke(app, ["model", "check", "--project", str(root / "Sample.pbip")])
            self.assertEqual(check_result.exit_code, 1, check_result.stdout)
            self.assertIn("Ambiguous active relationship paths", check_result.stdout)
            self.assertIn("D -> B -> A", check_result.stdout)
            self.assertIn("D -> C -> A", check_result.stdout)

    def test_model_check_accepts_auto_date_table_data_categories(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "LocalDateTable_abc.tmdl", """
table LocalDateTable_abc
\tannotation __PBI_LocalDateTable = true
\tcolumn Date
\t\tdataType: dateTime
\t\tdataCategory: PaddedDateTableDates
\t\tlineageTag: ld-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date
\tcolumn Year
\t\tdataType: int64
\t\tdataCategory: Years
\t\tlineageTag: ld-2
\t\tsummarizeBy: none
\t\tsourceColumn: Year
\tcolumn Month
\t\tdataType: string
\t\tdataCategory: Months
\t\tlineageTag: ld-3
\t\tsummarizeBy: none
\t\tsourceColumn: Month
\tcolumn MonthNo
\t\tdataType: int64
\t\tdataCategory: MonthOfYear
\t\tlineageTag: ld-4
\t\tsummarizeBy: none
\t\tsourceColumn: MonthNo
\tcolumn Quarter
\t\tdataType: string
\t\tdataCategory: Quarters
\t\tlineageTag: ld-5
\t\tsummarizeBy: none
\t\tsourceColumn: Quarter
\tcolumn QuarterNo
\t\tdataType: int64
\t\tdataCategory: QuarterOfYear
\t\tlineageTag: ld-6
\t\tsummarizeBy: none
\t\tsourceColumn: QuarterNo
""")

            result = runner.invoke(app, [
                "model", "check",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("No issues", result.stdout)

    def test_validate_reports_missing_relationship_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            _write_relationships(root, """
relationship rel-1
\tfromColumn: Sales.CustomerID
\ttoColumn: Customers.MissingID
""")
            findings = validate_relationships(root)
            errors = [f for f in findings if f["severity"] == "error"]
            self.assertTrue(any("Customers.MissingID" in f["message"] for f in errors))

    def test_validate_reports_mismatched_relationship_data_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            findings = validate_relationships(root)
            errors = [f for f in findings if f["severity"] == "error"]
            self.assertTrue(any("data types do not match" in f["message"] for f in errors))

    def test_validate_allows_datepartonly_date_datetime_relationship(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn OrderDateTime
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDateTime
""")
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Date
\t\tdataType: date
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: Date
""")
            _write_relationships(root, """
relationship rel-1
\tjoinOnDateBehavior: datePartOnly
\tfromColumn: Sales.OrderDateTime
\ttoColumn: Date.Date
""")
            findings = validate_relationships(root)
            errors = [f for f in findings if f["severity"] == "error"]
            self.assertFalse(any("data types do not match" in f["message"] for f in errors))

    def test_validate_reports_parallel_active_relationship_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID

\tcolumn RegionID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: RegionID
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-3
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID

\tcolumn RegionID
\t\tdataType: string
\t\tlineageTag: c-4
\t\tsummarizeBy: none
\t\tsourceColumn: RegionID
""")
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            create_relationship(root, "Sales.RegionID", "Customers.RegionID")
            findings = validate_relationships(root)
            errors = [f for f in findings if f["severity"] == "error"]
            self.assertTrue(any("same table edge" in f["message"] for f in errors))

    def test_validate_reports_invalid_column_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sideways
\t\tsourceColumn: Amount
""")
            findings = validate_relationships(root)
            errors = [f for f in findings if f["severity"] == "error"]
            self.assertTrue(any('Invalid summarizeBy "sideways"' in f["message"] for f in errors))

    def test_validate_reports_missing_sort_by_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn MonthName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsortByColumn: MonthNumber
\t\tsummarizeBy: none
\t\tsourceColumn: MonthName
""")
            findings = validate_relationships(root)
            errors = [f for f in findings if f["severity"] == "error"]
            self.assertTrue(any('sortByColumn references missing column "MonthNumber"' in f["message"] for f in errors))

    def test_validate_reports_sort_by_cycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn MonthName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsortByColumn: MonthNumber
\t\tsummarizeBy: none
\t\tsourceColumn: MonthName

\tcolumn MonthNumber
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsortByColumn: MonthName
\t\tsummarizeBy: none
\t\tsourceColumn: MonthNumber
""")
            findings = validate_relationships(root)
            errors = [f for f in findings if f["severity"] == "error"]
            self.assertTrue(any("sortByColumn cycle detected" in f["message"] for f in errors))

    def test_validate_reports_invalid_date_table_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tdataCategory: Time

\tcolumn DateText
\t\tdataType: string
\t\tlineageTag: c-1
\t\tisKey
\t\tsummarizeBy: none
\t\tsourceColumn: DateText
""")
            findings = validate_relationships(root)
            errors = [f for f in findings if f["severity"] == "error"]
            self.assertTrue(any("must use a date or dateTime data type" in f["message"] for f in errors))

    def test_validate_json(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn CustID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustID
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustID
""")
            _write_relationships(root, """
relationship AutoDetected_abc-123
\tfromColumn: Sales.CustID
\ttoColumn: Customers.CustID
""")
            result = runner.invoke(app, [
                "model", "check", "--json",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            data = json.loads(result.stdout)
            self.assertIsInstance(data, list)
            self.assertTrue(len(data) > 0)


if __name__ == "__main__":
    unittest.main()
