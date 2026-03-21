"""Semantic-model role and RLS CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from pbi.model import RoleMember

from .base import (
    ProjectOpt,
    console,
    get_model,
    get_project,
    model_role_app,
    model_role_filter_app,
    model_role_member_app,
    parse_property_assignments,
    resolve_model_expression_input,
)


def _role_json(role) -> dict:
    return {
        "name": role.name,
        "modelPermission": role.model_permission,
        "filters": [
            {"table": item.table, "expression": item.filter_expression}
            for item in role.table_permissions
        ],
        "members": [
            {
                "name": member.name,
                "type": member.member_type,
                "identityProvider": member.identity_provider,
            }
            for member in role.members
        ],
    }


@model_role_app.command("list")
def model_role_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List model roles."""
    _, model = get_model(project)
    if not model.roles:
        console.print("[yellow]No roles. Use `pbi model role create` to add one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        rows = [_role_json(role) for role in model.roles]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Role", style="cyan")
    table.add_column("Permission")
    table.add_column("Filters", style="dim")
    table.add_column("Members", style="dim")
    for role in model.roles:
        table.add_row(
            role.name,
            role.model_permission,
            str(len(role.table_permissions)),
            str(len(role.members)),
        )
    console.print(table)


@model_role_app.command("get")
def model_role_get(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one role."""
    _, model = get_model(project)
    try:
        role = model.find_role(role_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    payload = _role_json(role)
    if as_json or raw:
        console.print_json(json.dumps(payload, indent=2))
        return

    table = Table(title=role.name, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Permission", role.model_permission)
    table.add_row("Filters", str(len(role.table_permissions)))
    table.add_row("Members", str(len(role.members)))
    if role.table_permissions:
        table.add_section()
        for item in role.table_permissions:
            table.add_row(f"Filter: {item.table}", item.filter_expression)
    if role.members:
        table.add_section()
        for member in role.members:
            label = member.member_type
            if member.identity_provider:
                label = f"{label}, provider={member.identity_provider}"
            table.add_row("Member", f"{member.name} ({label})")
    console.print(table)


@model_role_app.command("create")
def model_role_create(
    name: Annotated[str, typer.Argument(help="Role name.")],
    permission: Annotated[str, typer.Option("--permission", help="Model permission.")] = "read",
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a model role."""
    from pbi.model import RoleSpec, create_role

    proj = get_project(project)
    try:
        role_name, changed = create_role(
            proj.root,
            name,
            RoleSpec(model_permission=permission),
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Created role "[cyan]{role_name}[/cyan]"')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] [cyan]{role_name}[/cyan] already exists')


@model_role_app.command("set")
def model_role_set(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments as key=value.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set writable role properties."""
    from pbi.model import set_role_permission

    proj = get_project(project)
    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    for prop_name, prop_value in pairs:
        if prop_name != "permission":
            console.print('[red]Error:[/red] Property "{}" is not writable. Allowed: permission'.format(prop_name))
            raise typer.Exit(1)
        try:
            role, changed = set_role_permission(
                proj.root,
                role_name,
                prop_value,
                dry_run=dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        if changed:
            console.print(f"{prefix}Updated role [cyan]{role}[/cyan]")
        else:
            console.print(f'{prefix}[dim]No change:[/dim] [cyan]{role}[/cyan] permission is already "{prop_value}"')


@model_role_app.command("delete")
def model_role_delete(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a model role."""
    from pbi.model import delete_role

    proj = get_project(project)
    if not force:
        confirm = typer.confirm(f'Delete role "{role_name}"?')
        if not confirm:
            raise typer.Abort()
    try:
        role, changed = delete_role(proj.root, role_name, dry_run=dry_run)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Deleted role "[cyan]{role}[/cyan]"')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] role [cyan]{role}[/cyan] is already absent')


@model_role_member_app.command("list")
def model_role_member_list(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List members for one role."""
    _, model = get_model(project)
    try:
        role = model.find_role(role_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rows = [
        {
            "name": member.name,
            "type": member.member_type,
            "identityProvider": member.identity_provider,
        }
        for member in role.members
    ]
    if as_json:
        console.print_json(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[yellow]No role members. Use `pbi model role member create` to add one.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f'Members: "{role.name}"', box=box.SIMPLE)
    table.add_column("Member", style="cyan")
    table.add_column("Type")
    table.add_column("Identity Provider", style="dim")
    for row in rows:
        table.add_row(row["name"], row["type"], row["identityProvider"] or "")
    console.print(table)


@model_role_member_app.command("create")
def model_role_member_create(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    member_name: Annotated[str, typer.Argument(help="Member name or principal.")],
    member_type: Annotated[str, typer.Option("--type", help="Member type: user, group, auto, activeDirectory.")] = "user",
    identity_provider: Annotated[str | None, typer.Option("--identity-provider", help="Custom identity provider name.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Add one member to a role."""
    from pbi.model import add_role_member

    proj = get_project(project)
    try:
        role, member, changed = add_role_member(
            proj.root,
            role_name,
            RoleMember(name=member_name, member_type=member_type, identity_provider=identity_provider),
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Added role member [cyan]{member}[/cyan] to [cyan]{role}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] role member [cyan]{member}[/cyan] is already present')


@model_role_member_app.command("delete")
def model_role_member_delete(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    member_name: Annotated[str, typer.Argument(help="Member name or principal.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete one role member."""
    from pbi.model import delete_role_member

    proj = get_project(project)
    if not force:
        confirm = typer.confirm(f'Delete role member "{member_name}" from "{role_name}"?')
        if not confirm:
            raise typer.Abort()
    try:
        role, member, changed = delete_role_member(proj.root, role_name, member_name, dry_run=dry_run)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Deleted role member [cyan]{member}[/cyan] from [cyan]{role}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] role member [cyan]{member}[/cyan] is already absent')


@model_role_filter_app.command("list")
def model_role_filter_list(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List table filters for one role."""
    _, model = get_model(project)
    try:
        role = model.find_role(role_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    rows = [{"table": item.table, "expression": item.filter_expression} for item in role.table_permissions]
    if as_json:
        console.print_json(json.dumps(rows, indent=2))
        return
    if not rows:
        console.print("[yellow]No role filters. Use `pbi model role filter set` to add one.[/yellow]")
        raise typer.Exit(0)

    table = Table(title=f'Filters: "{role.name}"', box=box.SIMPLE)
    table.add_column("Table", style="cyan")
    table.add_column("Expression")
    for row in rows:
        table.add_row(row["table"], row["expression"])
    console.print(table)


@model_role_filter_app.command("get")
def model_role_filter_get(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    project: ProjectOpt = None,
) -> None:
    """Show one role table filter."""
    _, model = get_model(project)
    try:
        role = model.find_role(role_name)
        permission = role.find_table_permission(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(permission.filter_expression)


@model_role_filter_app.command("set")
def model_role_filter_set(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    expression: Annotated[str | None, typer.Argument(help="Filter expression. Omit when using --from-file or stdin.")] = None,
    from_file: Annotated[Path | None, typer.Option("--from-file", help="Read the filter expression from a file.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set or replace one role table filter."""
    from pbi.model import set_role_table_filter

    proj = get_project(project)
    try:
        resolved_expression = resolve_model_expression_input(expression, from_file)
        role, table_name, changed = set_role_table_filter(
            proj.root,
            role_name,
            table_name,
            resolved_expression,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Updated role filter [cyan]{role}[/cyan] [dim]->[/dim] [cyan]{table_name}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] role filter for [cyan]{table_name}[/cyan] is already current')


@model_role_filter_app.command("clear")
def model_role_filter_clear(
    role_name: Annotated[str, typer.Argument(help="Role name.")],
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clear one role table filter."""
    from pbi.model import clear_role_table_filter

    proj = get_project(project)
    try:
        role, table_name, changed = clear_role_table_filter(
            proj.root,
            role_name,
            table_name,
            dry_run=dry_run,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    if changed:
        console.print(f'{prefix}Cleared role filter [cyan]{role}[/cyan] [dim]->[/dim] [cyan]{table_name}[/cyan]')
    else:
        console.print(f'{prefix}[dim]No change:[/dim] role filter for [cyan]{table_name}[/cyan] is already absent')
