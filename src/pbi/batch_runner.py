"""In-process batch runner: execute many pbi sub-commands in one process.

Each line is a full pbi sub-command — the same text an agent would type after
``pbi`` (e.g. ``visual set "Sales" 1 title.show=true``). The Click command tree
is built once by the caller and reused for every line, so the per-process
startup cost (interpreter + imports + Typer command-tree construction) is paid
once instead of once per edit. This makes long edit sequences dramatically
faster than separate ``pbi ...`` invocations without requiring a YAML round-trip.
"""

from __future__ import annotations

import shlex
import sys
from dataclasses import dataclass, field
from pathlib import Path

import click

# Sub-commands that would re-enter this runner; disallowed inside a script to
# avoid surprising recursion / stdin re-reads.
_NESTED_COMMANDS = {"batch", "run"}
_ROOT_VALUE_OPTIONS = {"--project", "-p"}
_ROOT_VALUE_OPTION_PREFIXES = ("--project=",)


@dataclass
class BatchLineResult:
    """Outcome of dispatching a single batch line."""

    lineno: int
    command: str
    ok: bool
    exit_code: int
    error: str | None = None


@dataclass
class BatchSummary:
    """Aggregate outcome of a batch run."""

    results: list[BatchLineResult] = field(default_factory=list)

    @property
    def ran(self) -> int:
        return len(self.results)

    @property
    def failures(self) -> list[BatchLineResult]:
        return [r for r in self.results if not r.ok]

    @property
    def ok_count(self) -> int:
        return sum(1 for r in self.results if r.ok)


def resolve_batch_input(source: str | None) -> str:
    """Resolve batch script text from a file path, '-' sentinel, or piped stdin."""
    if source not in (None, "-"):
        path = source if isinstance(source, Path) else Path(source)
        path = path if path.is_absolute() else Path.cwd() / path
        if not path.exists():
            raise ValueError(f"File not found: {path}")
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            raise ValueError(f"Script file is empty: {path}")
        return text

    if not sys.stdin.isatty():
        text = sys.stdin.read()
        if text.strip():
            return text

    raise ValueError(
        "Provide a script file, use '-' to read from stdin, or pipe commands into the command."
    )


def parse_batch_lines(text: str) -> list[tuple[int, str]]:
    """Return (lineno, command) for each non-blank, non-comment line.

    Only a line whose first non-whitespace character is ``#`` is treated as a
    comment, so property values that contain ``#`` (e.g. colors like ``#EDEBE9``)
    are preserved.
    """
    lines: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.append((lineno, stripped))
    return lines


def run_batch(
    cmd: click.BaseCommand,
    lines: list[tuple[int, str]],
    *,
    console,
    project: Path | None = None,
    stop_on_error: bool = False,
    echo: bool = True,
) -> BatchSummary:
    """Dispatch each parsed line through ``cmd`` in the current process.

    ``cmd`` is the already-built root Click command. When ``project`` is given,
    it is injected as the root ``--project`` for every line (a line's own
    ``-p``/``--project`` still takes precedence), so a batch run targets one
    project without repeating the flag on each line.
    """
    summary = BatchSummary()
    project_args = ["--project", str(project)] if project is not None else []

    for lineno, line in lines:
        try:
            tokens = shlex.split(line)
        except ValueError as e:
            _record(summary, lineno, line, 2, f"parse error: {e}", console)
            if stop_on_error:
                break
            continue
        if not tokens:
            continue
        root_command = _root_command_token(tokens)
        if root_command in _NESTED_COMMANDS:
            _record(
                summary,
                lineno,
                line,
                2,
                f"nested '{root_command}' is not allowed inside a batch script",
                console,
            )
            if stop_on_error:
                break
            continue

        if echo:
            console.print(f"[dim]{lineno}:[/dim] [cyan]{line}[/cyan]")

        args = [*project_args, *tokens]
        error: str | None = None
        try:
            rv = cmd.main(args, prog_name="pbi", standalone_mode=False)
            # Success returns the command's return value (None); a command that
            # signals failure via ``raise typer.Exit(code)`` returns the int code.
            code = rv if isinstance(rv, int) else 0
        except click.exceptions.UsageError as e:
            code = e.exit_code or 2
            error = e.format_message()
            console.print(f"[red]Error:[/red] {error}")
        except click.exceptions.Abort:
            code = 1
            error = "aborted"
            console.print("[yellow]Aborted.[/yellow]")
        except SystemExit as e:  # defensive: a command called sys.exit directly
            code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
            if code:
                error = f"exited with code {code}"
        except Exception as e:  # a command raised an unexpected error
            code = 1
            error = f"{type(e).__name__}: {e}"
            console.print(f"[red]Error:[/red] {error}")

        ok = code == 0
        summary.results.append(BatchLineResult(lineno, line, ok, code, error))
        if not ok and stop_on_error:
            break

    return summary


def _root_command_token(tokens: list[str]) -> str | None:
    """Return the root command token after valid root-level options."""
    idx = 0
    while idx < len(tokens):
        token = tokens[idx]
        if token in _ROOT_VALUE_OPTIONS:
            idx += 2
            continue
        if any(token.startswith(prefix) for prefix in _ROOT_VALUE_OPTION_PREFIXES):
            idx += 1
            continue
        if token.startswith("-p") and token != "-p":
            idx += 1
            continue
        return token
    return None


def _record(
    summary: BatchSummary, lineno: int, line: str, code: int, error: str, console
) -> None:
    console.print(f"[red]Error:[/red] line {lineno}: {error}")
    summary.results.append(BatchLineResult(lineno, line, False, code, error))
