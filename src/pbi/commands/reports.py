"""Report metadata CLI commands."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from pbi.properties import REPORT_PROPERTIES, get_property, list_properties, set_property
from pbi.resources import normalize_resource_packages
from pbi.schema_refs import REPORT_SCHEMA

from .common import ProjectOpt, console, get_project, parse_property_assignments

report_app = typer.Typer(help="Report metadata operations.", no_args_is_help=True)
report_annotation_app = typer.Typer(help="Report annotation operations.", no_args_is_help=True)
report_object_app = typer.Typer(help="Report-level object and array operations.", no_args_is_help=True)
report_app.add_typer(report_annotation_app, name="annotation")
report_app.add_typer(report_object_app, name="object")

_REPORT_OBJECT_KEYS = (
    "annotations",
    "filterConfig",
    "objects",
    "organizationCustomVisuals",
    "resourcePackages",
    "settings",
    "themeCollection",
)


def _save_report_json(project, data: dict) -> None:
    from pbi.project import _write_json

    _write_json(project.definition_folder / "report.json", data)


def _load_json_value(payload: str | None, from_file: Path | None) -> object:
    if payload is not None and from_file is not None:
        raise ValueError("Provide either inline JSON or --from-file, not both.")
    if from_file is not None:
        text = from_file.read_text(encoding="utf-8")
    elif payload is not None:
        text = payload
    else:
        raise ValueError("Provide JSON inline or via --from-file.")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON: {e}") from e


def _resolve_object_key(name: str) -> str:
    lowered = name.lower()
    for key in _REPORT_OBJECT_KEYS:
        if key.lower() == lowered:
            return key
    matches = difflib.get_close_matches(name, _REPORT_OBJECT_KEYS, n=3, cutoff=0.5)
    if matches:
        raise ValueError(f'Unknown report object "{name}". Did you mean: {", ".join(matches)}?')
    raise ValueError(f'Unknown report object "{name}". Available: {", ".join(_REPORT_OBJECT_KEYS)}')


def _annotation_rows(data: dict) -> list[dict]:
    annotations = data.get("annotations", [])
    if not isinstance(annotations, list):
        return []
    rows: list[dict] = []
    for entry in annotations:
        if isinstance(entry, dict) and "name" in entry and "value" in entry:
            rows.append(entry)
    return rows


def _find_annotation(data: dict, identifier: str) -> dict:
    rows = _annotation_rows(data)
    lowered = identifier.lower()

    for entry in rows:
        if str(entry.get("name", "")).lower() == lowered:
            return entry

    names = [str(entry.get("name", "")) for entry in rows]
    matches = difflib.get_close_matches(identifier, names, n=3, cutoff=0.5)
    if matches:
        raise ValueError(f'Annotation "{identifier}" not found. Did you mean: {", ".join(matches)}?')
    if names:
        raise ValueError(f'Annotation "{identifier}" not found. Available: {", ".join(names)}')
    raise ValueError("No annotations defined. Use `pbi report annotation set` to add one.")


def _normalize_report_object_value(key: str, value: object) -> object:
    if not isinstance(value, (dict, list)):
        raise ValueError("Report objects must be JSON objects or arrays.")
    if key == "resourcePackages":
        wrapper = {"resourcePackages": value}
        normalize_resource_packages(wrapper)
        return wrapper["resourcePackages"]
    return value


def _print_object_summary(name: str, value: object) -> None:
    table = Table(title=name, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Type", "array" if isinstance(value, list) else "object")
    if isinstance(value, list):
        table.add_row("Items", str(len(value)))
        if value and isinstance(value[0], dict):
            table.add_row("Item Keys", ", ".join(sorted(value[0].keys())))
    else:
        table.add_row("Keys", ", ".join(sorted(value.keys())))
    console.print(table)


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
        _save_report_json(proj, data)


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


@report_annotation_app.command("list")
def report_annotation_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List report annotations."""
    proj = get_project(project)
    rows = _annotation_rows(proj.get_report_meta())

    if as_json:
        console.print_json(json.dumps(rows, indent=2))
        return

    if not rows:
        console.print("[yellow]No annotations. Use `pbi report annotation set` to add one.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Report Annotations", box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Value")
    for entry in rows:
        table.add_row(str(entry["name"]), str(entry["value"]))
    console.print(table)


@report_annotation_app.command("get")
def report_annotation_get(
    name: Annotated[str, typer.Argument(help="Annotation name.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one report annotation."""
    proj = get_project(project)
    try:
        entry = _find_annotation(proj.get_report_meta(), name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        console.print_json(json.dumps(entry, indent=2))
        return

    table = Table(title=str(entry["name"]), box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Name", str(entry["name"]))
    table.add_row("Value", str(entry["value"]))
    console.print(table)


@report_annotation_app.command("set")
def report_annotation_set(
    name: Annotated[str, typer.Argument(help="Annotation name.")],
    value: Annotated[str, typer.Argument(help="Annotation value.")],
    project: ProjectOpt = None,
) -> None:
    """Create or update a report annotation."""
    proj = get_project(project)
    data = proj.get_report_meta()
    data.setdefault("$schema", REPORT_SCHEMA)
    annotations = data.setdefault("annotations", [])
    if not isinstance(annotations, list):
        console.print("[red]Error:[/red] report.annotations is not an array.")
        raise typer.Exit(1)

    for entry in annotations:
        if isinstance(entry, dict) and str(entry.get("name", "")).lower() == name.lower():
            old = entry.get("value")
            if str(old) == value:
                console.print(f'[dim]No change:[/dim] [cyan]{name}[/cyan] is already {value}')
                return
            entry["name"] = name
            entry["value"] = value
            _save_report_json(proj, data)
            console.print(f"[dim]{name}:[/dim] {old} [dim]->[/dim] {value}")
            return

    annotations.append({"name": name, "value": value})
    _save_report_json(proj, data)
    console.print(f'Created report annotation "[cyan]{name}[/cyan]"')


@report_annotation_app.command("delete")
def report_annotation_delete(
    name: Annotated[str, typer.Argument(help="Annotation name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a report annotation."""
    proj = get_project(project)
    data = proj.get_report_meta()
    annotations = data.get("annotations", [])
    if not isinstance(annotations, list):
        console.print("[yellow]No annotations. Use `pbi report annotation set` to add one.[/yellow]")
        raise typer.Exit(0)

    target = None
    for entry in annotations:
        if isinstance(entry, dict) and str(entry.get("name", "")).lower() == name.lower():
            target = entry
            break

    if target is None:
        try:
            _find_annotation(data, name)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        raise typer.Exit(1)

    target_name = str(target.get("name", name))
    if not force:
        confirm = typer.confirm(f'Delete "{target_name}"?')
        if not confirm:
            raise typer.Abort()

    annotations.remove(target)
    if not annotations:
        data.pop("annotations", None)
    _save_report_json(proj, data)
    console.print(f'Deleted report annotation "[cyan]{target_name}[/cyan]"')


@report_object_app.command("list")
def report_object_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List report-level objects and arrays."""
    proj = get_project(project)
    data = proj.get_report_meta()
    rows = []
    for name in _REPORT_OBJECT_KEYS:
        value = data.get(name)
        present = isinstance(value, (dict, list))
        size = len(value) if isinstance(value, (dict, list)) else 0
        rows.append({
            "name": name,
            "present": present,
            "type": "array" if isinstance(value, list) else ("object" if isinstance(value, dict) else ""),
            "size": size,
        })

    if as_json:
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title="Report Objects", box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Present")
    table.add_column("Size", justify="right")
    for row in rows:
        table.add_row(row["name"], row["type"], "yes" if row["present"] else "", str(row["size"]) if row["present"] else "")
    console.print(table)


@report_object_app.command("get")
def report_object_get(
    name: Annotated[str, typer.Argument(help="Top-level report object name.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one report-level object or array."""
    proj = get_project(project)
    data = proj.get_report_meta()
    try:
        key = _resolve_object_key(name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    value = data.get(key)
    if not isinstance(value, (dict, list)):
        console.print(f'[yellow]No report object configured for "[cyan]{key}[/cyan]".[/yellow]')
        raise typer.Exit(0)

    if raw:
        console.print_json(json.dumps(value, indent=2))
        return

    _print_object_summary(key, value)


@report_object_app.command("set")
def report_object_set(
    name: Annotated[str, typer.Argument(help="Top-level report object name.")],
    payload: Annotated[str | None, typer.Argument(help="Inline JSON object/array.", show_default=False)] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the JSON object/array from a file.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set one top-level report object or array from JSON."""
    proj = get_project(project)
    data = proj.get_report_meta()
    data.setdefault("$schema", REPORT_SCHEMA)

    try:
        key = _resolve_object_key(name)
        value = _normalize_report_object_value(key, _load_json_value(payload, from_file))
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old = data.get(key)
    if old == value:
        console.print(f'[dim]No change:[/dim] [cyan]{key}[/cyan] already matches the provided JSON')
        return

    data[key] = value
    _save_report_json(proj, data)
    console.print(f'Set report object "[cyan]{key}[/cyan]"')


@report_object_app.command("clear")
def report_object_clear(
    name: Annotated[str, typer.Argument(help="Top-level report object name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Remove one top-level report object or array."""
    proj = get_project(project)
    data = proj.get_report_meta()
    try:
        key = _resolve_object_key(name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if key not in data:
        console.print(f'[dim]No change:[/dim] [cyan]{key}[/cyan] is not configured')
        return

    if not force:
        confirm = typer.confirm(f'Clear report object "{key}"?')
        if not confirm:
            raise typer.Abort()

    data.pop(key, None)
    _save_report_json(proj, data)
    console.print(f'Cleared report object "[cyan]{key}[/cyan]"')
