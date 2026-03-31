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
    create_hierarchy,
    create_relationship,
    delete_hierarchy,
    delete_relationship,
    mark_as_date_table,
    set_member_property,
    set_time_intelligence_enabled,
    set_relationship_property,
)
from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml


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
    def test_set_member_property_rejects_description(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1
""")
            with self.assertRaisesRegex(ValueError, "not supported by Power BI TMDL"):
                set_member_property(
                    root, "Sales.Revenue", "description", "Total revenue from sales",
                )

    def test_set_member_property_display_folder_on_column(self):
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
            _, _, _, changed = set_member_property(
                root, "Sales.OrderDate", "displayFolder", "Dates",
            )
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            c = model.find_table("Sales").find_column("OrderDate")
            self.assertEqual(c.display_folder, "Dates")

    def test_set_member_property_sort_by_column(self):
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
\t\tsummarizeBy: none
\t\tsourceColumn: MonthNumber
""")
            _, _, _, changed = set_member_property(
                root, "Date.MonthName", "sortByColumn", "MonthNumber",
            )
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            c = model.find_table("Date").find_column("MonthName")
            self.assertEqual(c.sort_by_column, "MonthNumber")

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

    def test_parser_reads_metadata_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 1
""")
            _write_table(root, "Sales.tmdl", """
table Sales
\tdataCategory: Time
\tmeasure Revenue = SUM(Sales[Amount])
\t\tdescription: Total revenue
\t\tdisplayFolder: KPIs
\t\tlineageTag: m-1

\tcolumn OrderDate
\t\tdataType: dateTime
\t\tisKey
\t\tdescription: When the order was placed
\t\tdisplayFolder: Dates
\t\tsortByColumn: OrderDateKey
\t\tdataCategory: DateOfBirth
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
""")
            model = SemanticModel.load(root)
            self.assertTrue(model.time_intelligence_enabled)
            t = model.find_table("Sales")
            self.assertEqual(t.data_category, "Time")
            self.assertEqual(t.date_table_column, "OrderDate")
            m = t.find_measure("Revenue")
            self.assertEqual(m.description, "Total revenue")
            self.assertEqual(m.display_folder, "KPIs")

            c = t.find_column("OrderDate")
            self.assertEqual(c.description, "When the order was placed")
            self.assertEqual(c.display_folder, "Dates")
            self.assertEqual(c.sort_by_column, "OrderDateKey")
            self.assertEqual(c.data_category, "DateOfBirth")
            self.assertTrue(c.is_key)

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
            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("not supported by Power BI TMDL", result.stdout)

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
    def test_create_relationship(self):
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
            rel_id, from_ref, to_ref = create_relationship(
                root, "Sales.CustomerID", "Customers.CustomerID",
            )
            self.assertEqual(from_ref, "Sales.CustomerID")
            self.assertEqual(to_ref, "Customers.CustomerID")

            model = SemanticModel.load(root)
            self.assertEqual(len(model.relationships), 1)
            rel = model.relationships[0]
            self.assertEqual(rel.from_table, "Sales")
            self.assertEqual(rel.to_column, "CustomerID")

    def test_create_relationship_with_properties(self):
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
            model = SemanticModel.load(root)
            rel = model.relationships[0]
            self.assertEqual(rel.properties.get("crossFilteringBehavior"), "bothDirections")

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

    def test_delete_relationship(self):
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
            from_ref, to_ref = delete_relationship(root, "Sales.CustomerID", "Customers.CustomerID")
            self.assertEqual(from_ref, "Sales.CustomerID")

            model = SemanticModel.load(root)
            self.assertEqual(len(model.relationships), 0)

    def test_set_relationship_property(self):
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
            _, _, changed = set_relationship_property(
                root, "Sales.CustomerID", "Customers.CustomerID",
                "crossFilteringBehavior", "bothDirections",
            )
            self.assertTrue(changed)

            model = SemanticModel.load(root)
            rel = model.relationships[0]
            self.assertEqual(rel.properties.get("crossFilteringBehavior"), "bothDirections")

    def test_set_relationship_property_rejects_invalid_cardinality_orientation(self):
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
            with self.assertRaisesRegex(ValueError, "Set both fromCardinality and toCardinality together"):
                set_relationship_property(
                    root,
                    "Sales.CustomerID",
                    "Customers.CustomerID",
                    "fromCardinality",
                    "one",
                )

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


# ── Phase 3: Hierarchy CRUD ─────────────────────────────────────


class HierarchyCRUDTests(unittest.TestCase):
    def test_create_hierarchy(self):
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

\tcolumn MonthNumber
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: MonthNumber

\tcolumn DayOfMonth
\t\tdataType: int64
\t\tlineageTag: c-3
\t\tsummarizeBy: sum
\t\tsourceColumn: DayOfMonth
""")
            table, name, created = create_hierarchy(
                root, "Date", "Calendar", ["Year", "MonthNumber", "DayOfMonth"],
            )
            self.assertTrue(created)
            self.assertEqual(name, "Calendar")

            model = SemanticModel.load(root)
            t = model.find_table("Date")
            self.assertEqual(len(t.hierarchies), 1)
            h = t.hierarchies[0]
            self.assertEqual(h.name, "Calendar")
            self.assertEqual(len(h.levels), 3)
            self.assertEqual(h.levels[0].column, "Year")
            self.assertEqual(h.levels[1].column, "MonthNumber")
            self.assertEqual(h.levels[2].column, "DayOfMonth")

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

    def test_delete_hierarchy(self):
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
            table, name, deleted = delete_hierarchy(root, "Date", "YearOnly")
            self.assertTrue(deleted)

            model = SemanticModel.load(root)
            self.assertEqual(len(model.find_table("Date").hierarchies), 0)

    def test_parser_reads_hierarchies(self):
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

\thierarchy Calendar
\t\tlineageTag: h-1

\t\tlevel Year
\t\t\tlineageTag: hl-1
\t\t\tcolumn: Year

\t\tlevel Month
\t\t\tlineageTag: hl-2
\t\t\tcolumn: Month
""")
            model = SemanticModel.load(root)
            t = model.find_table("Date")
            self.assertEqual(len(t.hierarchies), 1)
            h = t.hierarchies[0]
            self.assertEqual(h.name, "Calendar")
            self.assertEqual(h.lineage_tag, "h-1")
            self.assertEqual(len(h.levels), 2)
            self.assertEqual(h.levels[0].column, "Year")
            self.assertEqual(h.levels[1].column, "Month")
            self.assertEqual(h.levels[0].lineage_tag, "hl-1")


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


class ModelExportTests(unittest.TestCase):
    def test_export_model_and_table_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 0
""")
            _write_table(root, "Date.tmdl", """
table Date
\tdataCategory: Time
\tcolumn Date
\t\tdataType: dateTime
\t\tisKey
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date
""")
            yaml_str = export_model_yaml(root)
            spec = yaml.safe_load(yaml_str)
            self.assertFalse(spec["model"]["timeIntelligence"])
            self.assertEqual(spec["tables"]["Date"]["dataCategory"], "Time")
            self.assertEqual(spec["tables"]["Date"]["dateTable"], "Date")

    def test_export_measures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tformatString: 0
\t\tdescription: Total revenue
\t\tdisplayFolder: KPIs
\t\tlineageTag: m-1
""")
            yaml_str = export_model_yaml(root)
            spec = yaml.safe_load(yaml_str)
            self.assertIn("measures", spec)
            self.assertIn("Sales", spec["measures"])
            m = spec["measures"]["Sales"][0]
            self.assertEqual(m["name"], "Revenue")
            self.assertEqual(m["format"], "0")
            self.assertNotIn("description", m)
            self.assertEqual(m["displayFolder"], "KPIs")

    def test_export_columns_with_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Date.tmdl", """
table Date
\tcolumn MonthName
\t\tdataType: string
\t\tsortByColumn: MonthNumber
\t\tdisplayFolder: Calendar
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: MonthName

\tcolumn MonthNumber
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: MonthNumber
""")
            yaml_str = export_model_yaml(root)
            spec = yaml.safe_load(yaml_str)
            self.assertIn("columns", spec)
            self.assertIn("Date", spec["columns"])
            mn = spec["columns"]["Date"]["MonthName"]
            self.assertEqual(mn["sortByColumn"], "MonthNumber")
            self.assertEqual(mn["displayFolder"], "Calendar")

    def test_export_relationships(self):
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
relationship abc-123
\tfromColumn: Sales.CustomerID
\ttoColumn: Customers.CustomerID
""")
            yaml_str = export_model_yaml(root)
            spec = yaml.safe_load(yaml_str)
            self.assertIn("relationships", spec)
            rel = spec["relationships"][0]
            self.assertEqual(rel["from"], "Sales.CustomerID")
            self.assertEqual(rel["to"], "Customers.CustomerID")

    def test_export_hierarchies(self):
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

\thierarchy Calendar
\t\tlineageTag: h-1

\t\tlevel Year
\t\t\tlineageTag: hl-1
\t\t\tcolumn: Year

\t\tlevel Month
\t\t\tlineageTag: hl-2
\t\t\tcolumn: Month
""")
            yaml_str = export_model_yaml(root)
            spec = yaml.safe_load(yaml_str)
            self.assertIn("hierarchies", spec)
            self.assertIn("Date", spec["hierarchies"])
            h = spec["hierarchies"]["Date"][0]
            self.assertEqual(h["name"], "Calendar")
            self.assertEqual(h["levels"], ["Year", "Month"])

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

    def test_export_to_file(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tlineageTag: m-1
""")
            out_path = root / "model.yaml"
            result = runner.invoke(app, [
                "model", "export", "-o", str(out_path),
                "--project", str(root / "Sample.pbip"),
            ])
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertTrue(out_path.exists())
            spec = yaml.safe_load(out_path.read_text())
            self.assertIn("measures", spec)


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

    def test_apply_measure_description_reports_clear_error(self):
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
            self.assertEqual(
                result.errors,
                ['measures.Sales.Revenue.description: Property "description" is not supported by Power BI TMDL for columns or measures.'],
            )

            model = SemanticModel.load(root)
            m = model.find_table("Sales").find_measure("Revenue")
            self.assertEqual(m.display_folder, "KPIs")

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


# ── Round-trip test ─────────────────────────────────────────────


class RoundtripTests(unittest.TestCase):
    def test_export_apply_roundtrip_model_and_table_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_model(root, """
model Model
\tannotation __PBI_TimeIntelligenceEnabled = 0
""")
            _write_table(root, "Date.tmdl", """
table Date
\tdataCategory: Time
\tcolumn Date
\t\tdataType: dateTime
\t\tisKey
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: Date
""")
            yaml_str = export_model_yaml(root)
            result = apply_model_yaml(root, yaml_str)
            self.assertFalse(result.has_changes)

    def test_export_apply_roundtrip_measures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_project(root)
            _write_table(root, "Sales.tmdl", """
table Sales
\tmeasure Revenue = SUM(Sales[Amount])
\t\tformatString: 0
\t\tdescription: Total revenue
\t\tlineageTag: m-1

\tcolumn Amount
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Amount
""")
            yaml_str = export_model_yaml(root)
            result = apply_model_yaml(root, yaml_str)
            self.assertFalse(result.has_changes)

    def test_export_apply_roundtrip_hierarchies(self):
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
            yaml_str = export_model_yaml(root)
            result = apply_model_yaml(root, yaml_str)
            self.assertFalse(result.has_changes)


if __name__ == "__main__":
    unittest.main()
