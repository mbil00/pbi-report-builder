from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import yaml
from typer.testing import CliRunner

from pbi.apply import apply_yaml
from pbi.bookmarks import create_bookmark, list_bookmarks
from pbi.cli import app
from pbi.project import Project
from pbi.properties import VISUAL_PROPERTIES, get_property
from pbi.styles import (
    create_style,
    extract_style_properties,
    get_style,
    _normalize_style_properties,
)
from pbi.templates import apply_template, save_template
from tests.cli_regressions_support import make_project


class TemplateRegressionTests(unittest.TestCase):
    def test_template_name_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            page = project.create_page("Demo")
            visual = project.create_visual(page, "textSlicer")

            with self.assertRaises(ValueError):
                save_template(project, page, "../escape", [visual])

    def test_global_template_preserves_bindings_and_bookmarks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            with mock.patch("pathlib.Path.home", return_value=home):
                source = make_project(root / "source")
                source_page = source.create_page("Source")
                visual = source.create_visual(source_page, "textSlicer", x=0, y=0, width=100, height=50)
                visual.data["name"] = "regionSlicer"
                visual.save()
                source.add_binding(visual, "Values", "Customers", "Region")
                create_bookmark(
                    source,
                    display_name="Intro Hidden",
                    page=source_page,
                    visuals=source.get_visuals(source_page),
                    hidden_visuals=["regionSlicer"],
                )

                save_template(source, source_page, "intro", global_scope=True)

                target = make_project(root / "target")
                target_page = target.create_page("Landing")
                result = apply_template(target, target_page, "intro", global_scope=True)

                self.assertEqual(result.errors, [])
                applied_visual = target.find_visual(target_page, "regionSlicer")
                projections = applied_visual.data["visual"]["query"]["queryState"]["Values"]["projections"]
                self.assertEqual(projections[0]["queryRef"], "Customers.Region")

                bookmarks = list_bookmarks(target)
                self.assertEqual(len(bookmarks), 1)
                self.assertEqual(bookmarks[0].display_name, "Intro Hidden")
                self.assertEqual(bookmarks[0].active_section, target_page.name)

    def test_page_templates_json_lists_project_and_global_scope(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            with mock.patch("pathlib.Path.home", return_value=home):
                project = make_project(root)
                page = project.create_page("Demo")
                project.create_visual(page, "cardVisual")
                save_template(project, page, "local-template")
                save_template(project, page, "global-template", global_scope=True)

                result = runner.invoke(
                    app,
                    ["catalog", "list", "--kind", "page", "--json", "--project", str(root / "Sample.pbip")],
                )

                self.assertEqual(result.exit_code, 0, result.stdout)
                data = json.loads(result.stdout)
                scopes = {row["name"]: row["scope"] for row in data}
                self.assertEqual(scopes["local-template"], "project")
                self.assertEqual(scopes["global-template"], "global")

class StylePresetRegressionTests(unittest.TestCase):
    def test_style_create_list_show_delete_cli_flow(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_project(root)

            empty_list = runner.invoke(
                app,
                ["catalog", "list", "--kind", "style", "--scope", "project", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(empty_list.exit_code, 0, empty_list.stdout)
            self.assertIn("No catalog items found", empty_list.stdout)

            create_result = runner.invoke(
                app,
                [
                    "catalog",
                    "create",
                    "style",
                    "border.show=true",
                    "border.radius=10",
                    "title.text=Standard Card",
                    "--description",
                    "Card baseline",
                    "--name",
                    "card-standard",
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
                ["catalog", "list", "--kind", "style", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            self.assertIn("card-standard", list_result.stdout)
            self.assertIn("3", list_result.stdout)

            show_result = runner.invoke(
                app,
                ["catalog", "get", "style/card-standard", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(show_result.exit_code, 0, show_result.stdout)
            self.assertIn("name: card-standard", show_result.stdout)
            self.assertIn("border.show: true", show_result.stdout)
            self.assertIn("title.text: Standard Card", show_result.stdout)

            delete_result = runner.invoke(
                app,
                ["catalog", "delete", "style/card-standard", "--force", "--project", str(root / "Sample.pbip")],
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
                    "catalog",
                    "create",
                    "style",
                    "border.show=true",
                    "--name",
                    "../escape",
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

class TestPageCreateFromTemplate(unittest.TestCase):
    """pbi page create --from-template."""

    def test_page_create_with_global_template(self):
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / "home"
            with mock.patch("pathlib.Path.home", return_value=home):
                source = make_project(root / "source")
                source_page = source.create_page("Source")
                source.create_visual(source_page, "card")
                source.create_visual(source_page, "tableEx")
                visuals = source.get_visuals(source_page)
                save_template(source, source_page, "my-layout", visuals, global_scope=True)

                target_root = root / "target"
                make_project(target_root)

                result = runner.invoke(
                    app,
                    [
                        "page",
                        "create",
                        "New Page",
                        "--from-template",
                        "my-layout",
                        "--template-global",
                        "--project",
                        str(target_root / "Sample.pbip"),
                    ],
                )
                self.assertEqual(result.exit_code, 0, result.stdout)
                self.assertIn("Created page", result.stdout)
                self.assertIn("my-layout", result.stdout)
                self.assertIn("2 visuals created", result.stdout)
