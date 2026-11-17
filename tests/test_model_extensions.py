"""Tests for extended semantic model support (metadata, relationships, hierarchies, export)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml
from typer.testing import CliRunner

from pbi.cli import app
from pbi.model import (
    SemanticModel,
    create_calculated_column,
    create_source_column,
    create_hierarchy,
    create_measure,
    create_relationship,
    delete_calculated_column,
    delete_hierarchy,
    delete_measure,
    delete_relationship,
    mark_as_date_table,
    set_member_property,
    set_table_property,
    set_time_intelligence_enabled,
    set_relationship_property,
)
from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml
from tests.support import FIXTURES


def _make_project(root: Path) -> None:
    """Scaffold a minimal PBIP project."""
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


def _write_model(root: Path, content: str) -> Path:
    defn = root / "Sample.SemanticModel" / "definition"
    defn.mkdir(parents=True, exist_ok=True)
    path = defn / "model.tmdl"
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


# ── Phase 1: Column/Measure Metadata ────────────────────────────


class MetadataWriteTests(unittest.TestCase):
    def test_set_member_property_rejects_column_only_property_on_measure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1
""")
            with self.assertRaisesRegex(ValueError, 'not writable on measures'):
                set_member_property(root, "Sales.Revenue", "summarizeBy", "sum")

    def test_set_member_property_sort_by_spaced_calculated_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            path = _write_table(root, "Date.tmdl", """
table Date
\tcolumn 'Month Name'
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Month Name

\tcolumn DateValue
\t\tdataType: dateTime
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: DateValue
""")
            create_calculated_column(
                root,
                "Date",
                "Month Number",
                "MONTH([DateValue])",
                data_type="int64",
            )

            _, _, _, changed = set_member_property(
                root, "Date.Month Name", "sortByColumn", "Month Number",
            )
            self.assertTrue(changed)

            content = path.read_text(encoding="utf-8")
            self.assertIn("\tcolumn 'Month Number' = MONTH([DateValue])", content)
            self.assertIn("\t\tsortByColumn: 'Month Number'", content)

            model = SemanticModel.load(root)
            month_name = model.find_table("Date").find_column("Month Name")
            month_number = model.find_table("Date").find_column("Month Number")
            self.assertEqual(month_name.sort_by_column, "Month Number")
            self.assertEqual(month_number.kind, "calculatedColumn")

    def test_set_member_property_rejects_missing_sort_by_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn MonthName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: MonthName
""")
            with self.assertRaisesRegex(ValueError, 'Column "MonthNumber" not found'):
                set_member_property(root, "Date.MonthName", "sortByColumn", "MonthNumber")

    def test_set_member_property_rejects_sort_by_self(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn MonthName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: MonthName
""")
            with self.assertRaisesRegex(ValueError, "cannot sort by itself"):
                set_member_property(root, "Date.MonthName", "sortByColumn", "MonthName")

    def test_set_member_property_normalizes_desktop_summarize_by_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Amount
""")
            _, _, _, changed = set_member_property(root, "Sales.Amount", "summarizeBy", "DistinctCount")
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            amount = model.find_table("Sales").find_column("Amount")
            self.assertEqual(amount.summarize_by, "distinctCount")

    def test_set_member_property_rejects_invalid_summarize_by_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Amount
""")
            with self.assertRaisesRegex(ValueError, 'Invalid summarizeBy'):
                set_member_property(root, "Sales.Amount", "summarizeBy", "sideways")

    def test_set_member_property_normalizes_data_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Geo.tmdl", """
table Geo
\tcolumn CityName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: CityName
""")
            _, _, _, changed = set_member_property(root, "Geo.CityName", "dataCategory", "city")
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            city = model.find_table("Geo").find_column("CityName")
            self.assertEqual(city.data_category, "City")

    def test_set_table_property_rejects_invalid_data_category(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Date
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date
""")
            with self.assertRaisesRegex(ValueError, 'Invalid table dataCategory'):
                set_table_property(root, "Date", "dataCategory", "City")

    def test_create_calculated_column_normalizes_desktop_data_type(self):
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
            create_calculated_column(
                root,
                "Sales",
                "Amount Label",
                'FORMAT([Amount], "0")',
                data_type="Text",
            )

            model = SemanticModel.load(root)
            column = model.find_table("Sales").find_column("Amount Label")
            self.assertEqual(column.data_type, "string")

    def test_create_source_column_writes_source_bound_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "DimDate.tmdl", """
table DimDate
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Year
""")
            create_source_column(
                root,
                "DimDate",
                "Date",
                "Date",
                data_type="dateTime",
                format_string="MMM YYYY",
            )

            model = SemanticModel.load(root)
            column = model.find_table("DimDate").find_column("Date")
            self.assertEqual(column.data_type, "dateTime")
            self.assertEqual(column.source_column, "Date")
            self.assertEqual(column.format_string, "MMM YYYY")
            self.assertEqual(column.expression, "")
            self.assertEqual(column.kind, "column")  # not calculatedColumn

    def test_create_source_column_rejects_duplicate_name(self):
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
            with self.assertRaises(ValueError):
                create_source_column(
                    root,
                    "Sales",
                    "Amount",
                    "Amount",
                    data_type="int64",
                )

    def test_create_source_column_quotes_names_with_spaces(self):
        """Source column names with spaces must be single-quoted in TMDL and round-trip via the parser."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            path = _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Anchor
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Anchor
""")
            create_source_column(
                root,
                "Sales",
                "Order Date",
                "Order Date",
                data_type="dateTime",
            )

            content = path.read_text(encoding="utf-8")
            # TMDL identifier with spaces must be single-quoted on both the
            # declaration and the sourceColumn value.
            self.assertIn("\tcolumn 'Order Date'", content)
            self.assertIn("\t\tsourceColumn: 'Order Date'", content)

            # Parser must strip the quotes so the value round-trips cleanly.
            model = SemanticModel.load(root)
            column = model.find_table("Sales").find_column("Order Date")
            self.assertEqual(column.source_column, "Order Date")

    def test_create_source_column_escapes_embedded_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            path = _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Anchor
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Anchor
""")
            create_source_column(
                root,
                "Sales",
                "Foo Bar",
                "It's Bad",
                data_type="string",
            )

            content = path.read_text(encoding="utf-8")
            # Embedded single quote is doubled per TMDL escaping rules.
            self.assertIn("\t\tsourceColumn: 'It''s Bad'", content)

            model = SemanticModel.load(root)
            column = model.find_table("Sales").find_column("Foo Bar")
            self.assertEqual(column.source_column, "It's Bad")

    def test_create_source_column_rejects_control_characters(self):
        """A newline in source_column would break the TMDL block; reject it at the CLI."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Anchor
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Anchor
""")
            with self.assertRaisesRegex(ValueError, "control characters"):
                create_source_column(
                    root,
                    "Sales",
                    "OrderDate",
                    "Foo\nlineageTag: x",
                    data_type="dateTime",
                )

    def test_create_source_column_rejects_control_characters_in_format(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn Anchor
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Anchor
""")
            with self.assertRaisesRegex(ValueError, "control characters"):
                create_source_column(
                    root,
                    "Sales",
                    "OrderDate",
                    "OrderDate",
                    data_type="dateTime",
                    format_string="MMM\nlineageTag: x",
                )

    def test_create_calculated_column_rejects_control_characters_in_format(self):
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
            with self.assertRaisesRegex(ValueError, "control characters"):
                create_calculated_column(
                    root,
                    "Sales",
                    "Doubled",
                    "[Amount] * 2",
                    data_type="int64",
                    format_string="0\nlineageTag: x",
                )

    def test_create_calculated_column_rejects_invalid_data_type(self):
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
            with self.assertRaisesRegex(ValueError, 'Invalid dataType'):
                create_calculated_column(
                    root,
                    "Sales",
                    "Amount Label",
                    'FORMAT([Amount], "0")',
                    data_type="sideways",
                )

    def test_set_member_property_inserts_before_annotation_separator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            path = _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate

\t\tannotation SummarizationSetBy = Automatic
""")
            _, _, _, changed = set_member_property(
                root, "Sales.OrderDate", "displayFolder", "Dates",
            )
            self.assertTrue(changed)

            content = path.read_text(encoding="utf-8")
            self.assertIn(
                "\t\tsourceColumn: OrderDate\n\t\tdisplayFolder: Dates\n\n\t\tannotation SummarizationSetBy = Automatic",
                content,
            )

    def test_set_member_property_rejects_unknown_property(self):
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
            with self.assertRaises(ValueError, msg="not writable"):
                set_member_property(root, "Sales.OrderDate", "lineageTag", "x")

    def test_set_member_property_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tdisplayFolder: existing
\t\tlineageTag: m-1
""")
            _, _, _, changed = set_member_property(
                root, "Sales.Revenue", "displayFolder", "existing",
            )
            self.assertFalse(changed)

    def test_mark_as_date_table_sets_table_and_column_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 1
""")
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Date
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date

\tcolumn FiscalDate
\t\tdataType: dateTime
\t\tisKey
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: FiscalDate
""")
            table, column, changed = mark_as_date_table(root, "Date", "Date")
            self.assertEqual((table, column), ("Date", "Date"))
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            date_table = model.find_table("Date")
            self.assertEqual(date_table.data_category, "Time")
            self.assertEqual(date_table.date_table_column, "Date")
            self.assertTrue(date_table.find_column("Date").is_key)
            self.assertFalse(date_table.find_column("FiscalDate").is_key)

    def test_mark_as_date_table_rejects_calculated_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 1
""")
            _write_table(root, "DimDate.tmdl", """
table DimDate
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Year

\tcolumn Month
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: Month

\tcolumn Date = DATE(DimDate[Year], DimDate[Month], 1)
\t\tdataType: dateTime
\t\tformatString: MMM YYYY
\t\tlineageTag: c-3
\t\tsummarizeBy: none
""")
            with self.assertRaises(ValueError) as ctx:
                mark_as_date_table(root, "DimDate", "Date")
            self.assertIn("calculated column", str(ctx.exception))
            self.assertIn("sourceColumn", str(ctx.exception))

    def test_disabling_time_intelligence_removes_auto_date_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 1
\tref table Date
\tref table DateTableTemplate_abc
\tref table LocalDateTable_abc
""")
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Date
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date

\t\tvariation Variation
\t\t\tisDefault
\t\t\tdefaultHierarchy: LocalDateTable_abc.'Date Hierarchy'
""")
            auto_local = _write_table(root, "LocalDateTable_abc.tmdl", """
table LocalDateTable_abc
\tshowAsVariationsOnly
\tannotation __PBI_LocalDateTable = true
""")
            auto_template = _write_table(root, "DateTableTemplate_abc.tmdl", """
table DateTableTemplate_abc
\tisPrivate
\tannotation __PBI_TemplateDateTable = true
""")
            _write_relationships(root, """
relationship rel1
\tfromColumn: Date.Date
\ttoColumn: LocalDateTable_abc.Date
""")

            changed = set_time_intelligence_enabled(root, False)
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            self.assertFalse(model.time_intelligence_enabled)
            model_text = (root / "Sample.SemanticModel" / "definition" / "model.tmdl").read_text(encoding="utf-8")
            self.assertIn("__PBI_TimeIntelligenceEnabled = 0", model_text)
            self.assertNotIn("LocalDateTable_abc", model_text)
            self.assertNotIn("DateTableTemplate_abc", model_text)
            self.assertFalse(auto_local.exists())
            self.assertFalse(auto_template.exists())
            self.assertNotIn("variation Variation", (root / "Sample.SemanticModel" / "definition" / "tables" / "Date.tmdl").read_text(encoding="utf-8"))
            relationships_text = (root / "Sample.SemanticModel" / "definition" / "relationships.tmdl").read_text(encoding="utf-8")
            self.assertNotIn("LocalDateTable_abc", relationships_text)


class MetadataCLITests(unittest.TestCase):
    def test_column_set_cli(self):
        runner = CliRunner()
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
            result = runner.invoke(app, [
                "model", "column", "set", "Sales.OrderDate",
                "description=Order placement date",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            text = (root / "Sample.SemanticModel" / "definition" / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
            self.assertIn("\t/// Order placement date\n\tcolumn OrderDate", text)

    def test_measure_set_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1
""")
            result = runner.invoke(app, [
                "model", "measure", "set", "Sales.Revenue",
                "displayFolder=KPIs",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("displayFolder", result.stdout)

    def test_column_get_shows_metadata(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tdescription: When placed
\t\tdisplayFolder: Dates
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
""")
            result = runner.invoke(app, [
                "model", "column", "get", "Sales.OrderDate",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("When placed", result.stdout)
            self.assertIn("Dates", result.stdout)

    def test_measure_get_shows_metadata(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tdescription: Total revenue
\t\tdisplayFolder: KPIs
\t\tlineageTag: m-1
""")
            result = runner.invoke(app, [
                "model", "measure", "get", "Sales", "Revenue",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Total revenue", result.stdout)
            self.assertIn("KPIs", result.stdout)

    def test_table_set_date_table_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 1
""")
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Date
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date
""")
            result = runner.invoke(app, [
                "model", "table", "set", "Date",
                "dateTable=Date",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("dateTable", result.stdout)

    def test_model_set_time_intelligence_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 1
""")
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Date
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date
""")
            result = runner.invoke(app, [
                "model", "set",
                "timeIntelligence=off",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("timeIntelligence", result.stdout)


# ── Phase 2: Relationship CRUD ──────────────────────────────────


class RelationshipCRUDTests(unittest.TestCase):
    def test_create_duplicate_relationship_fails(self):
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
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            with self.assertRaises(ValueError, msg="already exists"):
                create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")

    def test_set_relationship_property_accepts_one_sided_cardinality(self):
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
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            # Desktop writes one-to-one as `fromCardinality: one` alone (toCardinality defaults to one).
            _, _, changed = set_relationship_property(
                root, "Sales.CustomerID", "Customers.CustomerID", "fromCardinality", "one",
            )
            self.assertTrue(changed)
            rel = SemanticModel.load(root).relationships[0]
            self.assertEqual(rel.properties.get("fromCardinality"), "one")
            self.assertNotIn("toCardinality", rel.properties)

            # one -> many is the wrong way round, even when only one side is written.
            with self.assertRaisesRegex(ValueError, "Invalid cardinality orientation"):
                set_relationship_property(
                    root, "Sales.CustomerID", "Customers.CustomerID", "toCardinality", "many",
                )

    def test_validate_relationship_properties_accepts_desktop_one_sided_forms(self):
        from pbi.modeling.writes_relationships import validate_relationship_properties

        validate_relationship_properties({"fromCardinality": "one"})  # one-to-one
        validate_relationship_properties({"toCardinality": "many"})  # many-to-many
        validate_relationship_properties({"toCardinality": "many", "crossFilteringBehavior": "bothDirections"})
        validate_relationship_properties({"fromCardinality": "many", "toCardinality": "one"})
        with self.assertRaisesRegex(ValueError, "Invalid cardinality orientation"):
            validate_relationship_properties({"fromCardinality": "one", "toCardinality": "many"})
        with self.assertRaisesRegex(ValueError, "cannot use crossFilteringBehavior=oneDirection"):
            validate_relationship_properties({"fromCardinality": "one", "crossFilteringBehavior": "oneDirection"})

    def test_model_check_accepts_desktop_one_sided_cardinality(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            for name in ("Sales", "Customers", "Profiles", "Tags"):
                _write_table(root, f"{name}.tmdl", f"""
table {name}
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: {name}-1
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            # Exactly as Desktop saves them (report-04 relationships.tmdl).
            _write_relationships(root, """
relationship r-one-one
\tfromCardinality: one
\tcrossFilteringBehavior: bothDirections
\tfromColumn: Profiles.CustomerID
\ttoColumn: Customers.CustomerID

relationship r-many-many
\ttoCardinality: many
\tfromColumn: Tags.CustomerID
\ttoColumn: Customers.CustomerID

relationship r-default
\tfromColumn: Sales.CustomerID
\ttoColumn: Customers.CustomerID
""")
            from pbi.model import validate_relationships

            errors = [f for f in validate_relationships(root) if f["severity"] == "error"]
            self.assertEqual(errors, [])

    def test_create_relationship_rejects_invalid_cross_filter_value(self):
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
            with self.assertRaisesRegex(ValueError, "Invalid crossFilteringBehavior"):
                create_relationship(
                    root,
                    "Sales.CustomerID",
                    "Customers.CustomerID",
                    properties={"crossFilteringBehavior": "sideways"},
                )

    def test_create_relationship_normalizes_desktop_style_values_and_aliases(self):
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
            create_relationship(
                root,
                "Sales.CustomerID",
                "Customers.CustomerID",
                properties={
                    "CrossFilteringBehavior": "BothDirections",
                    "referentialIntegrity": "TRUE",
                },
            )

            model = SemanticModel.load(root)
            rel = model.relationships[0]
            self.assertEqual(rel.properties.get("crossFilteringBehavior"), "bothDirections")
            self.assertEqual(rel.properties.get("relyOnReferentialIntegrity"), "true")

    def test_create_relationship_rejects_unknown_property(self):
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
            with self.assertRaisesRegex(ValueError, "Unknown relationship property"):
                create_relationship(
                    root,
                    "Sales.CustomerID",
                    "Customers.CustomerID",
                    properties={"sideways": "true"},
                )

    def test_create_relationship_rejects_security_filter_without_bidirectional_cross_filter(self):
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
            with self.assertRaisesRegex(ValueError, "securityFilteringBehavior=bothDirections requires bidirectional cross filtering"):
                create_relationship(
                    root,
                    "Sales.CustomerID",
                    "Customers.CustomerID",
                    properties={"securityFilteringBehavior": "bothDirections"},
                )

    def test_delete_nonexistent_relationship_fails(self):
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
            with self.assertRaises(ValueError):
                delete_relationship(root, "Sales.CustomerID", "Customers.CustomerID")


class RelationshipCLITests(unittest.TestCase):
    def test_relationship_create_cli(self):
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
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            result = runner.invoke(app, [
                "model", "relationship", "create",
                "Sales.CustomerID", "Customers.CustomerID",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Created relationship", result.stdout)

    def test_relationship_delete_cli(self):
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
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            result = runner.invoke(app, [
                "model", "relationship", "delete",
                "Sales.CustomerID", "Customers.CustomerID",
                "--force",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Deleted relationship", result.stdout)
            self.assertEqual(SemanticModel.load(root).relationships, [])

    def test_relationship_set_cli(self):
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
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            result = runner.invoke(app, [
                "model", "relationship", "set",
                "Sales.CustomerID", "Customers.CustomerID",
                "crossFilteringBehavior=bothDirections",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("crossFilteringBehavior", result.stdout)

    def test_relationships_list_shows_cross_filter(self):
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
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            create_relationship(
                root, "Sales.CustomerID", "Customers.CustomerID",
                properties={"crossFilteringBehavior": "bothDirections"},
            )
            result = runner.invoke(app, [
                "model", "relationship", "list",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("bothDirections", result.stdout)

    def test_relationship_set_cli_rejects_invalid_semantics(self):
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
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            result = runner.invoke(app, [
                "model", "relationship", "set",
                "Sales.CustomerID", "Customers.CustomerID",
                "crossFilteringBehavior=sideways",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("Invalid crossFilteringBehavior", result.stdout)

    def test_relationship_set_cli_rejects_unknown_property(self):
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
""")
            _write_table(root, "Customers.tmdl", """
table Customers
\tcolumn CustomerID
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: CustomerID
""")
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            result = runner.invoke(app, [
                "model", "relationship", "set",
                "Sales.CustomerID", "Customers.CustomerID",
                "sideways=true",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("Unknown relationship property", result.stdout)


# ── Phase 3: Hierarchy CRUD ─────────────────────────────────────


class HierarchyCRUDTests(unittest.TestCase):
    def test_create_hierarchy_with_spaced_level_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            path = _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year

\tcolumn 'Fiscal Month'
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: Fiscal Month
""")
            table, name, created = create_hierarchy(
                root, "Date", "Fiscal Calendar", ["Year", "Fiscal Month"],
            )
            self.assertTrue(created)
            self.assertEqual((table, name), ("Date", "Fiscal Calendar"))

            content = path.read_text(encoding="utf-8")
            self.assertIn("\thierarchy 'Fiscal Calendar'", content)
            self.assertIn("\t\tlevel 'Fiscal Month'", content)
            self.assertIn("\t\t\tcolumn: 'Fiscal Month'", content)

            model = SemanticModel.load(root)
            hierarchy = model.find_table("Date").find_hierarchy("Fiscal Calendar")
            self.assertEqual([level.column for level in hierarchy.levels], ["Year", "Fiscal Month"])

    def test_create_hierarchy_validates_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year
""")
            with self.assertRaises(ValueError):
                create_hierarchy(root, "Date", "Bad", ["Year", "NoSuchColumn"])

    def test_create_hierarchy_rejects_empty_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year
""")
            with self.assertRaises(ValueError, msg="at least one"):
                create_hierarchy(root, "Date", "Empty", [])

    def test_create_duplicate_hierarchy_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year
""")
            create_hierarchy(root, "Date", "YearOnly", ["Year"])
            with self.assertRaises(ValueError, msg="already exists"):
                create_hierarchy(root, "Date", "YearOnly", ["Year"])


class HierarchyCLITests(unittest.TestCase):
    def test_hierarchy_create_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year

\tcolumn Month
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: Month
""")
            result = runner.invoke(app, [
                "model", "hierarchy", "create", "Date", "Calendar",
                "Year", "Month",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Created hierarchy", result.stdout)
            self.assertIn("2 levels", result.stdout)

    def test_hierarchy_list_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year

\tcolumn Month
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: Month
""")
            create_hierarchy(root, "Date", "Calendar", ["Year", "Month"])
            result = runner.invoke(app, [
                "model", "hierarchy", "list", "Date",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Calendar", result.stdout)
            self.assertIn("Year", result.stdout)

    def test_hierarchy_delete_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year
""")
            create_hierarchy(root, "Date", "YearOnly", ["Year"])
            result = runner.invoke(app, [
                "model", "hierarchy", "delete", "Date", "YearOnly",
                "--force",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Deleted hierarchy", result.stdout)

    def test_hierarchy_list_empty(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year
""")
            result = runner.invoke(app, [
                "model", "hierarchy", "list", "Date",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("No hierarchies", result.stdout)


# ── Phase 4: Model Export ───────────────────────────────────────


class DescriptionPreservationTests(unittest.TestCase):
    """`///` descriptions stay with their own object on every block edit (#56)."""

    SALES = """
/// Sales facts
table Sales
\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount

\t/// Doubled amount
\tcolumn Margin = Sales[Amount] * 2
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum

\t/// Units sold
\tmeasure 'Total Quantity' = SUM(Sales[Amount])
\t\tlineageTag: m-1

\t/// Number of orders
\t/// counted "once" per order & line
\tmeasure 'Order Count' = COUNTROWS(Sales)
\t\tlineageTag: m-2

\t/// Drill path
\thierarchy Path
\t\tlineageTag: h-1

\t\tlevel Amount
\t\t\tlineageTag: l-1
\t\t\tcolumn: Amount
"""

    def _project(self, tmp: str) -> Path:
        root = Path(tmp)
        _make_project(root)
        _write_table(root, "Sales.tmdl", self.SALES)
        return root

    def _text(self, root: Path) -> str:
        return (root / "Sample.SemanticModel" / "definition" / "tables" / "Sales.tmdl").read_text(encoding="utf-8")

    def test_delete_measure_takes_its_own_description_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            delete_measure(root, "Sales", "Total Quantity")
            text = self._text(root)
            self.assertNotIn("Units sold", text)
            self.assertIn(
                "\tsummarizeBy: sum\n\n\t/// Number of orders\n\t/// counted \"once\" per order & line\n"
                "\tmeasure 'Order Count'",
                text,
            )

    def test_delete_measure_keeps_next_objects_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            delete_measure(root, "Sales", "Order Count")
            text = self._text(root)
            self.assertNotIn("Number of orders", text)
            self.assertIn("\t/// Units sold\n\tmeasure 'Total Quantity'", text)
            self.assertIn("\t\tlineageTag: m-1\n\n\t/// Drill path\n\thierarchy Path", text)

    def test_delete_calculated_column_keeps_next_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            delete_calculated_column(root, "Sales", "Margin")
            text = self._text(root)
            self.assertNotIn("Doubled amount", text)
            self.assertIn("\t\tsourceColumn: Amount\n\n\t/// Units sold\n\tmeasure 'Total Quantity'", text)

    def test_delete_hierarchy_takes_its_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            delete_hierarchy(root, "Sales", "Path")
            text = self._text(root)
            self.assertNotIn("Drill path", text)
            self.assertTrue(text.endswith("\t\tlineageTag: m-2\n"), repr(text[-60:]))

    def test_set_property_inserts_inside_own_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            set_member_property(root, "Sales.Total Quantity", "displayFolder", "Counts")
            text = self._text(root)
            self.assertIn(
                "\tmeasure 'Total Quantity' = SUM(Sales[Amount])\n\t\tlineageTag: m-1\n\t\tdisplayFolder: Counts\n"
                "\n\t/// Number of orders\n",
                text,
            )

    def test_create_measure_lands_before_next_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._project(tmp)
            create_measure(root, "Sales", "Avg Amount", "AVERAGE(Sales[Amount])")
            text = self._text(root)
            new_at = text.index("measure 'Avg Amount'")
            self.assertLess(text.index("\tmeasure 'Order Count'"), new_at)
            self.assertLess(new_at, text.index("/// Drill path"))
            self.assertIn("\t/// Drill path\n\thierarchy Path", text)


class ModelExportTests(unittest.TestCase):
    def test_export_omits_empty_sections(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tcolumn SaleID
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: SaleID
""")
            yaml_str = export_model_yaml(root)
            spec = yaml.safe_load(yaml_str)
            # No measures, no metadata columns, no relationships, no hierarchies
            self.assertNotIn("measures", spec or {})
            self.assertNotIn("relationships", spec or {})
            self.assertNotIn("hierarchies", spec or {})

    def test_export_cli(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1
""")
            result = runner.invoke(app, [
                "model", "export",
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            spec = yaml.safe_load(result.stdout)
            self.assertIn("measures", spec)


def test_export_and_parser_carry_desktop_model_metadata() -> None:
    """Named facts from report-04's Desktop-saved TMDL reach `model export`.

    The harness's export -> apply no-op can't see `model export` or the parser
    dropping content (#122), so this checks the export against the fixture's TMDL.
    """
    root = FIXTURES["report-04-desktop-shapes"]
    model = SemanticModel.load(root)
    spec = yaml.safe_load(export_model_yaml(root, model=model))

    assert spec["model"]["timeIntelligence"] is False
    assert spec["model"]["annotations"]["PBI_ProTooling"] == '["DevMode"]'
    assert spec["tables"]["Date"] == {"dataCategory": "Time", "dateTable": "Date"}

    task_count = next(m for m in spec["measures"]["Measures Table"] if m["name"] == "Task Count")
    assert task_count == {
        "name": "Task Count",
        "expression": "COUNTROWS ( Task )",
        "format": "#,0",
        "displayFolder": "Counts",
        "description": "Number of tasks in the current filter context.\nCounts every Task row, including blocked tasks.",
    }
    assert spec["columns"]["Date"]["MonthName"] == {"sortByColumn": "MonthNumber"}
    assert spec["columns"]["Person"]["Country"] == {"dataCategory": "Country"}
    assert spec["columns"]["Task"]["EstimateHours"] == {"summarizeBy": "sum", "displayFolder": "Effort"}

    relationships = spec["relationships"]
    assert len(relationships) == 12
    assert {"from": "Task.DueDate", "to": "Date.Date", "isActive": "false"} in relationships
    assert {
        "from": "Q/A Notes.ProjectKey",
        "to": "Project.ProjectKey",
        "crossFilteringBehavior": "bothDirections",
        "fromCardinality": "one",
    } in relationships

    assert spec["hierarchies"]["Date"] == [{
        "name": "Calendar",
        "levels": ["Year", "Quarter", "MonthName", "Date"],
        "description": "Year > Quarter > Month > Date drill path.",
    }]
    date_partition = spec["partitions"]["Date"][0]
    assert (date_partition["name"], date_partition["sourceType"], date_partition["mode"]) == ("Date", "m", "import")

    # What the parser reads but the export leaves out.
    date = model.find_table("Date")
    assert date.find_column("Date").is_key
    calendar = date.find_hierarchy("Calendar")
    assert calendar.lineage_tag == "7c177391-bd7d-46fe-8cfd-4b51a987f348"
    assert [(level.name, level.lineage_tag) for level in calendar.levels[:1]] == [
        ("Year", "b9ae94c1-d2f3-4e33-8f4d-9ff511b935de"),
    ]


# ── Model Apply Extensions ──────────────────────────────────────


class ModelApplyExtensionTests(unittest.TestCase):
    def test_apply_model_and_table_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 1
""")
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Date
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date
""")
            yaml_content = yaml.safe_dump({
                "model": {"timeIntelligence": False},
                "tables": {
                    "Date": {
                        "dataCategory": "Time",
                        "dateTable": "Date",
                    },
                },
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content)
            self.assertTrue(result.has_changes)
            self.assertIn("Model", result.model_updated)
            self.assertIn("Date", result.tables_updated)

            model = SemanticModel.load(root)
            self.assertFalse(model.time_intelligence_enabled)
            date_table = model.find_table("Date")
            self.assertEqual(date_table.data_category, "Time")
            self.assertEqual(date_table.date_table_column, "Date")

    def test_apply_measure_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1
""")
            yaml_content = yaml.safe_dump({
                "measures": {
                    "Sales": [{
                        "name": "Revenue",
                        "displayFolder": "KPIs",
                    }],
                },
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content)
            self.assertTrue(result.has_changes)
            self.assertIn("Sales.Revenue", result.measures_updated)
            self.assertEqual(result.errors, [])

            model = SemanticModel.load(root)
            m = model.find_table("Sales").find_measure("Revenue")
            self.assertEqual(m.display_folder, "KPIs")

    def test_apply_measure_description_writes_doc_comment(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1
""")
            yaml_content = yaml.safe_dump({
                "measures": {
                    "Sales": [{
                        "name": "Revenue",
                        "description": "Total revenue",
                        "displayFolder": "KPIs",
                    }],
                },
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content)
            self.assertIn("Sales.Revenue", result.measures_updated)
            self.assertEqual(result.errors, [])

            model = SemanticModel.load(root)
            m = model.find_table("Sales").find_measure("Revenue")
            self.assertEqual(m.display_folder, "KPIs")
            self.assertEqual(m.description, "Total revenue")

    def test_apply_column_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn MonthName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: MonthName

\tcolumn MonthNumber
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: MonthNumber
""")
            yaml_content = yaml.safe_dump({
                "columns": {
                    "Date": {
                        "MonthName": {
                            "sortByColumn": "MonthNumber",
                            "displayFolder": "Calendar",
                            "summarizeBy": "none",
                        },
                    },
                },
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content)
            self.assertTrue(result.has_changes)
            self.assertIn("Date.MonthName", result.columns_updated)

            model = SemanticModel.load(root)
            c = model.find_table("Date").find_column("MonthName")
            self.assertEqual(c.sort_by_column, "MonthNumber")
            self.assertEqual(c.display_folder, "Calendar")
            self.assertEqual(c.summarize_by, "none")

    def test_apply_relationships(self):
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
            yaml_content = yaml.safe_dump({
                "relationships": [{
                    "from": "Sales.CustomerID",
                    "to": "Customers.CustomerID",
                    "crossFilteringBehavior": "bothDirections",
                }],
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content)
            self.assertTrue(result.has_changes)
            self.assertEqual(len(result.relationships_created), 1)

            model = SemanticModel.load(root)
            self.assertEqual(len(model.relationships), 1)

    def test_apply_relationships_updates_existing(self):
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
            create_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            yaml_content = yaml.safe_dump({
                "relationships": [{
                    "from": "Sales.CustomerID",
                    "to": "Customers.CustomerID",
                    "crossFilteringBehavior": "bothDirections",
                }],
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content)
            self.assertTrue(result.has_changes)
            self.assertEqual(len(result.relationships_updated), 1)

    def test_apply_hierarchies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year

\tcolumn Month
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: Month
""")
            yaml_content = yaml.safe_dump({
                "hierarchies": {
                    "Date": [{
                        "name": "Calendar",
                        "levels": ["Year", "Month"],
                    }],
                },
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content)
            self.assertTrue(result.has_changes)
            self.assertEqual(len(result.hierarchies_created), 1)

            model = SemanticModel.load(root)
            h = model.find_table("Date").hierarchies[0]
            self.assertEqual(h.name, "Calendar")
            self.assertEqual(len(h.levels), 2)

    def test_apply_hierarchies_updates_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn Year
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Year

\tcolumn Month
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: Month

\tcolumn Day
\t\tdataType: int64
\t\tlineageTag: c-3
\t\tsummarizeBy: sum
\t\tsourceColumn: Day
""")
            create_hierarchy(root, "Date", "Calendar", ["Year", "Month"])
            yaml_content = yaml.safe_dump({
                "hierarchies": {
                    "Date": [{
                        "name": "Calendar",
                        "levels": ["Year", "Month", "Day"],
                    }],
                },
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content)
            self.assertTrue(result.has_changes)
            self.assertEqual(len(result.hierarchies_updated), 1)

            model = SemanticModel.load(root)
            h = model.find_table("Date").hierarchies[0]
            self.assertEqual(len(h.levels), 3)

    def test_apply_known_keys_validation(self):
        result = apply_model_yaml(Path("/tmp"), "foo: bar\n")
        self.assertTrue(result.errors)

    def test_apply_dry_run(self):
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
            yaml_content = yaml.safe_dump({
                "relationships": [{
                    "from": "Sales.CustomerID",
                    "to": "Customers.CustomerID",
                }],
            }, sort_keys=False)
            result = apply_model_yaml(root, yaml_content, dry_run=True)
            self.assertTrue(result.has_changes)
            # Verify nothing was actually written
            rel_path = root / "Sample.SemanticModel" / "definition" / "relationships.tmdl"
            self.assertFalse(rel_path.exists())


if __name__ == "__main__":
    unittest.main()
