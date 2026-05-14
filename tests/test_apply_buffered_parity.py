from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from unittest import mock

from pbi.apply import apply_yaml, apply_yaml_buffered
from pbi.apply.buffered import BufferedPbirApplySession
from pbi.project import Project, _write_json
from pbi.themes import get_theme_data
from tests.apply_parity_support import (
    assert_apply_results_equivalent,
    assert_project_trees_equivalent,
)
from tests.cli_regressions_support import make_project


class BufferedApplyParityHarnessTests(unittest.TestCase):
    """Parity harness for the experimental buffered apply path."""

    def test_noop_spec_matches_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            spec = yaml.safe_dump({"version": 1, "pages": []}, sort_keys=False)

            eager_result = apply_yaml(eager_project, spec)
            buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_noop_buffered_apply_does_not_snapshot_definition_on_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            spec = yaml.safe_dump({"version": 1, "pages": []}, sort_keys=False)

            with mock.patch("pbi.apply.buffered.shutil.copytree", wraps=__import__("shutil").copytree) as copytree_mock:
                result = apply_yaml_buffered(project, spec)

            self.assertEqual(result.errors, [])
            self.assertEqual(copytree_mock.call_count, 0)

    def test_simple_page_and_visual_creation_matches_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
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
                                    "position": "10, 20",
                                    "size": "100 x 50",
                                },
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001"]):
                eager_result = apply_yaml(eager_project, spec)
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001"]):
                buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_buffered_commit_failure_returns_rolled_back_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [{"name": "card1", "type": "cardVisual"}],
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001"]), \
                 mock.patch("pbi.apply.buffered.BufferedPbirApplySession._flush_to_project_root", side_effect=[None, OSError("disk full")]):
                result = apply_yaml_buffered(project, spec)

            self.assertTrue(result.rolled_back)
            self.assertEqual(result.errors, ["Commit failed: disk full"])
            with self.assertRaises(ValueError):
                project.find_page("Demo")
            restored = Project.find(root / "Sample.pbip")
            with self.assertRaises(ValueError):
                restored.find_page("Demo")

    def test_visual_type_conversion_matches_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            initial = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [{"name": "card1", "type": "cardVisual"}],
                        }
                    ],
                },
                sort_keys=False,
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
                                    "type": "clusteredColumnChart",
                                    "position": "20, 30",
                                    "size": "400 x 240",
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001"]):
                apply_yaml(eager_project, initial)
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001"]):
                apply_yaml(buffered_project, initial)
            with mock.patch("secrets.token_hex", side_effect=["visual0002"]):
                eager_result = apply_yaml(eager_project, spec)
            with mock.patch("secrets.token_hex", side_effect=["visual0002"]):
                buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_overwrite_deletes_absent_visuals_matches_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            initial = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {"name": "keep", "type": "cardVisual"},
                                {"name": "remove", "type": "cardVisual", "position": "50, 0"},
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [{"name": "keep", "type": "cardVisual"}],
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001", "visual0002"]):
                apply_yaml(eager_project, initial)
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001", "visual0002"]):
                apply_yaml(buffered_project, initial)

            eager_result = apply_yaml(eager_project, spec, overwrite=True)
            buffered_result = apply_yaml_buffered(buffered_project, spec, overwrite=True)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_bookmark_create_and_group_reconcile_matches_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [{"name": "card1", "type": "cardVisual"}],
                        }
                    ],
                    "bookmarks": [
                        {"name": "Open", "page": "Demo", "group": "Flow"},
                        {"name": "Closed", "page": "Demo", "group": "Flow", "hide": ["card1"]},
                    ],
                },
                sort_keys=False,
            )

            tokens = ["page000001", "visual0001", "bookmark01", "bookmark02", "group00001"]
            with mock.patch("secrets.token_hex", side_effect=tokens):
                eager_result = apply_yaml(eager_project, spec)
            with mock.patch("secrets.token_hex", side_effect=tokens):
                buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_bookmark_reconcile_preserves_legacy_meta_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            initial = yaml.safe_dump({"version": 1, "pages": [{"name": "Demo"}]}, sort_keys=False)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [],
                    "bookmarks": [{"name": "New", "page": "Demo"}],
                },
                sort_keys=False,
            )

            with mock.patch("secrets.token_hex", side_effect=["page000001"]):
                apply_yaml(eager_project, initial)
            with mock.patch("secrets.token_hex", side_effect=["page000001"]):
                apply_yaml(buffered_project, initial)
            for project in (eager_project, buffered_project):
                bookmarks_dir = project.definition_folder / "bookmarks"
                bookmarks_dir.mkdir()
                _write_json(
                    bookmarks_dir / "oldid.bookmark.json",
                    {
                        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/1.4.0/schema.json",
                        "displayName": "Old",
                        "name": "oldid",
                        "explorationState": {"activeSection": "page000001", "sections": {}},
                    },
                )
                _write_json(bookmarks_dir / "bookmarks.json", {"bookmarkOrder": ["oldid"]})

            with mock.patch("secrets.token_hex", side_effect=["newid"]):
                eager_result = apply_yaml(eager_project, spec)
            with mock.patch("secrets.token_hex", side_effect=["newid"]):
                buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_ambiguous_staged_bookmark_error_lists_bookmark_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            session = BufferedPbirApplySession(project=project, dry_run=False)
            bookmarks_dir = project.definition_folder / "bookmarks"
            session.dirty_json[bookmarks_dir / "one.bookmark.json"] = {
                "displayName": "Open",
                "name": "bookmark01",
            }
            session.dirty_json[bookmarks_dir / "two.bookmark.json"] = {
                "displayName": "Open",
                "name": "bookmark02",
            }

            with self.assertRaisesRegex(ValueError, "bookmark01, bookmark02"):
                session._find_staged_bookmark_id_by_display("Open")

    def test_staged_visual_delete_does_not_touch_disk_until_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            initial = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [{"name": "remove", "type": "cardVisual"}],
                        }
                    ],
                },
                sort_keys=False,
            )
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001"]):
                apply_yaml(project, initial)

            page = project.find_page("Demo")
            visual = project.find_visual(page, "remove")
            visual_json = visual.folder / "visual.json"
            session = BufferedPbirApplySession(project=project, dry_run=False)

            session.begin()
            session.delete_visual(visual)
            self.assertTrue(visual_json.exists())

            session.rollback()
            self.assertTrue(visual_json.exists())

            session.delete_visual(visual)
            self.assertTrue(visual_json.exists())
            session.commit()
            self.assertFalse(visual_json.exists())

    def test_first_time_theme_with_missing_report_matches_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            (eager_project.definition_folder / "report.json").unlink()
            (buffered_project.definition_folder / "report.json").unlink()
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "theme": {"name": "Demo Theme", "dataColors": ["#118DFF"]},
                    "pages": [],
                },
                sort_keys=False,
            )

            eager_result = apply_yaml(eager_project, spec)
            buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_report_and_first_time_theme_writes_match_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "theme": {"name": "Demo Theme", "dataColors": ["#118DFF", "#D83B01"]},
                    "report": {"layoutOptimization": "MobilePortrait"},
                    "pages": [],
                },
                sort_keys=False,
            )

            eager_result = apply_yaml(eager_project, spec)
            buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_report_resource_packages_with_first_time_theme_matches_eager(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "theme": {"name": "Demo Theme", "dataColors": ["#118DFF"]},
                    "report": {
                        "resourcePackages": [
                            {
                                "name": "RegisteredResources",
                                "type": "RegisteredResources",
                                "items": [
                                    {"name": "Logo", "path": "logo.png", "type": "Image"}
                                ],
                            }
                        ]
                    },
                    "pages": [],
                },
                sort_keys=False,
            )

            eager_result = apply_yaml(eager_project, spec)
            buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_existing_theme_commit_failure_restores_theme_resource(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            initial = yaml.safe_dump(
                {"version": 1, "theme": {"name": "Demo Theme", "dataColors": ["#118DFF"]}, "pages": []},
                sort_keys=False,
            )
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "theme": {"dataColors": ["#118DFF", "#107C10"]},
                    "report": {"layoutOptimization": "MobilePortrait"},
                    "pages": [],
                },
                sort_keys=False,
            )
            apply_yaml(project, initial)
            before = get_theme_data(project)
            real_write_json = _write_json
            writes = 0

            def fail_after_first_write(path: Path, data: dict) -> None:
                nonlocal writes
                writes += 1
                if writes > 1:
                    raise OSError("disk full")
                real_write_json(path, data)

            with mock.patch(
                "pbi.apply.buffered.BufferedPbirApplySession.project_for_validation",
                return_value=project,
            ), mock.patch("pbi.apply.buffered._write_json", side_effect=fail_after_first_write):
                result = apply_yaml_buffered(project, spec)

            self.assertTrue(result.rolled_back)
            self.assertEqual(result.errors, ["Commit failed: disk full"])
            self.assertEqual(get_theme_data(Project.find(root / "Sample.pbip")), before)

    def test_existing_theme_update_repairs_resource_path_like_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            initial = yaml.safe_dump(
                {"version": 1, "theme": {"name": "Demo Theme", "dataColors": ["#118DFF"]}, "pages": []},
                sort_keys=False,
            )
            spec = yaml.safe_dump(
                {"version": 1, "theme": {"dataColors": ["#118DFF", "#107C10"]}, "pages": []},
                sort_keys=False,
            )

            apply_yaml(eager_project, initial)
            apply_yaml(buffered_project, initial)
            for project in (eager_project, buffered_project):
                report = project.get_report_meta()
                for package in report.get("resourcePackages", []):
                    for item in package.get("items", []):
                        if item.get("type") == "CustomTheme":
                            item["name"] = "Demo Theme"
                            item["path"] = "Demo Theme"
                _write_json(project.definition_folder / "report.json", report)

            eager_result = apply_yaml(eager_project, spec)
            buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_existing_theme_update_matches_eager_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            eager_root = root / "eager"
            buffered_root = root / "buffered"
            eager_project = make_project(eager_root)
            buffered_project = make_project(buffered_root)
            initial = yaml.safe_dump(
                {"version": 1, "theme": {"name": "Demo Theme", "dataColors": ["#118DFF"]}, "pages": []},
                sort_keys=False,
            )
            spec = yaml.safe_dump(
                {"version": 1, "theme": {"dataColors": ["#118DFF", "#107C10"]}, "pages": []},
                sort_keys=False,
            )

            apply_yaml(eager_project, initial)
            apply_yaml(buffered_project, initial)
            eager_result = apply_yaml(eager_project, spec)
            buffered_result = apply_yaml_buffered(buffered_project, spec)

            assert_apply_results_equivalent(self, eager_result, buffered_result)
            assert_project_trees_equivalent(self, eager_root, buffered_root)

    def test_unsupported_buffered_operation_returns_apply_result_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [{"name": "Group", "type": "group"}],
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("secrets.token_hex", side_effect=["page000001"]):
                result = apply_yaml_buffered(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(result.rolled_back)
            self.assertTrue(any("create_group_container" in error for error in result.errors))

    def test_buffered_validation_sees_staged_invalid_visual_and_rolls_back(self) -> None:
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
                                    "name": "badchart",
                                    "type": "clusteredColumnChart",
                                    "chart:legnd.show": True,
                                }
                            ],
                        }
                    ],
                },
                sort_keys=False,
            )

            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001"]):
                result = apply_yaml_buffered(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(result.rolled_back)
            self.assertTrue(any("Schema:" in error for error in result.errors))

            with self.assertRaises(ValueError):
                project.find_page("Demo")
            restored = Project.find(root / "Sample.pbip")
            with self.assertRaises(ValueError):
                restored.find_page("Demo")


if __name__ == "__main__":
    unittest.main()
