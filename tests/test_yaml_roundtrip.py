from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from pbi.apply import apply_yaml
from pbi.columns import get_columns, rename_column, set_column_width
from pbi.drillthrough import configure_drillthrough, configure_tooltip_page
from pbi.export import export_yaml
from pbi.filters import add_topn_filter
from pbi.project import Project
from pbi.properties import VISUAL_PROPERTIES, set_property
from pbi.schema_refs import REPORT_SCHEMA


class YamlRoundTripTests(unittest.TestCase):
    def _make_project(self, root: Path) -> Project:
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
        return Project.find(pbip)

    def test_round_trip_preserves_float_geometry_and_unnamed_visual_identity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            page = project.create_page("Demo")
            original = project.create_visual(
                page,
                "textSlicer",
                x=9.5,
                y=20.25,
                width=300.75,
                height=100.5,
            )

            spec = export_yaml(project, page_filter="Demo")
            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            page = project.find_page("Demo")
            visuals = project.get_visuals(page)
            self.assertEqual(len(visuals), 1)
            self.assertEqual(visuals[0].folder.name, original.folder.name)
            self.assertEqual(visuals[0].position["x"], 9.5)
            self.assertEqual(visuals[0].position["width"], 300.75)

    def test_round_trip_preserves_topn_filters_via_raw_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Demo")
            add_topn_filter(
                page.data,
                "Customers",
                "Region",
                n=5,
                order_entity="Sales",
                order_prop="Total Revenue",
            )
            page.save()
            spec = export_yaml(source, page_filter="Demo")

            target = self._make_project(root / "target")
            result = apply_yaml(target, spec)

            self.assertEqual(result.errors, [])
            self.assertEqual(result.warnings, [])

            page = target.find_page("Demo")
            filters = page.data["filterConfig"]["filters"]
            self.assertEqual(len(filters), 1)
            self.assertEqual(filters[0]["type"], "TopN")

    def test_minimal_card_export_no_longer_needs_raw_visual_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Demo")
            visual = source.create_visual(page, "cardVisual", x=10, y=20, width=300, height=100)
            visual.data["name"] = "card1"
            visual.save()
            spec = export_yaml(source, page_filter="Demo")
            parsed = yaml.safe_load(spec)
            self.assertNotIn("pbir", parsed["pages"][0]["visuals"][0])

            target = self._make_project(root / "target")
            result = apply_yaml(target, spec)

            self.assertEqual(result.errors, [])
            page = target.find_page("Demo")
            visual = target.find_visual(page, "card1")
            self.assertEqual(visual.data["visual"]["objects"], {})
            self.assertNotIn("visualContainerObjects", visual.data["visual"])

    def test_apply_include_filter_keeps_include_type(self) -> None:
        spec = """\
version: 1
pages:
- name: Demo
  filters:
  - field: Product.Category
    type: Include
    values: [Bikes]
"""
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            page = project.find_page("Demo")
            filters = page.data["filterConfig"]["filters"]
            self.assertEqual(filters[0]["type"], "Include")
            self.assertEqual(filters[0]["howCreated"], "Include")

    def test_export_apply_round_trip_preserves_binding_display_names_and_widths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Demo")
            visual = source.create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            source.add_binding(visual, "Values", "Product", "Category")
            rename_column(visual, "Product.Category", "Category Label")
            set_column_width(visual, "Product.Category", 420)
            visual.save()

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            binding = spec["pages"][0]["visuals"][0]["bindings"]["Values"]
            self.assertEqual(
                binding,
                {
                    "field": "Product.Category",
                    "displayName": "Category Label",
                    "width": 420,
                },
            )
            self.assertNotIn("columnWidth", spec["pages"][0]["visuals"][0])

            target = self._make_project(root / "target")
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))

            self.assertEqual(result.errors, [])
            page = target.find_page("Demo")
            visual = target.find_visual(page, "table1")
            columns = get_columns(visual)
            self.assertEqual(len(columns), 1)
            self.assertEqual(columns[0].display_name, "Category Label")
            self.assertEqual(columns[0].width, 420.0)

    def test_export_uses_canonical_cli_property_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            page = project.create_page("Demo")
            visual = project.create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            set_property(visual.data, "title.color", "#112233", VISUAL_PROPERTIES)
            set_property(visual.data, "grid.horizontal", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "values.fontColor", "#111111", VISUAL_PROPERTIES)
            visual.save()

            spec = yaml.safe_load(export_yaml(project, page_filter="Demo"))
            exported = spec["pages"][0]["visuals"][0]

            self.assertEqual(exported["title"]["color"], "#112233")
            self.assertEqual(exported["grid"]["horizontal"], True)
            self.assertEqual(exported["values"]["fontColor"], "#111111")
            self.assertNotIn("fontColor", exported["title"])
            self.assertNotIn("gridHorizontal", exported["grid"])
            self.assertNotIn("fontColorPrimary", exported["values"])

    def test_export_uses_canonical_page_property_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            page = project.create_page("Demo")
            page.data.setdefault("objects", {})["background"] = [
                {
                    "properties": {
                        "color": {
                            "solid": {
                                "color": {
                                    "expr": {"Literal": {"Value": "'#123456'"}}
                                }
                            }
                        },
                        "transparency": {
                            "expr": {"Literal": {"Value": "15D"}}
                        },
                    }
                }
            ]
            page.save()

            spec = yaml.safe_load(export_yaml(project, page_filter="Demo"))
            exported = spec["pages"][0]
            self.assertEqual(exported["background"]["color"], "#123456")
            self.assertEqual(exported["background"]["transparency"], 15)

    def test_export_unknown_chart_property_uses_chart_prefix(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            set_property(visual.data, "chart:legend.seriesOrder", "descending", VISUAL_PROPERTIES)
            visual.save()

            spec = yaml.safe_load(export_yaml(project, page_filter="Demo"))
            exported = spec["pages"][0]["visuals"][0]
            self.assertEqual(exported["chart:legend.seriesOrder"], "descending")

            target = self._make_project(Path(tmp) / "target")
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))
            self.assertEqual(result.errors, [])

    def test_export_prunes_query_and_filter_state_already_represented_in_yaml(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Demo")
            visual = source.create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            source.add_binding(visual, "Values", "Product", "Category")
            set_column_width(visual, "Product.Category", 420)
            visual.data["filterConfig"] = {
                "filters": [
                    {
                        "name": "f1",
                        "field": {
                            "Column": {
                                "Expression": {"SourceRef": {"Entity": "Product"}},
                                "Property": "Category",
                            }
                        },
                        "type": "Categorical",
                    }
                ]
            }
            visual.save()

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            exported = spec["pages"][0]["visuals"][0]
            self.assertIn("bindings", exported)
            self.assertIn("filters", exported)
            self.assertNotIn("pbir", exported)

    def test_export_promotes_drill_filter_other_visuals_from_pbir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            page = project.create_page("Demo")
            visual = project.create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            visual.data["visual"]["drillFilterOtherVisuals"] = True
            visual.save()

            spec = yaml.safe_load(export_yaml(project, page_filter="Demo"))
            exported = spec["pages"][0]["visuals"][0]
            self.assertEqual(exported["drillFilterOtherVisuals"], True)
            self.assertNotIn("pbir", exported)

            target = self._make_project(Path(tmp) / "target")
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))
            self.assertEqual(result.errors, [])
            page = target.find_page("Demo")
            visual = target.find_visual(page, "table1")
            self.assertEqual(
                visual.data["visual"].get("drillFilterOtherVisuals"),
                True,
            )

    def test_export_action_button_uses_canonical_yaml_without_pbir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Demo")
            visual = source.create_visual(page, "actionButton")
            visual.data["name"] = "btn1"
            visual.data["howCreated"] = "InsertVisualButton"
            visual.data["visual"]["drillFilterOtherVisuals"] = True
            set_property(visual.data, "action.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "action.type", "Back", VISUAL_PROPERTIES)
            set_property(visual.data, "chart:icon.shapeType [default]", "back", VISUAL_PROPERTIES)
            set_property(visual.data, "chart:text.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "chart:text.text [default]", "Back Button", VISUAL_PROPERTIES)
            visual.save()

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            exported = spec["pages"][0]["visuals"][0]
            self.assertEqual(exported["action"]["type"], "Back")
            self.assertEqual(exported["chart:icon.shapeType [default]"], "back")
            self.assertEqual(exported["chart:text.show"], True)
            self.assertEqual(exported["chart:text.text [default]"], "Back Button")
            self.assertNotIn("pbir", exported)

            target = self._make_project(root / "target")
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))
            self.assertEqual(result.errors, [])
            page = target.find_page("Demo")
            visual = target.find_visual(page, "btn1")
            self.assertEqual(visual.data["visual"]["drillFilterOtherVisuals"], True)
            icon_entries = visual.data["visual"]["objects"]["icon"]
            self.assertEqual(icon_entries[0]["selector"]["id"], "default")
            self.assertIn("visualLink", visual.data["visual"]["visualContainerObjects"])

    def test_apply_simple_bindings_preserve_matching_pbir_projection_metadata(self) -> None:
        spec = """\
version: 1
pages:
- name: Demo
  visuals:
  - name: tbl
    type: tableEx
    bindings:
      Values:
      - Product.Category
    pbir:
      visual:
        visualType: tableEx
        query:
          queryState:
            Values:
              projections:
              - queryRef: Product.Category
                displayName: Category Label
                field:
                  Column:
                    Expression:
                      SourceRef:
                        Entity: Product
                    Property: Category
"""
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            page = project.find_page("Demo")
            visual = project.find_visual(page, "tbl")
            projection = visual.data["visual"]["query"]["queryState"]["Values"]["projections"][0]
            self.assertEqual(projection["displayName"], "Category Label")

    def test_export_apply_round_trip_preserves_tooltip_page_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Tip")
            configure_tooltip_page(page, [("Product", "Category", "column")], width=400, height=300)
            page.save()

            spec = export_yaml(source, page_filter="Tip")
            target = self._make_project(root / "target")
            result = apply_yaml(target, spec)

            self.assertEqual(result.errors, [])
            page = target.find_page("Tip")
            self.assertEqual(page.data["type"], "Tooltip")
            self.assertEqual(page.data["pageBinding"]["type"], "Tooltip")
            self.assertEqual(page.width, 400)
            self.assertEqual(page.height, 300)

    def test_export_apply_round_trip_preserves_drillthrough_page_binding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = source.create_page("Drill")
            configure_drillthrough(page, [("Product", "Category", "column")], cross_report=True)
            page.save()

            spec = export_yaml(source, page_filter="Drill")
            target = self._make_project(root / "target")
            result = apply_yaml(target, spec)

            self.assertEqual(result.errors, [])
            page = target.find_page("Drill")
            self.assertEqual(page.data["type"], "Drillthrough")
            self.assertEqual(page.data["pageBinding"]["type"], "Drillthrough")
            self.assertEqual(page.data["pageBinding"]["referenceScope"], "CrossReport")
            self.assertEqual(page.data["filterConfig"]["filters"][0]["name"], "drillFilter0")


if __name__ == "__main__":
    unittest.main()
