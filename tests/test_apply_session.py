"""Tests for the ApplySession lifecycle helper."""

from __future__ import annotations

import unittest
from dataclasses import dataclass, field

from pbi.apply.session import run_apply


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


if __name__ == "__main__":
    unittest.main()
