from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pbi.bookmarks import create_bookmark, update_bookmark_visuals
from pbi.filters import (
    TupleField,
    add_advanced_filter,
    add_exclude_filter,
    add_include_filter,
    add_relative_date_filter,
    add_relative_time_filter,
    add_topn_filter,
    add_tuple_filter,
    filter_field_refs,
    parse_filter,
)
from pbi.project import Project
from pbi.properties import PAGE_PROPERTIES, set_property
from pbi.schema_refs import REPORT_SCHEMA
from pbi.themes import apply_theme, remove_theme


class BookmarkSchemaShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.definition_folder = Path(self.tmp.name) / "definition"
        self.definition_folder.mkdir(parents=True)
        self.project = SimpleNamespace(definition_folder=self.definition_folder)
        self.page = SimpleNamespace(name="PageOne")
        self.visuals = [
            SimpleNamespace(name="visA"),
            SimpleNamespace(name="visB"),
        ]

    def _load_bookmark(self, bookmark_id: str) -> dict:
        path = self.definition_folder / "bookmarks" / f"{bookmark_id}.bookmark.json"
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def test_create_bookmark_uses_schema_display_node(self) -> None:
        data = create_bookmark(
            self.project,
            "Bookmark A",
            self.page,
            self.visuals,
            hidden_visuals=["visA"],
        )

        bookmark = self._load_bookmark(data["name"])
        visual_state = (
            bookmark["explorationState"]["sections"]["PageOne"]["visualContainers"]["visA"]
        )

        self.assertEqual(visual_state["singleVisual"]["display"]["mode"], "hidden")
        self.assertNotIn("displayState", visual_state["singleVisual"])

    def test_update_bookmark_keeps_required_visual_containers(self) -> None:
        data = create_bookmark(self.project, "Bookmark B", self.page, self.visuals)
        update_bookmark_visuals(self.project, data["name"], hidden_visuals=["visB"])
        update_bookmark_visuals(self.project, data["name"], visible_visuals=["visB"])

        bookmark = self._load_bookmark(data["name"])
        section = bookmark["explorationState"]["sections"]["PageOne"]

        self.assertIn("visualContainers", section)
        self.assertEqual(section["visualContainers"], {})


class ThemeSchemaShapeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.report_folder = self.root / "Sample.Report"
        self.definition_folder = self.report_folder / "definition"
        self.definition_folder.mkdir(parents=True)
        self.project = Project(
            root=self.root,
            pbip_file=self.root / "sample.pbip",
            report_folder=self.report_folder,
            definition_folder=self.definition_folder,
        )

    def test_apply_theme_normalizes_resource_packages_to_report_schema(self) -> None:
        report_path = self.definition_folder / "report.json"
        report_path.write_text(
            json.dumps(
                {
                    "$schema": REPORT_SCHEMA,
                    "layoutOptimization": "None",
                    "themeCollection": {},
                    "resourcePackages": [
                        {
                            "resourcePackage": {
                                "name": "RegisteredResources",
                                "type": 1,
                                "items": [
                                    {
                                        "name": "Legacy Theme",
                                        "path": "BaseThemes/Legacy Theme.json",
                                        "type": 202,
                                    }
                                ],
                            }
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        theme_path = self.root / "custom-theme.json"
        theme_path.write_text('{"name": "Custom Theme"}\n', encoding="utf-8")

        apply_theme(self.project, theme_path)

        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        pkg = report["resourcePackages"][0]

        self.assertNotIn("resourcePackage", pkg)
        self.assertEqual(pkg["name"], "RegisteredResources")
        self.assertEqual(pkg["type"], "RegisteredResources")
        self.assertTrue(all(isinstance(item["type"], str) for item in pkg["items"]))
        self.assertEqual(report["themeCollection"]["customTheme"]["name"], "Custom Theme")

    def test_apply_theme_rejects_unsafe_theme_name(self) -> None:
        report_path = self.definition_folder / "report.json"
        report_path.write_text(
            json.dumps({"$schema": REPORT_SCHEMA, "themeCollection": {}}, indent=2) + "\n",
            encoding="utf-8",
        )
        theme_path = self.root / "custom-theme.json"
        theme_path.write_text('{"name": "../../escape"}\n', encoding="utf-8")

        with self.assertRaises(ValueError):
            apply_theme(self.project, theme_path)

        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        self.assertEqual(report.get("themeCollection"), {})

    def test_remove_theme_does_not_follow_unsafe_resource_path(self) -> None:
        victim = self.root.parent / "pbi-theme-victim.json"
        victim.write_text("keep\n", encoding="utf-8")
        self.addCleanup(lambda: victim.unlink(missing_ok=True))

        report_path = self.definition_folder / "report.json"
        report_path.write_text(
            json.dumps(
                {
                    "$schema": REPORT_SCHEMA,
                    "themeCollection": {
                        "customTheme": {
                            "name": "Unsafe Theme",
                            "type": "RegisteredResources",
                            "reportVersionAtImport": {},
                        }
                    },
                    "resourcePackages": [
                        {
                            "name": "RegisteredResources",
                            "type": "RegisteredResources",
                            "items": [
                                {
                                    "name": "Unsafe Theme",
                                    "path": "../../../../pbi-theme-victim.json",
                                    "type": "CustomTheme",
                                }
                            ],
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        removed = remove_theme(self.project)
        self.assertEqual(removed, "Unsafe Theme")
        self.assertTrue(victim.exists())

        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        self.assertNotIn("customTheme", report["themeCollection"])
        self.assertEqual(report["resourcePackages"][0]["items"], [])

    def test_apply_theme_keeps_existing_theme_if_copy_fails(self) -> None:
        report_path = self.definition_folder / "report.json"
        reg_dir = self.report_folder / "StaticResources" / "RegisteredResources"
        reg_dir.mkdir(parents=True, exist_ok=True)
        (reg_dir / "Old Theme.json").write_text('{"name":"Old Theme"}\n', encoding="utf-8")
        report_path.write_text(
            json.dumps(
                {
                    "$schema": REPORT_SCHEMA,
                    "themeCollection": {
                        "customTheme": {
                            "name": "Old Theme",
                            "type": "RegisteredResources",
                            "reportVersionAtImport": {},
                        }
                    },
                    "resourcePackages": [
                        {
                            "name": "RegisteredResources",
                            "type": "RegisteredResources",
                            "items": [
                                {
                                    "name": "Old Theme",
                                    "path": "Old Theme.json",
                                    "type": "CustomTheme",
                                }
                            ],
                        }
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        theme_path = self.root / "custom-theme.json"
        theme_path.write_text('{"name": "New Theme"}\n', encoding="utf-8")

        with mock.patch("pbi.themes.shutil.copy2", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                apply_theme(self.project, theme_path)

        report = json.loads(report_path.read_text(encoding="utf-8-sig"))
        self.assertEqual(report["themeCollection"]["customTheme"]["name"], "Old Theme")
        self.assertTrue((reg_dir / "Old Theme.json").exists())


class PagePropertyShapeTests(unittest.TestCase):
    def test_outspace_color_writes_to_schema_property(self) -> None:
        data: dict = {}
        set_property(data, "outspace.color", "#123456", PAGE_PROPERTIES)

        props = data["objects"]["outspace"][0]["properties"]

        self.assertIn("color", props)
        self.assertNotIn("backgroundColor", props)


class UnsupportedFilterWriterTests(unittest.TestCase):
    def test_relative_date_in_this_requires_count_one(self) -> None:
        with self.assertRaises(ValueError):
            add_relative_date_filter(
                {},
                "Date",
                "Date",
                operator="InThis",
                time_units_count=2,
                time_unit_type="Months",
            )


class SchemaBackedAdvancedFilterTests(unittest.TestCase):
    def test_include_filter_uses_schema_enum_and_in_expression(self) -> None:
        data: dict = {}
        add_include_filter(data, "Product", "Category", ["Bikes", "Accessories"])

        filter_obj = data["filterConfig"]["filters"][0]
        self.assertEqual(filter_obj["type"], "Include")
        self.assertEqual(filter_obj["howCreated"], "Include")
        self.assertIn("In", filter_obj["filter"]["Where"][0]["Condition"])

    def test_exclude_filter_uses_schema_enum_and_not_in_expression(self) -> None:
        data: dict = {}
        add_exclude_filter(data, "Product", "Category", ["Bikes"])

        filter_obj = data["filterConfig"]["filters"][0]
        self.assertEqual(filter_obj["type"], "Exclude")
        self.assertEqual(filter_obj["howCreated"], "Exclude")
        condition = filter_obj["filter"]["Where"][0]["Condition"]
        self.assertIn("Not", condition)
        self.assertIn("Expression", condition["Not"])
        self.assertIn("In", condition["Not"]["Expression"])

    def test_tuple_filter_uses_multi_expression_in_shape(self) -> None:
        data: dict = {}
        add_tuple_filter(
            data,
            [
                [
                    TupleField("Product", "Color", "Red"),
                    TupleField("Product", "Size", "Large"),
                ],
                [
                    TupleField("Product", "Color", "Blue"),
                    TupleField("Product", "Size", "Medium"),
                ],
            ],
        )

        filter_obj = data["filterConfig"]["filters"][0]
        condition = filter_obj["filter"]["Where"][0]["Condition"]["In"]
        self.assertEqual(filter_obj["type"], "Tuple")
        self.assertEqual(len(condition["Expressions"]), 2)
        self.assertEqual(len(condition["Values"]), 2)
        self.assertEqual(condition["Values"][0][0]["Literal"]["Value"], "'Red'")
        self.assertEqual(condition["Values"][0][1]["Literal"]["Value"], "'Large'")

    def test_topn_filter_uses_subquery_table_shape(self) -> None:
        data: dict = {}
        add_topn_filter(
            data,
            "Customers",
            "Region",
            n=7,
            order_entity="Order_Details",
            order_prop="Revenue",
        )

        filter_obj = data["filterConfig"]["filters"][0]
        self.assertEqual(filter_obj["type"], "TopN")
        self.assertNotIn("howCreated", filter_obj)
        subquery_source = filter_obj["filter"]["From"][0]
        self.assertEqual(subquery_source["Type"], 2)
        query = subquery_source["Expression"]["Subquery"]["Query"]
        self.assertEqual(query["Top"], 7)
        self.assertEqual(query["OrderBy"][0]["Direction"], 2)
        in_condition = filter_obj["filter"]["Where"][0]["Condition"]["In"]
        self.assertEqual(in_condition["Table"]["SourceRef"]["Source"], "subquery")
        self.assertNotIn("Values", in_condition)
        self.assertEqual(
            parse_filter(filter_obj).values,
            ["top 7 by Order_Details.Revenue"],
        )

    def test_relative_date_filter_uses_between_datespan_shape(self) -> None:
        data: dict = {}
        add_relative_date_filter(
            data,
            "Date",
            "Date",
            operator="InLast",
            time_units_count=100,
            time_unit_type="Days",
            include_today=True,
        )

        filter_obj = data["filterConfig"]["filters"][0]
        condition = filter_obj["filter"]["Where"][0]["Condition"]["Between"]
        self.assertEqual(filter_obj["type"], "RelativeDate")
        self.assertIn("DateSpan", condition["LowerBound"])
        self.assertIn("DateSpan", condition["UpperBound"])
        self.assertEqual(parse_filter(filter_obj).values, ["in last 100 days incl today"])

    def test_relative_time_filter_uses_between_now_shape(self) -> None:
        data: dict = {}
        add_relative_time_filter(
            data,
            "Date",
            "Date",
            operator="InNext",
            time_units_count=1,
            time_unit_type="Hours",
        )

        filter_obj = data["filterConfig"]["filters"][0]
        condition = filter_obj["filter"]["Where"][0]["Condition"]["Between"]
        self.assertEqual(filter_obj["type"], "RelativeTime")
        self.assertEqual(condition["LowerBound"], {"Now": {}})
        self.assertIn("DateAdd", condition["UpperBound"])
        self.assertEqual(parse_filter(filter_obj).values, ["in next 1 hours"])


class AdvancedFilterTests(unittest.TestCase):
    def test_contains_filter_shape(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Name", operator="contains", value="Pro")

        f = data["filterConfig"]["filters"][0]
        self.assertEqual(f["type"], "Advanced")
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("Contains", cond)
        self.assertEqual(
            cond["Contains"]["Right"], {"Literal": {"Value": "'Pro'"}}
        )
        self.assertEqual(parse_filter(f).values, ["contains Pro"])

    def test_does_not_contain_filter_uses_not_wrapper(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Name", operator="does-not-contain", value="Test")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("Not", cond)
        self.assertIn("Contains", cond["Not"]["Expression"])
        self.assertEqual(parse_filter(f).values, ["does not contain Test"])

    def test_starts_with_filter_shape(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Customer", "Region", operator="starts-with", value="North")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("StartsWith", cond)
        self.assertEqual(
            cond["StartsWith"]["Right"], {"Literal": {"Value": "'North'"}}
        )
        self.assertEqual(parse_filter(f).values, ["starts with North"])

    def test_does_not_start_with_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Customer", "Region", operator="does-not-start-with", value="South")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("Not", cond)
        self.assertIn("StartsWith", cond["Not"]["Expression"])
        self.assertEqual(parse_filter(f).values, ["does not start with South"])

    def test_is_filter_uses_comparison_equal(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Category", operator="is", value="Bikes")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("Comparison", cond)
        self.assertEqual(cond["Comparison"]["ComparisonKind"], 0)
        self.assertEqual(
            cond["Comparison"]["Right"], {"Literal": {"Value": "'Bikes'"}}
        )

    def test_is_not_filter_wraps_in_not(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Category", operator="is-not", value="Bikes")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("Not", cond)
        inner = cond["Not"]["Expression"]
        self.assertIn("Comparison", inner)
        self.assertEqual(inner["Comparison"]["ComparisonKind"], 0)
        self.assertEqual(parse_filter(f).values, ["is not Bikes"])

    def test_greater_than_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Sales", "Revenue", operator="greater-than", value="1000", data_type="number")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertEqual(cond["Comparison"]["ComparisonKind"], 1)
        self.assertEqual(
            cond["Comparison"]["Right"], {"Literal": {"Value": "1000D"}}
        )

    def test_less_than_or_equal_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Sales", "Revenue", operator="less-than-or-equal", value="500")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertEqual(cond["Comparison"]["ComparisonKind"], 4)

    def test_is_blank_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Name", operator="is-blank")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertEqual(cond["Comparison"]["ComparisonKind"], 0)
        self.assertEqual(cond["Comparison"]["Right"], {"Literal": {"Value": "null"}})
        self.assertEqual(parse_filter(f).values, ["is blank"])

    def test_is_not_blank_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Name", operator="is-not-blank")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("Not", cond)
        inner = cond["Not"]["Expression"]
        self.assertEqual(inner["Comparison"]["Right"], {"Literal": {"Value": "null"}})
        self.assertEqual(parse_filter(f).values, ["is not blank"])

    def test_is_empty_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Name", operator="is-empty")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertEqual(cond["Comparison"]["Right"], {"Literal": {"Value": "''"}})
        self.assertEqual(parse_filter(f).values, ["is empty"])

    def test_is_not_empty_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Name", operator="is-not-empty")

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("Not", cond)
        self.assertEqual(parse_filter(f).values, ["is not empty"])

    def test_field_refs_extracted_from_contains(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Name", operator="contains", value="X")
        f = data["filterConfig"]["filters"][0]
        refs = filter_field_refs(f)
        self.assertIn("Product.Name", refs)

    def test_field_refs_extracted_from_not_starts_with(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Customer", "City", operator="does-not-start-with", value="New")
        f = data["filterConfig"]["filters"][0]
        refs = filter_field_refs(f)
        self.assertIn("Customer.City", refs)

    def test_value_required_for_contains(self) -> None:
        with self.assertRaises(ValueError):
            add_advanced_filter({}, "Product", "Name", operator="contains")

    def test_value_not_required_for_is_blank(self) -> None:
        data: dict = {}
        add_advanced_filter(data, "Product", "Name", operator="is-blank")
        self.assertEqual(len(data["filterConfig"]["filters"]), 1)

    def test_unknown_operator_raises(self) -> None:
        with self.assertRaises(ValueError):
            add_advanced_filter({}, "Product", "Name", operator="banana", value="x")

    def test_compound_and_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(
            data, "Product", "Name",
            operator="contains", value="Pro",
            operator2="does-not-contain", value2="Prototype",
            logic="and",
        )

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("And", cond)
        self.assertIn("Contains", cond["And"]["Left"])
        self.assertIn("Not", cond["And"]["Right"])
        self.assertIn("Contains", cond["And"]["Right"]["Not"]["Expression"])
        self.assertEqual(
            parse_filter(f).values,
            ["contains Pro and does not contain Prototype"],
        )

    def test_compound_or_filter(self) -> None:
        data: dict = {}
        add_advanced_filter(
            data, "Sales", "Revenue",
            operator="less-than", value="100",
            operator2="greater-than", value2="10000",
            logic="or",
        )

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("Or", cond)
        self.assertEqual(cond["Or"]["Left"]["Comparison"]["ComparisonKind"], 3)
        self.assertEqual(cond["Or"]["Right"]["Comparison"]["ComparisonKind"], 1)

    def test_compound_with_nullary_operator(self) -> None:
        data: dict = {}
        add_advanced_filter(
            data, "Product", "Name",
            operator="contains", value="Pro",
            operator2="is-not-blank",
            logic="and",
        )

        f = data["filterConfig"]["filters"][0]
        cond = f["filter"]["Where"][0]["Condition"]
        self.assertIn("And", cond)
        self.assertIn("Contains", cond["And"]["Left"])
        self.assertIn("Not", cond["And"]["Right"])

    def test_invalid_logic_raises(self) -> None:
        with self.assertRaises(ValueError):
            add_advanced_filter(
                {}, "Product", "Name",
                operator="is", value="X",
                operator2="is-not", value2="Y",
                logic="xor",
            )


if __name__ == "__main__":
    unittest.main()
