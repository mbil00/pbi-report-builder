"""Report metadata CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from pbi.properties import REPORT_PROPERTIES, get_property, list_properties, set_property
from pbi.schema_refs import REPORT_SCHEMA

from .common import ProjectOpt, console, get_project, parse_property_assignments

report_app = typer.Typer(help="Report metadata operations.", no_args_is_help=True)


@report_app.command("get")
def report_get(
    props: Annotated[list[str] | None, typer.Argument(help="Property or properties to read (omit for overview).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show report metadata or one or more report properties."""
    proj = get_project(project)
    data = proj.get_report_meta()

    if props:
        if len(props) == 1:
            value = get_property(data, props[0], REPORT_PROPERTIES)
            console.print(value)
            return

        table = Table(title="Report Properties", box=box.SIMPLE)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        for prop in props:
            value = get_property(data, prop, REPORT_PROPERTIES)
            table.add_row(prop, "" if value is None else str(value))
        console.print(table)
        return

    table = Table(title="Report", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    for key in (
        "layoutOptimization",
        "reportSource",
        "settings.pagesPosition",
        "settings.exportDataMode",
        "settings.useEnhancedTooltips",
        "settings.allowInlineExploration",
        "settings.useCrossReportDrillthrough",
    ):
        value = get_property(data, key, REPORT_PROPERTIES)
        if value is not None:
            table.add_row(key, str(value))

    console.print(table)


@report_app.command("set")
def report_set(
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    project: ProjectOpt = None,
) -> None:
    """Set report metadata properties."""
    from pbi.project import _write_json

    proj = get_project(project)
    data = proj.get_report_meta()
    data.setdefault("$schema", REPORT_SCHEMA)
    data.setdefault("layoutOptimization", "None")
    data.setdefault("themeCollection", {})

    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    changed = False
    for prop, value in pairs:
        old = get_property(data, prop, REPORT_PROPERTIES)
        try:
            set_property(data, prop, value, REPORT_PROPERTIES)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {prop}: {e}")
            raise typer.Exit(1)
        new = get_property(data, prop, REPORT_PROPERTIES)
        if str(old) == str(new):
            console.print(f"[dim]No change:[/dim] [cyan]{prop}[/cyan] is already {new}")
        else:
            console.print(f"[dim]{prop}:[/dim] {old} [dim]->[/dim] {new}")
            changed = True

    if changed:
        _write_json(proj.definition_folder / "report.json", data)


@report_app.command("properties")
def report_props() -> None:
    """List available report metadata properties."""
    table = Table(title="Report Properties", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for name, vtype, desc, _group, _enums in list_properties(REPORT_PROPERTIES):
        table.add_row(name, vtype, desc)

    console.print(table)
