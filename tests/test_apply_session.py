"""Tests for the ApplySession lifecycle helper and PBIR write seam."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from pathlib import Path

from pbi.apply.session import run_apply
from pbi.apply.state import save_page_if_changed, save_visual_if_changed
from pbi.project import Page, Visual

from tests.apply_session_fakes import FakePbirWriteSession


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


if __name__ == "__main__":
    unittest.main()
