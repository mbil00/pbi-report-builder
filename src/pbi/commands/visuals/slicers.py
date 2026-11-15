"""Slicer sync group and saved selection commands (#42)."""

from __future__ import annotations

import datetime as dt
import json
from typing import Annotated, Any

import typer

from pbi.slicer_state import (
    SLICER_TYPES,
    apply_slicer_selection,
    apply_sync_group,
    export_slicer_selection,
    export_sync_group,
    slicer_field,
)

from ..common import ProjectOpt, console
from .app import visual_slicer_app, visual_slicer_selection_app, visual_slicer_sync_app
from .helpers import resolve_visual_target

PageArg = Annotated[str, typer.Argument(help="Page name, display name, or index.")]
VisualArg = Annotated[str, typer.Argument(help="Slicer visual name or index.")]


def _resolve_slicer(project, page: str, visual: str):
    proj, pg, vis = resolve_visual_target(project, page, visual)
    if vis.visual_type not in SLICER_TYPES:
        console.print(
            f'[red]Error:[/red] "{vis.name}" is a {vis.visual_type}, not a slicer '
            f"(supported: {', '.join(SLICER_TYPES)})."
        )
        raise typer.Exit(1)
    return proj, pg, vis


def _sync_text(sync: Any) -> str:
    if sync is None:
        return "[dim](none)[/dim]"
    if isinstance(sync, str):
        return f"[cyan]{sync}[/cyan] [dim](fields, filters)[/dim]"
    synced = [name for name in ("fields", "filters") if sync[name]]
    return f"[cyan]{sync['group']}[/cyan] [dim]({', '.join(synced) or 'nothing synced'})[/dim]"


def _selection_text(found: bool, selected: Any, raw_filter: bool) -> str:
    if not found:
        return "[yellow]custom filter (see visual get --raw)[/yellow]" if raw_filter else "[dim](none)[/dim]"
    if isinstance(selected, dict) and "from" in selected:
        return f"[cyan]{selected['from']}[/cyan] [dim]to[/dim] [cyan]{selected['to']}[/cyan]"
    if isinstance(selected, dict):
        return "all except " + ", ".join(f"[cyan]{value}[/cyan]" for value in selected["except"])
    return ", ".join(f"[cyan]{value}[/cyan]" for value in selected)


def _json_value(value: Any) -> Any:
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_value(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_value(child) for child in value]
    return value


def _has_raw_filter(vis) -> bool:
    general = vis.data.get("visual", {}).get("objects", {}).get("general", [])
    return any(
        isinstance(entry, dict) and "filter" in entry.get("properties", {})
        for entry in general if isinstance(general, list)
    )


@visual_slicer_app.command("get")
def slicer_get(
    page: PageArg,
    visual: VisualArg,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show a slicer's field, sync group and saved selection."""
    _proj, _pg, vis = _resolve_slicer(project, page, visual)
    field = slicer_field(vis.data)
    sync = export_sync_group(vis.data)
    found, selected = export_slicer_selection(vis.data)

    if as_json:
        console.print_json(json.dumps({
            "visual": vis.name,
            "field": f"{field[0]}.{field[1]}" if field else None,
            "sync": _json_value(sync),
            "selected": _json_value(selected) if found else None,
            "hidden": bool(vis.data.get("isHidden")),
        }, indent=2))
        return

    console.print(f"[bold]{vis.name}[/bold]")
    console.print(f"  [dim]field:[/dim] {f'[cyan]{field[0]}.{field[1]}[/cyan]' if field else '[dim](none)[/dim]'}")
    console.print(f"  [dim]sync:[/dim] {_sync_text(sync)}")
    console.print(f"  [dim]selected:[/dim] {_selection_text(found, selected, _has_raw_filter(vis))}")
    if vis.data.get("isHidden"):
        console.print("  [yellow]hidden[/yellow]")


@visual_slicer_sync_app.command("set")
def slicer_sync_set(
    page: PageArg,
    visual: VisualArg,
    group: Annotated[str, typer.Argument(help="Sync group name. Slicers with the same group name stay in sync.")],
    fields: Annotated[bool, typer.Option("--fields/--no-fields", help="Sync field changes.")] = True,
    filters: Annotated[bool, typer.Option("--filters/--no-filters", help="Sync filter (selection) changes.")] = True,
    project: ProjectOpt = None,
) -> None:
    """Put a slicer in a sync group."""
    _proj, _pg, vis = _resolve_slicer(project, page, visual)
    spec = {"group": group, "fields": fields, "filters": filters}
    old = export_sync_group(vis.data)
    try:
        changed = apply_sync_group(vis.data, spec)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if not changed:
        console.print(f"[dim]No change:[/dim] [cyan]{vis.name}[/cyan] is already in that sync group")
        return
    vis.save()
    console.print(f"[dim]sync:[/dim] {_sync_text(old)} [dim]->[/dim] {_sync_text(export_sync_group(vis.data))}")


@visual_slicer_sync_app.command("clear")
def slicer_sync_clear(
    page: PageArg,
    visual: VisualArg,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Take a slicer out of its sync group."""
    _proj, _pg, vis = _resolve_slicer(project, page, visual)
    if "syncGroup" not in vis.data.get("visual", {}):
        console.print(f"[dim]No change:[/dim] [cyan]{vis.name}[/cyan] is not in a sync group")
        return
    if not force:
        confirm = typer.confirm(f'Remove "{vis.name}" from its sync group?')
        if not confirm:
            raise typer.Abort()
    vis.data["visual"].pop("syncGroup")
    vis.save()
    console.print(f'Cleared sync group from "[cyan]{vis.name}[/cyan]"')


@visual_slicer_selection_app.command("set")
def slicer_selection_set(
    page: PageArg,
    visual: VisualArg,
    values: Annotated[list[str] | None, typer.Argument(help="Values to select.")] = None,
    except_: Annotated[bool, typer.Option("--except", help="Select every value except the ones given.")] = False,
    date_from: Annotated[str | None, typer.Option("--from", help="Start of a date range (YYYY-MM-DD).")] = None,
    date_to: Annotated[str | None, typer.Option("--to", help="End of a date range, inclusive (YYYY-MM-DD).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Save a slicer's default selection: values, all-except values, or a date range."""
    proj, _pg, vis = _resolve_slicer(project, page, visual)

    is_range = date_from is not None or date_to is not None
    if is_range and (values or except_):
        console.print("[red]Error:[/red] Give either values or --from/--to, not both.")
        raise typer.Exit(1)
    if is_range and (date_from is None or date_to is None):
        console.print("[red]Error:[/red] A date range needs both --from and --to.")
        raise typer.Exit(1)
    if not is_range and not values:
        console.print("[red]Error:[/red] Give values to select, or --from/--to for a date range.")
        raise typer.Exit(1)

    spec: Any
    if is_range:
        spec = {"from": date_from, "to": date_to}
    elif except_:
        spec = {"except": list(values or [])}
    else:
        spec = list(values or [])

    field = slicer_field(vis.data)
    data_type = None
    if field is not None:
        from pbi.fields import resolve_field_info

        try:
            data_type = resolve_field_info(proj, f"{field[0]}.{field[1]}", "column")[3]
        except ValueError:
            pass

    old_found, old = export_slicer_selection(vis.data)
    try:
        changed, warnings = apply_slicer_selection(vis.data, spec, data_type=data_type)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    for warning in warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    if not changed:
        console.print(f"[dim]No change:[/dim] [cyan]{vis.name}[/cyan] already has that selection")
        return
    vis.save()
    new_found, new = export_slicer_selection(vis.data)
    console.print(
        f"[dim]selected:[/dim] {_selection_text(old_found, old, False)} "
        f"[dim]->[/dim] {_selection_text(new_found, new, False)}"
    )


@visual_slicer_selection_app.command("clear")
def slicer_selection_clear(
    page: PageArg,
    visual: VisualArg,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear a slicer's saved selection."""
    _proj, _pg, vis = _resolve_slicer(project, page, visual)
    if not _has_raw_filter(vis):
        console.print(f"[dim]No change:[/dim] [cyan]{vis.name}[/cyan] has no saved selection")
        return
    if not force:
        confirm = typer.confirm(f'Clear the saved selection of "{vis.name}"?')
        if not confirm:
            raise typer.Abort()
    try:
        apply_slicer_selection(vis.data, None, data_type=None)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    vis.save()
    console.print(f'Cleared saved selection from "[cyan]{vis.name}[/cyan]"')
