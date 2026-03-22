from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from typer.testing import CliRunner

from pbi.cli import app
from pbi.project import Project, _read_json, _write_json
from pbi.properties import VISUAL_PROPERTIES, _property_alias_map
from tests.cli_regressions_support import make_project


class ProjectCachingRegressionTests(unittest.TestCase):
    def test_repeated_page_and_visual_lookups_reuse_cached_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            first = project.create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
            first.data["name"] = "card1"
            first.save()
            second = project.create_visual(page, "cardVisual", x=120, y=20, width=100, height=50)
            second.data["name"] = "card2"
            second.save()

            with mock.patch("pbi.project._read_json", wraps=_read_json) as read_json:
                cached_page = project.find_page("Demo")
                visuals = project.get_visuals(cached_page)
                project.find_visual(cached_page, "card1")
                initial_reads = read_json.call_count

                self.assertEqual(len(visuals), 2)

                project.get_pages()
                project.find_page("Demo")
                project.get_visuals(cached_page)
                project.find_visual(cached_page, "card2")

                self.assertEqual(read_json.call_count, initial_reads)

    def test_create_visual_updates_cached_page_visuals_without_reload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
            visual.data["name"] = "card1"
            visual.save()

            cached_page = project.find_page("Demo")
            self.assertEqual(len(project.get_visuals(cached_page)), 1)

            with mock.patch("pbi.project._read_json", wraps=_read_json) as read_json:
                created = project.create_visual(cached_page, "cardVisual", x=120, y=20, width=100, height=50)
                created.data["name"] = "card2"
                created.save()

                visuals = project.get_visuals(cached_page)

                self.assertEqual(read_json.call_count, 0)
                self.assertEqual([v.name for v in visuals], ["card1", "card2"])

class PropertyAliasCacheRegressionTests(unittest.TestCase):
    def test_property_alias_map_is_cached_per_registry(self) -> None:
        registry = {
            "position.x": VISUAL_PROPERTIES["position.x"],
            "title.text": VISUAL_PROPERTIES["title.text"],
        }

        first = _property_alias_map(registry)
        second = _property_alias_map(registry)

        self.assertIs(first, second)

        registry["position.y"] = VISUAL_PROPERTIES["position.y"]
        third = _property_alias_map(registry)

        self.assertIsNot(first, third)
        self.assertEqual(third["y"], "position.y")

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
    def test_model_export_allows_output_outside_project(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "project"
            root.mkdir()
            make_project(root, with_model=True)
            outside = Path(tmp) / "model.yaml"

            result = runner.invoke(
                app,
                ["model", "export", "--output", str(outside), "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertTrue(outside.exists())

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

            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                result = runner.invoke(
                    app,
                    ["map", "--output", "exports/maps/project.yaml", "--project", str(root / "Sample.pbip")],
                )
            finally:
                os.chdir(old_cwd)

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertTrue(out_path.exists())

    def test_page_export_allows_relative_escape(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Demo")

            old_cwd = os.getcwd()
            try:
                os.chdir(root)
                result = runner.invoke(
                    app,
                    ["page", "export", "Demo", "--output", "../escape.yaml", "--project", str(root / "Sample.pbip")],
                )
            finally:
                os.chdir(old_cwd)

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


class GroupDeleteRegressionTests(unittest.TestCase):
    def test_delete_visual_group_clears_children_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            first = project.create_visual(page, "textbox")
            first.data["name"] = "first"
            first.save()
            second = project.create_visual(page, "textbox")
            second.data["name"] = "second"
            second.save()

            group = project.create_group(page, [first, second], display_name="header")

            project.delete_visual(group)
            project.clear_caches()

            visuals = {visual.name: visual for visual in project.get_visuals(page)}
            self.assertNotIn("header", visuals)
            self.assertNotIn("parentGroupName", visuals["first"].data)
            self.assertNotIn("parentGroupName", visuals["second"].data)
