from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from unittest import mock

from pbi.apply import apply_yaml, apply_yaml_buffered
from pbi.project import Project
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
            restored = Project.find(root / "Sample.pbip")
            with self.assertRaises(ValueError):
                restored.find_page("Demo")

    def test_unsupported_buffered_operation_returns_apply_result_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            spec = yaml.safe_dump(
                {
                    "version": 1,
                    "report": {"layoutOptimization": "MobilePortrait"},
                    "pages": [],
                },
                sort_keys=False,
            )

            result = apply_yaml_buffered(project, spec)

            self.assertTrue(result.errors)
            self.assertTrue(result.rolled_back)
            self.assertIn("write_report", result.errors[0])

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

            restored = Project.find(root / "Sample.pbip")
            with self.assertRaises(ValueError):
                restored.find_page("Demo")


if __name__ == "__main__":
    unittest.main()
