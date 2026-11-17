"""Tests for ``plan_bookmarks_spec``, bookmark lookup in apply, and the bookmarks branch.

The planner is a pure function of ``(project, bookmarks_spec) -> BookmarksApplyPlan``.
These tests drive the planner directly without any session, the lookup rules
through ``apply_yaml``, and the engine's ``_apply_bookmarks_branch`` against
``FakePbirWriteSession`` to assert the call sequence (write_bookmark per op,
then exactly one reconcile_bookmark_groups).

Group membership, hidden visuals and bookmark order are covered by the
fixture harness on report-03 (``test_report_roundtrip_is_noop``).
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import yaml

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

class ApplyBookmarkLookupTests(unittest.TestCase):
    """How ``apply`` matches a ``bookmarks:`` entry to an existing bookmark.

    Upsert matches the exact display name only: the CLI's substring lookup
    must never make apply overwrite an unrelated bookmark.
    """

    def _apply(self, project: Project, entries: list[dict]) -> ApplyResult:
        return apply_yaml(project, yaml.safe_dump({"pages": [], "bookmarks": entries}, sort_keys=False))

    def _files(self, project: Project) -> dict[str, bytes]:
        folder = project.definition_folder / "bookmarks"
        return {path.name: path.read_bytes() for path in sorted(folder.glob("*.bookmark.json"))}

    def test_name_contained_in_several_existing_names_creates_a_bookmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, _ = _seed_page_with_visual(project, "Demo")
            create_bookmark(project, "OverviewA", page, [])
            create_bookmark(project, "OverviewB", page, [])
            before = self._files(project)

            result = self._apply(project, [{"name": "Overview", "page": "Demo"}])

            self.assertEqual(result.errors, [])
            after = self._files(project)
            self.assertEqual({name: after[name] for name in before}, before)
            self.assertEqual(
                sorted(bookmark.display_name for bookmark in list_bookmarks(project)),
                ["Overview", "OverviewA", "OverviewB"],
            )

    def test_name_contained_in_one_existing_name_creates_a_bookmark(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, _ = _seed_page_with_visual(project, "Demo")
            create_bookmark(project, "OverviewFull", page, [])
            before = self._files(project)

            result = self._apply(project, [{"name": "Over", "page": "Demo"}])

            self.assertEqual(result.errors, [])
            after = self._files(project)
            self.assertEqual({name: after[name] for name in before}, before)
            self.assertEqual(
                sorted(bookmark.display_name for bookmark in list_bookmarks(project)),
                ["Over", "OverviewFull"],
            )

    def test_exact_name_updates_the_existing_bookmark_in_place(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, visual = _seed_page_with_visual(project, "Demo")
            existing = create_bookmark(project, "Existing", page, [visual])

            result = self._apply(project, [{"name": "Existing", "page": "Demo", "captureData": False}])

            self.assertEqual(result.errors, [])
            bookmarks = list_bookmarks(project)
            self.assertEqual(len(bookmarks), 1)
            self.assertEqual(bookmarks[0].name, existing["name"])
            self.assertEqual(bookmarks[0].file, f"{existing['name']}.bookmark.json")
            self.assertTrue(bookmarks[0].suppress_data)

    def test_two_existing_bookmarks_with_the_name_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            page, _ = _seed_page_with_visual(project, "Demo")
            create_bookmark(project, "Overview", page, [])
            create_bookmark(project, "Overview", page, [])
            before = self._files(project)

            result = self._apply(project, [{"name": "Overview", "page": "Demo"}])

            self.assertTrue(result.rolled_back)
            self.assertEqual(len(result.errors), 1)
            self.assertIn("Ambiguous", result.errors[0])
            self.assertIn("Overview", result.errors[0])
            self.assertEqual(self._files(project), before)

    def test_repeated_name_in_spec_writes_one_bookmark_last_entry_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "Demo", "table1")

            result = self._apply(
                project,
                [
                    {"name": "Overview", "page": "Demo", "hide": ["table1"], "group": "Old"},
                    {"name": "Overview", "page": "Demo", "captureData": False, "group": "New"},
                    # A group needs two members; one alone is written standalone.
                    {"name": "Detail", "page": "Demo", "group": "New"},
                ],
            )

            self.assertEqual(result.errors, [])
            self.assertFalse(result.rolled_back)
            bookmarks = {bookmark.display_name: bookmark for bookmark in list_bookmarks(project)}
            self.assertEqual(sorted(bookmarks), ["Detail", "Overview"])
            overview = bookmarks["Overview"]
            self.assertEqual(overview.group, "New")
            self.assertTrue(overview.suppress_data)
            self.assertEqual(overview.hidden_visuals, 0)

    def test_repeated_name_on_different_pages_is_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project(Path(tmp))
            _seed_page_with_visual(project, "PageA")
            _seed_page_with_visual(project, "PageB")

            result = self._apply(
                project,
                [{"name": "Overview", "page": "PageA"}, {"name": "Overview", "page": "PageB"}],
            )

            self.assertTrue(result.rolled_back)
            self.assertEqual(len(result.errors), 1)
            self.assertIn("Overview", result.errors[0])
            self.assertIn("page", result.errors[0])
            self.assertEqual(list_bookmarks(project), [])


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
