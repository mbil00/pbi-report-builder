from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.bookmarks import create_bookmark, get_bookmark, update_bookmark_visuals
from pbi.cli import app
from pbi.interactions import get_interactions, set_interaction
from pbi.project import Project, _write_json
from pbi.properties import VISUAL_PROPERTIES, get_property, set_property
from tests.cli_regressions_support import make_project


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

class NavigationCommandTests(unittest.TestCase):
    def test_nav_set_page_resolves_target_page_and_clears_old_action(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            home = project.create_page("Home")
            details = project.create_page("Details")
            visual = project.create_visual(home, "shape")
            visual.data["name"] = "navButton"
            set_property(visual.data, "action.type", "WebUrl", VISUAL_PROPERTIES)
            set_property(visual.data, "action.url", "https://example.com", VISUAL_PROPERTIES)
            visual.save()

            result = runner.invoke(
                app,
                ["nav", "set-page", "Home", "navButton", "Details", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip").find_visual(
                Project.find(root / "Sample.pbip").find_page("Home"),
                "navButton",
            )
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "PageNavigation")
            self.assertEqual(get_property(updated.data, "action.page", VISUAL_PROPERTIES), details.name)
            self.assertIsNone(get_property(updated.data, "action.url", VISUAL_PROPERTIES))

    def test_nav_set_bookmark_and_clear(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Home")
            visual = project.create_visual(page, "shape")
            visual.data["name"] = "bookmarkButton"
            visual.save()
            bookmark = create_bookmark(
                project,
                display_name="Show Details",
                page=page,
                visuals=project.get_visuals(page),
            )

            set_result = runner.invoke(
                app,
                [
                    "nav",
                    "set-bookmark",
                    "Home",
                    "bookmarkButton",
                    "Show Details",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            refreshed = Project.find(root / "Sample.pbip")
            updated = refreshed.find_visual(refreshed.find_page("Home"), "bookmarkButton")
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "Bookmark")
            self.assertEqual(get_property(updated.data, "action.bookmark", VISUAL_PROPERTIES), bookmark["name"])

            clear_result = runner.invoke(
                app,
                ["nav", "clear", "Home", "bookmarkButton", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)

            refreshed = Project.find(root / "Sample.pbip")
            updated = refreshed.find_visual(refreshed.find_page("Home"), "bookmarkButton")
            self.assertEqual(get_property(updated.data, "action.bookmark", VISUAL_PROPERTIES), None)

    def test_nav_set_url_and_back(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Home")
            visual = project.create_visual(page, "shape")
            visual.data["name"] = "urlButton"
            visual.save()

            url_result = runner.invoke(
                app,
                [
                    "nav",
                    "set-url",
                    "Home",
                    "urlButton",
                    "https://example.com/docs",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(url_result.exit_code, 0, url_result.stdout)

            refreshed = Project.find(root / "Sample.pbip")
            updated = refreshed.find_visual(refreshed.find_page("Home"), "urlButton")
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "WebUrl")
            self.assertEqual(
                get_property(updated.data, "action.url", VISUAL_PROPERTIES),
                "https://example.com/docs",
            )

            back_result = runner.invoke(
                app,
                ["nav", "set-back", "Home", "urlButton", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(back_result.exit_code, 0, back_result.stdout)

            refreshed = Project.find(root / "Sample.pbip")
            updated = refreshed.find_visual(refreshed.find_page("Home"), "urlButton")
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "Back")
            self.assertEqual(get_property(updated.data, "action.url", VISUAL_PROPERTIES), None)
