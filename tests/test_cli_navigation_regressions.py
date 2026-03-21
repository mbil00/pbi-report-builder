from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.bookmarks import (
    create_bookmark,
    create_bookmark_group,
    get_bookmark,
    get_bookmark_group,
    list_bookmark_groups,
    list_bookmarks,
    update_bookmark_visuals,
)
from pbi.cli import app
from pbi.drillthrough import configure_drillthrough, configure_tooltip_page
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
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)
            page = Project.find(root / "Sample.pbip").find_page("Demo")
            self.assertEqual(get_interactions(page), [])

    def test_bookmark_group_create_list_and_delete_round_trip(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "shape")
            visual.data["name"] = "button1"
            visual.save()

            create_bookmark(project, "Default", page, [visual])
            create_bookmark(project, "Filtered", page, [visual], hidden_visuals=["button1"])

            create_result = runner.invoke(
                app,
                [
                    "bookmark",
                    "group",
                    "create",
                    "Main Views",
                    "Default",
                    "Filtered",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(create_result.exit_code, 0, create_result.stdout)

            list_result = runner.invoke(
                app,
                ["bookmark", "group", "list", "--json", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            self.assertIn('"name": "Main Views"', list_result.stdout)

            meta = json.loads((root / "Sample.Report" / "definition" / "bookmarks" / "bookmarks.json").read_text())
            created_group = next(item for item in meta["items"] if item.get("displayName") == "Main Views")
            self.assertRegex(created_group["name"], r"^[0-9a-f]{20}$")

            bookmark_rows = list_bookmarks(Project.find(root / "Sample.pbip"))
            self.assertEqual([row.group for row in bookmark_rows], ["Main Views", "Main Views"])

            delete_result = runner.invoke(
                app,
                [
                    "bookmark",
                    "group",
                    "delete",
                    "Main Views",
                    "--force",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(delete_result.exit_code, 0, delete_result.stdout)

            groups = list_bookmark_groups(Project.find(root / "Sample.pbip"))
            self.assertEqual(groups, [])
            bookmark_rows = list_bookmarks(Project.find(root / "Sample.pbip"))
            self.assertEqual([row.group for row in bookmark_rows], [None, None])

    def test_bookmark_get_and_list_show_group_membership(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "shape")
            visual.data["name"] = "button1"
            visual.save()

            first = create_bookmark(project, "Default", page, [visual])
            second = create_bookmark(project, "Focus", page, [visual])
            create_bookmark_group(project, "Views", [first["name"], second["name"]])

            list_result = runner.invoke(
                app,
                ["bookmark", "list", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            self.assertIn("Views", list_result.stdout)

            get_result = runner.invoke(
                app,
                ["bookmark", "get", "Default", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Group", get_result.stdout)
            self.assertIn("Views", get_result.stdout)

    def test_nav_toggle_set_targets_bookmark_group_identifier(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Home")
            visual = project.create_visual(page, "shape")
            visual.data["name"] = "toggleButton"
            visual.save()

            first = create_bookmark(project, "Default", page, [visual])
            second = create_bookmark(project, "Focus", page, [visual])
            group = create_bookmark_group(project, "Views", [first["name"], second["name"]])

            result = runner.invoke(
                app,
                ["nav", "toggle", "set", "Home", "toggleButton", "Views", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn('bookmark group "Views"', result.stdout)

            refreshed = Project.find(root / "Sample.pbip")
            updated = refreshed.find_visual(refreshed.find_page("Home"), "toggleButton")
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "Bookmark")
            self.assertEqual(get_property(updated.data, "action.bookmark", VISUAL_PROPERTIES), group.identifier)
            self.assertEqual(get_bookmark_group(refreshed, "Views").identifier, group.identifier)

    def test_bookmark_set_updates_page_targets_options_and_state_patch(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            home = project.create_page("Home")
            details = project.create_page("Details")
            first = project.create_visual(home, "shape")
            first.data["name"] = "vis1"
            first.save()
            second = project.create_visual(details, "tableEx")
            second.data["name"] = "vis2"
            second.save()

            create_bookmark(project, "Stateful", home, [first], hidden_visuals=["vis1"])

            state_path = root / "bookmark-state.json"
            state_path.write_text(
                json.dumps(
                    {
                        "sections": {
                            details.name: {
                                "visualContainers": {
                                    "vis2": {
                                        "orderBy": {"Direction": 2},
                                        "singleVisual": {
                                            "objects": {"title": {"show": True}},
                                            "projections": {"Values": [{"queryRef": "Product.Category"}]},
                                        },
                                    }
                                }
                            }
                        }
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            options_path = root / "bookmark-options.json"
            options_path.write_text(json.dumps({"customFlag": True}) + "\n", encoding="utf-8")

            result = runner.invoke(
                app,
                [
                    "bookmark",
                    "set",
                    "Stateful",
                    "--show",
                    "vis1",
                    "--page",
                    "Details",
                    "--target",
                    "vis2",
                    "--no-capture-data",
                    "--state-file",
                    str(state_path),
                    "--options-file",
                    str(options_path),
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            bookmark = get_bookmark(reloaded, "Stateful")
            self.assertEqual(bookmark["explorationState"]["activeSection"], details.name)
            self.assertEqual(bookmark["options"]["targetVisualNames"], ["vis2"])
            self.assertTrue(bookmark["options"]["suppressData"])
            self.assertTrue(bookmark["options"]["customFlag"])
            detail_state = bookmark["explorationState"]["sections"][details.name]["visualContainers"]["vis2"]
            self.assertEqual(detail_state["orderBy"]["Direction"], 2)
            self.assertIn("objects", detail_state["singleVisual"])
            self.assertIn("projections", detail_state["singleVisual"])

            list_result = runner.invoke(
                app,
                ["bookmark", "list", "--json", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(list_result.exit_code, 0, list_result.stdout)
            rows = json.loads(list_result.stdout)
            self.assertEqual(rows[0]["sortStates"], 1)
            self.assertEqual(rows[0]["projectionStates"], 1)
            self.assertEqual(rows[0]["objectStates"], 1)
            self.assertEqual(rows[0]["hiddenVisuals"], 1)

            get_result = runner.invoke(
                app,
                ["bookmark", "get", "Stateful", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Sort States", get_result.stdout)
            self.assertIn("Projection States", get_result.stdout)
            self.assertIn("sort:", get_result.stdout)

    def test_diff_reports_bookmark_state_changes(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = project.create_page("Demo")
            visual = project.create_visual(page, "shape")
            visual.data["name"] = "vis1"
            visual.save()
            create_bookmark(project, "Stateful", page, [visual])

            spec_path = root / "bookmark-diff.yaml"
            spec_path.write_text(
                """\
version: 1
pages:
- name: Demo
bookmarks:
- name: Stateful
  page: Demo
  hide: [vis1]
  state:
    sections:
      Demo:
        visualContainers:
          vis1:
            orderBy:
              Direction: 2
""",
                encoding="utf-8",
            )

            result = runner.invoke(
                app,
                ["diff", str(spec_path), "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            self.assertIn("Bookmark Stateful", result.stdout)
            self.assertIn("state.sections", result.stdout)

class NavigationCommandTests(unittest.TestCase):
    def test_nav_page_set_resolves_target_page_and_clears_old_action(self) -> None:
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
                ["nav", "page", "set", "Home", "navButton", "Details", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip").find_visual(
                Project.find(root / "Sample.pbip").find_page("Home"),
                "navButton",
            )
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "PageNavigation")
            self.assertEqual(get_property(updated.data, "action.page", VISUAL_PROPERTIES), details.name)
            self.assertIsNone(get_property(updated.data, "action.url", VISUAL_PROPERTIES))

    def test_nav_drillthrough_set_validates_target_and_sets_action(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            home = project.create_page("Home")
            details = project.create_page("Details")
            configure_drillthrough(details, [("Product", "Category", "column")])
            details.save()
            visual = project.create_visual(home, "shape")
            visual.data["name"] = "drillBtn"
            visual.save()

            result = runner.invoke(
                app,
                ["nav", "drillthrough", "set", "Home", "drillBtn", "Details", "--project", str(root / "Sample.pbip")],
            )

            self.assertEqual(result.exit_code, 0, result.stdout)
            updated = Project.find(root / "Sample.pbip").find_visual(
                Project.find(root / "Sample.pbip").find_page("Home"),
                "drillBtn",
            )
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "Drillthrough")
            self.assertEqual(get_property(updated.data, "action.drillthrough", VISUAL_PROPERTIES), details.name)
            self.assertIsNone(get_property(updated.data, "action.page", VISUAL_PROPERTIES))

    def test_page_drillthrough_set_hides_page_by_default_and_can_opt_out(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            project.create_page("Detail")

            result = runner.invoke(
                app,
                ["page", "drillthrough", "set", "Detail", "Sales.Region", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            refreshed = Project.find(root / "Sample.pbip").find_page("Detail")
            self.assertEqual(refreshed.visibility, "HiddenInViewMode")

            detail = refreshed
            detail.data["visibility"] = "AlwaysVisible"
            detail.save()

            result = runner.invoke(
                app,
                [
                    "page",
                    "drillthrough",
                    "set",
                    "Detail",
                    "Sales.Region",
                    "--no-hide",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(result.exit_code, 0, result.stdout)
            refreshed = Project.find(root / "Sample.pbip").find_page("Detail")
            self.assertEqual(refreshed.visibility, "AlwaysVisible")

    def test_nav_tooltip_set_get_and_clear(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            home = project.create_page("Home")
            tip = project.create_page("Tip")
            configure_tooltip_page(tip, [("Product", "Category", "column")], width=320, height=240)
            tip.save()
            visual = project.create_visual(home, "barChart")
            visual.data["name"] = "chart1"
            visual.save()

            set_result = runner.invoke(
                app,
                ["nav", "tooltip", "set", "Home", "chart1", "Tip", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            get_result = runner.invoke(
                app,
                ["nav", "tooltip", "get", "Home", "chart1", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("ReportPage", get_result.stdout)
            self.assertIn(tip.name, get_result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            updated = reloaded.find_visual(reloaded.find_page("Home"), "chart1")
            self.assertEqual(get_property(updated.data, "tooltip.type", VISUAL_PROPERTIES), "ReportPage")
            self.assertEqual(get_property(updated.data, "tooltip.section", VISUAL_PROPERTIES), tip.name)
            self.assertEqual(get_property(updated.data, "tooltip.show", VISUAL_PROPERTIES), True)

            clear_result = runner.invoke(
                app,
                ["nav", "tooltip", "clear", "Home", "chart1", "--force", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)

            reloaded = Project.find(root / "Sample.pbip")
            updated = reloaded.find_visual(reloaded.find_page("Home"), "chart1")
            self.assertIsNone(get_property(updated.data, "tooltip.type", VISUAL_PROPERTIES))
            self.assertIsNone(get_property(updated.data, "tooltip.section", VISUAL_PROPERTIES))

    def test_page_drillthrough_and_tooltip_get_show_binding_details(self) -> None:
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            drill = project.create_page("Drill")
            configure_drillthrough(
                drill,
                [("Product", "Category", "column"), ("Sales", "Total Revenue", "measure")],
                cross_report=True,
            )
            drill.save()
            tip = project.create_page("Tip")
            configure_tooltip_page(tip, [("Product", "Category", "column")], width=360, height=220)
            tip.save()

            drill_result = runner.invoke(
                app,
                ["page", "drillthrough", "get", "Drill", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(drill_result.exit_code, 0, drill_result.stdout)
            self.assertIn("Cross Report", drill_result.stdout)
            self.assertIn("Product.Category", drill_result.stdout)
            self.assertIn("Sales.Total Revenue (measure)", drill_result.stdout)

            tip_result = runner.invoke(
                app,
                ["page", "tooltip", "get", "Tip", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(tip_result.exit_code, 0, tip_result.stdout)
            self.assertIn("Width", tip_result.stdout)
            self.assertIn("360", tip_result.stdout)
            self.assertIn("Product.Category", tip_result.stdout)

    def test_nav_bookmark_set_action_get_and_clear(self) -> None:
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
                    "bookmark",
                    "set",
                    "Home",
                    "bookmarkButton",
                    "Show Details",
                    "--project",
                    str(root / "Sample.pbip"),
                ],
            )
            self.assertEqual(set_result.exit_code, 0, set_result.stdout)

            get_result = runner.invoke(
                app,
                ["nav", "action", "get", "Home", "bookmarkButton", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(get_result.exit_code, 0, get_result.stdout)
            self.assertIn("Bookmark", get_result.stdout)
            self.assertIn(bookmark["name"], get_result.stdout)

            refreshed = Project.find(root / "Sample.pbip")
            updated = refreshed.find_visual(refreshed.find_page("Home"), "bookmarkButton")
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "Bookmark")
            self.assertEqual(get_property(updated.data, "action.bookmark", VISUAL_PROPERTIES), bookmark["name"])

            clear_result = runner.invoke(
                app,
                ["nav", "action", "clear", "Home", "bookmarkButton", "--force", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(clear_result.exit_code, 0, clear_result.stdout)

            refreshed = Project.find(root / "Sample.pbip")
            updated = refreshed.find_visual(refreshed.find_page("Home"), "bookmarkButton")
            self.assertEqual(get_property(updated.data, "action.bookmark", VISUAL_PROPERTIES), None)

    def test_nav_url_set_and_back_set(self) -> None:
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
                    "url",
                    "set",
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
                ["nav", "back", "set", "Home", "urlButton", "--project", str(root / "Sample.pbip")],
            )
            self.assertEqual(back_result.exit_code, 0, back_result.stdout)

            refreshed = Project.find(root / "Sample.pbip")
            updated = refreshed.find_visual(refreshed.find_page("Home"), "urlButton")
            self.assertEqual(get_property(updated.data, "action.type", VISUAL_PROPERTIES), "Back")
            self.assertEqual(get_property(updated.data, "action.url", VISUAL_PROPERTIES), None)
