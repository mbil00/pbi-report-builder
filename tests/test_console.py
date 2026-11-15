"""The CLI console keeps piped output on one line per message (#48)."""

from __future__ import annotations

import io
import unittest
from unittest import mock

from pbi.commands.common import make_console


class _Stdout(io.StringIO):
    def __init__(self, tty: bool) -> None:
        super().__init__()
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


class MakeConsoleTests(unittest.TestCase):
    def _console(self, *, tty: bool, env: dict[str, str]):
        stdout = _Stdout(tty)
        with mock.patch.dict("os.environ", env, clear=True), mock.patch("sys.stdout", stdout):
            console = make_console()
            console.print("word " * 60)
        return console, stdout.getvalue()

    def test_piped_output_does_not_wrap(self) -> None:
        _, output = self._console(tty=False, env={})
        self.assertEqual(output.count("\n"), 1)

    def test_columns_env_still_sets_width(self) -> None:
        console, output = self._console(tty=False, env={"COLUMNS": "40"})
        self.assertEqual(console.width, 40)
        self.assertGreater(output.count("\n"), 1)

    def test_piped_output_has_no_styling(self) -> None:
        stdout = _Stdout(False)
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch("sys.stdout", stdout):
            make_console().print("[red]Error:[/red] boom")
        self.assertEqual(stdout.getvalue(), "Error: boom\n")


if __name__ == "__main__":
    unittest.main()
