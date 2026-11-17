from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

from pbi.apply import apply_yaml
from pbi.bookmarks import create_bookmark, create_bookmark_group, export_bookmarks, get_bookmark, list_bookmarks
from pbi.columns import get_columns, rename_column, set_column_width
from pbi.drillthrough import configure_drillthrough, configure_tooltip_page
from pbi.export import export_yaml
from pbi.filters import add_topn_filter
from pbi.formatting import build_measure_format, set_conditional_format
from pbi.project import Project
from pbi.properties import VISUAL_PROPERTIES, get_property, set_property
from pbi.schema_refs import REPORT_SCHEMA
from pbi.styles import create_style
from pbi.themes import apply_theme, create_theme
from pbi.validate import validate_project
from pbi.report_authoring import ReportAuthoring


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
            page = ReportAuthoring(project).create_page("Demo")
            original = ReportAuthoring(project).create_visual(
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

    def test_full_report_round_trip_preserves_report_section_and_page_export_omits_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            ReportAuthoring(source).create_page("Demo")
            report = source.get_report_meta()
            report["annotations"] = [{"name": "README", "value": "hello"}]
            report["organizationCustomVisuals"] = [{"name": "Org Timeline", "path": "store/org.pbiviz"}]
            report["dataSourceVariables"] = '{"region":"EMEA"}'
            report["resourcePackages"] = [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [{"name": "logo.png", "path": "logo.png", "type": "Image"}],
                }
            ]
            (source.definition_folder / "report.json").write_text(
                json.dumps(report) + "\n",
                encoding="utf-8",
            )

            parsed = yaml.safe_load(export_yaml(source))
            self.assertIn("report", parsed)
            self.assertEqual(parsed["report"]["annotations"][0]["name"], "README")
            self.assertEqual(parsed["report"]["organizationCustomVisuals"][0]["name"], "Org Timeline")
            self.assertEqual(parsed["report"]["dataSourceVariables"], '{"region":"EMEA"}')

            page_only = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            self.assertNotIn("report", page_only)

            target = self._make_project(root / "target")
            result = apply_yaml(target, yaml.safe_dump(parsed, sort_keys=False))
            self.assertEqual(result.errors, [])

            target_report = target.get_report_meta()
            self.assertEqual(target_report["annotations"], [{"name": "README", "value": "hello"}])
            self.assertEqual(
                target_report["organizationCustomVisuals"],
                [{"name": "Org Timeline", "path": "store/org.pbiviz"}],
            )
            self.assertEqual(target_report["dataSourceVariables"], '{"region":"EMEA"}')
            self.assertEqual(target_report["resourcePackages"][0]["items"][0]["path"], "logo.png")

    def test_full_report_round_trip_preserves_theme_section_and_creates_theme_on_target(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            ReportAuthoring(source).create_page("Demo")

            theme = create_theme("Corporate")
            theme["visualStyles"] = {
                "columnChart": {
                    "*": {"legend": [{"show": True}]},
                    "Series": {
                        "legend": [
                            {
                                "complex": {
                                    "expr": {"ThemeDataColor": {"ColorId": 2}},
                                    "fallback": {"solid": {"color": "#123456"}},
                                }
                            }
                        ]
                    },
                }
            }
            theme_file = root / "corporate-theme.json"
            theme_file.write_text(json.dumps(theme, indent=2) + "\n", encoding="utf-8")
            apply_theme(source, theme_file)

            parsed = yaml.safe_load(export_yaml(source))
            self.assertIn("theme", parsed)
            self.assertEqual(parsed["theme"]["name"], "Corporate")
            self.assertEqual(
                parsed["theme"]["visualStyles"]["columnChart"]["Series"]["legend"][0]["complex"]["fallback"]["solid"]["color"],
                "#123456",
            )

            target = self._make_project(root / "target")
            result = apply_yaml(target, yaml.safe_dump(parsed, sort_keys=False))
            self.assertEqual(result.errors, [])

            target_spec = yaml.safe_load(export_yaml(target))
            self.assertIn("theme", target_spec)
            self.assertEqual(
                target_spec["theme"]["visualStyles"]["columnChart"]["Series"]["legend"][0]["complex"]["expr"]["ThemeDataColor"]["ColorId"],
                2,
            )

    def test_round_trip_preserves_topn_filters_via_raw_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = ReportAuthoring(source).create_page("Demo")
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

    def test_round_trip_preserves_selector_based_conditional_formatting_via_pbir_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            tables_dir = source.root / "Sample.SemanticModel" / "definition" / "tables"
            tables_dir.mkdir(parents=True)
            (tables_dir / "Customers.tmdl").write_text(
                "\n".join(
                    [
                        "table Customers",
                        "\tcolumn Region",
                        "\t\tdataType: string",
                        "\t\tlineageTag: c-1",
                        "\t\tsummarizeBy: none",
                        "\t\tsourceColumn: Region",
                    ]
                ) + "\n",
                encoding="utf-8",
            )

            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            ReportAuthoring(source).add_binding(visual, "Values", "Customers", "Region")
            set_conditional_format(
                visual.data,
                "values",
                "backColor",
                build_measure_format("Customers", "Region"),
                column="Customers.Region",
            )
            visual.save()

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            exported = spec["pages"][0]["visuals"][0]
            self.assertNotIn("chart:values.backColor [Customers.Region]", exported)
            self.assertIn("pbir", exported)

            target = self._make_project(root / "target")
            target_tables = target.root / "Sample.SemanticModel" / "definition" / "tables"
            target_tables.mkdir(parents=True)
            (target_tables / "Customers.tmdl").write_text(
                "\n".join(
                    [
                        "table Customers",
                        "\tcolumn Region",
                        "\t\tdataType: string",
                        "\t\tlineageTag: c-1",
                        "\t\tsummarizeBy: none",
                        "\t\tsourceColumn: Region",
                    ]
                ) + "\n",
                encoding="utf-8",
            )

            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False), overwrite=True)
            self.assertEqual(result.errors, [])
            self.assertEqual(result.warnings, [])

            issues = validate_project(target)
            schema_warnings = [issue.message for issue in issues if issue.message.startswith("Schema:")]
            self.assertEqual(schema_warnings, [])

    def test_round_trip_preserves_rich_bookmarks_and_updates_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            visual.save()

            first = create_bookmark(
                source,
                "Detailed View",
                page,
                [visual],
                hidden_visuals=["table1"],
                target_visuals=["table1"],
                exploration_state_patch={
                    "version": "1.0",
                    "sections": {
                        page.name: {
                            "visualContainers": {
                                "table1": {
                                    "orderBy": {"Direction": 2},
                                    "singleVisual": {
                                        "display": {"mode": "hidden"},
                                        "objects": {"title": {"show": True}},
                                        "projections": {"Values": [{"queryRef": "Product.Category"}]},
                                    },
                                }
                            }
                        }
                    },
                },
                options_patch={"customFlag": True},
            )
            second = create_bookmark(source, "Overview", page, [visual])
            create_bookmark_group(source, "Views", [first["name"], second["name"]])

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            self.assertIn("bookmarks", spec)
            exported = {entry["name"]: entry for entry in spec["bookmarks"]}
            self.assertEqual(exported["Detailed View"]["group"], "Views")
            self.assertEqual(exported["Detailed View"]["target"], ["table1"])
            self.assertEqual(exported["Detailed View"]["hide"], ["table1"])
            self.assertEqual(exported["Detailed View"]["state"]["version"], "1.0")
            self.assertIn("orderBy", exported["Detailed View"]["state"]["sections"]["Demo"]["visualContainers"]["table1"])
            self.assertTrue(exported["Detailed View"]["options"]["customFlag"])

            target = self._make_project(root / "target")
            yaml_content = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=120)
            first_apply = apply_yaml(target, yaml_content)
            second_apply = apply_yaml(target, yaml_content)

            self.assertEqual(first_apply.errors, [])
            self.assertEqual(second_apply.errors, [])
            bookmarks = list_bookmarks(target)
            self.assertEqual([bookmark.display_name for bookmark in bookmarks], ["Detailed View", "Overview"])
            self.assertEqual([bookmark.group for bookmark in bookmarks], ["Views", "Views"])

            bookmark = get_bookmark(target, "Detailed View")
            container = bookmark["explorationState"]["sections"][target.find_page("Demo").name]["visualContainers"]["table1"]
            self.assertEqual(container["orderBy"]["Direction"], 2)
            self.assertIn("objects", container["singleVisual"])
            self.assertIn("projections", container["singleVisual"])
            self.assertTrue(bookmark["options"]["customFlag"])

            reexported = export_bookmarks(target, page=target.find_page("Demo"))
            reexported_map = {entry["name"]: entry for entry in reexported}
            self.assertEqual(reexported_map["Detailed View"]["group"], "Views")
            self.assertIn("state", reexported_map["Detailed View"])

    def test_round_trip_preserves_visual_groups(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = ReportAuthoring(source).create_page("Demo")
            first = ReportAuthoring(source).create_visual(page, "cardVisual", x=10, y=10, width=120, height=80)
            first.data["name"] = "card1"
            first.save()
            second = ReportAuthoring(source).create_visual(page, "cardVisual", x=140, y=10, width=120, height=80)
            second.data["name"] = "card2"
            second.save()
            group = ReportAuthoring(source).create_group(page, [first, second], display_name="Cards")

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            visuals = spec["pages"][0]["visuals"]
            group_entry = next(vis for vis in visuals if vis.get("type") == "group")
            self.assertEqual(group_entry["name"], group.name)
            child_groups = {vis["name"]: vis.get("group") for vis in visuals if vis.get("type") != "group"}
            self.assertEqual(child_groups["card1"], group.name)
            self.assertEqual(child_groups["card2"], group.name)

            target = self._make_project(root / "target")
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))

            self.assertEqual(result.errors, [])
            demo = target.find_page("Demo")
            visuals = target.get_visuals(demo)
            groups = [vis for vis in visuals if "visualGroup" in vis.data]
            self.assertEqual(len(groups), 1)
            self.assertEqual(groups[0].name, group.name)
            child_map = {
                vis.name: vis.data.get("parentGroupName")
                for vis in visuals
                if "visualGroup" not in vis.data
            }
            self.assertEqual(child_map["card1"], group.name)
            self.assertEqual(child_map["card2"], group.name)

    def test_minimal_card_export_no_longer_needs_raw_visual_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "cardVisual", x=10, y=20, width=300, height=100)
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
            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            ReportAuthoring(source).add_binding(visual, "Values", "Product", "Category")
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
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "tableEx")
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

    def test_export_emits_style_reference_for_exact_preset_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            create_style(
                source,
                "card-standard",
                {
                    "background.color": "#112233",
                    "title.show": True,
                    "title.text": "Overview",
                },
            )
            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            set_property(visual.data, "background.color", "#112233", VISUAL_PROPERTIES)
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "title.text", "Overview", VISUAL_PROPERTIES)
            visual.save()

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            exported = spec["pages"][0]["visuals"][0]

            self.assertEqual(exported["style"], "card-standard")
            self.assertNotIn("background", exported)
            self.assertNotIn("title", exported)

            target = self._make_project(root / "target")
            create_style(
                target,
                "card-standard",
                {
                    "background.color": "#112233",
                    "title.show": True,
                    "title.text": "Overview",
                },
            )
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))
            self.assertEqual(result.errors, [])
            page = target.find_page("Demo")
            visual = target.find_visual(page, "card1")
            self.assertEqual(
                get_property(visual.data, "background.color", VISUAL_PROPERTIES),
                "#112233",
            )

    def test_export_keeps_explicit_properties_for_partial_preset_match(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = self._make_project(root)
            create_style(
                project,
                "card-standard",
                {
                    "background.color": "#112233",
                    "title.show": True,
                },
            )
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            set_property(visual.data, "background.color", "#112233", VISUAL_PROPERTIES)
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "title.text", "Extra", VISUAL_PROPERTIES)
            visual.save()

            spec = yaml.safe_load(export_yaml(project, page_filter="Demo"))
            exported = spec["pages"][0]["visuals"][0]

            self.assertNotIn("style", exported)
            self.assertEqual(exported["background"]["color"], "#112233")
            self.assertEqual(exported["title"]["text"], "Extra")

    def test_export_uses_canonical_page_property_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            page = ReportAuthoring(project).create_page("Demo")
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
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "barChart")
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
            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "tableEx")
            visual.data["name"] = "table1"
            ReportAuthoring(source).add_binding(visual, "Values", "Product", "Category")
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
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "tableEx")
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
            page = ReportAuthoring(source).create_page("Demo")
            visual = ReportAuthoring(source).create_visual(page, "actionButton")
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
            page = ReportAuthoring(source).create_page("Tip")
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

    def test_apply_resolves_page_refs_to_pages_created_later_in_the_spec(self) -> None:
        # The fixture harness covers page refs to existing pages. Here the
        # referenced pages come later in the same spec, so apply resolves
        # them in a second pass once every page exists.
        spec = """\
version: 1
pages:
- name: Home
  visuals:
  - name: btn1
    type: actionButton
    action:
      show: true
      type: Drillthrough
      drillthrough: Drill
  - name: chart1
    type: barChart
    tooltip:
      show: true
      type: ReportPage
      section: Tip
- name: Drill
- name: Tip
"""
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            result = apply_yaml(project, spec)
            self.assertEqual(result.errors, [])

            reloaded = Project.find(Path(tmp) / "Sample.pbip")
            home = reloaded.find_page("Home")
            button = reloaded.find_visual(home, "btn1")
            chart = reloaded.find_visual(home, "chart1")
            self.assertEqual(
                get_property(button.data, "action.drillthrough", VISUAL_PROPERTIES),
                reloaded.find_page("Drill").name,
            )
            self.assertEqual(
                get_property(chart.data, "tooltip.section", VISUAL_PROPERTIES),
                reloaded.find_page("Tip").name,
            )

    def test_apply_tooltip_shorthand_compiles_to_canonical_page_binding(self) -> None:
        spec = """\
version: 1
pages:
- name: Tip
  width: 400
  height: 300
  tooltip:
    fields:
    - Product.Category
"""
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            page = project.find_page("Tip")
            self.assertEqual(page.data["type"], "Tooltip")
            self.assertEqual(page.data["visibility"], "HiddenInViewMode")
            self.assertEqual(page.data["pageBinding"]["type"], "Tooltip")
            param = page.data["pageBinding"]["parameters"][0]["fieldExpr"]["Column"]
            self.assertEqual(param["Expression"]["SourceRef"]["Entity"], "Product")
            self.assertEqual(param["Property"], "Category")

    def test_export_apply_round_trip_preserves_drillthrough_page_binding(self) -> None:
        """Guessed shape: no Desktop sample has a ``CrossReport`` drillthrough page binding.

        The write shape is not verified against Desktop output (#85).
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self._make_project(root / "source")
            page = ReportAuthoring(source).create_page("Drill")
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

    def test_apply_drillthrough_shorthand_supports_cross_report(self) -> None:
        """Guessed shape: no Desktop sample has a ``CrossReport`` drillthrough page binding.

        The write shape is not verified against Desktop output (#85).
        """
        spec = """\
version: 1
pages:
- name: Drill
  drillthrough:
    fields:
    - Product.Category
    - Sales.Total Revenue (measure)
    crossReport: true
"""
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            page = project.find_page("Drill")
            self.assertEqual(page.data["type"], "Drillthrough")
            self.assertEqual(page.data["visibility"], "HiddenInViewMode")
            self.assertEqual(page.data["pageBinding"]["referenceScope"], "CrossReport")
            params = page.data["pageBinding"]["parameters"]
            self.assertEqual(len(params), 2)
            self.assertEqual(page.data["filterConfig"]["filters"][0]["name"], "drillFilter0")
            self.assertEqual(page.data["filterConfig"]["filters"][1]["name"], "drillFilter1")

    def test_configure_tooltip_page_clears_prior_drillthrough_filters(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = self._make_project(Path(tmp))
            page = ReportAuthoring(project).create_page("Switch")
            configure_drillthrough(page, [("Product", "Category", "column")])
            configure_tooltip_page(page, [("Product", "Category", "column")], width=320, height=240)
            page.save()

            self.assertEqual(page.data["type"], "Tooltip")
            self.assertEqual(page.data["pageBinding"]["type"], "Tooltip")
            self.assertEqual(page.data.get("filterConfig", {}).get("filters", []), [])


if __name__ == "__main__":
    unittest.main()
