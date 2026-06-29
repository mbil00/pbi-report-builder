from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import typer
from typer.testing import CliRunner

from pbi import cli
from pbi.batch_runner import (
    BatchSummary,
    parse_batch_lines,
    resolve_batch_input,
    run_batch,
)
from pbi.cli import app
from pbi.report_authoring import ReportAuthoring
from tests.cli_regressions_support import make_project


class _CapturingConsole:
    """Minimal console stand-in that records printed markup."""

    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, *args, **kwargs) -> None:
        self.lines.append(" ".join(str(a) for a in args))


def _make_project_with_visuals(root: Path):
    project = make_project(root)
    authoring = ReportAuthoring(project)
    page = authoring.create_page("Demo")
    first = authoring.create_visual(page, "cardVisual", x=0, y=0, width=100, height=50)
    first.data["name"] = "card1"
    first.save()
    second = authoring.create_visual(page, "cardVisual", x=120, y=0, width=100, height=50)
    second.data["name"] = "card2"
    second.save()
    return project


class ParseBatchLinesTests(unittest.TestCase):
    def test_skips_blank_and_comment_lines_but_keeps_hash_values(self) -> None:
        text = "\n".join(
            [
                "# a comment",
                "",
                "   ",
                'visual set Demo 1 title.text="Hi"',
                "  # indented comment",
                "page set Demo border.color=#EDEBE9",
            ]
        )
        lines = parse_batch_lines(text)
        self.assertEqual(
            lines,
            [
                (4, 'visual set Demo 1 title.text="Hi"'),
                (6, "page set Demo border.color=#EDEBE9"),
            ],
        )


class ResolveBatchInputTests(unittest.TestCase):
    def test_reads_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "script.txt"
            path.write_text("visual set Demo 1 title.show=true\n", encoding="utf-8")
            self.assertEqual(
                resolve_batch_input(str(path)),
                "visual set Demo 1 title.show=true\n",
            )

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(ValueError):
            resolve_batch_input("/no/such/script.txt")

    def test_empty_file_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "empty.txt"
            path.write_text("   \n", encoding="utf-8")
            with self.assertRaises(ValueError):
                resolve_batch_input(str(path))


class RunBatchTests(unittest.TestCase):
    def _cmd(self):
        return typer.main.get_command(app)

    def test_multiple_edits_land_in_one_process(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            console = _CapturingConsole()
            lines = parse_batch_lines(
                "\n".join(
                    [
                        "visual set Demo 1 title.show=true",
                        'visual set Demo 1 title.text="Region"',
                        "visual set Demo 2 title.show=true",
                    ]
                )
            )
            summary = run_batch(
                self._cmd(), lines, console=console, project=project.pbip_file
            )
            self.assertIsInstance(summary, BatchSummary)
            self.assertEqual(summary.ran, 3)
            self.assertEqual(summary.ok_count, 3)
            self.assertEqual(summary.failures, [])

            # Both edits must have persisted within the single batch process.
            project.clear_caches()
            page = project.find_page("Demo")
            card1 = project.find_visual(page, "card1")
            self.assertIn("Region", card1.folder.joinpath("visual.json").read_text())

    def test_continue_on_error_reports_failure_and_runs_rest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            console = _CapturingConsole()
            lines = parse_batch_lines(
                "\n".join(
                    [
                        "visual set Demo 1 title.show=true",
                        "visual set Demo 99 title.show=true",  # no such visual
                        "visual set Demo 2 title.show=true",
                    ]
                )
            )
            summary = run_batch(
                self._cmd(), lines, console=console, project=project.pbip_file
            )
            self.assertEqual(summary.ran, 3)
            self.assertEqual(summary.ok_count, 2)
            self.assertEqual([r.lineno for r in summary.failures], [2])

    def test_stop_on_error_halts_at_first_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            console = _CapturingConsole()
            lines = parse_batch_lines(
                "\n".join(
                    [
                        "visual set Demo 1 title.show=true",
                        "visual set Demo 99 title.show=true",  # fails
                        "visual set Demo 2 title.show=true",  # should not run
                    ]
                )
            )
            summary = run_batch(
                self._cmd(),
                lines,
                console=console,
                project=project.pbip_file,
                stop_on_error=True,
            )
            self.assertEqual(summary.ran, 2)
            self.assertEqual([r.ok for r in summary.results], [True, False])

    def test_nested_batch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            console = _CapturingConsole()
            lines = parse_batch_lines("batch other.txt\nrun other.txt")
            summary = run_batch(
                self._cmd(), lines, console=console, project=project.pbip_file
            )
            self.assertEqual(summary.ran, 2)
            self.assertEqual(summary.ok_count, 0)

    def test_nested_batch_with_root_project_option_is_rejected(self) -> None:
        console = _CapturingConsole()
        lines = parse_batch_lines(
            "\n".join(
                [
                    "--project /tmp/Sample.pbip batch other.txt",
                    "-p /tmp/Sample.pbip run other.txt",
                ]
            )
        )
        summary = run_batch(self._cmd(), lines, console=console)
        self.assertEqual(summary.ran, 2)
        self.assertEqual(summary.ok_count, 0)
        self.assertEqual([r.error for r in summary.results], [
            "nested 'batch' is not allowed inside a batch script",
            "nested 'run' is not allowed inside a batch script",
        ])

    def test_usage_error_is_caught_as_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            console = _CapturingConsole()
            lines = parse_batch_lines("nope-not-a-command")
            summary = run_batch(
                self._cmd(), lines, console=console, project=project.pbip_file
            )
            self.assertEqual(summary.ran, 1)
            self.assertFalse(summary.results[0].ok)
            self.assertEqual(summary.results[0].exit_code, 2)


class BatchCommandCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()

    def test_batch_command_applies_all_edits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            script = root / "edits.txt"
            script.write_text(
                "\n".join(
                    [
                        "# heterogeneous edits",
                        "visual set Demo 1 title.show=true",
                        'page set Demo displayName="Renamed"',
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = self.runner.invoke(
                app, ["batch", str(script), "-p", str(project.pbip_file)]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("successfully", result.output)

            project.clear_caches()
            page = project.find_page("Renamed")
            self.assertEqual(page.display_name, "Renamed")

    def test_batch_honors_root_level_project_option(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            script = root / "edits.txt"
            script.write_text("visual set Demo 1 title.show=true\n", encoding="utf-8")
            result = self.runner.invoke(
                app, ["-p", str(project.pbip_file), "batch", str(script)]
            )
            self.assertEqual(result.exit_code, 0, result.output)

            project.clear_caches()
            page = project.find_page("Demo")
            card1 = project.find_visual(page, "card1")
            self.assertIn("title", card1.folder.joinpath("visual.json").read_text())

    def test_run_alias_reports_failure_with_nonzero_exit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            script = root / "edits.txt"
            script.write_text(
                "\n".join(
                    [
                        "visual set Demo 1 title.show=true",
                        "visual set Demo 99 title.show=true",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = self.runner.invoke(
                app, ["run", str(script), "-p", str(project.pbip_file)]
            )
            self.assertEqual(result.exit_code, 1, result.output)
            self.assertIn("failed", result.output)

    def test_empty_script_is_a_noop(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            script = root / "edits.txt"
            script.write_text("# only a comment\n\n", encoding="utf-8")
            result = self.runner.invoke(
                app, ["batch", str(script), "-p", str(project.pbip_file)]
            )
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("No commands to run", result.output)


class LazyGroupTests(unittest.TestCase):
    def test_root_is_lazy_group_and_lists_all_commands(self) -> None:
        cmd = typer.main.get_command(app)
        self.assertIsInstance(cmd, cli.LazyGroup)
        names = set(cmd.list_commands(None))
        # Lazy groups and eager core commands are all advertised.
        for expected in ("visual", "model", "theme", "batch", "run", "apply", "info"):
            self.assertIn(expected, names)

    def test_heavy_apps_are_not_bound_eagerly_on_cli_module(self) -> None:
        # cli.py must no longer import these at module load; they load on demand.
        for attr in ("visual_app", "model_app", "theme_app", "bookmark_app"):
            self.assertFalse(hasattr(cli, attr), attr)

    def test_lazy_subcommand_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            result = CliRunner().invoke(
                app,
                ["visual", "set", "Demo", "1", "title.show=true", "-p", str(project.pbip_file)],
            )
            self.assertEqual(result.exit_code, 0, result.output)


if __name__ == "__main__":
    unittest.main()
