from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml
from unittest import mock

from pbi.apply import apply_yaml, apply_yaml_buffered
from pbi.apply.buffered import BufferedPbirApplySession
from pbi.project import Project, _write_json
from pbi.validate import ValidationIssue
from pbi.themes import get_theme_data
from tests.apply_parity_support import (
    assert_apply_results_equivalent,
    assert_project_trees_equivalent,
)
from tests.cli_regressions_support import make_project


def _capture_tree(root: Path) -> dict[str, bytes | None]:
    """Capture files and empty directories below root for byte equality checks."""
    captured: dict[str, bytes | None] = {}
    if not root.exists():
        return captured
    for path in sorted(root.rglob("*")):
        rel = str(path.relative_to(root))
        if path.is_file():
            captured[rel] = path.read_bytes()
        elif path.is_dir() and not any(path.iterdir()):
            captured[f"{rel}/"] = None
    return captured


def _complex_rollback_initial_spec() -> str:
    return yaml.safe_dump(
        {
            "version": 1,
            "pages": [
                {
                    "name": "Demo",
                    "visuals": [
                        {"name": "keep", "type": "cardVisual", "position": "0, 0"},
                        {"name": "remove", "type": "cardVisual", "position": "50, 0"},
                    ],
                }
            ],
        },
        sort_keys=False,
    )


def _complex_rollback_spec() -> str:
    return yaml.safe_dump(
        {
            "version": 1,
            "theme": {"name": "Rollback Theme", "dataColors": ["#118DFF"]},
            "report": {"layoutOptimization": "MobilePortrait"},
            "pages": [
                {
                    "name": "Demo",
                    "visuals": [
                        {"name": "keep", "position": "100, 100", "size": "200 x 100"},
                        {"name": "new", "type": "cardVisual", "position": "200, 0"},
                    ],
                }
            ],
            "bookmarks": [
                {"name": "Open", "page": "Demo", "group": "Flow"},
                {"name": "Closed", "page": "Demo", "group": "Flow", "hide": ["keep"]},
            ],
        },
        sort_keys=False,
    )


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

    def test_compact_json_apply_writes_valid_minified_json(self) -> None:
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

            result = apply_yaml(project, spec, compact_json=True)

            self.assertEqual(result.errors, [])
            visual_path = next(
                path
                for path in project.definition_folder.glob("pages/*/visuals/*/visual.json")
                if json.loads(path.read_text(encoding="utf-8"))["name"] == "card1"
            )
            text = visual_path.read_text(encoding="utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertNotIn("\n  ", text)
            self.assertEqual(json.loads(text)["name"], "card1")

    def test_apply_can_skip_validation_passes(self) -> None:
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

            with mock.patch("pbi.apply.engine.validate_project") as validate_mock:
                result = apply_yaml(project, spec, validate=False)

            self.assertEqual(result.errors, [])
            validate_mock.assert_not_called()

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
                 mock.patch("pbi.apply.buffered.BufferedPbirApplySession._flush_to_project_root", side_effect=OSError("disk full")):
                result = apply_yaml_buffered(project, spec)

            self.assertTrue(result.rolled_back)
            self.assertEqual(result.errors, ["Commit failed: disk full"])
            with self.assertRaises(ValueError):
                project.find_page("Demo")
            restored = Project.find(root / "Sample.pbip")
            with self.assertRaises(ValueError):
                restored.find_page("Demo")

    def test_buffered_commit_uses_journal_instead_of_report_snapshot(self) -> None:
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
                 mock.patch("pbi.apply.buffered.shutil.copytree", wraps=__import__("shutil").copytree) as copytree_mock:
                result = apply_yaml_buffered(project, spec)

            self.assertEqual(result.errors, [])
            self.assertEqual(copytree_mock.call_count, 0)
            self.assertIsNotNone(project.find_page("Demo"))

    def test_buffered_post_commit_validation_failure_rolls_back(self) -> None:
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

            issue = ValidationIssue(
                "definition/report.json", "error", "forced validation failure"
            )
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001"]), \
                 mock.patch("pbi.apply.engine.validate_project", side_effect=[[], [issue]]):
                result = apply_yaml_buffered(project, spec)

            self.assertTrue(result.rolled_back)
            self.assertEqual(
                result.errors,
                [
                    "Post-apply validation: definition/report.json: forced validation failure"
                ],
            )
            restored = Project.find(root / "Sample.pbip")
            with self.assertRaises(ValueError):
                restored.find_page("Demo")

    def test_eager_complex_validation_failure_restores_whole_report_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001", "visual0002"]):
                initial_result = apply_yaml(project, _complex_rollback_initial_spec())
            self.assertEqual(initial_result.errors, [])
            project.clear_caches()
            before = _capture_tree(project.report_folder)
            issue = ValidationIssue(
                "definition/report.json", "error", "forced validation failure"
            )
            tokens = ["visual0003", "bookmark01", "bookmark02", "group00001"]

            with mock.patch("secrets.token_hex", side_effect=tokens), \
                 mock.patch("pbi.apply.engine.validate_project", side_effect=[[], [issue]]):
                result = apply_yaml(project, _complex_rollback_spec(), overwrite=True)

            self.assertTrue(result.rolled_back)
            self.assertEqual(_capture_tree(project.report_folder), before)

    def test_buffered_complex_validation_failure_restores_whole_report_tree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001", "visual0002"]):
                initial_result = apply_yaml(project, _complex_rollback_initial_spec())
            self.assertEqual(initial_result.errors, [])
            project.clear_caches()
            before = _capture_tree(project.report_folder)
            issue = ValidationIssue(
                "definition/report.json", "error", "forced validation failure"
            )
            tokens = ["visual0003", "bookmark01", "bookmark02", "group00001"]

            with mock.patch("secrets.token_hex", side_effect=tokens), \
                 mock.patch("pbi.apply.engine.validate_project", side_effect=[[], [issue]]):
                result = apply_yaml_buffered(project, _complex_rollback_spec(), overwrite=True)

            self.assertTrue(result.rolled_back)
            self.assertEqual(_capture_tree(project.report_folder), before)

    def test_buffered_validation_failure_rolls_back_overwrite_with_deleted_visual(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            initial = yaml.safe_dump(
                {
                    "version": 1,
                    "pages": [
                        {
                            "name": "Demo",
                            "visuals": [
                                {"name": "keep", "type": "cardVisual", "position": "0, 0"},
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
                            "visuals": [{"name": "keep", "position": "100, 100"}],
                        }
                    ],
                },
                sort_keys=False,
            )
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001", "visual0002"]):
                apply_yaml(project, initial)
            page = project.find_page("Demo")
            before = {
                visual.name: (visual.folder / "visual.json").read_bytes()
                for visual in project.get_visuals(page)
            }
            issue = ValidationIssue(
                "definition/report.json", "error", "forced validation failure"
            )

            with mock.patch("pbi.apply.engine.validate_project", side_effect=[[], [issue]]):
                result = apply_yaml_buffered(project, spec, overwrite=True)

            self.assertTrue(result.rolled_back)
            restored = Project.find(root / "Sample.pbip")
            restored_page = restored.find_page("Demo")
            restored_visuals = restored.get_visuals(restored_page)
            self.assertEqual([visual.name for visual in restored_visuals], ["keep", "remove"])
            self.assertEqual(
                {
                    visual.name: (visual.folder / "visual.json").read_bytes()
                    for visual in restored_visuals
                },
                before,
            )

    def test_buffered_post_commit_invariants_use_current_cached_state_until_cleanup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
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
                apply_yaml(project, initial)
            project.clear_caches()

            original_invariants = __import__(
                "pbi.apply.engine", fromlist=["_validate_apply_invariants"]
            )._validate_apply_invariants
            observed: list[list[str]] = []

            def assert_cached_current_state(validation_project: Project, result) -> None:
                self.assertIsNotNone(validation_project._pages_cache)
                page = validation_project.find_page("Demo")
                visuals = validation_project.get_visuals(page)
                names = [visual.name for visual in visuals]
                observed.append(names)
                self.assertEqual(names, ["keep"])
                original_invariants(validation_project, result)

            with mock.patch(
                "pbi.apply.engine._validate_apply_invariants",
                side_effect=assert_cached_current_state,
            ):
                result = apply_yaml_buffered(project, spec, overwrite=True)

            self.assertEqual(result.errors, [])
            self.assertEqual(observed, [["keep"]])
            self.assertIsNone(project._pages_cache)
            self.assertEqual(project._visuals_cache, {})

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

    def test_reconcile_bookmark_groups_raises_for_missing_bookmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            session = BufferedPbirApplySession(project=project, dry_run=False)

            with self.assertRaisesRegex(FileNotFoundError, 'Bookmark "Missing" not found'):
                session.reconcile_bookmark_groups([("Missing", "Group")])

    def test_first_time_theme_does_not_mutate_existing_staged_report_reference(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(Path(tmp))
            session = BufferedPbirApplySession(project=project, dry_run=False)
            report_path = project.definition_folder / "report.json"
            staged_report = {"layoutOptimization": "MobilePortrait"}
            session.dirty_json[report_path] = staged_report

            session.write_theme({"name": "Demo Theme"}, first_time=True)

            self.assertEqual(staged_report, {"layoutOptimization": "MobilePortrait"})
            self.assertIsNot(session.dirty_json[report_path], staged_report)
            self.assertIn("themeCollection", session.dirty_json[report_path])

    def test_created_dirs_under_deleted_visual_are_not_recreated(self) -> None:
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
            orphan_dir = visual.folder / "subresource"
            session = BufferedPbirApplySession(project=project, dry_run=False)
            session.created_dirs.add(orphan_dir)
            session.delete_visual(visual)

            session.commit()

            self.assertFalse(visual.folder.exists())
            self.assertFalse(orphan_dir.exists())

    def test_staged_bookmark_lookup_ignores_rewritten_path_old_display_name(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            bookmarks_dir = project.definition_folder / "bookmarks"
            bookmarks_dir.mkdir()
            _write_json(
                bookmarks_dir / "bookmark01.bookmark.json",
                {"displayName": "Old", "name": "bookmark01"},
            )
            session = BufferedPbirApplySession(project=project, dry_run=False)
            session.dirty_json[bookmarks_dir / "bookmark01.bookmark.json"] = {
                "displayName": "New",
                "name": "bookmark01",
            }

            self.assertIsNone(session._find_staged_bookmark_id_by_display("Old"))

    def test_reconcile_bookmark_groups_does_not_mutate_staged_meta_before_replacing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            bookmarks_dir = project.definition_folder / "bookmarks"
            session = BufferedPbirApplySession(project=project, dry_run=False)
            meta_path = bookmarks_dir / "bookmarks.json"
            staged_meta = {"items": [{"displayName": "Group", "children": []}]}
            session.dirty_json[meta_path] = staged_meta

            with mock.patch("secrets.token_hex", return_value="groupid"):
                session.reconcile_bookmark_groups([])

            self.assertNotIn("$schema", staged_meta)
            self.assertNotIn("name", staged_meta["items"][0])
            self.assertIsNot(session.dirty_json[meta_path], staged_meta)

    def test_staged_delete_replaces_cached_visual_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
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
            with mock.patch("secrets.token_hex", side_effect=["page000001", "visual0001", "visual0002"]):
                apply_yaml(project, initial)
            page = project.find_page("Demo")
            original_cached = project._get_visuals_cached(page)
            visual = project.find_visual(page, "remove")

            BufferedPbirApplySession(project=project, dry_run=False).delete_visual(visual)

            self.assertIsNot(project._get_visuals_cached(page), original_cached)
            self.assertEqual([visual.name for visual in original_cached], ["keep", "remove"])
            self.assertEqual([visual.name for visual in project._get_visuals_cached(page)], ["keep"])

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
