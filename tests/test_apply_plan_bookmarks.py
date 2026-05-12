"""Tests for ``plan_bookmarks_spec`` and the apply-leaf bookmarks branch.

The planner is a pure function of ``(project, bookmarks_spec) -> BookmarksApplyPlan``.
These tests drive the planner directly without any session, plus apply-leaf
tests that drive ``_apply_bookmarks_branch`` against ``FakePbirWriteSession``
to assert the call sequence (write_bookmark per op, then exactly one
reconcile_bookmark_groups).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pbi.apply import apply_yaml
from pbi.apply.engine import _apply_bookmarks_branch
from pbi.apply.plan_bookmarks import (
    BookmarkPersist,
    BookmarksApplyPlan,
    plan_bookmarks_spec,
)
from pbi.apply.state import ApplyResult
from pbi.bookmarks import create_bookmark, list_bookmarks
from pbi.project import Project
from pbi.report_authoring import ReportAuthoring
from pbi.schema_refs import REPORT_SCHEMA

from tests.apply_session_fakes import FakePbirWriteSession


def _make_project(root: Path) -> Project:
    pbip = root / "Sample.pbip"
    report = root / "Sample.Report"
    definition = report / "definition"
    definition.mkdir(parents=True)
    pbip.write_text(
        json.dumps({"artifacts": [{"report": {"path": "Sample.Report"}}]}) + "\n",
        encoding="utf-8",
    )
    (definition / "report.json").write_text(
        json.dumps({"$schema": REPORT_SCHEMA, "themeCollection": {}}) + "\n",
        encoding="utf-8",
    )
    return Project.find(pbip)


def _seed_page_with_visual(project: Project, page_name: str, visual_name: str = "table1") -> tuple:
    """Create a page and a visual; return (page, visual)."""
    page = ReportAuthoring(project).create_page(page_name)
    visual = ReportAuthoring(project).create_visual(page, "tableEx")
    visual.data["name"] = visual_name
    visual.save()
    project.clear_caches()
    return page, visual


class PlanBookmarksSpecTests(unittest.TestCase):
    """Pure-function planner: ``(project, bookmarks_spec) -> BookmarksApplyPlan``."""

    def test_empty_spec_returns_empty_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            plan = plan_bookmarks_spec(project, [])
            self.assertIsInstance(plan, BookmarksApplyPlan)
            self.assertEqual(plan.operations, [])
            self.assertEqual(plan.groups, [])
            self.assertEqual(plan.errors, [])
            self.assertEqual(plan.keys_touched, 0)

    def test_single_bookmark_produces_one_persist_op_and_groups_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, _ = _seed_page_with_visual(project, "Demo")

            spec = [{"name": "Overview", "page": "Demo"}]
            plan = plan_bookmarks_spec(project, spec)

        self.assertEqual(len(plan.operations), 1)
        op = plan.operations[0]
        self.assertIsInstance(op, BookmarkPersist)
        self.assertEqual(op.display_name, "Overview")
        self.assertEqual(op.payload["displayName"], "Overview")
        self.assertEqual(
            op.payload["explorationState"]["activeSection"], page.name
        )
        self.assertTrue(op.payload["name"])  # bookmark id assigned
        self.assertEqual(op.file_path.name, f"{op.payload['name']}.bookmark.json")
        self.assertEqual(plan.groups, [("Overview", None)])
        self.assertEqual(plan.errors, [])
        self.assertEqual(plan.keys_touched, 1)

    def test_state_normalization_through_planner(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, _ = _seed_page_with_visual(project, "Demo")

            # ``state.sections`` keyed by the page *display* name should be
            # normalized to the page folder id on the planned payload.
            spec = [
                {
                    "name": "Filtered",
                    "page": "Demo",
                    "state": {
                        "sections": {
                            "Demo": {  # display name -> folder id after normalize
                                "visualContainers": {
                                    "table1": {
                                        "singleVisual": {"objects": {"title": {"show": True}}}
                                    }
                                }
                            }
                        }
                    },
                }
            ]
            plan = plan_bookmarks_spec(project, spec)

        op = plan.operations[0]
        sections = op.payload["explorationState"]["sections"]
        self.assertIn(page.name, sections)
        self.assertNotIn("Demo", sections)

    def test_hide_target_capture_flags_thread_into_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _, visual = _seed_page_with_visual(project, "Demo", "table1")

            spec = [
                {
                    "name": "Detailed",
                    "page": "Demo",
                    "hide": ["table1"],
                    "target": ["table1"],
                    "captureData": False,
                    "captureDisplay": False,
                    "capturePage": False,
                }
            ]
            plan = plan_bookmarks_spec(project, spec)

        op = plan.operations[0]
        # hidden visual recorded in the visual container.
        active_section = op.payload["explorationState"]["activeSection"]
        sections = op.payload["explorationState"]["sections"]
        container = sections[active_section]["visualContainers"][visual.name]
        self.assertEqual(container["singleVisual"]["display"]["mode"], "hidden")
        # Capture flags inverted into suppress* options.
        options = op.payload["options"]
        self.assertTrue(options["suppressActiveSection"])
        self.assertTrue(options["suppressData"])
        self.assertTrue(options["suppressDisplay"])
        self.assertTrue(options["applyOnlyToTargetVisuals"])
        self.assertEqual(options["targetVisualNames"], ["table1"])

    def test_group_hierarchy_partial_membership(self) -> None:
        # Some bookmarks reference a group, others don't.
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [
                {"name": "Standalone", "page": "Demo"},
                {"name": "GroupedA", "page": "Demo", "group": "Views"},
                {"name": "GroupedB", "page": "Demo", "group": "Views"},
                {"name": "Detached", "page": "Demo"},
            ]
            plan = plan_bookmarks_spec(project, spec)

        self.assertEqual(len(plan.operations), 4)
        self.assertEqual(
            plan.groups,
            [
                ("Standalone", None),
                ("GroupedA", "Views"),
                ("GroupedB", "Views"),
                ("Detached", None),
            ],
        )

    def test_missing_required_fields_collected_as_plan_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [
                "not a mapping",  # not a dict
                {"page": "Demo"},  # missing name
                {"name": "OK"},  # missing page
                {"name": "Valid", "page": "Demo"},
            ]
            plan = plan_bookmarks_spec(project, spec)

        # 3 errors, 1 valid op
        self.assertEqual(len(plan.errors), 3)
        self.assertIn("Bookmark must be a mapping.", plan.errors)
        self.assertEqual(plan.errors.count("Bookmark requires 'name' and 'page'."), 2)
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].display_name, "Valid")
        # keys_touched only counts entries that produced an op.
        self.assertEqual(plan.keys_touched, 1)

    def test_unresolvable_page_collected_as_plan_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [{"name": "BadPage", "page": "DoesNotExist"}]
            plan = plan_bookmarks_spec(project, spec)

        self.assertEqual(plan.operations, [])
        self.assertEqual(len(plan.errors), 1)
        self.assertIn("BadPage", plan.errors[0])
        # An entry that errors out before producing an op must not bump
        # keys_touched (which feeds ``ApplyResult.properties_set``).
        self.assertEqual(plan.keys_touched, 0)

    def test_ambiguous_existing_bookmark_collected_as_plan_error(self) -> None:
        # Two existing bookmarks whose display names both contain the spec
        # name as a substring make ``_find_bookmark_file`` raise
        # ``ValueError``. The planner must catch it and surface a per-
        # bookmark error -- if it propagates, ``run_apply`` rolls back and
        # reraises, turning a recoverable spec-level diagnostic into a full
        # apply failure.
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, _ = _seed_page_with_visual(project, "Demo")
            create_bookmark(project, "OverviewA", page, [])
            create_bookmark(project, "OverviewB", page, [])

            spec = [{"name": "Overview", "page": "Demo"}]
            plan = plan_bookmarks_spec(project, spec)

        self.assertEqual(plan.operations, [])
        self.assertEqual(len(plan.errors), 1)
        self.assertIn("Overview", plan.errors[0])
        self.assertIn("Ambiguous", plan.errors[0])
        self.assertEqual(plan.keys_touched, 0)

    def test_substring_match_does_not_clobber_unrelated_bookmark(self) -> None:
        # ``_find_bookmark_file`` falls back to case-insensitive substring
        # matching, which is the right behavior for user-facing CLI lookups
        # but a footgun for upsert. A spec entry "Over" against a project
        # whose only existing bookmark is "OverviewFull" must plan a fresh
        # bookmark file -- not reuse OverviewFull's path and clobber it in
        # place. Pre-existing flaw in ``upsert_bookmark`` that the planner
        # is the right place to tighten.
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, _ = _seed_page_with_visual(project, "Demo")

            existing = create_bookmark(project, "OverviewFull", page, [])
            existing_id = existing["name"]

            spec = [{"name": "Over", "page": "Demo"}]
            plan = plan_bookmarks_spec(project, spec)

        self.assertEqual(plan.errors, [])
        self.assertEqual(len(plan.operations), 1)
        op = plan.operations[0]
        # Fresh id distinct from the existing bookmark's, fresh file path.
        self.assertEqual(op.payload["displayName"], "Over")
        self.assertNotEqual(op.payload["name"], existing_id)
        self.assertNotEqual(op.file_path.name, f"{existing_id}.bookmark.json")

    def test_upsert_reuses_existing_bookmark_id_and_file_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, visual = _seed_page_with_visual(project, "Demo")

            existing = create_bookmark(project, "Existing", page, [visual])
            existing_id = existing["name"]

            spec = [{"name": "Existing", "page": "Demo", "captureData": False}]
            plan = plan_bookmarks_spec(project, spec)

        self.assertEqual(len(plan.operations), 1)
        op = plan.operations[0]
        # Reused id and the file path from the existing bookmark.
        self.assertEqual(op.payload["name"], existing_id)
        self.assertEqual(op.file_path.name, f"{existing_id}.bookmark.json")

    def test_duplicate_bookmark_names_are_coalesced_last_spec_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _, visual = _seed_page_with_visual(project, "Demo", "table1")

            spec = [
                {
                    "name": "Overview",
                    "page": "Demo",
                    "hide": ["table1"],
                    "group": "Old",
                },
                {
                    "name": "Overview",
                    "page": "Demo",
                    "captureData": False,
                    "group": "New",
                },
            ]
            plan = plan_bookmarks_spec(project, spec)

        self.assertEqual(plan.errors, [])
        # Duplicates collapse to a single op, and ``keys_touched`` reports
        # that single op (not the per-spec-entry count) so dry-run and
        # real-apply credit the same number into ``properties_set``.
        self.assertEqual(plan.keys_touched, 1)
        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.groups, [("Overview", "New")])
        op = plan.operations[0]
        self.assertEqual(op.display_name, "Overview")
        self.assertEqual(op.file_path.name, f"{op.payload['name']}.bookmark.json")
        options = op.payload["options"]
        self.assertTrue(options["suppressData"])
        active_section = op.payload["explorationState"]["activeSection"]
        containers = op.payload["explorationState"]["sections"][active_section][
            "visualContainers"
        ]
        self.assertNotIn(visual.name, containers)

    def test_apply_duplicate_bookmark_names_creates_one_bookmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo", "table1")

            result = apply_yaml(
                project,
                """
pages: []
bookmarks:
  - name: Overview
    page: Demo
    hide: [table1]
  - name: Overview
    page: Demo
    captureData: false
""",
            )

            bookmarks = list_bookmarks(project)

        self.assertEqual(result.errors, [])
        self.assertFalse(result.rolled_back)
        self.assertEqual(len(bookmarks), 1)
        self.assertEqual(bookmarks[0].display_name, "Overview")
        self.assertTrue(bookmarks[0].suppress_data)
        self.assertEqual(bookmarks[0].hidden_visuals, 0)

    def test_duplicate_bookmark_names_with_different_pages_surface_as_error(
        self,
    ) -> None:
        # Identical duplicates collapse via last-wins. Duplicates that
        # differ in their ``page`` field can't be coalesced -- a bookmark
        # belongs to exactly one page -- so the planner should surface a
        # spec error instead of silently letting the second entry win.
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "PageA")
            _seed_page_with_visual(project, "PageB")

            spec = [
                {"name": "Overview", "page": "PageA"},
                {"name": "Overview", "page": "PageB"},
            ]
            plan = plan_bookmarks_spec(project, spec)

        self.assertEqual(len(plan.operations), 1)
        self.assertEqual(plan.operations[0].display_name, "Overview")
        # First occurrence wins for the persisted op; the second is
        # surfaced as a spec error rather than silently coercing.
        self.assertEqual(len(plan.errors), 1)
        self.assertIn("Overview", plan.errors[0])
        self.assertIn("page", plan.errors[0])

    def test_relative_ordering_preserved_across_re_apply(self) -> None:
        # Spec order is preserved in plan.operations and plan.groups so that
        # ``reconcile_bookmark_groups`` writes meta items in the same order
        # on re-apply.
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [
                {"name": "Alpha", "page": "Demo"},
                {"name": "Beta", "page": "Demo"},
                {"name": "Gamma", "page": "Demo"},
            ]
            plan = plan_bookmarks_spec(project, spec)
            order_first = [op.display_name for op in plan.operations]
            groups_first = list(plan.groups)

            # Re-plan from same state and check stability.
            plan2 = plan_bookmarks_spec(project, spec)
            order_second = [op.display_name for op in plan2.operations]

        self.assertEqual(order_first, ["Alpha", "Beta", "Gamma"])
        self.assertEqual(order_second, order_first)
        self.assertEqual(
            groups_first,
            [("Alpha", None), ("Beta", None), ("Gamma", None)],
        )


class ApplyBookmarksBranchSessionTests(unittest.TestCase):
    """The engine's bookmarks branch persists exactly via the session.

    Asserts the full call sequence:
      1. N ``write_bookmark`` calls in spec order
      2. exactly one ``reconcile_bookmark_groups`` with the full group list
    """

    def test_apply_branch_records_write_bookmark_then_one_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [
                {"name": "Alpha", "page": "Demo"},
                {"name": "Beta", "page": "Demo", "group": "Views"},
                {"name": "Gamma", "page": "Demo", "group": "Views"},
            ]
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_bookmarks_branch(
                project, spec, result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            write_calls = [c for c in session.calls if c[0] == "write_bookmark"]
            reconcile_calls = [
                c for c in session.calls if c[0] == "reconcile_bookmark_groups"
            ]

            # N writes, in spec order, then exactly one reconcile.
            self.assertEqual(len(write_calls), 3)
            self.assertEqual(
                [c[1]["displayName"] for c in write_calls],
                ["Alpha", "Beta", "Gamma"],
            )
            # write_bookmark must come before reconcile_bookmark_groups.
            write_positions = [
                i for i, c in enumerate(session.calls) if c[0] == "write_bookmark"
            ]
            reconcile_positions = [
                i for i, c in enumerate(session.calls)
                if c[0] == "reconcile_bookmark_groups"
            ]
            self.assertEqual(len(reconcile_positions), 1)
            self.assertGreater(reconcile_positions[0], max(write_positions))

            # Reconcile receives the full (display, group | None) list.
            (_, groups) = reconcile_calls[0]
            self.assertEqual(
                groups,
                [
                    ("Alpha", None),
                    ("Beta", "Views"),
                    ("Gamma", "Views"),
                ],
            )

            # ApplyResult accounting matches keys touched.
            self.assertEqual(result.properties_set, 3)
            self.assertEqual(result.errors, [])

    def test_apply_branch_does_not_call_session_on_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [{"name": "Alpha", "page": "Demo"}]
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_bookmarks_branch(
                project, spec, result,
                dry_run=True,
                session=session,  # type: ignore[arg-type]
            )

            self.assertEqual(
                [c for c in session.calls if c[0] == "write_bookmark"], []
            )
            self.assertEqual(
                [c for c in session.calls if c[0] == "reconcile_bookmark_groups"], []
            )
            # keys_touched is still accounted for in dry-run mode.
            self.assertEqual(result.properties_set, 1)

    def test_reconcile_excludes_bookmarks_whose_write_failed(self) -> None:
        # If a per-bookmark ``write_bookmark`` raises, the engine collects
        # the error and continues. The final ``reconcile_bookmark_groups``
        # must run with only the bookmarks that successfully wrote --
        # otherwise ``_find_bookmark_file`` raises ``FileNotFoundError``
        # for the missing one and aborts the whole reconcile, so even the
        # bookmarks that did write lose their group membership in the
        # meta file.
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [
                {"name": "Alpha", "page": "Demo", "group": "Views"},
                {"name": "Beta", "page": "Demo", "group": "Views"},
                {"name": "Gamma", "page": "Demo", "group": "Views"},
            ]

            class _FailOnBeta(FakePbirWriteSession):
                def write_bookmark(self, payload, *, file_path):  # type: ignore[override]
                    super().write_bookmark(payload, file_path=file_path)
                    if payload.get("displayName") == "Beta":
                        raise OSError("disk full")

            session = _FailOnBeta()
            result = ApplyResult()

            _apply_bookmarks_branch(
                project, spec, result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            self.assertTrue(
                any("Beta" in e for e in result.errors),
                f"expected Beta in errors, got: {result.errors}",
            )
            reconcile_calls = [
                c for c in session.calls if c[0] == "reconcile_bookmark_groups"
            ]
            self.assertEqual(len(reconcile_calls), 1)
            (_, groups) = reconcile_calls[0]
            self.assertEqual(
                groups,
                [("Alpha", "Views"), ("Gamma", "Views")],
            )
            # The failed Beta write must not be credited to properties_set.
            # Three resolved spec entries; two successful writes.
            self.assertEqual(result.properties_set, 2)

    def test_dry_run_does_not_count_entries_with_unresolvable_page(self) -> None:
        # Behavior change vs. the pre-refactor ``apply_bookmarks_spec``:
        # that function's dry-run branch unconditionally bumped
        # ``properties_set`` for every dict entry with both ``name`` and
        # ``page``, before ever calling ``project.find_page``. The new
        # branch routes dry-run through ``plan_bookmarks_spec``, which
        # only increments ``keys_touched`` after ``find_page`` succeeds
        # -- so dry-run and the real apply now agree on the count for
        # specs that contain unresolvable page refs. This test locks
        # that convergence in so it can't silently regress.
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [
                {"name": "Valid", "page": "Demo"},
                {"name": "Bad", "page": "DoesNotExist"},
            ]
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_bookmarks_branch(
                project, spec, result,
                dry_run=True,
                session=session,  # type: ignore[arg-type]
            )

            # Only the valid entry contributes to properties_set.
            self.assertEqual(result.properties_set, 1)
            # The bad entry surfaces as a plan error.
            self.assertTrue(
                any("Bad" in e for e in result.errors),
                f"expected Bad in errors, got: {result.errors}",
            )
            # No session writes in dry-run.
            self.assertEqual(
                [c for c in session.calls if c[0] == "write_bookmark"], []
            )

    def test_apply_branch_surfaces_planner_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo")

            spec = [
                {"page": "Demo"},  # missing name
                {"name": "Valid", "page": "Demo"},
            ]
            session = FakePbirWriteSession()
            result = ApplyResult()

            _apply_bookmarks_branch(
                project, spec, result,
                dry_run=False,
                session=session,  # type: ignore[arg-type]
            )

            self.assertIn(
                "Bookmark requires 'name' and 'page'.", result.errors
            )
            # The valid spec entry still wrote.
            write_calls = [c for c in session.calls if c[0] == "write_bookmark"]
            self.assertEqual(len(write_calls), 1)


if __name__ == "__main__":
    unittest.main()
