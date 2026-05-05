"""Tests for ``plan_theme_spec`` and the apply-leaf theme branch.

The planner is a pure function of ``(project, theme_spec) -> ThemeApplyPlan |
None``. These tests drive the planner directly without any session, plus one
apply-leaf test that drives ``apply_theme_branch`` against
``FakePbirWriteSession`` to assert the call sequence.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pbi.apply.engine import _apply_theme_branch
from pbi.apply.plan_theme import ThemeApplyPlan, plan_theme_spec
from pbi.apply.state import ApplyResult
from pbi.project import Project
from pbi.schema_refs import REPORT_SCHEMA

from tests.apply_session_fakes import FakePbirWriteSession


def _make_project_with_theme(
    root: Path,
    theme_data: dict | None,
) -> Project:
    """Build a project fixture optionally pre-applied with a custom theme."""
    pbip = root / "Sample.pbip"
    report_folder = root / "Sample.Report"
    definition = report_folder / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )

    report: dict = {
        "$schema": REPORT_SCHEMA,
        "themeCollection": {},
    }

    if theme_data is not None:
        resources = report_folder / "StaticResources" / "RegisteredResources"
        resources.mkdir(parents=True)
        theme_filename = "TestTheme.json"
        (resources / theme_filename).write_text(
            json.dumps(theme_data, indent=2),
            encoding="utf-8",
        )
        report["themeCollection"]["customTheme"] = {
            "name": theme_filename,
            "type": "RegisteredResources",
        }
        report["resourcePackages"] = [
            {
                "name": "SharedResources",
                "type": "SharedResources",
                "items": [
                    {
                        "name": theme_data.get("name", "TestTheme"),
                        "path": theme_filename,
                        "type": "CustomTheme",
                    }
                ],
            }
        ]

    (definition / "report.json").write_text(
        json.dumps(report) + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip)


class PlanThemeSpecTests(unittest.TestCase):
    """Pure-function planner: ``(project, theme_spec) -> ThemeApplyPlan | None``."""

    def test_empty_spec_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), {"name": "Existing"})
            self.assertIsNone(plan_theme_spec(project, {}))

    def test_partial_spec_merges_into_existing_theme_preserving_siblings(self) -> None:
        existing = {
            "name": "Existing",
            "dataColors": ["#111111", "#222222"],
            "foreground": "#000000",
            "textClasses": {"title": {"fontSize": 12}},
        }
        spec = {"foreground": "#ABCDEF"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            plan = plan_theme_spec(project, spec)

        self.assertIsInstance(plan, ThemeApplyPlan)
        assert plan is not None  # for type narrowing
        self.assertFalse(plan.first_time)
        self.assertEqual(plan.keys_touched, 1)
        self.assertEqual(plan.payload["foreground"], "#ABCDEF")
        # Siblings preserved.
        self.assertEqual(plan.payload["dataColors"], ["#111111", "#222222"])
        self.assertEqual(plan.payload["textClasses"], {"title": {"fontSize": 12}})
        self.assertEqual(plan.payload["name"], "Existing")

    def test_partial_spec_deep_merges_dicts(self) -> None:
        existing = {
            "name": "Existing",
            "textClasses": {
                "title": {"fontSize": 12, "color": "#000000"},
                "label": {"fontSize": 10},
            },
        }
        spec = {"textClasses": {"title": {"color": "#FF0000"}}}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            plan = plan_theme_spec(project, spec)

        assert plan is not None
        # Deep merge: title.fontSize preserved, title.color replaced, label preserved.
        self.assertEqual(
            plan.payload["textClasses"]["title"],
            {"fontSize": 12, "color": "#FF0000"},
        )
        self.assertEqual(plan.payload["textClasses"]["label"], {"fontSize": 10})

    def test_null_value_removes_key(self) -> None:
        existing = {
            "name": "Existing",
            "foreground": "#000000",
            "background": "#FFFFFF",
        }
        spec = {"foreground": None}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            plan = plan_theme_spec(project, spec)

        assert plan is not None
        self.assertNotIn("foreground", plan.payload)
        self.assertEqual(plan.payload["background"], "#FFFFFF")
        self.assertEqual(plan.keys_touched, 1)

    def test_missing_name_defaults_to_existing_name(self) -> None:
        existing = {"name": "MyTheme", "foreground": "#000000"}
        spec = {"foreground": "#ABCDEF"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            plan = plan_theme_spec(project, spec)

        assert plan is not None
        self.assertEqual(plan.payload["name"], "MyTheme")

    def test_missing_name_first_time_defaults_to_custom_theme(self) -> None:
        spec = {"foreground": "#ABCDEF"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), theme_data=None)
            plan = plan_theme_spec(project, spec)

        assert plan is not None
        self.assertTrue(plan.first_time)
        self.assertEqual(plan.payload["name"], "Custom Theme")

    def test_no_op_detection_returns_none(self) -> None:
        existing = {
            "name": "Existing",
            "foreground": "#000000",
            "dataColors": ["#111", "#222"],
        }
        # Re-applying current values should be a no-op.
        spec = {"foreground": "#000000"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            plan = plan_theme_spec(project, spec)

        self.assertIsNone(plan)

    def test_first_time_flag_set_when_no_theme_exists(self) -> None:
        spec = {"name": "Brand", "foreground": "#ABCDEF"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), theme_data=None)
            plan = plan_theme_spec(project, spec)

        assert plan is not None
        self.assertTrue(plan.first_time)
        self.assertEqual(plan.payload["name"], "Brand")
        self.assertEqual(plan.payload["foreground"], "#ABCDEF")
        # Both top-level keys touched.
        self.assertEqual(plan.keys_touched, 2)

    def test_keys_touched_counts_top_level_spec_keys(self) -> None:
        existing = {"name": "Existing"}
        spec = {"foreground": "#ABCDEF", "background": "#FFFFFF"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            plan = plan_theme_spec(project, spec)

        assert plan is not None
        self.assertEqual(plan.keys_touched, 2)


class ApplyThemeBranchSessionTests(unittest.TestCase):
    """The engine's theme branch persists exactly via ``session.write_theme``."""

    def test_apply_theme_branch_records_one_write_theme_call(self) -> None:
        existing = {"name": "Existing", "foreground": "#000000"}
        spec = {"foreground": "#ABCDEF"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_theme_branch(
                project,
                spec,
                result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            theme_calls = [c for c in session.calls if c[0] == "write_theme"]
            self.assertEqual(len(theme_calls), 1)
            _, payload, first_time = theme_calls[0]
            self.assertFalse(first_time)
            self.assertEqual(payload["foreground"], "#ABCDEF")
            self.assertEqual(payload["name"], "Existing")
            # ApplyResult accounting matches keys touched.
            self.assertEqual(result.properties_set, 1)

    def test_apply_theme_branch_reports_first_time_flag(self) -> None:
        spec = {"name": "Brand", "foreground": "#ABCDEF"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), theme_data=None)
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_theme_branch(
                project,
                spec,
                result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            theme_calls = [c for c in session.calls if c[0] == "write_theme"]
            self.assertEqual(len(theme_calls), 1)
            _, _, first_time = theme_calls[0]
            self.assertTrue(first_time)

    def test_apply_theme_branch_skips_session_on_no_op_spec(self) -> None:
        existing = {"name": "Existing", "foreground": "#000000"}
        spec = {"foreground": "#000000"}  # no-op
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_theme_branch(
                project,
                spec,
                result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            self.assertEqual(
                [c for c in session.calls if c[0] == "write_theme"],
                [],
            )
            self.assertEqual(result.properties_set, 0)

    def test_apply_theme_branch_skips_session_on_dry_run(self) -> None:
        # Dry-run still computes the plan and accounts for keys_touched, but
        # does not call session.write_theme.
        existing = {"name": "Existing", "foreground": "#000000"}
        spec = {"foreground": "#ABCDEF"}
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_theme(Path(tmp), existing)
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_theme_branch(
                project,
                spec,
                result,
                dry_run=True,
                session=session,  # type: ignore[arg-type]
            )

            self.assertEqual(
                [c for c in session.calls if c[0] == "write_theme"],
                [],
            )
            self.assertEqual(result.properties_set, 1)


if __name__ == "__main__":
    unittest.main()
