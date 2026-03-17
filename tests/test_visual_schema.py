"""Tests for schema-powered PBIR validation and auto-resolve.

Covers:
  - visual_schema.py: schema loading, object/property/value validation, fuzzy suggestions
  - properties.py: auto-resolve of chart properties, schema warnings on set_property
  - roles.py: schema-backed role merging and fallback
  - validate.py: schema validation in _validate_visual_schema
  - inspection.py: schema-aware property listing, enum display
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.cli import app
from pbi.project import Project
from pbi.properties import VISUAL_PROPERTIES, list_properties, set_property
from pbi.roles import (
    get_visual_roles,
    get_visual_type_info,
    is_known_visual_type,
    list_visual_type_info,
    normalize_visual_role,
)
from pbi.schema_refs import PAGE_SCHEMA, PAGES_METADATA_SCHEMA, REPORT_SCHEMA
from pbi.visual_schema import (
    get_data_roles,
    get_object_names,
    get_property_names,
    get_property_type,
    get_visual_schema,
    get_visual_types,
    validate_chart_property,
    validate_object,
    validate_property,
    validate_value,
    validate_visual_objects,
)


# ── Schema loading and querying ─────────────────────────────────────


class SchemaLoadingTests(unittest.TestCase):
    def test_loads_visual_types(self) -> None:
        types = get_visual_types()
        self.assertGreater(len(types), 50)
        self.assertIn("clusteredBarChart", types)
        self.assertIn("cardVisual", types)
        self.assertIn("slicer", types)

    def test_returns_none_for_unknown_visual_type(self) -> None:
        self.assertIsNone(get_visual_schema("nonExistentVisual"))
        self.assertIsNone(get_object_names("nonExistentVisual"))
        self.assertIsNone(get_property_names("nonExistentVisual", "legend"))

    def test_object_names_per_visual_type(self) -> None:
        bar_objects = get_object_names("clusteredBarChart")
        self.assertIn("legend", bar_objects)
        self.assertIn("categoryAxis", bar_objects)
        self.assertIn("valueAxis", bar_objects)
        self.assertIn("dataPoint", bar_objects)

        card_objects = get_object_names("cardVisual")
        self.assertIn("accentBar", card_objects)
        self.assertIn("value", card_objects)
        self.assertNotIn("legend", card_objects)
        self.assertNotIn("categoryAxis", card_objects)

    def test_property_names_per_object(self) -> None:
        props = get_property_names("clusteredBarChart", "legend")
        self.assertIn("show", props)
        self.assertIn("position", props)
        self.assertIn("fontSize", props)

    def test_property_type_bool(self) -> None:
        ptype = get_property_type("clusteredBarChart", "legend", "show")
        self.assertEqual(ptype, "bool")

    def test_property_type_enum(self) -> None:
        ptype = get_property_type("clusteredBarChart", "legend", "position")
        self.assertIsInstance(ptype, list)
        self.assertIn("Top", ptype)
        self.assertIn("Bottom", ptype)

    def test_property_type_color(self) -> None:
        ptype = get_property_type("cardVisual", "accentBar", "color")
        self.assertEqual(ptype, "color")

    def test_property_type_numeric(self) -> None:
        ptype = get_property_type("cardVisual", "accentBar", "transparency")
        self.assertEqual(ptype, "num")

    def test_data_roles(self) -> None:
        roles = get_data_roles("treemap")
        self.assertIn("Group", roles)
        self.assertIn("Values", roles)
        self.assertEqual(roles["Group"]["kind"], 0)
        self.assertEqual(roles["Values"]["kind"], 1)

    def test_data_roles_unknown_type(self) -> None:
        self.assertIsNone(get_data_roles("nonExistentVisual"))


# ── Object validation ───────────────────────────────────────────────


class ObjectValidationTests(unittest.TestCase):
    def test_valid_object_returns_none(self) -> None:
        self.assertIsNone(validate_object("clusteredBarChart", "legend"))
        self.assertIsNone(validate_object("cardVisual", "accentBar"))

    def test_invalid_object_returns_warning(self) -> None:
        w = validate_object("cardVisual", "categoryAxis")
        self.assertIsNotNone(w)
        self.assertIn("categoryAxis", str(w))
        self.assertIn("cardVisual", str(w))

    def test_typo_object_suggests_correction(self) -> None:
        w = validate_object("clusteredBarChart", "legnd")
        self.assertIsNotNone(w)
        self.assertIn("Did you mean", str(w))
        self.assertIn("legend", str(w))

    def test_unknown_visual_type_skips_validation(self) -> None:
        self.assertIsNone(validate_object("customThirdPartyVisual", "anything"))


# ── Property validation ─────────────────────────────────────────────


class PropertyValidationTests(unittest.TestCase):
    def test_valid_property_returns_none(self) -> None:
        self.assertIsNone(
            validate_property("clusteredBarChart", "legend", "show")
        )

    def test_invalid_property_returns_warning(self) -> None:
        w = validate_property("clusteredBarChart", "legend", "nonExistent")
        self.assertIsNotNone(w)
        self.assertIn("nonExistent", str(w))

    def test_typo_property_suggests_correction(self) -> None:
        w = validate_property("clusteredBarChart", "legend", "showTitl")
        self.assertIsNotNone(w)
        self.assertIn("Did you mean", str(w))
        self.assertIn("showTitle", str(w))

    def test_unknown_object_skips_property_validation(self) -> None:
        self.assertIsNone(
            validate_property("clusteredBarChart", "nonExistent", "show")
        )


# ── Value validation ────────────────────────────────────────────────


class ValueValidationTests(unittest.TestCase):
    def test_valid_enum_value(self) -> None:
        self.assertIsNone(
            validate_value("clusteredBarChart", "legend", "position", "Top")
        )

    def test_invalid_enum_value(self) -> None:
        w = validate_value(
            "clusteredBarChart", "legend", "position", "Diagonal"
        )
        self.assertIsNotNone(w)
        self.assertIn("Diagonal", str(w))
        self.assertIn("Allowed", str(w))

    def test_enum_case_insensitive(self) -> None:
        self.assertIsNone(
            validate_value("clusteredBarChart", "legend", "position", "top")
        )

    def test_valid_bool_values(self) -> None:
        for val in ("true", "false", True, False, "yes", "no"):
            self.assertIsNone(
                validate_value("clusteredBarChart", "legend", "show", val)
            )

    def test_invalid_bool_value(self) -> None:
        w = validate_value("clusteredBarChart", "legend", "show", "maybe")
        self.assertIsNotNone(w)

    def test_valid_color(self) -> None:
        self.assertIsNone(
            validate_value("cardVisual", "accentBar", "color", "#FF0000")
        )

    def test_suspicious_color_warns(self) -> None:
        w = validate_value("cardVisual", "accentBar", "color", "red")
        self.assertIsNotNone(w)
        self.assertIn("#RRGGBB", str(w))


# ── Bulk visual objects validation ──────────────────────────────────


class BulkValidationTests(unittest.TestCase):
    def test_valid_objects_no_warnings(self) -> None:
        warnings = validate_visual_objects("clusteredBarChart", {
            "legend": [{"properties": {"show": True, "position": "Top"}}],
            "categoryAxis": [{"properties": {"show": True}}],
        })
        self.assertEqual(len(warnings), 0)

    def test_invalid_object_and_property_both_caught(self) -> None:
        warnings = validate_visual_objects("clusteredBarChart", {
            "legnd": [{"properties": {"show": True}}],
            "legend": [{"properties": {"showTitl": True, "show": True}}],
        })
        self.assertEqual(len(warnings), 2)
        messages = [str(w) for w in warnings]
        self.assertTrue(any("legnd" in m for m in messages))
        self.assertTrue(any("showTitl" in m for m in messages))


# ── Chart property helper ───────────────────────────────────────────


class ChartPropertyValidationTests(unittest.TestCase):
    def test_valid_chart_property_no_warnings(self) -> None:
        warnings = validate_chart_property(
            "clusteredBarChart", "legend", "show", "true"
        )
        self.assertEqual(len(warnings), 0)

    def test_invalid_object_for_type(self) -> None:
        warnings = validate_chart_property(
            "slicer", "categoryAxis", "show", "true"
        )
        self.assertEqual(len(warnings), 1)
        self.assertIn("categoryAxis", str(warnings[0]))

    def test_none_visual_type_skips(self) -> None:
        warnings = validate_chart_property(None, "legend", "show", "true")
        self.assertEqual(len(warnings), 0)


# ── Auto-resolve in set_property ────────────────────────────────────


class AutoResolveChartPropertyTests(unittest.TestCase):
    def _bar_data(self) -> dict:
        return {"visual": {"visualType": "clusteredBarChart"}}

    def _card_data(self) -> dict:
        return {"visual": {"visualType": "cardVisual"}}

    def test_auto_resolves_schema_valid_property(self) -> None:
        data = self._bar_data()
        warnings = set_property(data, "legend.show", "false", VISUAL_PROPERTIES)
        objects = data["visual"].get("objects", {})
        self.assertIn("legend", objects)
        self.assertEqual(len(warnings), 0)

    def test_auto_resolves_with_selector(self) -> None:
        data = self._bar_data()
        set_property(data, "dataPoint.fill [default]", "#FF0000", VISUAL_PROPERTIES)
        entries = data["visual"]["objects"]["dataPoint"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["selector"], {"id": "default"})
        self.assertIn("fill", entries[0]["properties"])

    def test_rejects_invalid_object_for_visual_type(self) -> None:
        data = self._card_data()
        with self.assertRaises(ValueError):
            set_property(data, "zoom.show", "true", VISUAL_PROPERTIES)

    def test_rejects_invalid_property_on_valid_object(self) -> None:
        data = self._bar_data()
        with self.assertRaises(ValueError):
            set_property(data, "legend.nonExistent", "true", VISUAL_PROPERTIES)

    def test_registered_properties_still_work(self) -> None:
        data = self._bar_data()
        set_property(data, "background.show", "true", VISUAL_PROPERTIES)
        container = data["visual"]["visualContainerObjects"]
        self.assertIn("background", container)

    def test_chart_prefix_still_works(self) -> None:
        data = self._bar_data()
        set_property(data, "chart:legend.show", "true", VISUAL_PROPERTIES)
        self.assertIn("legend", data["visual"]["objects"])

    def test_schema_warnings_returned_for_invalid_chart_prefix(self) -> None:
        data = self._bar_data()
        warnings = set_property(data, "chart:legnd.show", "true", VISUAL_PROPERTIES)
        self.assertGreater(len(warnings), 0)
        self.assertTrue(any("legnd" in w for w in warnings))

    def test_no_auto_resolve_without_visual_type(self) -> None:
        data = {"visual": {}}
        with self.assertRaises(ValueError):
            # zoom.show is not a registered property and there's no visualType
            # to look up in the schema, so it should raise
            set_property(data, "zoom.show", "true", VISUAL_PROPERTIES)


# ── Schema-aware type coercion ──────────────────────────────────────


class SchemaTypeCoercionTests(unittest.TestCase):
    """Verify _resolve_value_type uses schema types instead of guessing."""

    def _bar_data(self) -> dict:
        return {"visual": {"visualType": "clusteredBarChart"}}

    def _card_data(self) -> dict:
        return {"visual": {"visualType": "cardVisual"}}

    def _get_raw(self, data: dict, obj: str, prop: str) -> dict:
        return data["visual"]["objects"][obj][0]["properties"][prop]

    def test_bool_property_encodes_1_as_true(self) -> None:
        """'1' on a bool schema property should encode as bool, not number."""
        data = self._bar_data()
        set_property(data, "legend.show", "1", VISUAL_PROPERTIES)
        raw = self._get_raw(data, "legend", "show")
        self.assertEqual(raw, {"expr": {"Literal": {"Value": "true"}}})

    def test_bool_property_encodes_0_as_false(self) -> None:
        data = self._bar_data()
        set_property(data, "legend.show", "0", VISUAL_PROPERTIES)
        raw = self._get_raw(data, "legend", "show")
        self.assertEqual(raw, {"expr": {"Literal": {"Value": "false"}}})

    def test_number_property_encodes_as_float_literal(self) -> None:
        data = self._bar_data()
        set_property(data, "dataPoint.fillTransparency", "50", VISUAL_PROPERTIES)
        raw = self._get_raw(data, "dataPoint", "fillTransparency")
        self.assertEqual(raw, {"expr": {"Literal": {"Value": "50.0D"}}})

    def test_integer_property_encodes_as_long_literal(self) -> None:
        """Schema 'int' type should use L suffix (long), not D (double)."""
        data = self._card_data()
        set_property(data, "cardCalloutArea.paddingUniform", "10", VISUAL_PROPERTIES)
        raw = self._get_raw(data, "cardCalloutArea", "paddingUniform")
        self.assertEqual(raw, {"expr": {"Literal": {"Value": "10L"}}})

    def test_color_property_encodes_as_solid_structure(self) -> None:
        data = self._bar_data()
        set_property(data, "dataPoint.defaultColor", "#FF0000", VISUAL_PROPERTIES)
        raw = self._get_raw(data, "dataPoint", "defaultColor")
        self.assertIn("solid", raw)

    def test_enum_property_encodes_as_quoted_string(self) -> None:
        data = self._bar_data()
        set_property(data, "legend.position", "Top", VISUAL_PROPERTIES)
        raw = self._get_raw(data, "legend", "position")
        self.assertEqual(raw, {"expr": {"Literal": {"Value": "'Top'"}}})

    def test_fallback_to_inference_without_visual_type(self) -> None:
        """Without a visualType, inference is used (1 → number, not bool)."""
        data = {"visual": {}}
        set_property(data, "chart:legend.show", "1", VISUAL_PROPERTIES)
        raw = self._get_raw(data, "legend", "show")
        # Without schema, '1' is inferred as number → "1.0D"
        self.assertEqual(raw, {"expr": {"Literal": {"Value": "1.0D"}}})

    def test_schema_coercion_via_chart_prefix(self) -> None:
        """chart: prefix also uses schema-aware coercion."""
        data = self._bar_data()
        set_property(data, "chart:legend.show", "1", VISUAL_PROPERTIES)
        raw = self._get_raw(data, "legend", "show")
        self.assertEqual(raw, {"expr": {"Literal": {"Value": "true"}}})


# ── Schema-backed roles ────────────────────────────────────────────


class SchemaBackedRolesTests(unittest.TestCase):
    def test_supplements_missing_roles(self) -> None:
        roles = get_visual_roles("clusteredBarChart")
        role_names = [r["name"] for r in roles]
        self.assertIn("Category", role_names)
        self.assertIn("Y", role_names)
        self.assertIn("Gradient", role_names)
        self.assertIn("Rows", role_names)

    def test_handcrafted_descriptions_preserved(self) -> None:
        roles = get_visual_roles("clusteredBarChart")
        by_name = {r["name"]: r for r in roles}
        self.assertIn("Y axis", by_name["Category"]["description"])

    def test_schema_only_type(self) -> None:
        roles = get_visual_roles("heatMap")
        role_names = [r["name"] for r in roles]
        self.assertIn("Category", role_names)
        self.assertIn("Size", role_names)
        self.assertIn("Gradient", role_names)
        self.assertGreater(len(roles), 0)

    def test_schema_only_type_is_known(self) -> None:
        self.assertTrue(is_known_visual_type("heatMap"))
        self.assertTrue(is_known_visual_type("realTimeLineChart"))
        self.assertTrue(is_known_visual_type("shapeMap"))

    def test_kpi_trendline_role(self) -> None:
        roles = get_visual_roles("kpi")
        role_names = [r["name"] for r in roles]
        self.assertIn("TrendLine", role_names)
        self.assertNotIn("TrendAxis", role_names)

    def test_kpi_trendaxis_alias_resolves(self) -> None:
        self.assertEqual(normalize_visual_role("kpi", "TrendAxis"), "TrendLine")

    def test_visual_type_info_schema_backed_status(self) -> None:
        info = get_visual_type_info("heatMap")
        self.assertIsNotNone(info)
        self.assertEqual(info.status, "schema-backed")
        self.assertGreater(len(info.roles), 0)

    def test_list_visual_type_info_includes_schema_types(self) -> None:
        all_types = list_visual_type_info()
        type_names = [t.visual_type for t in all_types]
        self.assertIn("heatMap", type_names)
        self.assertIn("clusteredBarChart", type_names)

    def test_unknown_type_returns_empty_roles(self) -> None:
        roles = get_visual_roles("completelyFakeVisual")
        self.assertEqual(roles, [])

    def test_unknown_type_not_known(self) -> None:
        self.assertFalse(is_known_visual_type("completelyFakeVisual"))


# ── Schema-aware property listing ───────────────────────────────────


class SchemaPropertyListingTests(unittest.TestCase):
    def test_includes_schema_props_when_visual_type_set(self) -> None:
        props = list_properties(
            VISUAL_PROPERTIES, visual_type="cardVisual", group="chart"
        )
        schema_props = [p for p in props if "(schema)" in p[2]]
        self.assertGreater(len(schema_props), 100)

    def test_excludes_schema_props_without_visual_type(self) -> None:
        props = list_properties(VISUAL_PROPERTIES)
        schema_props = [p for p in props if "(schema)" in p[2]]
        self.assertEqual(len(schema_props), 0)

    def test_schema_props_filtered_to_visual_type(self) -> None:
        card_props = list_properties(
            VISUAL_PROPERTIES, visual_type="cardVisual", group="chart"
        )
        card_names = {p[0] for p in card_props}
        # zoom is a chart-only object that only exists on bar/column/line charts
        self.assertNotIn("zoom.show", card_names)
        self.assertNotIn("zoom.categoryMin", card_names)

        bar_props = list_properties(
            VISUAL_PROPERTIES, visual_type="clusteredBarChart", group="chart"
        )
        bar_names = {p[0] for p in bar_props}
        # zoom should appear in schema-derived props for bar charts
        self.assertIn("zoom.show", bar_names)
        self.assertIn("zoom.categoryMin", bar_names)

    def test_enum_values_are_tuples_of_strings(self) -> None:
        props = list_properties(
            VISUAL_PROPERTIES, visual_type="cardVisual", group="chart"
        )
        enum_props = [p for p in props if p[4] is not None]
        self.assertGreater(len(enum_props), 0)
        for name, vtype, desc, grp, enum_values in enum_props:
            for val in enum_values:
                self.assertIsInstance(
                    val, (str, int, float),
                    f"{name}: enum value {val!r} is {type(val).__name__}",
                )

    def test_schema_props_have_chart_group(self) -> None:
        props = list_properties(
            VISUAL_PROPERTIES, visual_type="cardVisual", group="chart"
        )
        for name, vtype, desc, grp, enum_values in props:
            if "(schema)" in desc:
                self.assertEqual(grp, "chart", f"{name} should have group 'chart'")


# ── Validate.py schema integration ──────────────────────────────────


class ValidateSchemaIntegrationTests(unittest.TestCase):
    def test_validate_visual_schema_catches_invalid_object(self) -> None:
        from pbi.validate import _validate_visual_schema

        issues = _validate_visual_schema(
            "cardVisual",
            {"legend": [{"properties": {"show": True}}]},
            "pages/p/visuals/v/visual.json",
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("legend", issues[0].message)
        self.assertEqual(issues[0].level, "warning")

    def test_validate_visual_schema_catches_invalid_property(self) -> None:
        from pbi.validate import _validate_visual_schema

        issues = _validate_visual_schema(
            "cardVisual",
            {"value": [{"properties": {"fontSiz": 12}}]},
            "pages/p/visuals/v/visual.json",
        )
        self.assertEqual(len(issues), 1)
        self.assertIn("fontSiz", issues[0].message)
        self.assertIn("Did you mean", issues[0].message)

    def test_validate_visual_schema_accepts_valid_objects(self) -> None:
        from pbi.validate import _validate_visual_schema

        issues = _validate_visual_schema(
            "clusteredBarChart",
            {
                "legend": [{"properties": {"show": True, "position": "Top"}}],
                "categoryAxis": [{"properties": {"show": True}}],
            },
            "pages/p/visuals/v/visual.json",
        )
        self.assertEqual(len(issues), 0)

    def test_validate_visual_schema_skips_unknown_type(self) -> None:
        from pbi.validate import _validate_visual_schema

        issues = _validate_visual_schema(
            "unknownCustomVisual",
            {"anything": [{"properties": {"whatever": True}}]},
            "pages/p/visuals/v/visual.json",
        )
        self.assertEqual(len(issues), 0)


# ── CLI integration ─────────────────────────────────────────────────


VISUAL_CONTAINER_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.7.0/schema.json"


class SchemaCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.pbip_path = self.root / "Sample.pbip"
        report_folder = self.root / "Sample.Report"
        definition = report_folder / "definition"
        pages_dir = definition / "pages"
        page_dir = pages_dir / "page001"
        (page_dir / "visuals").mkdir(parents=True)

        self.pbip_path.write_text(
            json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        )
        (definition / "report.json").write_text(
            json.dumps({"$schema": REPORT_SCHEMA, "themeCollection": {}, "layoutOptimization": "None"}) + "\n",
        )
        (page_dir / "page.json").write_text(
            json.dumps({
                "$schema": PAGE_SCHEMA,
                "name": "page001",
                "displayName": "Sales",
                "displayOption": "FitToPage",
                "width": 1280,
                "height": 720,
            }) + "\n",
        )
        (pages_dir / "pages.json").write_text(
            json.dumps({
                "$schema": PAGES_METADATA_SCHEMA,
                "pageOrder": ["page001"],
                "activePageName": "page001",
            }) + "\n",
        )

    def test_visual_properties_with_visual_type_shows_schema_props(self) -> None:
        result = self.runner.invoke(
            app, ["visual", "properties", "--visual-type", "cardVisual"]
        )
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("(schema)", result.stdout)
        self.assertIn("properties from PBI schema", result.stdout)

    def test_visual_properties_without_type_no_schema_props(self) -> None:
        result = self.runner.invoke(app, ["visual", "properties"])
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertNotIn("(schema)", result.stdout)

    def test_visual_types_shows_schema_backed(self) -> None:
        result = self.runner.invoke(app, ["visual", "types", "heatMap"])
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("schema-backed", result.stdout)

    def test_apply_auto_resolves_chart_property(self) -> None:
        # Create a bar chart
        create = self.runner.invoke(
            app,
            ["visual", "create", "Sales", "clusteredBarChart",
             "--project", str(self.pbip_path)],
        )
        self.assertEqual(create.exit_code, 0, create.stdout)

        # Find the visual name
        project = Project.find(self.pbip_path)
        page = project.find_page("Sales")
        visual = project.get_visuals(page)[0]

        # Apply YAML with schema-valid property (no chart: prefix)
        yaml_content = f"""
pages:
  - name: Sales
    visuals:
      - name: "{visual.name}"
        legend.show: false
"""
        result = self.runner.invoke(
            app,
            ["apply", "-", "--project", str(self.pbip_path)],
            input=yaml_content,
        )
        self.assertEqual(result.exit_code, 0, result.stdout)

        # Verify property was set
        project = Project.find(self.pbip_path)
        page = project.find_page("Sales")
        visual = project.get_visuals(page)[0]
        objects = visual.data.get("visual", {}).get("objects", {})
        self.assertIn("legend", objects)


if __name__ == "__main__":
    unittest.main()
