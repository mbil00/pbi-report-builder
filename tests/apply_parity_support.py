from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pbi.apply.state import ApplyResult


def assert_apply_results_equivalent(testcase: Any, eager: ApplyResult, buffered: ApplyResult) -> None:
    """Assert the user-visible apply summary is equivalent for parity tests."""
    testcase.assertEqual(buffered.pages_created, eager.pages_created)
    testcase.assertEqual(buffered.pages_updated, eager.pages_updated)
    testcase.assertEqual(buffered.visuals_created, eager.visuals_created)
    testcase.assertEqual(buffered.visuals_updated, eager.visuals_updated)
    testcase.assertEqual(buffered.visuals_deleted, eager.visuals_deleted)
    testcase.assertEqual(buffered.properties_set, eager.properties_set)
    testcase.assertEqual(buffered.bindings_added, eager.bindings_added)
    testcase.assertEqual(buffered.filters_added, eager.filters_added)
    testcase.assertEqual(buffered.interactions_set, eager.interactions_set)
    testcase.assertEqual(buffered.errors, eager.errors)
    testcase.assertEqual(buffered.warnings, eager.warnings)
    testcase.assertEqual(buffered.rolled_back, eager.rolled_back)


def assert_project_trees_equivalent(testcase: Any, left: Path, right: Path) -> None:
    """Compare two PBIP project trees for apply parity.

    JSON files are compared by parsed content so formatting does not matter.
    All other files are compared byte-for-byte.
    """
    left_files = _relative_files(left)
    right_files = _relative_files(right)
    testcase.assertEqual(right_files, left_files)

    for rel_path in left_files:
        left_file = left / rel_path
        right_file = right / rel_path
        if rel_path.suffix == ".json":
            testcase.assertEqual(
                _read_json(left_file),
                _read_json(right_file),
                f"JSON differs: {rel_path}",
            )
        else:
            testcase.assertEqual(
                left_file.read_bytes(),
                right_file.read_bytes(),
                f"File differs: {rel_path}",
            )


def _relative_files(root: Path) -> list[Path]:
    return sorted(
        path.relative_to(root)
        for path in root.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))
