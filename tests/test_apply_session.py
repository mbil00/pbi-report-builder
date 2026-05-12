"""Tests for the ApplySession lifecycle helper and PBIR write seam."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from pathlib import Path

from pbi.apply.session import run_apply
from pbi.apply.state import (
    ApplyResult,
    PageVisualState,
    PbirApplySession,
    save_page_if_changed,
    save_visual_if_changed,
)
from pbi.apply.visuals import apply_visual
from pbi.project import Page, Project, Visual
from pbi.report_authoring import ReportAuthoring

from tests.apply_session_fakes import FakePbirWriteSession
from tests.cli_regressions_support import make_project


@dataclass
class _FakeSession:
    calls: list[str] = field(default_factory=list)

    def begin(self) -> None:
        self.calls.append("begin")

    def commit(self) -> None:
        self.calls.append("commit")

    def rollback(self) -> None:
        self.calls.append("rollback")

    def cleanup(self) -> None:
        self.calls.append("cleanup")


@dataclass
class _FakeResult:
    errors: list[str] = field(default_factory=list)
    rolled_back: bool = False


class RunApplyLifecycleTests(unittest.TestCase):
    def test_clean_body_commits(self) -> None:
        session = _FakeSession()
        result = run_apply(session, lambda: _FakeResult())
        self.assertEqual(session.calls, ["begin", "commit", "cleanup"])
        self.assertFalse(result.rolled_back)

    def test_body_exception_rolls_back_and_reraises(self) -> None:
        session = _FakeSession()

        def body() -> _FakeResult:
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            run_apply(session, body)
        self.assertEqual(session.calls, ["begin", "rollback", "cleanup"])

    def test_collected_errors_roll_back_and_mark_result(self) -> None:
        session = _FakeSession()

        def body() -> _FakeResult:
            return _FakeResult(errors=["bad"])

        result = run_apply(session, body)
        self.assertEqual(session.calls, ["begin", "rollback", "cleanup"])
        self.assertTrue(result.rolled_back)

    def test_collected_errors_with_continue_on_error_commits(self) -> None:
        session = _FakeSession()

        def body() -> _FakeResult:
            return _FakeResult(errors=["bad"])

        result = run_apply(session, body, continue_on_error=True)
        self.assertEqual(session.calls, ["begin", "commit", "cleanup"])
        self.assertFalse(result.rolled_back)

    def test_cleanup_runs_even_when_commit_raises(self) -> None:
        class _CommitFails(_FakeSession):
            def commit(self) -> None:
                self.calls.append("commit")
                raise RuntimeError("commit blew up")

        session = _CommitFails()
        with self.assertRaises(RuntimeError):
            run_apply(session, lambda: _FakeResult())
        self.assertEqual(session.calls, ["begin", "commit", "cleanup"])


class SaveVisualLeafSeamTests(unittest.TestCase):
    """Apply leaf paths that persist a Visual go through ``session.save_visual``.

    Drives ``save_visual_if_changed`` against an in-memory
    ``FakePbirWriteSession`` so the test runs without a PBIP project on disk.
    """

    def _make_visual(self, *, data: dict | None = None) -> Visual:
        # Folder is never touched because the fake records the call instead of
        # invoking ``Visual.save``; an arbitrary Path keeps the dataclass valid.
        return Visual(folder=Path("/nonexistent/visuals/v1"), data=data or {})

    def test_changed_visual_routes_through_save_visual(self) -> None:
        baseline = {"name": "v1", "visual": {"visualType": "card"}}
        visual = self._make_visual(data={**baseline, "isHidden": True})
        session = FakePbirWriteSession()

        wrote = save_visual_if_changed(
            project=None,  # type: ignore[arg-type]
            visual=visual,
            original_data=baseline,
            session=session,
        )

        self.assertTrue(wrote)
        self.assertEqual(session.call_names(), ["save_visual"])
        self.assertIs(session.calls[0][1], visual)

    def test_unchanged_visual_does_not_call_save_visual(self) -> None:
        baseline = {"name": "v1", "visual": {"visualType": "card"}}
        visual = self._make_visual(data=dict(baseline))
        session = FakePbirWriteSession()

        wrote = save_visual_if_changed(
            project=None,  # type: ignore[arg-type]
            visual=visual,
            original_data=baseline,
            session=session,
        )

        self.assertFalse(wrote)
        self.assertEqual(session.calls, [])

    def test_save_visual_does_not_call_ensure_snapshot_at_leaf(self) -> None:
        # Migrated leaf paths must not double-take the snapshot. The session
        # method absorbs the guard internally; the leaf only records
        # ``save_visual``.
        baseline = {"name": "v1"}
        visual = self._make_visual(data={**baseline, "tooltip": {"show": True}})
        session = FakePbirWriteSession()

        save_visual_if_changed(
            project=None,  # type: ignore[arg-type]
            visual=visual,
            original_data=baseline,
            session=session,
        )

        self.assertNotIn("ensure_snapshot", session.call_names())


class SavePageLeafSeamTests(unittest.TestCase):
    """Apply leaf paths that persist a Page go through ``session.save_page``.

    Drives ``save_page_if_changed`` against an in-memory
    ``FakePbirWriteSession`` so the test runs without a PBIP project on disk.
    """

    def _make_page(self, *, data: dict | None = None) -> Page:
        # Folder is never touched because the fake records the call instead of
        # invoking ``Page.save``; an arbitrary Path keeps the dataclass valid.
        return Page(folder=Path("/nonexistent/pages/p1"), data=data or {})

    def test_changed_page_routes_through_save_page(self) -> None:
        baseline = {"displayName": "Page 1", "width": 1280, "height": 720}
        page = self._make_page(data={**baseline, "displayOption": "FitToPage"})
        session = FakePbirWriteSession()

        wrote = save_page_if_changed(
            project=None,  # type: ignore[arg-type]
            page=page,
            original_data=baseline,
            session=session,
        )

        self.assertTrue(wrote)
        self.assertEqual(session.call_names(), ["save_page"])
        self.assertIs(session.calls[0][1], page)

    def test_unchanged_page_does_not_call_save_page(self) -> None:
        baseline = {"displayName": "Page 1", "width": 1280, "height": 720}
        page = self._make_page(data=dict(baseline))
        session = FakePbirWriteSession()

        wrote = save_page_if_changed(
            project=None,  # type: ignore[arg-type]
            page=page,
            original_data=baseline,
            session=session,
        )

        self.assertFalse(wrote)
        self.assertEqual(session.calls, [])

    def test_save_page_does_not_call_ensure_snapshot_at_leaf(self) -> None:
        # Migrated leaf paths must not double-take the snapshot. The session
        # method absorbs the guard internally; the leaf only records
        # ``save_page``.
        baseline = {"displayName": "Page 1"}
        page = self._make_page(data={**baseline, "visibility": "HiddenInViewMode"})
        session = FakePbirWriteSession()

        save_page_if_changed(
            project=None,  # type: ignore[arg-type]
            page=page,
            original_data=baseline,
            session=session,
        )

        self.assertNotIn("ensure_snapshot", session.call_names())


class _StubbedPbirWriteSession(FakePbirWriteSession):
    """Fake session that returns scaffolded entities from ``create_*``.

    Apply-leaf tests for the structural creation paths need the session to
    return Page/Visual objects that the leaf code can mutate. The plain
    ``FakePbirWriteSession`` returns ``None`` from those methods — useful for
    paths that do not consume the return value, but ``apply_visual`` and
    friends do, so a subclass scaffolds in-memory entities here.
    """

    def create_page(  # type: ignore[override]
        self,
        display_name: str,
        *,
        width: int = 1280,
        height: int = 720,
        display_option: str = "FitToPage",
    ) -> Page:
        super().create_page(
            display_name,
            width=width,
            height=height,
            display_option=display_option,
        )
        return Page(
            folder=Path("/fake/pages") / display_name.replace(" ", ""),
            data={
                "displayName": display_name,
                "width": width,
                "height": height,
                "displayOption": display_option,
            },
        )

    def create_visual(  # type: ignore[override]
        self,
        page: Page,
        visual_type: str,
        *,
        x: int = 0,
        y: int = 0,
        width: int = 300,
        height: int = 200,
        behind: bool = False,
    ) -> Visual:
        super().create_visual(
            page,
            visual_type,
            x=x,
            y=y,
            width=width,
            height=height,
            behind=behind,
        )
        return Visual(
            folder=Path("/fake/visuals/v_new"),
            data={
                "name": "v_new",
                "position": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                },
                "visual": {
                    "visualType": visual_type,
                    "query": {"queryState": {}},
                    "objects": {},
                },
            },
        )

    def create_group_container(  # type: ignore[override]
        self,
        page: Page,
        *,
        name: str | None = None,
        display_name: str | None = None,
        x: int = 0,
        y: int = 0,
        width: int = 0,
        height: int = 0,
    ) -> Visual:
        super().create_group_container(
            page,
            name=name,
            display_name=display_name,
            x=x,
            y=y,
            width=width,
            height=height,
        )
        return Visual(
            folder=Path("/fake/visuals") / (name or "g_new"),
            data={
                "name": name or "g_new",
                "position": {
                    "x": x,
                    "y": y,
                    "width": width,
                    "height": height,
                },
                "visualGroup": {"displayName": display_name or name or "group"},
            },
        )


class StructuralLeafSeamTests(unittest.TestCase):
    """Apply-leaf paths reach ``create_*`` / ``delete_visual`` through the session.

    Each test drives the migrated leaf path against ``_StubbedPbirWriteSession``
    so the call sequence is observable without touching a real PBIP project.
    """

    def _make_page(self) -> Page:
        return Page(
            folder=Path("/fake/pages/p1"),
            data={"displayName": "P1", "width": 1280, "height": 720},
        )

    def test_create_visual_routes_through_session(self) -> None:
        page = self._make_page()
        page_state = PageVisualState(page=page, visuals=[])
        session = _StubbedPbirWriteSession()

        apply_visual(
            project=None,  # type: ignore[arg-type]
            page=page,
            vis_spec={"name": "v1", "type": "cardVisual"},
            result=ApplyResult(),
            dry_run=False,
            style_cache={},
            session=session,  # type: ignore[arg-type]
            page_state=page_state,
        )

        names = session.call_names()
        self.assertEqual(names[0], "create_visual")
        # The eager save persists the name override before further mutation.
        self.assertIn("save_visual", names)
        self.assertNotIn("ensure_snapshot", names)

    def test_delete_visual_routes_through_session_on_type_conversion(self) -> None:
        # An existing card visual is replaced with a line chart. The migrated
        # path must read as: delete_visual → create_visual (→ optional
        # save_visual eager + final save_visual_if_changed equivalent).
        page = self._make_page()
        existing = Visual(
            folder=Path("/fake/visuals/v1"),
            data={
                "name": "v1",
                "position": {"x": 0, "y": 0, "width": 100, "height": 50},
                "visual": {
                    "visualType": "cardVisual",
                    "query": {"queryState": {}},
                    "objects": {},
                },
            },
        )
        page_state = PageVisualState(page=page, visuals=[existing])
        session = _StubbedPbirWriteSession()

        apply_visual(
            project=None,  # type: ignore[arg-type]
            page=page,
            vis_spec={"name": "v1", "type": "lineChart"},
            result=ApplyResult(),
            dry_run=False,
            style_cache={},
            session=session,  # type: ignore[arg-type]
            page_state=page_state,
        )

        names = session.call_names()
        self.assertEqual(names[0], "delete_visual")
        self.assertEqual(names[1], "create_visual")
        # The eager save_visual after the name override is the third call.
        self.assertEqual(names[2], "save_visual")
        # The two delete/create entries each carry their target object.
        self.assertIs(session.calls[0][1], existing)
        self.assertNotIn("ensure_snapshot", names)

    def test_create_group_container_routes_through_session(self) -> None:
        page = self._make_page()
        page_state = PageVisualState(page=page, visuals=[])
        session = _StubbedPbirWriteSession()

        apply_visual(
            project=None,  # type: ignore[arg-type]
            page=page,
            vis_spec={
                "name": "section",
                "type": "group",
                "displayName": "Section",
            },
            result=ApplyResult(),
            dry_run=False,
            style_cache={},
            session=session,  # type: ignore[arg-type]
            page_state=page_state,
        )

        names = session.call_names()
        self.assertEqual(names[0], "create_group_container")
        self.assertNotIn("ensure_snapshot", names)

    def test_create_page_routes_through_session(self) -> None:
        # Drive the apply_page leaf path for a brand-new page. The page
        # creation lookup is patched out so this test does not need a Project.
        from pbi.apply.pages import apply_page

        class _NoFindProject:
            root = Path("/fake/project")

            def find_page(self, _name: str) -> Page:
                raise ValueError("not found")

            def get_visuals(self, _page: Page) -> list[Visual]:
                return []

        session = _StubbedPbirWriteSession()
        result = ApplyResult()

        apply_page(
            project=_NoFindProject(),  # type: ignore[arg-type]
            page_spec={"name": "Demo", "width": 1280, "height": 720},
            result=result,
            dry_run=False,
            overwrite=False,
            style_cache={},
            session=session,  # type: ignore[arg-type]
        )

        names = session.call_names()
        self.assertEqual(names[0], "create_page")
        self.assertEqual(session.calls[0][1], "Demo")
        self.assertNotIn("ensure_snapshot", names)
        self.assertIn("Demo", result.pages_created)


class PbirApplySessionRollbackTests(unittest.TestCase):
    """End-to-end rollback regression for ``PbirApplySession``.

    Drives the real adapter against a real PBIP fixture: an apply that fails
    mid-flight (forced exception during a leaf write) must restore the report
    definition exactly to its pre-apply state.
    """

    def _capture_definition(self, project: Project) -> dict[str, bytes]:
        """Capture every file under the report definition folder by content."""
        folder = project.definition_folder
        return {
            str(path.relative_to(folder)): path.read_bytes()
            for path in sorted(folder.rglob("*"))
            if path.is_file()
        }

    def test_first_time_theme_orphan_file_survives_rollback(self) -> None:
        # ``PbirApplySession`` snapshots only ``definition/`` for rollback.
        # First-time ``write_theme`` routes through ``apply_theme``, which
        # copies the theme JSON into
        # ``<report>/StaticResources/RegisteredResources/`` -- outside the
        # snapshot. A mid-flight failure rolls back ``report.json`` (so the
        # ``themeCollection.customTheme`` reference disappears) but leaves
        # the resource file behind as an orphan.
        #
        # This test codifies the known gap so it stays visible. If the
        # snapshot scope is widened to the whole report folder (to close
        # the gap), invert this test rather than delete it; the
        # orphan-file behaviour shouldn't silently shift one way or the
        # other.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)

            session = PbirApplySession(project=project, dry_run=False)

            def body() -> ApplyResult:
                # First-time theme write: copies into RegisteredResources/
                # and updates report.json.
                session.write_theme(
                    {"name": "OrphanProbe", "dataColors": ["#123456"]},
                    first_time=True,
                )
                raise RuntimeError("forced mid-apply failure")

            with self.assertRaises(RuntimeError):
                run_apply(session, body)

            registered = (
                project.report_folder / "StaticResources" / "RegisteredResources"
            )
            orphans = list(registered.glob("OrphanProbe*.json")) if registered.exists() else []
            self.assertEqual(
                len(orphans), 1,
                f"expected orphan resource file, got: {orphans}",
            )

            # report.json reference was rolled back -- the orphan is no
            # longer referenced from the report definition.
            project.clear_caches()
            report = project.get_report_meta()
            custom = report.get("themeCollection", {}).get("customTheme")
            self.assertIsNone(
                custom,
                f"expected report.json to be rolled back, got customTheme={custom}",
            )

    def test_pbir_apply_session_restores_definition_on_mid_flight_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(
                page, "cardVisual", x=10, y=20, width=100, height=50
            )
            visual.data["name"] = "v1"
            visual.save()
            project.clear_caches()

            before = self._capture_definition(project)

            session = PbirApplySession(project=project, dry_run=False)

            def body() -> ApplyResult:
                # First leaf write triggers the lazy snapshot, then the
                # in-flight failure forces rollback.
                session.create_visual(
                    page, "lineChart", x=200, y=300, width=400, height=250
                )
                raise RuntimeError("forced mid-apply failure")

            with self.assertRaises(RuntimeError):
                run_apply(session, body)

            project.clear_caches()
            after = self._capture_definition(project)
            self.assertEqual(before, after)

            restored = Project.find(root / "Sample.pbip")
            restored_page = restored.find_page("Demo")
            visuals = restored.get_visuals(restored_page)
            self.assertEqual(len(visuals), 1)
            self.assertEqual(visuals[0].visual_type, "cardVisual")


if __name__ == "__main__":
    unittest.main()
