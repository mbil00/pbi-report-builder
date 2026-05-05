"""Tests for ``plan_report_spec`` and the apply-leaf report branch.

The planner is a pure function of ``(project, report_spec) -> ReportApplyPlan
| None``. These tests drive the planner directly without any session, plus
apply-leaf tests that drive ``_apply_report_branch`` against
``FakePbirWriteSession`` to assert the call sequence, plus a diff regression
test that locks in fidelity between ``pbi diff`` and what ``pbi apply``
actually writes for a partial-key ``report:`` spec.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from pbi.apply.engine import _apply_report_branch
from pbi.apply.plan_report import ReportApplyPlan, plan_report_spec
from pbi.apply.state import ApplyResult
from pbi.cli import app
from pbi.project import Project
from pbi.schema_refs import REPORT_SCHEMA

from tests.apply_session_fakes import FakePbirWriteSession


def _make_project_with_report(
    root: Path,
    report_data: dict,
) -> Project:
    """Build a minimal PBIP project with a custom ``report.json`` payload."""
    pbip = root / "Sample.pbip"
    report_folder = root / "Sample.Report"
    definition = report_folder / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps(report_data) + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip)


class PlanReportSpecTests(unittest.TestCase):
    """Pure-function planner: ``(project, report_spec) -> ReportApplyPlan | None``."""

    def test_empty_spec_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(
                Path(tmp),
                {"$schema": REPORT_SCHEMA, "themeCollection": {}},
            )
            self.assertIsNone(plan_report_spec(project, {}))

    def test_partial_spec_merges_into_existing_report_preserving_siblings(self) -> None:
        existing = {
            "$schema": REPORT_SCHEMA,
            "themeCollection": {"baseTheme": {"name": "CY24SU10"}},
            "layoutOptimization": "None",
            "settings": {"useEnhancedTooltips": False, "pagesPosition": "Top"},
        }
        spec = {"layoutOptimization": "Vertical"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            plan = plan_report_spec(project, spec)

        self.assertIsInstance(plan, ReportApplyPlan)
        assert plan is not None  # for type narrowing
        self.assertEqual(plan.keys_touched, 1)
        self.assertEqual(plan.payload["layoutOptimization"], "Vertical")
        # Siblings preserved.
        self.assertEqual(
            plan.payload["themeCollection"], {"baseTheme": {"name": "CY24SU10"}}
        )
        self.assertEqual(
            plan.payload["settings"],
            {"useEnhancedTooltips": False, "pagesPosition": "Top"},
        )
        # ``$schema`` is preserved (set if missing) on the planned payload.
        self.assertEqual(plan.payload["$schema"], REPORT_SCHEMA)

    def test_partial_spec_deep_merges_dicts(self) -> None:
        existing = {
            "$schema": REPORT_SCHEMA,
            "settings": {
                "useEnhancedTooltips": False,
                "pagesPosition": "Top",
            },
        }
        spec = {"settings": {"useEnhancedTooltips": True}}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            plan = plan_report_spec(project, spec)

        assert plan is not None
        # Deep merge: useEnhancedTooltips replaced, pagesPosition preserved.
        self.assertEqual(
            plan.payload["settings"],
            {"useEnhancedTooltips": True, "pagesPosition": "Top"},
        )

    def test_null_value_removes_key(self) -> None:
        existing = {
            "$schema": REPORT_SCHEMA,
            "layoutOptimization": "None",
            "themeCollection": {"baseTheme": {"name": "CY24SU10"}},
        }
        spec = {"layoutOptimization": None}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            plan = plan_report_spec(project, spec)

        assert plan is not None
        self.assertNotIn("layoutOptimization", plan.payload)
        self.assertEqual(
            plan.payload["themeCollection"], {"baseTheme": {"name": "CY24SU10"}}
        )
        self.assertEqual(plan.keys_touched, 1)

    def test_resource_packages_normalized_through_planner(self) -> None:
        existing = {"$schema": REPORT_SCHEMA, "themeCollection": {}}
        # Legacy nested shape with ``resourcePackage`` wrapper, missing/odd
        # ``type`` and ``path`` -- normalization should rewrite into the
        # published schema shape.
        spec = {
            "resourcePackages": [
                {
                    "resourcePackage": {
                        "name": "RegisteredResources",
                        "items": [
                            {"name": "BrandTheme", "path": "BrandTheme.json"},
                        ],
                    }
                }
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            plan = plan_report_spec(project, spec)

        assert plan is not None
        packages = plan.payload["resourcePackages"]
        # Wrapper unwrapped, type populated, path coerced through normalizer.
        self.assertEqual(len(packages), 1)
        package = packages[0]
        self.assertEqual(package["name"], "RegisteredResources")
        self.assertIn("type", package)
        self.assertEqual(len(package["items"]), 1)
        item = package["items"][0]
        self.assertEqual(item["path"], "BrandTheme.json")
        # Items normalized to include ``type`` (CustomTheme inferred from
        # ``.json`` path or naming).
        self.assertIn("type", item)

    def test_no_op_detection_returns_none(self) -> None:
        existing = {
            "$schema": REPORT_SCHEMA,
            "layoutOptimization": "None",
            "settings": {"useEnhancedTooltips": False},
        }
        # Re-applying current values should be a no-op.
        spec = {"layoutOptimization": "None"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            plan = plan_report_spec(project, spec)

        self.assertIsNone(plan)

    def test_keys_touched_counts_top_level_spec_keys(self) -> None:
        existing = {"$schema": REPORT_SCHEMA, "themeCollection": {}}
        spec = {
            "layoutOptimization": "Vertical",
            "settings": {"useEnhancedTooltips": True},
        }
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            plan = plan_report_spec(project, spec)

        assert plan is not None
        self.assertEqual(plan.keys_touched, 2)

    def test_schema_set_when_missing_on_existing_report(self) -> None:
        # ``$schema`` set on the planned payload, but its addition alone is
        # not enough to trigger a non-None plan -- a real spec change is
        # also required.
        existing = {"themeCollection": {}}
        spec = {"layoutOptimization": "Vertical"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            plan = plan_report_spec(project, spec)

        assert plan is not None
        self.assertEqual(plan.payload["$schema"], REPORT_SCHEMA)


class ApplyReportBranchSessionTests(unittest.TestCase):
    """The engine's report branch persists exactly via ``session.write_report``."""

    def test_apply_report_branch_records_one_write_report_call(self) -> None:
        existing = {
            "$schema": REPORT_SCHEMA,
            "themeCollection": {},
            "layoutOptimization": "None",
        }
        spec = {"layoutOptimization": "Vertical"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_report_branch(
                project,
                spec,
                result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            report_calls = [c for c in session.calls if c[0] == "write_report"]
            self.assertEqual(len(report_calls), 1)
            _, payload = report_calls[0]
            self.assertEqual(payload["layoutOptimization"], "Vertical")
            # Siblings preserved into the persisted payload.
            self.assertEqual(payload["themeCollection"], {})
            # ApplyResult accounting matches keys touched.
            self.assertEqual(result.properties_set, 1)

    def test_apply_report_branch_skips_session_on_no_op_spec(self) -> None:
        existing = {
            "$schema": REPORT_SCHEMA,
            "layoutOptimization": "None",
        }
        spec = {"layoutOptimization": "None"}  # no-op
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_report_branch(
                project,
                spec,
                result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            self.assertEqual(
                [c for c in session.calls if c[0] == "write_report"],
                [],
            )
            self.assertEqual(result.properties_set, 0)

    def test_apply_report_branch_skips_session_on_dry_run(self) -> None:
        # Dry-run still computes the plan and accounts for keys_touched, but
        # does not call session.write_report.
        existing = {
            "$schema": REPORT_SCHEMA,
            "layoutOptimization": "None",
        }
        spec = {"layoutOptimization": "Vertical"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(Path(tmp), existing)
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_report_branch(
                project,
                spec,
                result,
                dry_run=True,
                session=session,  # type: ignore[arg-type]
            )

            self.assertEqual(
                [c for c in session.calls if c[0] == "write_report"],
                [],
            )
            self.assertEqual(result.properties_set, 1)

    def test_apply_report_branch_rejects_non_mapping_spec(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_report(
                Path(tmp), {"$schema": REPORT_SCHEMA, "themeCollection": {}}
            )
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_report_branch(
                project,
                ["not", "a", "mapping"],
                result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            self.assertIn("'report' must be a mapping.", result.errors)
            self.assertEqual(
                [c for c in session.calls if c[0] == "write_report"],
                [],
            )


class ReportDiffCommandTests(unittest.TestCase):
    """``pbi diff`` for ``report:`` should match what ``pbi apply`` writes."""

    def test_partial_key_diff_matches_what_apply_writes(self) -> None:
        """Regression: diff for a partial-key report spec matches apply.

        The previous behaviour flattened the YAML spec and compared it
        key-by-key to the full exported report. That diverged from apply
        for two cases: (1) ``null`` values in the spec rendered as
        ``-> null`` instead of ``-> (none)`` (apply *removes* the key),
        and (2) the diff couldn't represent siblings the merge would
        preserve. The planner-driven diff merges the spec into current
        state first so the rendered diff is exactly what apply persists.
        """
        runner = CliRunner()
        with tempfile.TemporaryDirectory() as tmp:
            existing = {
                "$schema": REPORT_SCHEMA,
                "themeCollection": {},
                "layoutOptimization": "None",
                "settings": {"useEnhancedTooltips": False},
            }
            pbip = Path(tmp) / "Test.pbip"
            report_folder = Path(tmp) / "Test.Report"
            definition = report_folder / "definition"
            definition.mkdir(parents=True)
            pbip.write_text(
                json.dumps(
                    {"artifacts": [{"report": {"path": "Test.Report"}}]}
                ) + "\n",
                encoding="utf-8",
            )
            (definition / "report.json").write_text(
                json.dumps(existing) + "\n", encoding="utf-8"
            )

            # Partial spec: replace layoutOptimization, remove settings via null.
            partial_spec = {
                "version": 1,
                "pages": [],
                "report": {
                    "layoutOptimization": "Vertical",
                    "settings": None,
                },
            }
            spec_file = Path(tmp) / "partial-report.yaml"
            spec_file.write_text(json.dumps(partial_spec), encoding="utf-8")

            result = runner.invoke(app, ["diff", str(spec_file), "-p", str(pbip)])
            self.assertEqual(result.exit_code, 0, result.stdout)
            # Replaced key shows the new value.
            self.assertIn("report.layoutOptimization", result.stdout)
            self.assertIn("Vertical", result.stdout)
            # The null-removed key shows ``(none)`` (post-apply state has no
            # ``settings`` key) and never the literal ``-> null`` string the
            # old flatten-compare bug produced.
            self.assertIn("settings", result.stdout)
            self.assertNotIn("-> null", result.stdout)


if __name__ == "__main__":
    unittest.main()
