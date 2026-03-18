from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml

from pbi.apply import apply_yaml
from pbi.properties import VISUAL_PROPERTIES, set_property
from tests.cli_regressions_support import make_project


class TestBug026FillRuleInput(unittest.TestCase):
    """BUG-026: FillRule Input must use Measure expression."""

    def test_gradient_uses_measure_expression(self):
        from pbi.formatting import GradientStop, build_gradient_format

        value = build_gradient_format(
            "Measures Table", "Total Devices",
            GradientStop("#FFFFFF", 0), GradientStop("#B83B3B", 90),
        )
        fill_rule = value["solid"]["color"]["expr"]["FillRule"]
        input_node = fill_rule["Input"]

        # Must use Measure expression
        self.assertIn("Measure", input_node)
        self.assertNotIn("SelectRef", input_node)
        self.assertNotIn("Column", input_node)
        self.assertEqual(
            input_node["Measure"]["Property"],
            "Total Devices",
        )
        self.assertEqual(
            input_node["Measure"]["Expression"]["SourceRef"]["Entity"],
            "Measures Table",
        )

    def test_gradient_stop_values_use_integer_format(self):
        from pbi.formatting import GradientStop, build_gradient_format

        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0), GradientStop("#000", 90),
        )
        gradient = value["solid"]["color"]["expr"]["FillRule"]["FillRule"]["linearGradient2"]

        # Must be "0D" not "0.0D"
        min_val = gradient["min"]["value"]["Literal"]["Value"]
        max_val = gradient["max"]["value"]["Literal"]["Value"]
        self.assertEqual(min_val, "0D")
        self.assertEqual(max_val, "90D")

    def test_gradient_stop_values_preserve_decimals(self):
        from pbi.formatting import GradientStop, build_gradient_format

        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0.5), GradientStop("#000", 99.9),
        )
        gradient = value["solid"]["color"]["expr"]["FillRule"]["FillRule"]["linearGradient2"]
        min_val = gradient["min"]["value"]["Literal"]["Value"]
        max_val = gradient["max"]["value"]["Literal"]["Value"]
        self.assertEqual(min_val, "0.5D")
        self.assertEqual(max_val, "99.9D")

    def test_per_column_selector_uses_matching_option_1(self):
        from pbi.formatting import GradientStop, build_gradient_format, set_conditional_format

        data: dict = {}
        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0), GradientStop("#000", 100),
        )
        set_conditional_format(data, "values", "backColor", value, column="T.F")

        entries = data["visual"]["objects"]["values"]
        selector = entries[0]["selector"]
        # Per-column must use matchingOption 1
        self.assertEqual(selector["data"][0]["dataViewWildcard"]["matchingOption"], 1)
        self.assertEqual(selector["metadata"], "T.F")

    def test_per_column_writes_column_formatting_marker(self):
        from pbi.formatting import GradientStop, build_gradient_format, set_conditional_format

        data: dict = {}
        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0), GradientStop("#000", 100),
        )
        set_conditional_format(data, "values", "backColor", value, column="T.F")

        # Must register in columnFormatting marker
        cf = data["visual"]["objects"].get("columnFormatting", [])
        self.assertEqual(len(cf), 1)
        self.assertEqual(cf[0]["selector"]["metadata"], "T.F")

    def test_all_columns_selector_uses_matching_option_0(self):
        from pbi.formatting import GradientStop, build_gradient_format, set_conditional_format

        data: dict = {}
        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0), GradientStop("#000", 100),
        )
        set_conditional_format(data, "values", "backColor", value)

        entries = data["visual"]["objects"]["values"]
        selector = entries[0]["selector"]
        # All-columns uses matchingOption 0, no metadata
        self.assertEqual(selector["data"][0]["dataViewWildcard"]["matchingOption"], 0)
        self.assertNotIn("metadata", selector)

    def test_null_strategy_in_gradient(self):
        from pbi.formatting import GradientStop, build_gradient_format

        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0), GradientStop("#000", 100),
            null_strategy="asZero",
        )
        gradient = value["solid"]["color"]["expr"]["FillRule"]["FillRule"]["linearGradient2"]
        self.assertIn("nullColoringStrategy", gradient)
        strategy = gradient["nullColoringStrategy"]["strategy"]["Literal"]["Value"]
        self.assertEqual(strategy, "'asZero'")

    def test_parse_measure_input(self):
        from pbi.formatting import get_conditional_formats, set_conditional_format, GradientStop, build_gradient_format

        data: dict = {}
        value = build_gradient_format(
            "Measures Table", "Total Devices",
            GradientStop("#FFF", 0), GradientStop("#000", 100),
        )
        set_conditional_format(data, "values", "backColor", value)

        formats = get_conditional_formats(data)
        self.assertEqual(len(formats), 1)
        self.assertEqual(formats[0].field_ref, "Measures Table.Total Devices")
        self.assertEqual(formats[0].format_type, "gradient2")

class TestConditionalFormattingListSyntaxGuard(unittest.TestCase):
    """List-syntax conditionalFormatting should produce a clear error, not crash."""

    def test_list_syntax_produces_error_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Test")
            project.create_visual(page, "tableEx")

            yaml_content = yaml.safe_dump({
                "version": 1,
                "pages": [{
                    "name": "Test",
                    "visuals": [{
                        "name": "table1",
                        "type": "tableEx",
                        "position": "16, 8",
                        "size": "400 x 300",
                        "conditionalFormatting": [
                            {"prop": "values.backColor", "mode": "gradient"},
                        ],
                    }],
                }],
            })

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertTrue(len(result.errors) > 0)
            self.assertIn("must be a mapping", result.errors[0])

class TestRulesBasedConditionalFormatting(unittest.TestCase):
    """Rules-based conditional formatting (mode: rules)."""

    def test_build_rules_format_structure(self):
        from pbi.formatting import build_rules_format

        value = build_rules_format(
            "Devices", "ComplianceState",
            [
                {"value": "noncompliant", "color": "#B83B3B"},
                {"value": "compliant", "color": "#2B7A4B"},
            ],
            else_color="#C4882E",
        )

        # Verify structure
        expr = value["solid"]["color"]["expr"]
        self.assertIn("Conditional", expr)
        cases = expr["Conditional"]["Cases"]
        self.assertEqual(len(cases), 2)

        # First case: noncompliant = red
        cmp = cases[0]["Condition"]["Comparison"]
        self.assertEqual(cmp["ComparisonKind"], 0)
        self.assertEqual(cmp["Right"]["Literal"]["Value"], "'noncompliant'")
        self.assertEqual(cases[0]["Value"]["Literal"]["Value"], "'#B83B3B'")

        # Else clause
        self.assertEqual(expr["Conditional"]["Else"]["Literal"]["Value"], "'#C4882E'")

    def test_parse_rules_format_info(self):
        from pbi.formatting import build_rules_format, get_conditional_formats, set_conditional_format

        data: dict = {}
        value = build_rules_format(
            "Devices", "ComplianceState",
            [{"value": "noncompliant", "color": "#B83B3B"}],
            else_color="#2B7A4B",
        )
        set_conditional_format(data, "values", "backColor", value)

        formats = get_conditional_formats(data)
        self.assertEqual(len(formats), 1)
        fmt = formats[0]
        self.assertEqual(fmt.format_type, "rules")
        self.assertEqual(fmt.field_ref, "Devices.ComplianceState")
        self.assertIn("noncompliant", fmt.details)
        self.assertIn("else=", fmt.details)

    def test_apply_yaml_rules_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Test")
            project.create_visual(page, "tableEx")

            yaml_content = yaml.safe_dump({
                "version": 1,
                "pages": [{
                    "name": "Test",
                    "visuals": [{
                        "name": "table1",
                        "type": "tableEx",
                        "position": "16, 8",
                        "size": "400 x 300",
                        "conditionalFormatting": {
                            "values.backColor": {
                                "mode": "rules",
                                "source": "Devices.ComplianceState",
                                "rules": [
                                    {"if": "noncompliant", "color": "#B83B3B"},
                                    {"if": "compliant", "color": "#2B7A4B"},
                                ],
                                "else": {"color": "#C4882E"},
                            },
                        },
                    }],
                }],
            })

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertEqual(result.errors, [], f"Unexpected errors: {result.errors}")
            self.assertGreater(result.properties_set, 0)

class TestPerColumnConditionalFormatting(unittest.TestCase):
    """Per-column conditional formatting targeting."""

    def test_set_conditional_format_with_column_selector(self):
        from pbi.formatting import GradientStop, build_gradient_format, get_conditional_formats, set_conditional_format

        data: dict = {}
        value = build_gradient_format(
            "Devices", "DaysSinceLastSync",
            GradientStop("#FFFFFF", 0), GradientStop("#B83B3B", 90),
        )
        set_conditional_format(data, "values", "backColor", value, column="Devices.DaysSinceLastSync")

        # Verify the selector has metadata
        entries = data["visual"]["objects"]["values"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["selector"]["metadata"], "Devices.DaysSinceLastSync")

        # Verify get_conditional_formats reads the column
        formats = get_conditional_formats(data)
        self.assertEqual(len(formats), 1)
        self.assertEqual(formats[0].column, "Devices.DaysSinceLastSync")

    def test_separate_selectors_for_different_columns(self):
        from pbi.formatting import GradientStop, build_gradient_format, set_conditional_format

        data: dict = {}
        v1 = build_gradient_format("T", "A", GradientStop("#FFF", 0), GradientStop("#000", 100))
        v2 = build_gradient_format("T", "B", GradientStop("#FFF", 0), GradientStop("#F00", 100))
        set_conditional_format(data, "values", "backColor", v1, column="T.A")
        set_conditional_format(data, "values", "backColor", v2, column="T.B")

        entries = data["visual"]["objects"]["values"]
        self.assertEqual(len(entries), 2)
        metadata_values = {e["selector"]["metadata"] for e in entries}
        self.assertEqual(metadata_values, {"T.A", "T.B"})

    def test_apply_yaml_column_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Test")

            yaml_content = yaml.safe_dump({
                "version": 1,
                "pages": [{
                    "name": "Test",
                    "visuals": [{
                        "name": "table1",
                        "type": "tableEx",
                        "position": "16, 8",
                        "size": "400 x 300",
                        "conditionalFormatting": {
                            "values.backColor": {
                                "mode": "gradient",
                                "source": "Devices.DaysSinceLastSync",
                                "column": "Devices.DaysSinceLastSync",
                                "min": {"color": "#FFFFFF", "value": 0},
                                "max": {"color": "#B83B3B", "value": 90},
                            },
                        },
                    }],
                }],
            })

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertEqual(result.errors, [], f"Unexpected errors: {result.errors}")

            # Verify the column selector was written
            page = project.find_page("Test")
            visuals = project.get_visuals(page)
            # Find the visual named table1
            vis = next(v for v in visuals if v.data.get("name") == "table1")
            entries = vis.data.get("visual", {}).get("objects", {}).get("values", [])
            col_entries = [e for e in entries if e.get("selector", {}).get("metadata")]
            self.assertEqual(len(col_entries), 1)
            self.assertEqual(col_entries[0]["selector"]["metadata"], "Devices.DaysSinceLastSync")

class TestSession6Bug026TileShape(unittest.TestCase):
    """BUG-026 (session 6): cardShape.tileShape must encode as enum, not boolean."""

    def test_tileshape_property_is_enum_type(self):
        from pbi.properties import VISUAL_PROPERTIES
        prop_def = VISUAL_PROPERTIES["cardShape.tileShape"]
        self.assertEqual(prop_def.value_type, "enum")

    def test_tileshape_encodes_as_quoted_string(self):
        from pbi.properties import encode_pbi_value
        result = encode_pbi_value("rectangleRoundedByPixel", "enum")
        self.assertEqual(result, {"expr": {"Literal": {"Value": "'rectangleRoundedByPixel'"}}})

    def test_tileshape_roundtrip(self):
        from pbi.properties import encode_pbi_value, decode_pbi_value
        encoded = encode_pbi_value("rectangleRoundedByPixel", "enum")
        decoded = decode_pbi_value(encoded)
        self.assertEqual(decoded, "rectangleRoundedByPixel")

class TestSession6Bug027ColumnVsMeasure(unittest.TestCase):
    """BUG-027 (session 6): gradient/rules must use Column ref for column fields."""

    def test_gradient_column_field_type(self):
        from pbi.formatting import GradientStop, build_gradient_format
        value = build_gradient_format(
            "SignInSummary", "FailureCount",
            GradientStop("#FFFFFF", 0), GradientStop("#FFEBEE", 100),
            field_type="column",
        )
        input_node = value["solid"]["color"]["expr"]["FillRule"]["Input"]
        self.assertIn("Column", input_node)
        self.assertNotIn("Measure", input_node)
        self.assertEqual(input_node["Column"]["Property"], "FailureCount")

    def test_gradient_measure_field_type(self):
        from pbi.formatting import GradientStop, build_gradient_format
        value = build_gradient_format(
            "Measures", "Total",
            GradientStop("#FFF", 0), GradientStop("#000", 100),
            field_type="measure",
        )
        input_node = value["solid"]["color"]["expr"]["FillRule"]["Input"]
        self.assertIn("Measure", input_node)
        self.assertNotIn("Column", input_node)

    def test_gradient_defaults_to_measure(self):
        from pbi.formatting import GradientStop, build_gradient_format
        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0), GradientStop("#000", 100),
        )
        input_node = value["solid"]["color"]["expr"]["FillRule"]["Input"]
        self.assertIn("Measure", input_node)

    def test_rules_column_field_type(self):
        from pbi.formatting import build_rules_format
        value = build_rules_format(
            "Devices", "ComplianceState",
            [{"value": "Compliant", "color": "#2B7A4B"}],
            field_type="column",
        )
        conditional = value["solid"]["color"]["expr"]["Conditional"]
        left = conditional["Cases"][0]["Condition"]["Comparison"]["Left"]
        self.assertIn("Column", left)
        self.assertNotIn("Measure", left)

    def test_rules_defaults_to_measure(self):
        from pbi.formatting import build_rules_format
        value = build_rules_format(
            "T", "F",
            [{"value": "X", "color": "#000"}],
        )
        conditional = value["solid"]["color"]["expr"]["Conditional"]
        left = conditional["Cases"][0]["Condition"]["Comparison"]["Left"]
        self.assertIn("Measure", left)

class TestSession6Bug028DuplicateEntries(unittest.TestCase):
    """BUG-028 (session 6): set-all must merge into existing default entry, not duplicate."""

    def test_no_duplicate_when_default_entry_exists(self):
        from pbi.properties import set_property, VISUAL_PROPERTIES
        data = {
            "visual": {
                "visualType": "cardVisual",
                "objects": {
                    "accentBar": [
                        {"selector": {"id": "default"}, "properties": {"show": True, "position": "Top"}},
                    ]
                }
            }
        }
        set_property(data, "chart:accentBar.width", "4", VISUAL_PROPERTIES)
        entries = data["visual"]["objects"]["accentBar"]
        # Should merge into existing entry, not create a new one
        self.assertEqual(len(entries), 1)
        self.assertIn("width", entries[0]["properties"])
        self.assertIn("position", entries[0]["properties"])

    def test_no_selector_falls_back_to_first_entry(self):
        from pbi.properties import set_property, VISUAL_PROPERTIES
        data = {
            "visual": {
                "visualType": "cardVisual",
                "objects": {
                    "accentBar": [
                        {"selector": {"id": "default"}, "properties": {"show": True}},
                    ]
                }
            }
        }
        # No explicit selector — should update the existing entry
        set_property(data, "chart:accentBar.color", "#FF0000", VISUAL_PROPERTIES)
        entries = data["visual"]["objects"]["accentBar"]
        self.assertEqual(len(entries), 1)

class TestSession6Bug029BracketSelector(unittest.TestCase):
    """BUG-029 (session 6): bracket selector must work with or without space."""

    def test_bracket_without_space_in_set_property(self):
        from pbi.properties import set_property, VISUAL_PROPERTIES
        data = {
            "visual": {
                "visualType": "cardVisual",
                "objects": {}
            }
        }
        set_property(data, "chart:accentBar.color[Measures Table.Total Sign-Ins]", "#1A6B7D", VISUAL_PROPERTIES)
        entries = data["visual"]["objects"]["accentBar"]
        # Should create an entry with metadata selector
        found = False
        for entry in entries:
            sel = entry.get("selector", {})
            if sel.get("metadata") == "Measures Table.Total Sign-Ins":
                self.assertIn("color", entry["properties"])
                found = True
        self.assertTrue(found, "Entry with metadata selector not found")

    def test_bracket_with_space_still_works(self):
        from pbi.properties import set_property, VISUAL_PROPERTIES
        data = {
            "visual": {
                "visualType": "cardVisual",
                "objects": {}
            }
        }
        set_property(data, "chart:accentBar.color [Measures Table.Total]", "#1A6B7D", VISUAL_PROPERTIES)
        entries = data["visual"]["objects"]["accentBar"]
        found = False
        for entry in entries:
            sel = entry.get("selector", {})
            if sel.get("metadata") == "Measures Table.Total":
                found = True
        self.assertTrue(found, "Entry with metadata selector not found")

    def test_parse_chart_prefix_without_space(self):
        from pbi.properties import _parse_chart_prefix
        obj, prop, selector = _parse_chart_prefix("chart:accentBar.color[MyMeasure]")
        self.assertEqual(obj, "accentBar")
        self.assertEqual(prop, "color")
        self.assertEqual(selector, "MyMeasure")

    def test_parse_chart_prefix_with_space(self):
        from pbi.properties import _parse_chart_prefix
        obj, prop, selector = _parse_chart_prefix("chart:accentBar.color [MyMeasure]")
        self.assertEqual(obj, "accentBar")
        self.assertEqual(prop, "color")
        self.assertEqual(selector, "MyMeasure")

class TestRulesFormatCLI(unittest.TestCase):
    """IMP-06: build_rules_format with field_type works from CLI."""

    def test_rules_format_column_field(self):
        from pbi.formatting import build_rules_format, set_conditional_format

        data: dict = {}
        value = build_rules_format(
            "Devices", "ComplianceState",
            [
                {"value": "Compliant", "color": "#2B7A4B"},
                {"value": "NonCompliant", "color": "#B83B3B"},
            ],
            else_color="#605E5C",
            field_type="column",
        )
        set_conditional_format(data, "values", "fontColor", value)

        # Verify the conditional was written
        entries = data["visual"]["objects"]["values"]
        self.assertEqual(len(entries), 1)
        color_expr = entries[0]["properties"]["fontColor"]["solid"]["color"]["expr"]
        self.assertIn("Conditional", color_expr)
        cases = color_expr["Conditional"]["Cases"]
        self.assertEqual(len(cases), 2)

        # Left operand must be Column, not Measure
        left = cases[0]["Condition"]["Comparison"]["Left"]
        self.assertIn("Column", left)
        self.assertNotIn("Measure", left)

        # Else present
        self.assertIn("Else", color_expr["Conditional"])

    def test_rules_format_measure_field(self):
        from pbi.formatting import build_rules_format

        value = build_rules_format(
            "Table", "StatusMeasure",
            [{"value": "OK", "color": "#00FF00"}],
            field_type="measure",
        )
        cases = value["solid"]["color"]["expr"]["Conditional"]["Cases"]
        left = cases[0]["Condition"]["Comparison"]["Left"]
        self.assertIn("Measure", left)

    def test_rules_no_else(self):
        from pbi.formatting import build_rules_format

        value = build_rules_format(
            "T", "F",
            [{"value": "X", "color": "#000"}],
        )
        conditional = value["solid"]["color"]["expr"]["Conditional"]
        self.assertNotIn("Else", conditional)
