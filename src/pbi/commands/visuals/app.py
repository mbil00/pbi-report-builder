"""Typer app definitions for visual commands."""

from __future__ import annotations

import typer

visual_app = typer.Typer(help="Visual operations.", no_args_is_help=True)
visual_arrange_app = typer.Typer(help="Visual layout operations.", no_args_is_help=True)
visual_sort_app = typer.Typer(help="Visual sort operations.", no_args_is_help=True)
visual_format_app = typer.Typer(help="Visual conditional formatting operations.", no_args_is_help=True)

visual_app.add_typer(visual_sort_app, name="sort")
visual_app.add_typer(visual_format_app, name="format")
visual_app.add_typer(visual_arrange_app, name="arrange")
