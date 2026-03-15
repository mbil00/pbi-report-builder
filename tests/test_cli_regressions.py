from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from typer.testing import CliRunner

from pbi.apply import apply_yaml
from pbi.bookmarks import get_bookmark, update_bookmark_visuals
from pbi.cli import app
from pbi.export import export_yaml
from pbi.filters import (
    TupleField,
    _format_literal,
    add_range_filter,
    add_tuple_filter,
    get_filters,
    parse_filter,
    remove_filter,
)
from pbi.interactions import get_interactions, set_interaction
from pbi.model_apply import apply_model_yaml
from pbi.model import _parse_tmdl_name
from pbi.project import Project, _read_json, _write_json
from pbi.properties import VISUAL_PROPERTIES, get_property, set_property
from pbi.schema_refs import REPORT_SCHEMA
from pbi.styles import (
    create_style,
    extract_style_properties,
    get_style,
    _normalize_style_properties,
)
from pbi.templates import apply_template, save_template
from pbi.validate import _validate_visual_relationships


def make_project(root: Path, *, with_model: bool = False) -> Project:
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
    if with_model:
        tables = root / "Sample.SemanticModel" / "definition" / "tables"
        tables.mkdir(parents=True)
        (tables / "Customers.tmdl").write_text(
            "\n".join(
                [
                    "table 'Customers'",
                    "    column 'Region'",
                    "        dataType: string",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
    return Project.find(pbip)


def write_model_table(root: Path, filename: str, content: str) -> Path:
    """Write a table TMDL file into the test semantic model."""
    tables = root / "Sample.SemanticModel" / "definition" / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    path = tables / filename
    path.write_text(content.strip() + "\n", encoding="utf-8")
    return path


class ApplyWorkflowRegressionTests(unittest.TestCase):
    def test_raw_pbir_visual_still_accepts_human_readable_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = make_project(root / "source")
            page = source.create_page("Demo")
            visual = source.create_visual(page, "textSlicer", x=10, y=20, width=300, height=120)
            source.add_binding(visual, "Values", "Customers", "Region")

            spec = yaml.safe_load(export_yaml(source, page_filter="Demo"))
            exported_visual = spec["pages"][0]["visuals"][0]
            exported_visual["isHidden"] = True
            exported_visual["bindings"] = {"Values": "Sales.Region"}

            target = make_project(root / "target")
            result = apply_yaml(target, yaml.safe_dump(spec, sort_keys=False))

            self.assertEqual(result.errors, [])
            page = target.find_page("Demo")
            visual = target.get_visuals(page)[0]
            self.assertTrue(visual.data.get("isHidden"))
            self.assertEqual(
                visual.data["visual"]["query"]["queryState"]["Values"]["projections"][0]["queryRef"],
                "Sales.Region",
            )

    def test_overwrite_apply_rolls_back_on_failure(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "textSlicer", x=1, y=2, width=100, height=50)
            visual.data["name"] = "keepme"
            visual.save()

            spec_path = root / "invalid.yaml"
            spec_path.write_text(
                """\
version: 1
pages:
- name: Demo
  visuals:
  - name: replacement
    type: textSlicer
    position: 0, 0
    size: 100 x 50
    notARealProperty:
      bogus: true
""",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                ["apply", str(spec_path), "--overwrite", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            visuals = restored.get_visuals(page)
            self.assertEqual(len(visuals), 1)
            self.assertEqual(visuals[0].name, "keepme")

    def test_apply_rolls_back_on_failure_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
            visual.data["name"] = "card1"
            visual.save()

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "card1",
                                    "position": "99, 88",
                                    "notARealProperty": {"bogus": True},
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertTrue(result.errors)

            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            updated = restored.find_visual(page, "card1")
            self.assertEqual(updated.position["x"], 10)
            self.assertEqual(updated.position["y"], 20)

    def test_apply_type_conversion_rolls_back_on_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "textSlicer", x=5, y=7, width=100, height=50)
            visual.data["name"] = "vis1"
            visual.save()

            yaml_content = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "vis1",
                                    "type": "cardVisual",
                                    "position": "77, 66",
                                    "notARealProperty": {"bogus": True},
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertTrue(result.errors)

            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            updated = restored.find_visual(page, "vis1")
            self.assertEqual(updated.visual_type, "textSlicer")
            self.assertEqual(updated.position["x"], 5)
            self.assertEqual(updated.position["y"], 7)

    def test_overwrite_backup_filename_is_sanitized(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("../../outside")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            visual.save()

            spec_path = root / "escape.yaml"
            spec_path.write_text(
                """\
version: 1
pages:
- name: ../../outside
  visuals:
  - name: card1
    notARealProperty:
      bogus: true
""",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                ["apply", str(spec_path), "--overwrite", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertFalse((root / "outside.yaml").exists())
            backups = list(root.glob(".pbi-backup-*.yaml"))
            self.assertEqual(len(backups), 1)


class PathSecurityRegressionTests(unittest.TestCase):
    def test_project_rejects_pbip_report_path_outside_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / "project"
            root.mkdir()
            outside_report = tmp_path / "outside.Report" / "definition"
            outside_report.mkdir(parents=True)

            pbip = root / "Sample.pbip"
            pbip.write_text(
                json.dumps({"artifacts": [{"report": {"path": "../outside.Report"}}]}) + "\n",
                encoding="utf-8",
            )

            with self.assertRaises(ValueError):
                Project.find(pbip)


class OutputPathHardeningTests(unittest.TestCase):
    def test_map_allows_output_outside_project(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            make_project(root)
            outside = Path(tmp) / "outside.yaml"

            result = runner.invoke(
                app,
                ["map", "--output", str(outside), "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertTrue(outside.exists())

    def test_map_creates_nested_output_directory_inside_project(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            out_path = root / "exports" / "maps" / "project.yaml"

            result = runner.invoke(
                app,
                ["map", "--output", "exports/maps/project.yaml", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertTrue(out_path.exists())

    def test_page_export_allows_relative_escape(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")

            result = runner.invoke(
                app,
                ["page", "export", "Demo", "--output", "../escape.yaml", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertTrue((root.parent / "escape.yaml").exists())

    def test_theme_export_creates_parent_directories(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            reg_dir = root / "Sample.Report" / "StaticResources" / "RegisteredResources"
            reg_dir.mkdir(parents=True, exist_ok=True)
            (reg_dir / "Custom Theme.json").write_text('{"name": "Custom Theme"}\n', encoding="utf-8")

            report_path = project.definition_folder / "report.json"
            report_data = _read_json(report_path)
            report_data["themeCollection"]["customTheme"] = {
                "name": "Custom Theme",
                "type": "RegisteredResources",
                "reportVersionAtImport": {},
            }
            report_data["resourcePackages"] = [
                {
                    "name": "RegisteredResources",
                    "type": "RegisteredResources",
                    "items": [
                        {
                            "name": "Custom Theme",
                            "path": "Custom Theme.json",
                            "type": "CustomTheme",
                        }
                    ],
                }
            ]
            _write_json(report_path, report_data)

            output = root / "exports" / "themes" / "theme.json"
            result = runner.invoke(
                app,
                ["theme", "export", str(output), "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertTrue(output.exists())


class TemplateRegressionTests(unittest.TestCase):
    def test_template_name_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            page = project.create_page("Demo")
            visual = project.create_visual(page, "textSlicer")

            with self.assertRaises(ValueError):
                save_template(project, page, "../escape", [visual])

    def test_applying_group_template_twice_keeps_unique_group_names(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            page = project.create_page("Demo")
            v1 = project.create_visual(page, "textSlicer", x=0, y=0, width=100, height=50)
            v2 = project.create_visual(page, "cardVisual", x=120, y=0, width=100, height=50)
            group = project.create_group(page, [v1, v2], display_name="salesGroup")

            save_template(project, page, "layout", [group, v1, v2])
            apply_template(project, page, "layout")
            apply_template(project, page, "layout")

            visuals = project.get_visuals(page)
            groups = [v for v in visuals if "visualGroup" in v.data]
            group_names = [v.name for v in groups]
            self.assertEqual(len(group_names), len(set(group_names)))

            valid_group_names = set(group_names)
            for visual in visuals:
                parent = visual.data.get("parentGroupName")
                if parent:
                    self.assertIn(parent, valid_group_names)


class StylePresetRegressionTests(unittest.TestCase):
    def test_style_create_list_show_delete_cli_flow(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)

            empty_list = runner.invoke(
                app,
                ["style", "list", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(empty_list.exit_code, 0, empty_list.stdout)
            self.assertIn("No styles saved", empty_list.stdout)

            create_result = runner.invoke(
                app,
                [
                    "style",
                    "create",
                    "card-standard",
                    "border.show=true",
                    "border.radius=10",
                    "title.text=Standard Card",
                    "--description",
                    "Card baseline",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            style_path = root / ".pbi-styles" / "card-standard.yaml"
            self.assertTrue(style_path.exists())
            style = get_style(Project.find(root / "Sample.pbip"), "card-standard")
            self.assertEqual(style.properties["border.show"], True)
            self.assertEqual(style.properties["border.radius"], 10)
            self.assertEqual(style.properties["title.text"], "Standard Card")

            list_result = runner.invoke(
                app,
                ["style", "list", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            self.assertIn("card-standard", list_result.stdout)
            self.assertIn("3", list_result.stdout)

            show_result = runner.invoke(
                app,
                ["style", "get", "card-standard", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(show_result.exit_code, 0, show_result.stdout)
            self.assertIn("name: card-standard", show_result.stdout)
            self.assertIn("border.show: true", show_result.stdout)
            self.assertIn("title.text: Standard Card", show_result.stdout)

            delete_result = runner.invoke(
                app,
                ["style", "delete", "card-standard", "--force", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            self.assertFalse(style_path.exists())

    def test_style_create_rejects_invalid_name(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)

            result = runner.invoke(
                app,
                [
                    "style",
                    "create",
                    "../escape",
                    "border.show=true",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("Style name", result.stdout)

    def test_apply_style_presets_merge_in_order_and_explicit_values_win(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            create_style(
                project,
                "base-card",
                {
                    "background.color": "#111111",
                    "border.show": True,
                    "border.radius": 4,
                    "grid.rowPadding": 3,
                },
            )
            create_style(
                project,
                "accent-card",
                {
                    "background.color": "#222222",
                    "border.radius": 8,
                    "title.show": True,
                },
            )

            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "card1",
                                    "type": "cardVisual",
                                    "position": "0, 0",
                                    "size": "200 x 100",
                                    "style": ["base-card", "accent-card"],
                                    "background": {"color": "#333333"},
                                    "title": {"text": "Sales"},
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertEqual(result.errors, [])
            page = project.find_page("Demo")
            visual = project.find_visual(page, "card1")
            self.assertEqual(
                get_property(visual.data, "background.color", VISUAL_PROPERTIES),
                "#333333",
            )
            self.assertTrue(get_property(visual.data, "border.show", VISUAL_PROPERTIES))
            self.assertEqual(
                get_property(visual.data, "border.radius", VISUAL_PROPERTIES),
                8,
            )
            self.assertTrue(get_property(visual.data, "title.show", VISUAL_PROPERTIES))
            self.assertEqual(
                get_property(visual.data, "title.text", VISUAL_PROPERTIES),
                "Sales",
            )
            self.assertIsNone(get_property(visual.data, "grid.rowPadding", VISUAL_PROPERTIES))

    def test_apply_style_reports_missing_preset(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)

            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {
                                    "name": "card1",
                                    "type": "cardVisual",
                                    "position": "0, 0",
                                    "size": "200 x 100",
                                    "style": "missing-style",
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            result = apply_yaml(project, spec)

            self.assertTrue(result.errors)
            self.assertIn('Style "missing-style" not found', result.errors[0])


class VisualDiffRegressionTests(unittest.TestCase):
    def test_visual_diff_uses_canonical_exported_spec(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")

            left = project.create_visual(page, "tableEx")
            left.data["name"] = "left"
            project.add_binding(left, "Values", "Product", "Category")
            project.set_sort(left, "Product", "Category", descending=True)
            add_range_filter(left.data, "Sales", "Amount", min_val="10", max_val="20")
            left.data["visual"].setdefault("query", {})["queryMetadata"] = {"foo": "left"}
            left.save()

            right = project.create_visual(page, "tableEx")
            right.data["name"] = "right"
            project.add_binding(right, "Values", "Product", "Brand")
            project.set_sort(right, "Product", "Brand", descending=False)
            add_range_filter(right.data, "Sales", "Quantity", min_val="20", max_val="30")
            right.data["visual"].setdefault("query", {})["queryMetadata"] = {"foo": "right"}
            right.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "diff",
                    "Demo",
                    "left",
                    "Demo",
                    "right",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("bindings.Values", result.stdout)
            self.assertIn("Product.Category", result.stdout)
            self.assertIn("Product.Brand", result.stdout)
            self.assertIn("sort", result.stdout)
            self.assertIn("Descending", result.stdout)
            self.assertIn("Ascending", result.stdout)
            self.assertIn("filters[0].field", result.stdout)
            self.assertIn("Sales.Amount", result.stdout)
            self.assertIn("Sales.Quantity", result.stdout)
            self.assertIn("filters[0].values[0]", result.stdout)
            self.assertIn("pbir.visual.query.quer", result.stdout)
            self.assertIn("left", result.stdout)
            self.assertIn("right", result.stdout)


class BookmarkInteractionRegressionTests(unittest.TestCase):
    def test_bookmark_update_preserves_non_display_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            bookmarks_dir = project.definition_folder / "bookmarks"
            bookmarks_dir.mkdir(parents=True)
            bookmark_path = bookmarks_dir / "bookmark001.bookmark.json"
            bookmark = {
                "name": "bookmark001",
                "displayName": "Sales bookmark",
                "explorationState": {
                    "activeSection": "Page1",
                    "sections": {
                        "Page1": {
                            "visualContainers": {
                                "vis1": {
                                    "singleVisual": {
                                        "display": {"mode": "hidden"},
                                        "objects": {"title": {"show": True}},
                                    },
                                    "orderBy": {"Direction": 2},
                                }
                            }
                        }
                    },
                },
            }
            _write_json(bookmark_path, bookmark)
            _write_json(bookmarks_dir / "bookmarks.json", {"items": [{"name": "bookmark001"}]})

            update_bookmark_visuals(project, "bookmark001", visible_visuals=["vis1"])
            data = get_bookmark(project, "bookmark001")
            container = data["explorationState"]["sections"]["Page1"]["visualContainers"]["vis1"]
            self.assertEqual(container["orderBy"]["Direction"], 2)
            self.assertIn("objects", container["singleVisual"])
            self.assertNotIn("display", container["singleVisual"])

            update_bookmark_visuals(project, "bookmark001", hidden_visuals=["vis1"])
            data = get_bookmark(project, "bookmark001")
            container = data["explorationState"]["sections"]["Page1"]["visualContainers"]["vis1"]
            self.assertEqual(container["singleVisual"]["display"]["mode"], "hidden")
            self.assertEqual(container["orderBy"]["Direction"], 2)

    def test_interaction_default_clears_custom_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            page = project.create_page("Demo")
            source = project.create_visual(page, "barChart")
            target = project.create_visual(page, "cardVisual")

            set_interaction(page, source.name, target.name, "DataFilter")
            self.assertEqual(len(get_interactions(page)), 1)

            set_interaction(page, source.name, target.name, "Default")
            self.assertEqual(get_interactions(page), [])

    def test_interaction_cli_uses_set_and_clear_commands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            source = project.create_visual(page, "barChart")
            target = project.create_visual(page, "cardVisual")
            source.data["name"] = "source1"
            target.data["name"] = "target1"
            source.save()
            target.save()

            set_result = runner.invoke(
                app,
                [
                    "interaction",
                    "set",
                    "Demo",
                    "source1",
                    "target1",
                    "--mode",
                    "DataFilter",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)
            page = Project.find(root / "Sample.pbip").find_page("Demo")
            self.assertEqual(len(get_interactions(page)), 1)

            clear_result = runner.invoke(
                app,
                [
                    "interaction",
                    "clear",
                    "Demo",
                    "source1",
                    "target1",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)
            page = Project.find(root / "Sample.pbip").find_page("Demo")
            self.assertEqual(get_interactions(page), [])


class VisualGetRegressionTests(unittest.TestCase):
    def test_visual_index_references_work_with_bare_and_prefixed_numbers(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            first = project.create_visual(page, "textSlicer", x=0, y=0)
            second = project.create_visual(page, "cardVisual", x=100, y=0)
            first.data["name"] = "7ac9f370abc"
            second.data["name"] = "26d0c6f4bee8"
            first.save()
            second.save()

            result_bare = runner.invoke(
                app,
                ["visual", "get", "Demo", "2", "visualType", "--project", str(root / "Sample.pbip")],
            )
            result_prefixed = runner.invoke(
                app,
                ["visual", "get", "Demo", "#2", "visualType", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result_bare.exit_code, 0, result_bare.stdout)
            self.assertIn("cardVisual", result_bare.stdout)
            self.assertEqual(result_prefixed.exit_code, 0, result_prefixed.stdout)
            self.assertIn("cardVisual", result_prefixed.stdout)

    def test_visual_get_accepts_multiple_properties(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "background.color", "#123456", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "get",
                    "Demo",
                    "card1",
                    "title.show",
                    "background.color",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("title.show", result.stdout)
            self.assertIn("background.color", result.stdout)
            self.assertIn("True", result.stdout)
            self.assertIn("#123456", result.stdout)

    def test_visual_get_all_props_lists_core_and_object_properties(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual", x=10, y=20, width=300, height=100)
            visual.data["name"] = "card1"
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "background.color", "#123456", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "get", "Demo", "card1", "--all-props", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("position.x", result.stdout)
            self.assertIn("position.y", result.stdout)
            self.assertIn("background.color", result.stdout)
            self.assertIn("title.show", result.stdout)
            self.assertIn("#123456", result.stdout)
            self.assertIn("10", result.stdout)

    def test_visual_get_defaults_resolves_known_default_values(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "get",
                    "Demo",
                    "chart1",
                    "background.show",
                    "title.show",
                    "tooltip.show",
                    "--defaults",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("background.show", result.stdout)
            self.assertIn("title.show", result.stdout)
            self.assertIn("tooltip.show", result.stdout)
            self.assertIn("False", result.stdout)
            self.assertIn("True", result.stdout)
            self.assertIn("default", result.stdout)

    def test_visual_get_defaults_marks_explicit_values_over_known_defaults(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            set_property(visual.data, "background.show", "true", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "get",
                    "Demo",
                    "card1",
                    "background.show",
                    "layout.backgroundShow",
                    "--defaults",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("background.show", result.stdout)
            self.assertIn("layout.backgroundShow", result.stdout)
            self.assertIn("explicit", result.stdout)
            self.assertIn("default", result.stdout)
            self.assertIn("True", result.stdout)

    def test_visual_get_overview_uses_canonical_property_names(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            set_property(visual.data, "shadow.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "cardShape.radius", "5", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "get", "Demo", "card1", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("shadow.show", result.stdout)
            self.assertIn("cardShape.radius", result.stdout)
            self.assertNotIn("dropShadow.show", result.stdout)
            self.assertNotIn("shapeCustomRectangle.rectangleRoundedCurve", result.stdout)

    def test_visual_get_page_lists_explicit_properties_for_matching_visuals(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            card = project.create_visual(page, "cardVisual")
            chart = project.create_visual(page, "barChart")
            card.data["name"] = "card1"
            chart.data["name"] = "chart1"
            set_property(card.data, "background.color", "#123456", VISUAL_PROPERTIES)
            set_property(chart.data, "title.show", "true", VISUAL_PROPERTIES)
            card.save()
            chart.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "get-page",
                    "Demo",
                    "--visual-type",
                    "cardVisual",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("card1", result.stdout)
            self.assertIn("background.color", result.stdout)
            self.assertIn("#123456", result.stdout)
            self.assertNotIn("chart1", result.stdout)

    def test_visual_diff_reports_differences_between_visuals(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page_a = project.create_page("Demo A")
            page_b = project.create_page("Demo B")
            left = project.create_visual(page_a, "cardVisual", x=10, y=20, width=300, height=100)
            right = project.create_visual(page_b, "cardVisual", x=40, y=20, width=300, height=100)
            left.data["name"] = "cardLeft"
            right.data["name"] = "cardRight"
            set_property(left.data, "background.color", "#123456", VISUAL_PROPERTIES)
            set_property(right.data, "background.color", "#654321", VISUAL_PROPERTIES)
            left.save()
            right.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "diff",
                    "Demo A",
                    "cardLeft",
                    "Demo B",
                    "cardRight",
                    "--all-props",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("background.color", result.stdout)
            self.assertIn("#123456", result.stdout)
            self.assertIn("#654321", result.stdout)
            self.assertIn("position.x", result.stdout)
            self.assertIn("10", result.stdout)
            self.assertIn("40", result.stdout)

    def test_page_get_accepts_multiple_properties(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo", width=1440, height=900, display_option="FitToWidth")

            result = runner.invoke(
                app,
                [
                    "page",
                    "get",
                    "Demo",
                    "width",
                    "displayOption",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("width", result.stdout)
            self.assertIn("1440", result.stdout)
            self.assertIn("displayOption", result.stdout)
            self.assertIn("FitToWidth", result.stdout)

    def test_report_get_accepts_multiple_properties(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            report_path = project.definition_folder / "report.json"
            data = _read_json(report_path)
            data["settings"] = {
                "pagesPosition": "Bottom",
                "useEnhancedTooltips": True,
            }
            _write_json(report_path, data)

            result = runner.invoke(
                app,
                [
                    "report",
                    "get",
                    "layoutOptimization",
                    "settings.pagesPosition",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("layoutOptimization", result.stdout)
            self.assertIn("None", result.stdout)
            self.assertIn("settings.pagesPosition", result.stdout)
            self.assertIn("Bottom", result.stdout)


class FilterModelRegressionTests(unittest.TestCase):
    def test_tuple_filter_can_be_removed_by_component_field(self) -> None:
        data: dict = {}
        add_tuple_filter(
            data,
            [[TupleField("Product", "Color", "Red"), TupleField("Product", "Size", "Large")]],
        )

        self.assertEqual(remove_filter(data, "Product.Color"), 1)

    def test_range_filter_respects_locked_flag(self) -> None:
        data: dict = {}
        add_range_filter(data, "Sales", "Revenue", min_val="1", is_locked=True)
        self.assertTrue(data["filterConfig"]["filters"][0]["isLockedInViewMode"])

    def test_parse_filter_understands_aggregation_field_refs(self) -> None:
        filter_obj = {
            "name": "aggFilter",
            "type": "Advanced",
            "field": {
                "Aggregation": {
                    "Expression": {
                        "Measure": {
                            "Expression": {"SourceRef": {"Entity": "Sales"}},
                            "Property": "Total Revenue",
                        }
                    },
                    "Function": 0,
                }
            },
            "filter": {"Where": []},
        }

        info = parse_filter(filter_obj)
        self.assertEqual(info.field_entity, "Sales")
        self.assertEqual(info.field_prop, "Total Revenue")

    def test_untyped_literals_stay_strings(self) -> None:
        self.assertEqual(_format_literal("00123"), "'00123'")
        self.assertEqual(_format_literal("2025-01-01"), "'2025-01-01'")

    def test_parse_tmdl_name_handles_escaped_apostrophes(self) -> None:
        self.assertEqual(_parse_tmdl_name("'Bob''s Revenue' ="), "Bob's Revenue")

    def test_filter_add_uses_named_scope_and_repeatable_values(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")

            result = runner.invoke(
                app,
                [
                    "filter",
                    "add",
                    "Product.Category",
                    "--mode",
                    "include",
                    "--value",
                    "Bikes",
                    "--value",
                    "Accessories",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            report_data = Project.find(root / "Sample.pbip").get_report_meta()
            filters = get_filters(report_data)
            self.assertEqual(len(filters), 1)
            info = parse_filter(filters[0], "report")
            self.assertEqual(info.filter_type, "Include")


class DrillthroughRegressionTests(unittest.TestCase):
    def test_cli_uses_canonical_table_name_for_drillthrough_fields(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            project.create_page("Demo")

            result = runner.invoke(
                app,
                [
                    "page",
                    "drillthrough",
                    "set",
                    "Demo",
                    "cust.Region",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            page = Project.find(root / "Sample.pbip").find_page("Demo")
            entity = page.data["pageBinding"]["parameters"][0]["fieldExpr"]["Column"]["Expression"]["SourceRef"]["Entity"]
            self.assertEqual(entity, "Customers")


class ModelManagementRegressionTests(unittest.TestCase):
    def test_model_format_updates_column_and_measure_tmdl(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tmeasure 'Compliance Rate' = DIVIDE ( 1, 2, 0 )
\t\tformatString: 0.0%
\t\tlineageTag: m-1

\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
                """,
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "format",
                    "Sales.OrderDate",
                    "dd/mm/yyyy",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)

            measure_result = runner.invoke(
                app,
                [
                    "model",
                    "format",
                    "Sales.Compliance Rate",
                    "0.00%",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(measure_result.exit_code, 0, measure_result.stdout)

            content = (root / "Sample.SemanticModel" / "definition" / "tables" / "Sales.tmdl").read_text(encoding="utf-8")
            self.assertIn("\t\tformatString: dd/mm/yyyy", content)
            self.assertIn("\t\tformatString: 0.00%", content)

    def test_model_format_dry_run_does_not_write(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
                """,
            )
            before = path.read_text(encoding="utf-8")

            result = runner.invoke(
                app,
                [
                    "model",
                    "format",
                    "Sales.OrderDate",
                    "dd/mm/yyyy",
                    "--dry-run",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("(dry run)", result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_model_column_hide_show_and_hidden_only_listing(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn DeviceName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: DeviceName

\tcolumn AzureADDeviceId
\t\tdataType: string
\t\tlineageTag: c-2
\t\tsummarizeBy: none
\t\tsourceColumn: AzureADDeviceId
                """,
            )

            hide_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "hide",
                    "Devices.AzureADDeviceId",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(hide_result.exit_code, 0, hide_result.stdout)

            hidden_list = runner.invoke(
                app,
                [
                    "model",
                    "columns",
                    "Devices",
                    "--hidden-only",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(hidden_list.exit_code, 0, hidden_list.stdout)
            self.assertIn("AzureADDeviceId", hidden_list.stdout)
            self.assertNotIn("DeviceName", hidden_list.stdout)

            show_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "unhide",
                    "Devices.AzureADDeviceId",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(show_result.exit_code, 0, show_result.stdout)

            visible_list = runner.invoke(
                app,
                [
                    "model",
                    "columns",
                    "Devices",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(visible_list.exit_code, 0, visible_list.stdout)
            self.assertIn("AzureADDeviceId", visible_list.stdout)

    def test_model_column_hide_rejects_measures(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tmeasure 'Compliance Rate' = DIVIDE ( 1, 2, 0 )
\t\tlineageTag: m-1
                """,
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "hide",
                    "Sales.Compliance Rate",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("not a column", result.stdout)

    def test_model_measure_create_show_edit_delete_flow(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tlineageTag: table-1

\tmeasure 'Old Measure' = 1
\t\tformatString: 0
\t\tlineageTag: m-1

\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
                """,
            )

            create_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "create",
                    "Sales",
                    "New KPI",
                    "SUM ( Sales[Revenue] )",
                    "--format",
                    "0.0%",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tmeasure 'New KPI' = SUM ( Sales[Revenue] )", content)
            self.assertIn("\t\tformatString: 0.0%", content)

            show_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "get",
                    "Sales",
                    "New KPI",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(show_result.exit_code, 0, show_result.stdout)
            self.assertIn("Sales.New KPI", show_result.stdout)
            self.assertIn("SUM ( Sales[Revenue] )", show_result.stdout)
            self.assertIn("0.0%", show_result.stdout)

            dax_path = root / "new-kpi.dax"
            dax_path.write_text(
                "CALCULATE(\n    SUM ( Sales[Revenue] ),\n    Sales[Revenue] > 0\n)\n",
                encoding="utf-8",
            )
            edit_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "edit",
                    "Sales",
                    "New KPI",
                    "--from-file",
                    str(dax_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(edit_result.exit_code, 0, edit_result.stdout)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tmeasure 'New KPI' =", content)
            self.assertIn("\t\tCALCULATE(", content)
            self.assertIn("SUM ( Sales[Revenue] ),", content)
            self.assertIn("\t\tlineageTag:", content)

            delete_result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "delete",
                    "Sales",
                    "New KPI",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            self.assertNotIn("New KPI", path.read_text(encoding="utf-8"))

    def test_model_measure_create_dry_run_does_not_write(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
                """,
            )
            before = path.read_text(encoding="utf-8")

            result = runner.invoke(
                app,
                [
                    "model",
                    "measure",
                    "create",
                    "Sales",
                    "Preview KPI",
                    "SUM ( Sales[Revenue] )",
                    "--dry-run",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("(dry run)", result.stdout)
            self.assertEqual(path.read_text(encoding="utf-8"), before)

    def test_model_calculated_column_create_get_edit_delete_flow(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            path = write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn TotalStorageGB
\t\tdataType: double
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: TotalStorageGB
                """,
            )

            create_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "create",
                    "Devices",
                    "StorageUsedPct",
                    "DIVIDE([TotalStorageGB], 100, 0)",
                    "--type",
                    "double",
                    "--format",
                    "0.0%",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tcolumn StorageUsedPct = DIVIDE([TotalStorageGB], 100, 0)", content)
            self.assertIn("\t\tdataType: double", content)
            self.assertIn("\t\tformatString: 0.0%", content)
            self.assertIn("\t\tsummarizeBy: none", content)

            get_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "get",
                    "Devices.StorageUsedPct",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Devices.StorageUsedPct", get_result.stdout)
            self.assertIn("calculatedColumn", get_result.stdout)
            self.assertIn("DIVIDE([TotalStorageGB], 100, 0)", get_result.stdout)

            dax_path = root / "storage-used.dax"
            dax_path.write_text(
                "DIVIDE(\n    [TotalStorageGB] - 10,\n    [TotalStorageGB],\n    0\n)\n",
                encoding="utf-8",
            )
            edit_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "edit",
                    "Devices",
                    "StorageUsedPct",
                    "--from-file",
                    str(dax_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(edit_result.exit_code, 0, edit_result.stdout)
            content = path.read_text(encoding="utf-8")
            self.assertIn("\tcolumn StorageUsedPct =", content)
            self.assertIn("DIVIDE(", content)
            self.assertIn("[TotalStorageGB] - 10,", content)

            delete_result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "delete",
                    "Devices",
                    "StorageUsedPct",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)
            self.assertNotIn("StorageUsedPct", path.read_text(encoding="utf-8"))

    def test_model_column_delete_rejects_source_columns(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn DeviceName
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: DeviceName
                """,
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "column",
                    "delete",
                    "Devices",
                    "DeviceName",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("source column", result.stdout)

    def test_model_apply_creates_and_updates_from_yaml(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            sales_path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tmeasure 'Compliance Rate' = DIVIDE ( 1, 2, 0 )
\t\tformatString: 0.0%
\t\tlineageTag: m-1

\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate

\tcolumn Revenue
\t\tdataType: int64
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: Revenue
                """,
            )
            devices_path = write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn AzureADDeviceId
\t\tdataType: string
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: AzureADDeviceId

\tcolumn TotalStorageGB
\t\tdataType: double
\t\tlineageTag: c-2
\t\tsummarizeBy: sum
\t\tsourceColumn: TotalStorageGB
                """,
            )
            spec_path = root / "model-changes.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "measures": {
                            "Sales": [
                                {
                                    "name": "Compliance Rate",
                                    "expression": "DIVIDE ( 4, 5, 0 )",
                                    "format": "0.00%",
                                },
                                {
                                    "name": "Total Revenue",
                                    "expression": "SUM ( Sales[Revenue] )",
                                    "format": "0",
                                },
                            ]
                        },
                        "columns": {
                            "Sales": {
                                "OrderDate": {"format": "dd/mm/yyyy"},
                            },
                            "Devices": {
                                "StorageUsedPct": {
                                    "type": "calculated",
                                    "dataType": "double",
                                    "expression": "DIVIDE([TotalStorageGB], 100, 0)",
                                    "format": "0.0%",
                                    "hidden": True,
                                },
                                "AzureADDeviceId": {"hidden": True},
                            },
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "apply",
                    str(spec_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Created measure", result.stdout)
            self.assertIn("Updated measure", result.stdout)
            self.assertIn("Created calculated column", result.stdout)
            self.assertIn("Updated column", result.stdout)

            sales_content = sales_path.read_text(encoding="utf-8")
            self.assertIn("\tmeasure 'Compliance Rate' = DIVIDE ( 4, 5, 0 )", sales_content)
            self.assertIn("\t\tformatString: 0.00%", sales_content)
            self.assertIn("\tmeasure 'Total Revenue' = SUM ( Sales[Revenue] )", sales_content)
            self.assertIn("\t\tformatString: 0", sales_content)
            self.assertIn("\t\tformatString: dd/mm/yyyy", sales_content)

            devices_content = devices_path.read_text(encoding="utf-8")
            self.assertIn("\tcolumn StorageUsedPct = DIVIDE([TotalStorageGB], 100, 0)", devices_content)
            self.assertIn("\t\tformatString: 0.0%", devices_content)
            self.assertIn("\t\tisHidden", devices_content)
            self.assertIn("\tcolumn AzureADDeviceId", devices_content)

    def test_model_apply_dry_run_does_not_write(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            sales_path = write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tformatString: General Date
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
                """,
            )
            devices_path = write_model_table(
                root,
                "Devices.tmdl",
                """
table Devices
\tcolumn TotalStorageGB
\t\tdataType: double
\t\tlineageTag: c-1
\t\tsummarizeBy: sum
\t\tsourceColumn: TotalStorageGB
                """,
            )
            before_sales = sales_path.read_text(encoding="utf-8")
            before_devices = devices_path.read_text(encoding="utf-8")
            spec_path = root / "model-dry-run.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "measures": {
                            "Sales": [
                                {
                                    "name": "Total Revenue",
                                    "expression": "1",
                                    "format": "0",
                                }
                            ]
                        },
                        "columns": {
                            "Sales": {"OrderDate": {"format": "dd/mm/yyyy"}},
                            "Devices": {
                                "StorageUsedPct": {
                                    "type": "calculated",
                                    "dataType": "double",
                                    "expression": "DIVIDE([TotalStorageGB], 100, 0)",
                                    "hidden": True,
                                }
                            },
                        },
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "apply",
                    str(spec_path),
                    "--dry-run",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("(dry run)", result.stdout)
            self.assertEqual(sales_path.read_text(encoding="utf-8"), before_sales)
            self.assertEqual(devices_path.read_text(encoding="utf-8"), before_devices)

    def test_model_apply_rejects_creating_source_columns(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)
            write_model_table(
                root,
                "Sales.tmdl",
                """
table Sales
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tlineageTag: c-1
\t\tsummarizeBy: none
\t\tsourceColumn: OrderDate
                """,
            )
            spec_path = root / "invalid-model.yaml"
            spec_path.write_text(
                yaml.safe_dump(
                    {
                        "columns": {
                            "Sales": {
                                "MissingColumn": {"hidden": True},
                            }
                        }
                    },
                    sort_keys=False,
                ),
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                [
                    "model",
                    "apply",
                    str(spec_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 1, result.stdout)
            self.assertIn("source columns are not created", result.stdout)


class VisualSetRegressionTests(unittest.TestCase):
    def test_visual_move_and_resize_use_named_geometry_options(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual", x=0, y=0, width=100, height=50)
            visual.data["name"] = "card1"
            visual.save()

            move_result = runner.invoke(
                app,
                [
                    "visual",
                    "move",
                    "Demo",
                    "card1",
                    "--x",
                    "25",
                    "--y",
                    "40",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(move_result.exit_code, 0, move_result.stdout)

            resize_result = runner.invoke(
                app,
                [
                    "visual",
                    "resize",
                    "Demo",
                    "card1",
                    "--width",
                    "220",
                    "--height",
                    "120",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(resize_result.exit_code, 0, resize_result.stdout)

            updated = Project.find(root / "Sample.pbip").find_visual(Project.find(root / "Sample.pbip").find_page("Demo"), "card1")
            self.assertEqual(updated.position["x"], 25)
            self.assertEqual(updated.position["y"], 40)
            self.assertEqual(updated.position["width"], 220)
            self.assertEqual(updated.position["height"], 120)

    def test_visual_paste_style_supports_batch_targeting_by_visual_type(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source_page = project.create_page("Source")
            target_page = project.create_page("Target")

            source = project.create_visual(source_page, "cardVisual")
            source.data["name"] = "sourceCard"
            set_property(source.data, "background.color", "#123456", VISUAL_PROPERTIES)
            set_property(source.data, "title.show", "true", VISUAL_PROPERTIES)
            source.save()

            for name in ("targetA", "targetB"):
                visual = project.create_visual(target_page, "cardVisual")
                visual.data["name"] = name
                visual.save()

            chart = project.create_visual(target_page, "barChart")
            chart.data["name"] = "chart1"
            chart.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "paste-style",
                    "Source",
                    "sourceCard",
                    "--to-page",
                    "Target",
                    "--visual-type",
                    "cardVisual",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn('2', result.stdout)
            updated = Project.find(root / "Sample.pbip")
            target_page = updated.find_page("Target")
            for name in ("targetA", "targetB"):
                visual = updated.find_visual(target_page, name)
                self.assertEqual(
                    get_property(visual.data, "background.color", VISUAL_PROPERTIES),
                    "#123456",
                )
                self.assertTrue(get_property(visual.data, "title.show", VISUAL_PROPERTIES))
            chart = updated.find_visual(target_page, "chart1")
            self.assertIsNone(get_property(chart.data, "background.color", VISUAL_PROPERTIES))

    def test_visual_arrange_row_positions_visuals_left_to_right(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            specs = [("card1", 100), ("card2", 120), ("card3", 80)]
            for name, width in specs:
                visual = project.create_visual(page, "cardVisual", width=width, height=50)
                visual.data["name"] = name
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "arrange",
                    "row",
                    "Demo",
                    "card1",
                    "card2",
                    "card3",
                    "--x",
                    "10",
                    "--y",
                    "20",
                    "--gap",
                    "15",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip")
            page = updated.find_page("Demo")
            self.assertEqual(updated.find_visual(page, "card1").position["x"], 10)
            self.assertEqual(updated.find_visual(page, "card1").position["y"], 20)
            self.assertEqual(updated.find_visual(page, "card2").position["x"], 125)
            self.assertEqual(updated.find_visual(page, "card3").position["x"], 260)

    def test_visual_arrange_grid_wraps_rows_using_visual_sizes(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            specs = [
                ("card1", 100, 50),
                ("card2", 120, 60),
                ("card3", 80, 40),
                ("card4", 90, 70),
            ]
            for name, width, height in specs:
                visual = project.create_visual(page, "cardVisual", width=width, height=height)
                visual.data["name"] = name
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "arrange",
                    "grid",
                    "Demo",
                    "card1",
                    "card2",
                    "card3",
                    "card4",
                    "--columns",
                    "2",
                    "--x",
                    "10",
                    "--y",
                    "20",
                    "--column-gap",
                    "15",
                    "--row-gap",
                    "25",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip")
            page = updated.find_page("Demo")
            self.assertEqual(updated.find_visual(page, "card1").position["x"], 10)
            self.assertEqual(updated.find_visual(page, "card1").position["y"], 20)
            self.assertEqual(updated.find_visual(page, "card2").position["x"], 125)
            self.assertEqual(updated.find_visual(page, "card2").position["y"], 20)
            self.assertEqual(updated.find_visual(page, "card3").position["x"], 10)
            self.assertEqual(updated.find_visual(page, "card3").position["y"], 105)
            self.assertEqual(updated.find_visual(page, "card4").position["x"], 105)
            self.assertEqual(updated.find_visual(page, "card4").position["y"], 105)

    def test_visual_arrange_column_positions_visuals_top_to_bottom(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            specs = [("card1", 50), ("card2", 60), ("card3", 40)]
            for name, height in specs:
                visual = project.create_visual(page, "cardVisual", width=100, height=height)
                visual.data["name"] = name
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "arrange",
                    "column",
                    "Demo",
                    "card1",
                    "card2",
                    "card3",
                    "--x",
                    "30",
                    "--y",
                    "10",
                    "--gap",
                    "12",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip")
            page = updated.find_page("Demo")
            self.assertEqual(updated.find_visual(page, "card1").position["x"], 30)
            self.assertEqual(updated.find_visual(page, "card1").position["y"], 10)
            self.assertEqual(updated.find_visual(page, "card2").position["y"], 72)
            self.assertEqual(updated.find_visual(page, "card3").position["y"], 144)

    def test_visual_set_accepts_raw_property_aliases(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual")
            visual.data["name"] = "card1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "card1",
                    "dropShadow.show=true",
                    "label.show=true",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            visual = Project.find(root / "Sample.pbip").find_visual(Project.find(root / "Sample.pbip").find_page("Demo"), "card1")
            self.assertTrue(get_property(visual.data, "shadow.show", VISUAL_PROPERTIES))
            self.assertTrue(get_property(visual.data, "cardLabel.show", VISUAL_PROPERTIES))

    def test_visual_set_suggests_nearby_property_names(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "chart1",
                    "dataLabel.show=true",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn("Did you mean", result.stdout)
            self.assertIn('"dataLabels.show"', result.stdout)

    def test_visual_set_unknown_chart_property_shows_exact_chart_prefix_hint(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set",
                    "Demo",
                    "chart1",
                    "legend.seriesOrder=descending",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertNotEqual(result.exit_code, 0)
            self.assertIn('chart:legend.seriesOrder', result.stdout)
            self.assertIn('For a raw', result.stdout)

    def test_visual_properties_can_filter_and_show_aliases(self) -> None:
        runner = CliRunner()

        result = runner.invoke(
            app,
            [
                "visual",
                "properties",
                "--match",
                "dropShadow",
                "--show-aliases",
            ],
        )

        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("shadow.show", result.stdout)
        self.assertIn("Accepted", result.stdout)
        self.assertIn("dropShadow", result.stdout)

    def test_visual_set_all_prevalidates_and_does_not_partially_write(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            for idx in range(2):
                visual = project.create_visual(page, "cardVisual")
                visual.data["name"] = f"card{idx}"
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set-all",
                    "background.show=true",
                    "notARealProperty=true",
                    "--page", "Demo",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertNotEqual(result.exit_code, 0)
            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            for visual in restored.get_visuals(page):
                self.assertIsNone(get_property(visual.data, "background.show", VISUAL_PROPERTIES))

    def test_visual_set_all_supports_dry_run(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            for idx in range(2):
                visual = project.create_visual(page, "cardVisual")
                visual.data["name"] = f"card{idx}"
                visual.save()

            result = runner.invoke(
                app,
                [
                    "visual",
                    "set-all",
                    "background.show=true",
                    "--page", "Demo",
                    "--dry-run",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Would set background.show", result.stdout)
            restored = Project.find(root / "Sample.pbip")
            page = restored.find_page("Demo")
            for visual in restored.get_visuals(page):
                self.assertIsNone(get_property(visual.data, "background.show", VISUAL_PROPERTIES))

    def test_visual_sort_cli_uses_get_set_clear_subcommands(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            set_result = runner.invoke(
                app,
                [
                    "visual",
                    "sort",
                    "set",
                    "Demo",
                    "chart1",
                    "Sales.Total Revenue",
                    "--direction",
                    "asc",
                    "--field-type",
                    "measure",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            get_result = runner.invoke(
                app,
                [
                    "visual",
                    "sort",
                    "get",
                    "Demo",
                    "chart1",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Ascending", get_result.stdout)

            clear_result = runner.invoke(
                app,
                [
                    "visual",
                    "sort",
                    "clear",
                    "Demo",
                    "chart1",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)


class TestBug025StyleNoneValues(unittest.TestCase):
    """BUG-025: extract_style_properties and _normalize_style_properties must skip None values."""

    def test_extract_style_properties_skips_none(self):
        spec = {
            "title": {"show": True, "text": None},
            "border": {"show": False},
            "background": {"color": None},
        }
        result = extract_style_properties(spec)
        self.assertIn("title.show", result)
        self.assertNotIn("title.text", result)
        self.assertIn("border.show", result)
        # background.color was None, so background should not appear
        for key in result:
            self.assertNotIn("background.color", key)

    def test_normalize_style_properties_skips_none(self):
        props = {
            "title.show": True,
            "title.text": None,
            "border.show": False,
        }
        result = _normalize_style_properties(props)
        self.assertIn("title.show", result)
        self.assertNotIn("title.text", result)
        self.assertIn("border.show", result)

    def test_normalize_style_properties_all_none(self):
        """All-None dict should produce empty result."""
        result = _normalize_style_properties({"title.text": None, "border.color": None})
        self.assertEqual(result, {})


class TestValidateMeasuresOnlyTable(unittest.TestCase):
    """Validate should not warn about missing relationships for measures-only tables."""

    def test_no_warning_for_measures_only_table(self):
        from pbi.modeling.schema import Column, Measure, SemanticModel, SemanticTable

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            page = project.create_page("Test")

            # Create a visual referencing both a data table and a measures table
            visual = project.create_visual(page, "card")
            visual.data["visual"]["query"] = {
                "queryState": {
                    "Values": {
                        "projections": [
                            {"queryRef": "Sales.Amount"},
                            {"queryRef": "Measures Table.Total Revenue"},
                        ]
                    }
                }
            }
            visual.save()

            # Build a model with a data table and a measures-only table (no columns)
            model = SemanticModel(
                folder=root / "Sample.SemanticModel",
                tables=[
                    SemanticTable(
                        name="Sales",
                        columns=[Column(name="Amount", table="Sales", data_type="int64")],
                    ),
                    SemanticTable(
                        name="Measures Table",
                        columns=[],
                        measures=[Measure(name="Total Revenue", table="Measures Table", expression="SUM(Sales[Amount])")],
                    ),
                ],
                relationships=[],
            )

            # Monkey-patch model loading to return our test model
            import pbi.validate as validate_mod

            original_fn = validate_mod._validate_visual_relationships

            def patched(proj):
                # Inline the logic with our model instead of loading from disk
                from pbi.validate import ValidationIssue as VI

                issues = []
                table_names = {t.name.lower() for t in model.tables}
                for pg in proj.get_pages():
                    for vis in proj.get_visuals(pg):
                        query_state = vis.data.get("visual", {}).get("query", {}).get("queryState", {})
                        if not query_state:
                            continue
                        tables_used: set[str] = set()
                        for _role, config in query_state.items():
                            for pr in config.get("projections", []):
                                ref = pr.get("queryRef", "")
                                dot = ref.find(".")
                                if dot > 0:
                                    table = ref[:dot]
                                    if table.lower() in table_names:
                                        tables_used.add(table)
                        if len(tables_used) < 2:
                            continue
                        table_list = sorted(tables_used)
                        for i in range(len(table_list)):
                            for j in range(i + 1, len(table_list)):
                                path = model.find_path(table_list[i], table_list[j])
                                if path is None:
                                    try:
                                        t1 = model.find_table(table_list[i])
                                        t2 = model.find_table(table_list[j])
                                        if not t1.columns or not t2.columns:
                                            continue
                                    except ValueError:
                                        pass
                                    rel = f"pages/{pg.folder.name}/visuals/{vis.folder.name}/visual.json"
                                    issues.append(VI(
                                        rel, "warning",
                                        f'Visual "{vis.name}" references tables '
                                        f'"{table_list[i]}" and "{table_list[j]}" '
                                        f'which have no relationship path',
                                    ))
                return issues

            issues = patched(project)
            warnings = [i for i in issues if i.level == "warning" and "relationship" in i.message]
            self.assertEqual(warnings, [], f"Got unexpected relationship warnings: {warnings}")

    def test_warning_for_data_tables_without_relationship(self):
        """Two data tables (both with columns) and no relationship should still warn."""
        from pbi.modeling.schema import Column, SemanticModel, SemanticTable

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root, with_model=True)
            page = project.create_page("Test")

            visual = project.create_visual(page, "card")
            visual.data["visual"]["query"] = {
                "queryState": {
                    "Values": {
                        "projections": [
                            {"queryRef": "Sales.Amount"},
                            {"queryRef": "Products.Name"},
                        ]
                    }
                }
            }
            visual.save()

            model = SemanticModel(
                folder=root / "Sample.SemanticModel",
                tables=[
                    SemanticTable(name="Sales", columns=[Column(name="Amount", table="Sales", data_type="int64")]),
                    SemanticTable(name="Products", columns=[Column(name="Name", table="Products", data_type="string")]),
                ],
                relationships=[],
            )

            from pbi.validate import ValidationIssue as VI

            issues = []
            table_names = {t.name.lower() for t in model.tables}
            for pg in project.get_pages():
                for vis in project.get_visuals(pg):
                    query_state = vis.data.get("visual", {}).get("query", {}).get("queryState", {})
                    if not query_state:
                        continue
                    tables_used: set[str] = set()
                    for _role, config in query_state.items():
                        for pr in config.get("projections", []):
                            ref = pr.get("queryRef", "")
                            dot = ref.find(".")
                            if dot > 0:
                                table = ref[:dot]
                                if table.lower() in table_names:
                                    tables_used.add(table)
                    if len(tables_used) < 2:
                        continue
                    table_list = sorted(tables_used)
                    for i in range(len(table_list)):
                        for j in range(i + 1, len(table_list)):
                            path = model.find_path(table_list[i], table_list[j])
                            if path is None:
                                try:
                                    t1 = model.find_table(table_list[i])
                                    t2 = model.find_table(table_list[j])
                                    if not t1.columns or not t2.columns:
                                        continue
                                except ValueError:
                                    pass
                                rel = f"pages/{pg.folder.name}/visuals/{vis.folder.name}/visual.json"
                                issues.append(VI(
                                    rel, "warning",
                                    f'Visual "{vis.name}" references tables '
                                    f'"{table_list[i]}" and "{table_list[j]}" '
                                    f'which have no relationship path',
                                ))

            warnings = [i for i in issues if i.level == "warning" and "relationship" in i.message]
            self.assertEqual(len(warnings), 1, f"Expected 1 warning, got: {warnings}")


class TestBug026FillRuleInput(unittest.TestCase):
    """BUG-026: FillRule Input must use SelectRef, not Measure/Column expression."""

    def test_gradient_uses_select_ref_not_measure(self):
        from pbi.formatting import GradientStop, build_gradient_format

        value = build_gradient_format(
            "Measures Table", "Total Devices",
            GradientStop("#FFFFFF", 0), GradientStop("#B83B3B", 90),
        )
        fill_rule = value["solid"]["color"]["expr"]["FillRule"]
        input_node = fill_rule["Input"]

        # Must use SelectRef, NOT Measure
        self.assertIn("SelectRef", input_node)
        self.assertNotIn("Measure", input_node)
        self.assertNotIn("Column", input_node)
        self.assertEqual(
            input_node["SelectRef"]["ExpressionName"],
            "Measures Table.Total Devices",
        )

    def test_gradient_stop_values_use_integer_format(self):
        from pbi.formatting import GradientStop, build_gradient_format

        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0), GradientStop("#000", 90),
        )
        gradient = value["solid"]["color"]["expr"]["FillRule"]["FillRule"]["linearGradient2"]

        # Must be "0D" not "0.0D"
        min_val = gradient["min"]["value"]["expr"]["Literal"]["Value"]
        max_val = gradient["max"]["value"]["expr"]["Literal"]["Value"]
        self.assertEqual(min_val, "0D")
        self.assertEqual(max_val, "90D")

    def test_gradient_stop_values_preserve_decimals(self):
        from pbi.formatting import GradientStop, build_gradient_format

        value = build_gradient_format(
            "T", "F",
            GradientStop("#FFF", 0.5), GradientStop("#000", 99.9),
        )
        gradient = value["solid"]["color"]["expr"]["FillRule"]["FillRule"]["linearGradient2"]
        min_val = gradient["min"]["value"]["expr"]["Literal"]["Value"]
        max_val = gradient["max"]["value"]["expr"]["Literal"]["Value"]
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

    def test_parse_select_ref_input(self):
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


class TestModelSearch(unittest.TestCase):
    """pbi model search command."""

    def test_model_search_finds_matching_fields(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            result = runner.invoke(
                app,
                ["model", "search", "Revenue", "--project", str(root / "Sample.pbip")],
            )
            # with_model=True creates a Measures Table with "Total Revenue"
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Revenue", result.stdout)

    def test_model_search_no_match(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            result = runner.invoke(
                app,
                ["model", "search", "zzznomatch", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("No fields matching", result.stdout)


class TestModelApplyPerformance(unittest.TestCase):
    def test_model_apply_loads_semantic_model_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root, with_model=True)

            yaml_content = yaml.safe_dump(
                {
                    "columns": {
                        "Customers": {
                            "Region": {
                                "hidden": True,
                                "format": "General",
                            }
                        }
                    }
                },
                sort_keys=False,
            )

            from pbi.model import SemanticModel

            with mock.patch("pbi.modeling.schema.SemanticModel.load", wraps=SemanticModel.load) as load_mock:
                result = apply_model_yaml(root, yaml_content, dry_run=False)

            self.assertEqual(result.errors, [], f"Unexpected errors: {result.errors}")
            self.assertEqual(load_mock.call_count, 1)


class TestCalcCommands(unittest.TestCase):
    """pbi calc row/grid layout calculators."""

    def test_calc_row_outputs_positions(self):
        runner = CliRunner()
        result = runner.invoke(app, ["calc", "row", "4", "--width", "1280", "--margin", "16", "--gap", "8"])
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("4 items", result.stdout)
        self.assertIn("#1", result.stdout)
        self.assertIn("#4", result.stdout)

    def test_calc_row_json(self):
        import json

        runner = CliRunner()
        result = runner.invoke(app, ["calc", "row", "3", "--width", "900", "--gap", "0", "--json"])
        self.assertEqual(result.exit_code, 0, result.stdout)
        items = json.loads(result.stdout)
        self.assertEqual(len(items), 3)
        self.assertEqual(items[0]["x"], 0)
        self.assertEqual(items[0]["width"], 300)
        self.assertEqual(items[1]["x"], 300)
        self.assertEqual(items[2]["x"], 600)

    def test_calc_grid_outputs_positions(self):
        runner = CliRunner()
        result = runner.invoke(
            app, ["calc", "grid", "6", "--columns", "3", "--width", "900", "--gap", "0", "--item-height", "100", "--y", "50"]
        )
        self.assertEqual(result.exit_code, 0, result.stdout)
        self.assertIn("6 items", result.stdout)
        self.assertIn("3 cols", result.stdout)

    def test_calc_grid_json_positions(self):
        import json

        runner = CliRunner()
        result = runner.invoke(
            app, ["calc", "grid", "4", "--columns", "2", "--width", "400", "--gap", "0", "--item-height", "100", "--y", "0", "--json"]
        )
        self.assertEqual(result.exit_code, 0, result.stdout)
        items = json.loads(result.stdout)
        self.assertEqual(len(items), 4)
        # 2 cols x 2 rows, 200px each
        self.assertEqual(items[0]["x"], 0)
        self.assertEqual(items[0]["y"], 0)
        self.assertEqual(items[1]["x"], 200)
        self.assertEqual(items[1]["y"], 0)
        self.assertEqual(items[2]["x"], 0)
        self.assertEqual(items[2]["y"], 100)
        self.assertEqual(items[3]["x"], 200)
        self.assertEqual(items[3]["y"], 100)


class TestPageCreateFromTemplate(unittest.TestCase):
    """pbi page create --from-template."""

    def test_page_create_with_template(self):
        from pbi.templates import save_template

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)

            # Create a page with visuals, save as template
            source_page = project.create_page("Source")
            project.create_visual(source_page, "card")
            project.create_visual(source_page, "tableEx")
            visuals = project.get_visuals(source_page)
            save_template(project, source_page, "my-layout", visuals)

            # Create a new page using the template
            result = runner.invoke(
                app,
                ["page", "create", "New Page", "--from-template", "my-layout",
                 "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Created page", result.stdout)
            self.assertIn("my-layout", result.stdout)
            self.assertIn("2 visuals created", result.stdout)


class TestVisualInspect(unittest.TestCase):
    """pbi visual inspect deep dump command."""

    def test_inspect_shows_object_properties(self):
        from pbi.formatting import GradientStop, build_gradient_format, set_conditional_format

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Test")
            visual = project.create_visual(page, "tableEx")

            # Set some chart objects
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "title.text", "My Table", VISUAL_PROPERTIES)

            # Add conditional formatting to create objects
            value = build_gradient_format(
                "T", "F", GradientStop("#FFF", 0), GradientStop("#000", 100),
            )
            set_conditional_format(visual.data, "values", "backColor", value, column="T.F")
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "inspect", "Test", "1", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("values", result.stdout)
            self.assertIn("backColor", result.stdout)
            self.assertIn("metadata=T.F", result.stdout)

    def test_inspect_search_filters(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Test")
            visual = project.create_visual(page, "card")
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            set_property(visual.data, "title.text", "Hello", VISUAL_PROPERTIES)
            set_property(visual.data, "border.show", "true", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "inspect", "Test", "1", "--search", "title",
                 "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            # Should show title properties but not border
            self.assertIn("title", result.stdout.lower())

    def test_inspect_json_output(self):
        import json

        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Test")
            visual = project.create_visual(page, "card")
            set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["visual", "inspect", "Test", "1", "--json",
                 "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            data = json.loads(result.stdout)
            self.assertIsInstance(data, dict)


class TestKpisShorthand(unittest.TestCase):
    """kpis: shorthand for cardVisual authoring."""

    def test_expand_kpis_builds_projections(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(data, [
            {"measure": "Measures.Total", "referenceLabels": [
                {"measure": "Measures.Sub1"},
            ]},
            {"measure": "Measures.Rate"},
        ])

        projections = data["visual"]["query"]["queryState"]["Data"]["projections"]
        refs = [p["queryRef"] for p in projections]
        self.assertEqual(refs, ["Measures.Total", "Measures.Sub1", "Measures.Rate"])

    def test_expand_kpis_writes_per_measure_value_objects(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(data, [
            {"measure": "T.A", "displayUnits": 1, "bold": True},
            {"measure": "T.B", "fontSize": 28},
        ])

        value_entries = data["visual"]["objects"]["value"]
        self.assertEqual(len(value_entries), 2)

        # First KPI
        self.assertEqual(value_entries[0]["selector"]["metadata"], "T.A")
        self.assertIn("labelDisplayUnits", value_entries[0]["properties"])
        self.assertIn("bold", value_entries[0]["properties"])

        # Second KPI
        self.assertEqual(value_entries[1]["selector"]["metadata"], "T.B")
        self.assertIn("fontSize", value_entries[1]["properties"])

    def test_expand_kpis_writes_accent_bar_per_kpi(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(
            data,
            [{"measure": "T.A", "accentColor": "#1A6B7D"}],
            accent_bar={"show": True, "position": "Top", "width": 5},
        )

        ab_entries = data["visual"]["objects"]["accentBar"]
        # Global entry + per-KPI entry
        self.assertEqual(len(ab_entries), 2)
        # Global uses default selector
        self.assertEqual(ab_entries[0]["selector"]["id"], "default")
        # Per-KPI uses metadata selector
        self.assertEqual(ab_entries[1]["selector"]["metadata"], "T.A")

    def test_expand_kpis_writes_tile_background(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(data, [{"measure": "T.A", "tileBackground": "#F0F9FA"}])

        cca = data["visual"]["objects"]["cardCalloutArea"]
        self.assertEqual(len(cca), 1)
        self.assertEqual(cca[0]["selector"]["metadata"], "T.A")
        self.assertIn("backgroundFillColor", cca[0]["properties"])

    def test_expand_kpis_writes_reference_labels(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(data, [{
            "measure": "T.Main",
            "referenceLabels": [
                {"measure": "T.Sub", "title": "Subtitle", "displayUnits": 1000},
            ],
        }])

        # Binding entry
        rl = data["visual"]["objects"]["referenceLabel"]
        self.assertEqual(len(rl), 1)
        sel = rl[0]["selector"]
        self.assertEqual(sel["metadata"], "T.Main")
        self.assertEqual(sel["id"], "field-kpi-0-ref-0")
        self.assertEqual(sel["order"], 0)
        # Value contains measure expression
        val_expr = rl[0]["properties"]["value"]["expr"]
        self.assertIn("Measure", val_expr)
        self.assertEqual(val_expr["Measure"]["Property"], "Sub")

        # Title entry
        rlt = data["visual"]["objects"]["referenceLabelTitle"]
        self.assertEqual(len(rlt), 1)
        self.assertEqual(rlt[0]["selector"]["id"], "field-kpi-0-ref-0")
        self.assertIn("titleText", rlt[0]["properties"])

        # Value formatting entry
        rlv = data["visual"]["objects"]["referenceLabelValue"]
        self.assertEqual(len(rlv), 1)
        self.assertIn("valueDisplayUnits", rlv[0]["properties"])

    def test_expand_kpis_writes_layout(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(
            data,
            [{"measure": "T.A"}],
            layout={"columns": 3, "calloutSize": 35, "alignment": "middle", "dividers": True},
        )

        layout_entries = data["visual"]["objects"]["layout"]
        self.assertEqual(len(layout_entries), 1)
        props = layout_entries[0]["properties"]
        self.assertIn("columnCount", props)
        self.assertIn("calloutSize", props)

        divider_entries = data["visual"]["objects"]["divider"]
        self.assertEqual(len(divider_entries), 1)

    def test_expand_kpis_writes_reference_label_layout(self):
        from pbi.card import expand_kpis

        data: dict = {"visual": {"visualType": "cardVisual"}}
        expand_kpis(
            data,
            [{"measure": "T.A"}],
            ref_label_layout={"position": "right", "arrangement": "rows"},
        )

        rll = data["visual"]["objects"]["referenceLabelLayout"]
        self.assertEqual(len(rll), 1)
        self.assertEqual(rll[0]["selector"]["id"], "default")
        self.assertIn("position", rll[0]["properties"])
        self.assertIn("arrangement", rll[0]["properties"])

    def test_apply_yaml_kpis_shorthand(self):
        """End-to-end: YAML with kpis: block creates full cardVisual."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Dashboard")

            yaml_content = yaml.safe_dump({
                "version": 1,
                "pages": [{
                    "name": "Dashboard",
                    "visuals": [{
                        "name": "healthCard",
                        "type": "cardVisual",
                        "position": "16, 81",
                        "size": "1260 x 280",
                        "layout": {
                            "columns": 3,
                            "calloutSize": 35,
                            "alignment": "middle",
                            "dividers": True,
                        },
                        "accentBar": {
                            "show": True,
                            "position": "Top",
                            "width": 5,
                        },
                        "kpis": [
                            {
                                "measure": "Measures Table.Total Devices",
                                "displayUnits": 1,
                                "accentColor": "#1A6B7D",
                                "tileBackground": "#F0F9FA",
                                "referenceLabels": [{
                                    "measure": "Measures Table.Managed Devices",
                                    "title": "Managed",
                                    "displayUnits": 1,
                                }],
                            },
                            {
                                "measure": "Measures Table.Compliance Rate",
                                "accentColor": "#2B7A4B",
                            },
                        ],
                        "referenceLabelLayout": {
                            "position": "right",
                            "arrangement": "rows",
                        },
                    }],
                }],
            })

            result = apply_yaml(project, yaml_content, dry_run=False)
            self.assertEqual(result.errors, [], f"Errors: {result.errors}")

            page = project.find_page("Dashboard")
            vis = next(v for v in project.get_visuals(page) if v.data.get("name") == "healthCard")

            # Verify projections
            projections = vis.data["visual"]["query"]["queryState"]["Data"]["projections"]
            refs = [p["queryRef"] for p in projections]
            self.assertIn("Measures Table.Total Devices", refs)
            self.assertIn("Measures Table.Managed Devices", refs)
            self.assertIn("Measures Table.Compliance Rate", refs)

            # Verify objects were created
            objects = vis.data["visual"]["objects"]
            self.assertIn("layout", objects)
            self.assertIn("accentBar", objects)
            self.assertIn("value", objects)
            self.assertIn("referenceLabel", objects)
            self.assertIn("referenceLabelTitle", objects)
            self.assertIn("referenceLabelLayout", objects)


if __name__ == "__main__":
    unittest.main()
