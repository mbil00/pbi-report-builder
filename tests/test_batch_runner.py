from __future__ import annotations

import io
import os
import signal
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import click
import typer
from rich.console import Console
from rich.errors import MarkupError
from typer.testing import CliRunner

from pbi import cli
from pbi.batch_runner import (
    BatchLineResult,
    BatchSummary,
    parse_batch_lines,
    resolve_batch_input,
    run_batch,
    split_command_line,
)
from pbi.cli import app
from pbi.report_authoring import ReportAuthoring
from tests.cli_regressions_support import make_project


# A minimal root group used to exercise run_batch's exception ladder with
# commands that raise specific exceptions, without depending on real command
# internals. run_batch only needs a click root command.
@click.group()
@click.option("--project", "-p", default=None)
def _fake_root(project=None):  # noqa: D401 - test fixture
    pass


@_fake_root.command("ok")
def _fake_ok():
    pass


@_fake_root.command("args")
@click.argument("rest", nargs=-1)
def _fake_args(rest):  # accepts any trailing tokens and succeeds
    pass


@_fake_root.command("boom")
def _fake_boom():
    raise KeyboardInterrupt()


@_fake_root.command("decline")
def _fake_decline():
    raise click.Abort()  # mimics `raise typer.Abort()` on a declined confirm


@_fake_root.command("exit0")
def _fake_exit0():
    raise typer.Exit(0)


@_fake_root.command("exit1")
def _fake_exit1():
    raise typer.Exit(1)


@_fake_root.command("prompt_interrupt")
def _fake_prompt_interrupt():
    # Mimic click.confirm()'s handling of Ctrl-C at a prompt: the SIGINT fires
    # (tripping run_batch's flag), the prompt catches the KeyboardInterrupt and
    # re-raises it as a bare Abort with no __cause__.
    try:
        signal.raise_signal(signal.SIGINT)
    except KeyboardInterrupt:
        raise click.Abort() from None


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


class SplitCommandLineTests(unittest.TestCase):
    def test_keeps_backslashes_and_handles_quotes(self) -> None:
        # Windows paths must survive intact; quotes are still processed away.
        self.assertEqual(
            split_command_line(
                r'--project=C:\Users\me\Report.pbip visual set "11 Slicers" 1 title.text="A B"'
            ),
            [
                r"--project=C:\Users\me\Report.pbip",
                "visual",
                "set",
                "11 Slicers",
                "1",
                "title.text=A B",
            ],
        )

    def test_hash_in_value_is_preserved(self) -> None:
        self.assertEqual(
            split_command_line("page set Demo border.color=#EDEBE9"),
            ["page", "set", "Demo", "border.color=#EDEBE9"],
        )

    def test_unbalanced_quote_raises(self) -> None:
        with self.assertRaises(ValueError):
            split_command_line('visual set "unterminated')

    def test_value_with_both_quote_types_is_mis_split(self) -> None:
        # Documented limitation: with backslash kept literal (escape=""), a value
        # containing BOTH a single and a double quote has no faithful inline
        # encoding — wrapping in double quotes silently strips the inner double
        # quotes. Lock this in so the docstring/help guidance (pass such DAX via
        # `model ... edit --from-file`) stays honest if the tokenizer changes.
        tokens = split_command_line(
            'model measure set Sales.Flag expression="IF(\'Sales T\'[x]>0,"Yes","No")"'
        )
        self.assertEqual(
            tokens[-1],
            "expression=IF('Sales T'[x]>0,Yes,No)",  # inner "Yes"/"No" quotes lost
        )

    def test_unquoted_apostrophe_error_explains_the_quoting_rule(self) -> None:
        # A bare apostrophe is an opening quote in POSIX shlex; the error must
        # point at the fix (wrap such values in double quotes), not just say
        # "No closing quotation".
        with self.assertRaises(ValueError) as ctx:
            split_command_line("page set Demo displayName=Customer's")
        self.assertIn("double quotes", str(ctx.exception))
        # The documented escape actually works.
        self.assertEqual(
            split_command_line('page set Demo displayName="Customer\'s Page"'),
            ["page", "set", "Demo", "displayName=Customer's Page"],
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

    def test_reads_from_piped_stdin_when_source_is_none(self) -> None:
        fake = io.StringIO("visual set Demo 1 title.show=true\n")
        with mock.patch("sys.stdin", fake):
            self.assertEqual(
                resolve_batch_input(None), "visual set Demo 1 title.show=true\n"
            )

    def test_reads_from_piped_stdin_with_dash(self) -> None:
        fake = io.StringIO("page set Demo displayName=Hi\n")
        with mock.patch("sys.stdin", fake):
            self.assertEqual(resolve_batch_input("-"), "page set Demo displayName=Hi\n")

    def test_tty_stdin_with_no_source_raises(self) -> None:
        fake = io.StringIO("")
        fake.isatty = lambda: True  # type: ignore[method-assign]
        with mock.patch("sys.stdin", fake):
            with self.assertRaises(ValueError):
                resolve_batch_input(None)

    def test_reads_relative_file_against_cwd(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "script.txt").write_text(
                "page set Demo displayName=Hi\n", encoding="utf-8"
            )
            prev = os.getcwd()
            try:
                os.chdir(root)
                self.assertEqual(
                    resolve_batch_input("script.txt"),
                    "page set Demo displayName=Hi\n",
                )
            finally:
                os.chdir(prev)


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

    def test_nested_batch_with_stop_on_error_halts_immediately(self) -> None:
        console = _CapturingConsole()
        lines = parse_batch_lines("batch other.txt\nvisual set Demo 1 title.show=true")
        summary = run_batch(
            self._cmd(), lines, console=console, stop_on_error=True
        )
        # The nested line is recorded as a failure and the batch halts before
        # the second line runs.
        self.assertEqual(summary.ran, 1)
        self.assertEqual(summary.ok_count, 0)
        self.assertFalse(summary.interrupted)

    def test_echo_true_prints_each_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_visuals(Path(tmp))
            console = _CapturingConsole()
            lines = parse_batch_lines("visual set Demo 1 title.show=true")
            run_batch(self._cmd(), lines, console=console, project=project.pbip_file)
            self.assertTrue(
                any("visual set Demo 1 title.show=true" in line for line in console.lines)
            )

    def test_echo_false_suppresses_line_echo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = _make_project_with_visuals(Path(tmp))
            console = _CapturingConsole()
            lines = parse_batch_lines("visual set Demo 1 title.show=true")
            run_batch(
                self._cmd(),
                lines,
                console=console,
                project=project.pbip_file,
                echo=False,
            )
            # run_batch's console only captures its own echo/error output (a
            # command's own success output goes to a different console), so a
            # clean run with echo disabled prints nothing here.
            self.assertEqual(console.lines, [])

    def test_line_level_project_overrides_batch_level(self) -> None:
        with tempfile.TemporaryDirectory() as ta, tempfile.TemporaryDirectory() as tb:
            proj_a = _make_project_with_visuals(Path(ta))
            proj_b = _make_project_with_visuals(Path(tb))
            console = _CapturingConsole()
            # Batch-level project is A, but the line explicitly targets B.
            lines = parse_batch_lines(
                f'visual set Demo 1 title.text="OnlyInB" -p {proj_b.pbip_file}'
            )
            summary = run_batch(
                self._cmd(), lines, console=console, project=proj_a.pbip_file
            )
            self.assertEqual(summary.ok_count, 1)

            proj_a.clear_caches()
            proj_b.clear_caches()
            a_card = proj_a.find_visual(proj_a.find_page("Demo"), "card1")
            b_card = proj_b.find_visual(proj_b.find_page("Demo"), "card1")
            self.assertIn(
                "OnlyInB", b_card.folder.joinpath("visual.json").read_text()
            )
            self.assertNotIn(
                "OnlyInB", a_card.folder.joinpath("visual.json").read_text()
            )


class RunBatchExceptionLadderTests(unittest.TestCase):
    """Exercise run_batch's exception handling with a synthetic command group."""

    def test_keyboard_interrupt_stops_batch_and_returns_summary(self) -> None:
        console = _CapturingConsole()
        lines = parse_batch_lines("ok\nboom\nok")
        summary = run_batch(_fake_root, lines, console=console)
        self.assertTrue(summary.interrupted)
        # The first line ran; the interrupted line and everything after it did not.
        self.assertEqual(summary.ran, 1)
        self.assertEqual(summary.ok_count, 1)

    def test_keyboard_interrupt_at_confirmation_prompt_stops_batch(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            self.skipTest("SIGINT handler is only installed on the main thread")
        console = _CapturingConsole()
        lines = parse_batch_lines("ok\nprompt_interrupt\nok")
        summary = run_batch(_fake_root, lines, console=console)
        # A Ctrl-C swallowed by a confirmation prompt (Abort with no __cause__)
        # must still stop the whole batch, not just skip the prompting line.
        self.assertTrue(summary.interrupted)
        self.assertEqual(summary.ran, 1)
        self.assertEqual(summary.ok_count, 1)

    def test_plain_abort_is_recorded_and_batch_continues(self) -> None:
        console = _CapturingConsole()
        lines = parse_batch_lines("ok\ndecline\nok")
        summary = run_batch(_fake_root, lines, console=console)
        self.assertFalse(summary.interrupted)
        self.assertEqual(summary.ran, 3)
        self.assertEqual(summary.ok_count, 2)
        self.assertEqual([r.lineno for r in summary.failures], [2])

    def test_typer_exit_codes_are_captured(self) -> None:
        console = _CapturingConsole()
        lines = parse_batch_lines("exit0\nexit1")
        summary = run_batch(_fake_root, lines, console=console)
        self.assertEqual(summary.ran, 2)
        self.assertTrue(summary.results[0].ok)
        self.assertEqual(summary.results[0].exit_code, 0)
        self.assertFalse(summary.results[1].ok)
        self.assertEqual(summary.results[1].exit_code, 1)


class RunBatchMarkupSafetyTests(unittest.TestCase):
    """A line/error containing Rich markup must not crash or be silently garbled.

    These use a real rich.Console (the _CapturingConsole stand-in bypasses Rich's
    markup parser, which is exactly why the bug was invisible to the other tests).
    """

    def _console_to_buffer(self):
        buf = io.StringIO()
        return Console(file=buf, force_terminal=False, soft_wrap=True), buf

    def test_markup_tokens_in_lines_are_echoed_literally_without_crashing(self) -> None:
        console, buf = self._console_to_buffer()
        # '[/done]' is a Rich closing tag — an unescaped echo raises MarkupError
        # and the whole batch dies. '[default]' is a documented selector token —
        # an unescaped echo silently consumes it as a style span.
        lines = parse_batch_lines(
            "\n".join(
                [
                    "args title.text=[/done]",
                    "args chart:legend.position [default]=Top",
                    "args plain",
                ]
            )
        )
        summary = run_batch(_fake_root, lines, console=console)
        self.assertFalse(summary.interrupted)
        self.assertEqual(summary.ran, 3)
        self.assertEqual(summary.ok_count, 3)
        out = buf.getvalue()
        self.assertIn("[/done]", out)
        self.assertIn("[default]", out)

    def test_markup_in_command_error_does_not_crash_reporting(self) -> None:
        # 'ok [/x]' carries a closing tag in BOTH the echo and the resulting
        # UsageError ("Got unexpected extra argument ([/x])"); neither may crash.
        console, buf = self._console_to_buffer()
        lines = parse_batch_lines("ok [/x]")
        summary = run_batch(_fake_root, lines, console=console)
        self.assertEqual(summary.ran, 1)
        self.assertFalse(summary.results[0].ok)
        self.assertEqual(summary.results[0].exit_code, 2)
        self.assertIn("[/x]", buf.getvalue())


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

    def test_batch_reads_script_from_stdin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            result = self.runner.invoke(
                app,
                ["batch", "-", "-p", str(project.pbip_file)],
                input='visual set Demo 1 title.text="FromStdin"\n',
            )
            self.assertEqual(result.exit_code, 0, result.output)

            project.clear_caches()
            card1 = project.find_visual(project.find_page("Demo"), "card1")
            self.assertIn(
                "FromStdin", card1.folder.joinpath("visual.json").read_text()
            )

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

    def test_stop_on_error_cli_halts_and_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            script = root / "edits.txt"
            script.write_text(
                "\n".join(
                    [
                        'visual set Demo 99 title.text="X"',  # fails first
                        'visual set Demo 1 title.text="ShouldNotApply"',  # must not run
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            result = self.runner.invoke(
                app,
                ["batch", str(script), "--stop-on-error", "-p", str(project.pbip_file)],
            )
            self.assertEqual(result.exit_code, 1, result.output)
            project.clear_caches()
            card1 = project.find_visual(project.find_page("Demo"), "card1")
            self.assertNotIn(
                "ShouldNotApply", card1.folder.joinpath("visual.json").read_text()
            )

    def test_interrupt_exits_130(self) -> None:
        # No real command interrupts on demand, so drive an interrupted summary
        # straight through batch_cmd to lock in the 130 exit code (cli.py).
        summary = BatchSummary(
            results=[BatchLineResult(1, "visual set Demo 1 title.show=true", True, 0)],
            interrupted=True,
        )
        with mock.patch("pbi.batch_runner.run_batch", return_value=summary), mock.patch(
            "pbi.batch_runner.resolve_batch_input",
            return_value="visual set Demo 1 title.show=true\n",
        ):
            result = self.runner.invoke(app, ["batch", "ignored.txt"])
        self.assertEqual(result.exit_code, 130, result.output)
        self.assertIn("interrupted", result.output.lower())

    def test_interrupt_with_failures_exits_130(self) -> None:
        summary = BatchSummary(
            results=[BatchLineResult(1, "visual set Demo 99 x=1", False, 1, "boom")],
            interrupted=True,
        )
        with mock.patch("pbi.batch_runner.run_batch", return_value=summary), mock.patch(
            "pbi.batch_runner.resolve_batch_input",
            return_value="visual set Demo 99 x=1\n",
        ):
            result = self.runner.invoke(app, ["batch", "ignored.txt"])
        self.assertEqual(result.exit_code, 130, result.output)

    def test_resolve_error_with_markup_in_path_is_escaped_not_crashed(self) -> None:
        # A bad script path containing Rich-markup characters must surface a clean
        # error, not crash reporting (a stray closing tag -> MarkupError) and not
        # silently drop part of the filename (a tag-like token -> vanishes).
        cases = [("[/red]", "[/red]"), ("report-[v2].pbip", "[v2]")]
        for bad_path, marker in cases:
            for verb in ("batch", "run"):
                with self.subTest(verb=verb, path=bad_path):
                    result = self.runner.invoke(app, [verb, bad_path])
                    self.assertEqual(result.exit_code, 1, result.output)
                    self.assertNotIsInstance(result.exception, MarkupError)
                    self.assertIn("File not found", result.output)
                    # The markup token survives literally rather than crashing
                    # reporting or being swallowed by Rich's markup parser.
                    self.assertIn(marker, result.output)


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

    def test_heavy_group_is_built_once_and_reused(self) -> None:
        # The headline perf win: a heavy group is imported/built once per process
        # and cached, so repeated dispatch (e.g. across batch lines) does not
        # rebuild the Click tree. A regression that rebuilt per call would fail.
        cmd = typer.main.get_command(app)
        real = cli._load_lazy_command
        calls: list[str] = []

        def spy(name):
            calls.append(name)
            return real(name)

        with mock.patch.object(cli, "_load_lazy_command", side_effect=spy):
            first = cmd.get_command(None, "visual")
            second = cmd.get_command(None, "visual")
            third = cmd.get_command(None, "visual")
        self.assertEqual(calls, ["visual"])
        self.assertIs(first, second)
        self.assertIs(second, third)

    def test_lazy_subcommand_dispatches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = _make_project_with_visuals(root)
            result = CliRunner().invoke(
                app,
                ["visual", "set", "Demo", "1", "title.show=true", "-p", str(project.pbip_file)],
            )
            self.assertEqual(result.exit_code, 0, result.output)

    def test_lazy_group_help_imports_and_lists_subcommands(self) -> None:
        # `pbi visual --help` must build the lazy group on demand and show it.
        result = CliRunner().invoke(app, ["visual", "--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("set", result.output)

    def test_root_help_advertises_lazy_groups(self) -> None:
        result = CliRunner().invoke(app, ["--help"])
        self.assertEqual(result.exit_code, 0, result.output)
        for group in ("visual", "model", "theme", "batch", "run"):
            self.assertIn(group, result.output)


if __name__ == "__main__":
    unittest.main()
