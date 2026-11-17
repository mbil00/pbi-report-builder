from __future__ import annotations

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
