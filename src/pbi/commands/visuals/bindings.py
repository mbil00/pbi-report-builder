"""Visual data-binding commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from pbi.fields import resolve_field_info
from pbi.visual_queries import add_binding, get_bindings, remove_binding

from ..common import ProjectOpt, console
from .app import visual_app
from .helpers import resolve_visual_target


@visual_app.command("bind")
def visual_bind(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    role: Annotated[str, typer.Argument(help="Data role (e.g. Category, Y, Values, Rows, Series).")],
    field: Annotated[str, typer.Argument(help="Field reference as Table.Field (e.g. Product.Category).")],
    field_type: Annotated[str, typer.Option("--field-type", help="Field type: auto, column, or measure.")] = "auto",
    project: ProjectOpt = None,
) -> None:
    """Bind a column or measure to a visual's data role."""
    from pbi.roles import get_visual_type_info, normalize_visual_role
    from pbi.visual_builders import BoundField, existing_bound_fields, validate_incremental_bindings

    proj, _pg, vis = resolve_visual_target(project, page, visual)

    try:
        entity, prop, resolved_field_type, data_type = resolve_field_info(
            proj,
            field,
            field_type,
            strict=True,
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    canonical_role = normalize_visual_role(vis.visual_type, role)
    if canonical_role != role:
        console.print(
            f'[dim]Using canonical role [cyan]{canonical_role}[/cyan] '
            f'for alias "{role}" on {vis.visual_type}.[/dim]'
        )

    info = get_visual_type_info(vis.visual_type)
    if info and info.roles:
        supported_roles = {entry["name"] for entry in info.roles}
        if canonical_role not in supported_roles:
            console.print(
                f'[red]Error:[/red] Role "{canonical_role}" is not supported for '
                f'{vis.visual_type}. Supported roles: {", ".join(sorted(supported_roles))}'
            )
            raise typer.Exit(1)

    try:
        current_fields = existing_bound_fields(proj, vis)
        validate_incremental_bindings(
            vis.visual_type,
            current_fields + [BoundField(canonical_role, entity, prop, resolved_field_type, data_type)],
        )
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    add_binding(vis, canonical_role, entity, prop, field_type=resolved_field_type)
    kind = "measure" if resolved_field_type == "measure" else "column"
    console.print(
        f'Bound [cyan]{entity}.{prop}[/cyan] ({kind}) -> '
        f'{vis.visual_type} role "[bold]{canonical_role}[/bold]"'
    )


@visual_app.command("unbind")
def visual_unbind(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    role: Annotated[str, typer.Argument(help="Data role to unbind from.")],
    field: Annotated[str | None, typer.Argument(help="Specific field to remove (Table.Field). Omit to remove entire role.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Remove data bindings from a visual."""
    from pbi.roles import normalize_visual_role

    proj, _pg, vis = resolve_visual_target(project, page, visual)

    canonical_role = normalize_visual_role(vis.visual_type, role)
    removed = remove_binding(vis, canonical_role, field_ref=field)
    if removed:
        target = f" ({field})" if field else ""
        console.print(f'Removed {removed} binding(s) from role "[bold]{canonical_role}[/bold]"{target}')
    else:
        console.print(f'[yellow]No bindings found for role "{canonical_role}"[/yellow]')


@visual_app.command("bindings")
def visual_bindings(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    project: ProjectOpt = None,
) -> None:
    """List all data bindings on a visual."""
    proj, _pg, vis = resolve_visual_target(project, page, visual)

    bindings = get_bindings(vis)
    if not bindings:
        console.print("[dim]No data bindings.[/dim]")
        return

    table = Table(title=f"Bindings on {vis.visual_type}", box=box.SIMPLE)
    table.add_column("Role", style="cyan")
    table.add_column("Table", style="cyan")
    table.add_column("Field")
    table.add_column("Type", style="dim")

    for role, entity, prop, ftype in bindings:
        table.add_row(role, entity, prop, ftype)

    console.print(table)
