from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import yaml
from unittest import mock

from pbi.apply import apply_yaml, apply_yaml_buffered
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


if __name__ == "__main__":
    unittest.main()
