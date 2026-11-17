"""Tests for the ApplySession lifecycle helper and PBIR write seam."""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import dataclass, field
from unittest import mock
from pathlib import Path

import yaml

from pbi.apply import apply_yaml
from pbi.apply.session import run_apply
from pbi.apply.state import ApplyResult, PbirApplySession
from pbi.project import Project
from pbi.report_authoring import ReportAuthoring

from tests.support import make_project


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

    def test_commit_exception_rolls_back_and_marks_result(self) -> None:
        class _CommitFails(_FakeSession):
            def commit(self) -> None:
                self.calls.append("commit")
                raise RuntimeError("commit blew up")

        session = _CommitFails()
        result = run_apply(session, lambda: _FakeResult())

        self.assertEqual(session.calls, ["begin", "commit", "rollback", "cleanup"])
        self.assertTrue(result.rolled_back)
        self.assertEqual(result.errors, ["Commit failed: commit blew up"])


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

    def _capture_report(self, project: Project) -> dict[str, bytes | None]:
        """Capture files and empty directories under the report folder."""
        folder = project.report_folder
        captured: dict[str, bytes | None] = {}
        for path in sorted(folder.rglob("*")):
            rel = str(path.relative_to(folder))
            if path.is_file():
                captured[rel] = path.read_bytes()
            elif path.is_dir() and not any(path.iterdir()):
                captured[f"{rel}/"] = None
        return captured

    def test_first_time_theme_temp_file_is_removed_when_replace_fails(self) -> None:
        # ``apply_theme_data`` writes .Theme.json.tmp before atomically
        # replacing the final resource file. If replace fails after the temp
        # file is written, rollback must remove that temp file too.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            registered = project.report_folder / "StaticResources" / "RegisteredResources"
            registered.mkdir(parents=True)
            before = self._capture_report(project)
            session = PbirApplySession(project=project, dry_run=False)

            def body() -> ApplyResult:
                with mock.patch("pathlib.Path.replace", side_effect=OSError("replace failed")):
                    session.write_theme(
                        {"name": "TempProbe", "dataColors": ["#123456"]},
                        first_time=True,
                    )
                return ApplyResult()

            with self.assertRaises(OSError):
                run_apply(session, body)

            self.assertEqual(self._capture_report(project), before)
            self.assertFalse((registered / ".TempProbe.json.tmp").exists())

    def test_first_time_theme_resource_is_removed_on_rollback(self) -> None:
        # Journal-backed eager rollback captures the report.json change and
        # first-time theme resource file, closing the old definition-snapshot
        # gap where orphan resource files survived rollback.
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
            self.assertEqual(orphans, [])

            # report.json reference was rolled back.
            project.clear_caches()
            report = project.get_report_meta()
            custom = report.get("themeCollection", {}).get("customTheme")
            self.assertIsNone(
                custom,
                f"expected report.json to be rolled back, got customTheme={custom}",
            )

    def test_eager_create_page_failure_removes_generated_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            pages_dir = project.definition_folder / "pages"
            session = PbirApplySession(project=project, dry_run=False)
            real_write_json = __import__("pbi.page_authoring", fromlist=["_write_json"])._write_json

            def fail_pages_meta(path: Path, data: dict) -> None:
                if path.name == "pages.json":
                    raise OSError("pages meta write failed")
                real_write_json(path, data)

            def body() -> ApplyResult:
                with mock.patch("pbi.page_authoring._write_json", side_effect=fail_pages_meta):
                    session.create_page("Generated")
                return ApplyResult()

            with mock.patch("secrets.token_hex", return_value="page000001"):
                with self.assertRaises(OSError):
                    run_apply(session, body)

            self.assertFalse((pages_dir / "page000001").exists())

    def test_eager_create_visual_failure_removes_generated_folder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visuals_dir = page.folder / "visuals"
            session = PbirApplySession(project=project, dry_run=False)
            real_write_json = __import__("pbi.visual_authoring", fromlist=["_write_json"])._write_json

            def fail_visual_write(path: Path, data: dict) -> None:
                if path.name == "visual.json":
                    raise OSError("visual write failed")
                real_write_json(path, data)

            def body() -> ApplyResult:
                with mock.patch("pbi.visual_authoring._write_json", side_effect=fail_visual_write):
                    session.create_visual(page, "cardVisual")
                return ApplyResult()

            with mock.patch("secrets.token_hex", return_value="visual0001"):
                with self.assertRaises(OSError):
                    run_apply(session, body)

            self.assertFalse((visuals_dir / "visual0001").exists())

    def test_failed_apply_restores_edited_page_and_removes_new_group(self) -> None:
        # Page saves and group creation must go through the session, so a
        # failed apply restores page.json and removes the new group folder.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(page, "cardVisual", x=10, y=20, width=100, height=50)
            visual.data["name"] = "card1"
            visual.save()
            before = self._capture_report(project)

            spec = {
                "pages": [
                    {
                        "name": "Demo",
                        "width": 1600,
                        "displayOption": "FitToWidth",
                        "visuals": [
                            {"name": "section", "type": "group", "displayName": "Section"},
                            {"name": "card1", "notARealProperty": {"bogus": True}},
                        ],
                    }
                ]
            }
            result = apply_yaml(project, yaml.safe_dump(spec, sort_keys=False))

            self.assertTrue(result.rolled_back)
            self.assertTrue(result.errors)
            self.assertEqual(self._capture_report(project), before)

    def test_eager_visual_update_rollback_uses_journal_without_copytree(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            page = ReportAuthoring(project).create_page("Demo")
            visual = ReportAuthoring(project).create_visual(
                page, "cardVisual", x=10, y=20, width=100, height=50
            )
            visual.data["name"] = "v1"
            visual.save()
            before = (visual.folder / "visual.json").read_bytes()

            session = PbirApplySession(project=project, dry_run=False)

            def body() -> ApplyResult:
                visual.data["position"]["x"] = 999
                session.save_visual(visual)
                raise RuntimeError("forced mid-apply failure")

            with mock.patch("shutil.copytree", wraps=__import__("shutil").copytree) as copytree_mock:
                with self.assertRaises(RuntimeError):
                    run_apply(session, body)

            self.assertEqual(copytree_mock.call_count, 0)
            self.assertEqual((visual.folder / "visual.json").read_bytes(), before)

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
                # First leaf write creates the rollback journal, then the
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
