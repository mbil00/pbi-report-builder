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
report_resource_app = typer.Typer(help="Report resource package operations.", no_args_is_help=True)
report_resource_package_app = typer.Typer(help="Resource package operations.", no_args_is_help=True)
report_resource_item_app = typer.Typer(help="Resource item operations.", no_args_is_help=True)
report_custom_visual_app = typer.Typer(help="Organization custom visual operations.", no_args_is_help=True)
report_data_source_variables_app = typer.Typer(help="Report dataSourceVariables operations.", no_args_is_help=True)
report_app.add_typer(report_annotation_app, name="annotation")
report_app.add_typer(report_object_app, name="object")
# Power-user features — fully functional but hidden from default --help
report_app.add_typer(report_resource_app, name="resource", hidden=True)
report_app.add_typer(report_custom_visual_app, name="custom-visual", hidden=True)
report_app.add_typer(report_data_source_variables_app, name="data-source-variables", hidden=True)
report_resource_app.add_typer(report_resource_package_app, name="package")
report_resource_app.add_typer(report_resource_item_app, name="item")

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


@report_resource_package_app.command("list")
def report_resource_package_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List report resource packages."""
    from pbi.report_resources import list_resource_packages

    proj = get_project(project)
    rows = list_resource_packages(proj)

    if as_json:
        console.print_json(
            json.dumps(
                [
                    {
                        "name": row.name,
                        "type": row.package_type,
                        "items": row.item_count,
                        "disabled": row.disabled,
                    }
                    for row in rows
                ],
                indent=2,
            )
        )
        return

    if not rows:
        console.print("[yellow]No resource packages. Use `pbi report resource package create` to add one.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Resource Packages", box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Items", justify="right")
    table.add_column("Disabled")
    for row in rows:
        table.add_row(row.name, row.package_type, str(row.item_count), "yes" if row.disabled else "")
    console.print(table)


@report_resource_package_app.command("get")
def report_resource_package_get(
    name: Annotated[str, typer.Argument(help="Resource package name.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one resource package."""
    from pbi.report_resources import get_resource_package

    proj = get_project(project)
    try:
        pkg = get_resource_package(proj, name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        console.print_json(json.dumps(pkg, indent=2))
        return

    table = Table(title=str(pkg.get("name", name)), box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Name", str(pkg.get("name", "")))
    table.add_row("Type", str(pkg.get("type", "")))
    table.add_row("Items", str(len(pkg.get("items", []))))
    if "disabled" in pkg:
        table.add_row("Disabled", "yes" if pkg.get("disabled") else "")
    console.print(table)


@report_resource_package_app.command("create")
def report_resource_package_create(
    name: Annotated[str, typer.Argument(help="Resource package name.")],
    package_type: Annotated[str, typer.Option("--type", help="Package type.")] = "RegisteredResources",
    disabled: Annotated[bool, typer.Option("--disabled", help="Create the package in a disabled state.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a report resource package."""
    from pbi.report_resources import create_resource_package

    proj = get_project(project)
    try:
        create_resource_package(proj, name, package_type=package_type, disabled=disabled)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(f'Created resource package "[cyan]{name}[/cyan]"')


@report_resource_package_app.command("delete")
def report_resource_package_delete(
    name: Annotated[str, typer.Argument(help="Resource package name.")],
    drop_files: Annotated[bool, typer.Option("--drop-files", help="Also delete RegisteredResources files for this package.")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a report resource package."""
    from pbi.report_resources import delete_resource_package, get_resource_package

    proj = get_project(project)
    try:
        pkg = get_resource_package(proj, name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f'Delete "{pkg.get("name", name)}"?')
        if not confirm:
            raise typer.Abort()

    try:
        deleted = delete_resource_package(proj, name, drop_files=drop_files)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(f'Deleted resource package "[cyan]{deleted.get("name", name)}[/cyan]"')


@report_resource_item_app.command("list")
def report_resource_item_list(
    package: Annotated[str, typer.Argument(help="Resource package name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List items within one resource package."""
    from pbi.report_resources import list_resource_items

    proj = get_project(project)
    try:
        rows = list_resource_items(proj, package)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if as_json:
        console.print_json(
            json.dumps(
                [
                    {
                        "package": row.package_name,
                        "name": row.name,
                        "path": row.path,
                        "type": row.item_type,
                    }
                    for row in rows
                ],
                indent=2,
            )
        )
        return

    if not rows:
        console.print("[yellow]No resource items. Use `pbi report resource item set` to add one.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=package, box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Path")
    table.add_column("Type", style="dim")
    for row in rows:
        table.add_row(row.name, row.path, row.item_type)
    console.print(table)


@report_resource_item_app.command("get")
def report_resource_item_get(
    package: Annotated[str, typer.Argument(help="Resource package name.")],
    item: Annotated[str, typer.Argument(help="Resource item name or path.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one resource item."""
    from pbi.report_resources import get_resource_item

    proj = get_project(project)
    try:
        entry = get_resource_item(proj, package, item)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        console.print_json(json.dumps(entry, indent=2))
        return

    table = Table(title=str(entry.get("name", item)), box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Name", str(entry.get("name", "")))
    table.add_row("Path", str(entry.get("path", "")))
    table.add_row("Type", str(entry.get("type", "")))
    console.print(table)


@report_resource_item_app.command("set")
def report_resource_item_set(
    package: Annotated[str, typer.Argument(help="Resource package name.")],
    stored_path: Annotated[str, typer.Argument(help="Stored path for the resource item within the package.")],
    item_type: Annotated[str, typer.Option("--type", help="Resource item type.")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Display name for the item.")] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Copy a file into RegisteredResources before registering it.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Create or update one resource item."""
    from pbi.report_resources import set_resource_item

    proj = get_project(project)
    try:
        entry, created = set_resource_item(
            proj,
            package,
            stored_path,
            item_type=item_type,
            name=name,
            source_path=from_file,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if created:
        console.print(
            f'Created resource item "[cyan]{entry.get("name", stored_path)}[/cyan]" in package "[cyan]{package}[/cyan]"'
        )
    else:
        console.print(
            f'Set resource item "[cyan]{entry.get("name", stored_path)}[/cyan]" in package "[cyan]{package}[/cyan]"'
        )


@report_resource_item_app.command("delete")
def report_resource_item_delete(
    package: Annotated[str, typer.Argument(help="Resource package name.")],
    item: Annotated[str, typer.Argument(help="Resource item name or path.")],
    drop_file: Annotated[bool, typer.Option("--drop-file", help="Also delete the RegisteredResources file for this item.")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete one resource item."""
    from pbi.report_resources import delete_resource_item, get_resource_item

    proj = get_project(project)
    try:
        entry = get_resource_item(proj, package, item)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f'Delete "{entry.get("name", item)}"?')
        if not confirm:
            raise typer.Abort()

    try:
        deleted = delete_resource_item(proj, package, item, drop_file=drop_file)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(f'Deleted resource item "[cyan]{deleted.get("name", item)}[/cyan]"')


@report_custom_visual_app.command("list")
def report_custom_visual_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List organization custom visuals used by the report."""
    from pbi.report_custom_visuals import list_organization_custom_visuals

    proj = get_project(project)
    rows = list_organization_custom_visuals(proj)

    if as_json:
        console.print_json(
            json.dumps(
                [
                    {
                        "name": row.name,
                        "path": row.path,
                        "disabled": row.disabled,
                    }
                    for row in rows
                ],
                indent=2,
            )
        )
        return

    if not rows:
        console.print("[yellow]No organization custom visuals. Use `pbi report custom-visual set` to add one.[/yellow]")
        raise typer.Exit(0)

    table = Table(title="Organization Custom Visuals", box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Path")
    table.add_column("Disabled")
    for row in rows:
        table.add_row(row.name, row.path, "yes" if row.disabled else "")
    console.print(table)


@report_custom_visual_app.command("get")
def report_custom_visual_get(
    identifier: Annotated[str, typer.Argument(help="Custom visual name or path.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one organization custom visual entry."""
    from pbi.report_custom_visuals import get_organization_custom_visual

    proj = get_project(project)
    try:
        entry = get_organization_custom_visual(proj, identifier)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        console.print_json(json.dumps(entry, indent=2))
        return

    table = Table(title=str(entry.get("name", identifier)), box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Name", str(entry.get("name", "")))
    table.add_row("Path", str(entry.get("path", "")))
    if "disabled" in entry:
        table.add_row("Disabled", "yes" if entry.get("disabled") else "")
    console.print(table)


@report_custom_visual_app.command("set")
def report_custom_visual_set(
    name: Annotated[str, typer.Argument(help="Custom visual name.")],
    path: Annotated[str, typer.Argument(help="Path where the custom visual is stored.")],
    disabled: Annotated[bool, typer.Option("--disabled/--enabled", help="Mark the custom visual as disabled or enabled.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create or update an organization custom visual entry."""
    from pbi.report_custom_visuals import set_organization_custom_visual

    proj = get_project(project)
    try:
        entry, created, changed = set_organization_custom_visual(proj, name, path, disabled=disabled)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not changed:
        console.print(f'[dim]No change:[/dim] [cyan]{name}[/cyan] already matches the requested state')
    elif created:
        console.print(f'Created organization custom visual "[cyan]{entry.get("name", name)}[/cyan]"')
    else:
        console.print(f'Set organization custom visual "[cyan]{entry.get("name", name)}[/cyan]"')


@report_custom_visual_app.command("delete")
def report_custom_visual_delete(
    identifier: Annotated[str, typer.Argument(help="Custom visual name or path.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete an organization custom visual entry."""
    from pbi.report_custom_visuals import delete_organization_custom_visual, get_organization_custom_visual

    proj = get_project(project)
    try:
        entry = get_organization_custom_visual(proj, identifier)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f'Delete "{entry.get("name", identifier)}"?')
        if not confirm:
            raise typer.Abort()

    try:
        deleted = delete_organization_custom_visual(proj, identifier)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(f'Deleted organization custom visual "[cyan]{deleted.get("name", identifier)}[/cyan]"')


@report_data_source_variables_app.command("get")
def report_data_source_variables_get(
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Print the raw variable payload.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show report data source variable overrides."""
    proj = get_project(project)
    data = proj.get_report_meta()
    value = data.get("dataSourceVariables")
    if not isinstance(value, str) or not value:
        console.print("[yellow]No data source variables configured.[/yellow]")
        raise typer.Exit(0)

    if raw:
        console.print(value)
        return

    table = Table(title="dataSourceVariables", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    preview = value if len(value) <= 120 else f"{value[:117]}..."
    table.add_row("Length", str(len(value)))
    table.add_row("Preview", preview)
    console.print(table)


@report_data_source_variables_app.command("set")
def report_data_source_variables_set(
    value: Annotated[str | None, typer.Argument(help="Raw dataSourceVariables payload.", show_default=False)] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the payload from a file.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set report data source variable overrides."""
    proj = get_project(project)
    try:
        if value is not None and from_file is not None:
            raise ValueError("Provide either an inline payload or --from-file, not both.")
        if from_file is not None:
            payload = from_file.read_text(encoding="utf-8")
        elif value is not None:
            payload = value
        else:
            raise ValueError("Provide a payload inline or via --from-file.")
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    data = proj.get_report_meta()
    data.setdefault("$schema", REPORT_SCHEMA)
    old = data.get("dataSourceVariables")
    if old == payload:
        console.print("[dim]No change:[/dim] [cyan]dataSourceVariables[/cyan] already matches the requested value")
        return

    data["dataSourceVariables"] = payload
    _save_report_json(proj, data)
    console.print("Set report data source variables")


@report_data_source_variables_app.command("clear")
def report_data_source_variables_clear(
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear report data source variable overrides."""
    proj = get_project(project)
    data = proj.get_report_meta()
    if "dataSourceVariables" not in data:
        console.print("[dim]No change:[/dim] [cyan]dataSourceVariables[/cyan] is not configured")
        return

    if not force:
        confirm = typer.confirm('Clear report object "dataSourceVariables"?')
        if not confirm:
            raise typer.Abort()

    data.pop("dataSourceVariables", None)
    _save_report_json(proj, data)
    console.print("Cleared report data source variables")
