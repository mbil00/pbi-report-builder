"""Relationship-related semantic-model commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .base import ProjectOpt, console, get_model, get_project, model_relationship_app, parse_property_assignments


@model_relationship_app.command("list")
def model_relationships(
    from_table: Annotated[str | None, typer.Option("--from", help="Filter by table name.")] = None,
    to_table: Annotated[str | None, typer.Option("--to", help="Filter by table name.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List relationships in the semantic model."""
    _, model = get_model(project)
    relationships = model.find_relationships(from_table=from_table, to_table=to_table)

    if not relationships:
        console.print("[yellow]No relationships found.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        rows = [
            {
                "from": f"{relationship.from_table}.{relationship.from_column}",
                "to": f"{relationship.to_table}.{relationship.to_column}",
                "properties": relationship.properties,
            }
            for relationship in relationships
        ]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title="Model Relationships", box=box.SIMPLE)
    table.add_column("From", style="cyan")
    table.add_column("", style="dim", width=2)
    table.add_column("To", style="cyan")
    table.add_column("Cross Filter", style="dim")
    table.add_column("Active", style="dim", justify="center")

    for relationship in relationships:
        cross_filter = relationship.properties.get("crossFilteringBehavior", "")
        is_active = relationship.properties.get("isActive", "")
        active_display = "" if is_active == "" else ("" if is_active == "true" else "no")
        table.add_row(
            f"{relationship.from_table}.{relationship.from_column}",
            "→",
            f"{relationship.to_table}.{relationship.to_column}",
            cross_filter,
            active_display,
        )
    console.print(table)


@model_relationship_app.command("create")
def model_relationship_create(
    from_field: Annotated[str, typer.Argument(help="From column as Table.Column. Use the many-side column here for standard many-to-one relationships.")],
    to_field: Annotated[str, typer.Argument(help="To column as Table.Column. Use the one-side column here for standard many-to-one relationships.")],
    cross_filter: Annotated[str | None, typer.Option("--cross-filter", help="Cross-filter direction. oneDirection flows from the one side to the many side; bothDirections enables bidirectional filtering.")] = None,
    inactive: Annotated[bool, typer.Option("--inactive", help="Create as inactive relationship.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a relationship between two columns."""
    from pbi.model import create_relationship

    proj = get_project(project)
    properties: dict[str, str] = {}
    cross_filter_map = {"singledirection": "oneDirection", "single": "oneDirection"}
    if cross_filter:
        properties["crossFilteringBehavior"] = cross_filter_map.get(
            cross_filter.lower(),
            cross_filter,
        )
    if inactive:
        properties["isActive"] = "false"

    try:
        _rel_id, from_ref, to_ref = create_relationship(
            proj.root,
            from_field,
            to_field,
            properties=properties if properties else None,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Created relationship [cyan]{from_ref}[/cyan] [dim]->[/dim] [cyan]{to_ref}[/cyan]')


@model_relationship_app.command("delete")
def model_relationship_delete(
    from_field: Annotated[str, typer.Argument(help="From column as Table.Column.")],
    to_field: Annotated[str, typer.Argument(help="To column as Table.Column.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview the change without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a relationship between two columns."""
    from pbi.model import delete_relationship

    if not force:
        confirm = typer.confirm(f'Delete relationship "{from_field}" -> "{to_field}"?')
        if not confirm:
            raise typer.Abort()

    proj = get_project(project)
    try:
        from_ref, to_ref = delete_relationship(
            proj.root,
            from_field,
            to_field,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    console.print(f'{prefix}Deleted relationship [cyan]{from_ref}[/cyan] [dim]->[/dim] [cyan]{to_ref}[/cyan]')


@model_relationship_app.command("set")
def model_relationship_set(
    from_field: Annotated[str, typer.Argument(help="From column as Table.Column. This should normally be the many-side column.")],
    to_field: Annotated[str, typer.Argument(help="To column as Table.Column. This should normally be the one-side column.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments as key=value.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set properties on a relationship."""
    from pbi.model import set_relationship_property

    proj = get_project(project)
    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    for prop_name, prop_value in pairs:
        try:
            from_ref, to_ref, changed = set_relationship_property(
                proj.root,
                from_field,
                to_field,
                prop_name,
                prop_value,
                dry_run=dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        if changed:
            console.print(
                f'{prefix}[dim]{prop_name}:[/dim] [cyan]{from_ref}[/cyan] [dim]->[/dim] '
                f'[cyan]{to_ref}[/cyan] [dim]->[/dim] "{prop_value}"'
            )
        else:
            console.print(f'{prefix}[dim]No change:[/dim] {prop_name} is already "{prop_value}"')
