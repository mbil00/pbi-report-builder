"""Component management commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project

component_app = typer.Typer(help="Reusable visual component operations.", no_args_is_help=True)


@component_app.command("create")
def component_create(
    page: Annotated[str, typer.Argument(help="Page containing the group.")],
    group: Annotated[str, typer.Argument(help="Group visual name or index.")],
    name: Annotated[str, typer.Option("--name", "-n", help="Component name.")] = "",
    description: Annotated[str | None, typer.Option("--description", help="Component description.")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing component.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Save as global component.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Save a visual group as a reusable component."""
    from pbi.components import save_component

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, group)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    comp_name = name or vis.data.get("visualGroup", {}).get("displayName", vis.name)
    if not comp_name:
        console.print("[red]Error:[/red] Provide --name or use a named group.")
        raise typer.Exit(1)

    try:
        path = save_component(
            proj, pg, vis, comp_name,
            description=description,
            overwrite=force,
            global_scope=global_scope,
        )
    except (FileExistsError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Count children
    all_visuals = proj.get_visuals(pg)
    children = [v for v in all_visuals if v.data.get("parentGroupName") == vis.name]

    scope_label = "global " if global_scope else ""
    console.print(
        f'Saved {scope_label}component "[cyan]{comp_name}[/cyan]" '
        f"({len(children)} visuals) → {path}"
    )

    # Show detected parameters
    from pbi.components import get_component
    comp = get_component(proj, comp_name, global_scope=global_scope)
    if comp.parameters:
        console.print("[dim]Parameters:[/dim]")
        for pname, pdef in comp.parameters.items():
            default = pdef.get("default", "")
            console.print(f"  [cyan]{pname}[/cyan] = {default}")


@component_app.command("list")
def component_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Show only global components.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List saved components."""
    from pbi.components import list_components

    proj = get_project(project) if not global_scope else None
    components = list_components(proj, global_scope=global_scope)

    if not components:
        console.print("[yellow]No components saved. Use `pbi component create` to create one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json
        rows = [
            {
                "name": c.name,
                "scope": c.scope,
                "visuals": len(c.visuals),
                "parameters": list(c.parameters.keys()),
                "description": c.description or "",
            }
            for c in components
        ]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Scope", style="dim")
    table.add_column("Visuals")
    table.add_column("Parameters", style="dim")
    table.add_column("Description", style="dim")

    for comp in components:
        params = ", ".join(comp.parameters.keys()) if comp.parameters else ""
        table.add_row(
            comp.name,
            comp.scope,
            str(len(comp.visuals)),
            params,
            comp.description or "",
        )
    console.print(table)


@component_app.command("get")
def component_get(
    component_name: Annotated[str, typer.Argument(help="Component name.")],
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Look up global only.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show component details."""
    from pbi.components import get_component

    proj = get_project(project) if not global_scope else None
    try:
        comp = get_component(proj, component_name, global_scope=global_scope)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f"[bold]{comp.name}[/bold]")
    if comp.description:
        console.print(f"[dim]{comp.description}[/dim]")
    console.print(f"[dim]Size:[/dim] {comp.size[0]} x {comp.size[1]}")
    console.print(f"[dim]Scope:[/dim] {comp.scope}")

    if comp.visuals:
        console.print(f"\n[bold]Visuals[/bold] ({len(comp.visuals)})")
        for i, vs in enumerate(comp.visuals, 1):
            pos = vs.get("position", "0, 0")
            size = vs.get("size", "? x ?")
            vtype = vs.get("type", "?")
            vname = vs.get("name", "")
            name_str = f'[cyan]{vname}[/cyan] ' if vname else ''
            console.print(f"  {i}. {name_str}{vtype} [dim]({pos}) {size}[/dim]")

    if comp.parameters:
        console.print(f"\n[bold]Parameters[/bold]")
        for pname, pdef in comp.parameters.items():
            default = pdef.get("default", "(none)")
            source = pdef.get("source", "")
            console.print(f"  [cyan]{pname}[/cyan]: {default} [dim]← {source}[/dim]")


@component_app.command("apply")
def component_apply(
    page: Annotated[str, typer.Argument(help="Target page.")],
    component_name: Annotated[str, typer.Argument(help="Component name to stamp.")],
    x: Annotated[int, typer.Option(help="X position.")] = 0,
    y: Annotated[int, typer.Option(help="Y position.")] = 0,
    set_params: Annotated[list[str] | None, typer.Option("--set", help="Parameter overrides as key=value.")] = None,
    row: Annotated[int | None, typer.Option("--row", help="Create N instances in a horizontal row.")] = None,
    gap: Annotated[int, typer.Option("--gap", help="Gap between row instances.")] = 12,
    set_each: Annotated[list[str] | None, typer.Option("--set-each", help="Per-instance values as key=v1,v2,v3.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Use global component.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Stamp a component onto a page."""
    from pbi.components import apply_component, apply_component_row, get_component

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Parse --set params
    params: dict[str, str] = {}
    if set_params:
        for s in set_params:
            eq = s.find("=")
            if eq == -1:
                console.print(f"[red]Error:[/red] Invalid --set format: {s}. Use key=value.")
                raise typer.Exit(1)
            params[s[:eq]] = s[eq + 1:]

    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    if row and row > 0:
        # Parse --set-each
        each_params: dict[str, list[str]] = {}
        if set_each:
            for s in set_each:
                eq = s.find("=")
                if eq == -1:
                    console.print(f"[red]Error:[/red] Invalid --set-each format: {s}. Use key=v1,v2,v3.")
                    raise typer.Exit(1)
                each_params[s[:eq]] = s[eq + 1:].split(",")

        # Merge single --set params into each_params as repeated values
        for k, v in params.items():
            if k not in each_params:
                each_params[k] = [v] * row

        try:
            all_created = apply_component_row(
                proj, pg, component_name, row,
                x=x, y=y, gap=gap,
                set_each=each_params if each_params else None,
                global_scope=global_scope,
                dry_run=dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        comp = get_component(proj, component_name, global_scope=global_scope)
        console.print(
            f'{prefix}Stamped [cyan]{row}[/cyan] instances of '
            f'"[cyan]{component_name}[/cyan]" on "{pg.display_name}"'
        )
        total = sum(len(group) for group in all_created)
        console.print(f"[dim]{total} visuals created[/dim]")
    else:
        try:
            created = apply_component(
                proj, pg, component_name,
                x=x, y=y,
                params=params if params else None,
                global_scope=global_scope,
                dry_run=dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        console.print(
            f'{prefix}Created "[cyan]{component_name}[/cyan]" '
            f'on "{pg.display_name}" at ({x}, {y})'
        )
        for vis in created:
            if "visualGroup" in vis.data:
                continue
            pos = vis.position
            console.print(
                f'  {prefix}[cyan]{vis.visual_type}[/cyan] "{vis.name}" '
                f'[dim]({pos.get("x", 0)}, {pos.get("y", 0)}) '
                f'{pos.get("width", 0)}x{pos.get("height", 0)}[/dim]'
            )


@component_app.command("delete")
def component_delete(
    component_name: Annotated[str, typer.Argument(help="Component name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Delete from global.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a saved component."""
    from pbi.components import delete_component

    proj = get_project(project) if not global_scope else None
    if not force:
        confirm = typer.confirm(f'Delete component "{component_name}"?')
        if not confirm:
            raise typer.Abort()

    try:
        deleted = delete_component(proj, component_name, global_scope=global_scope)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if deleted:
        console.print(f'Deleted component "[cyan]{component_name}[/cyan]"')
    else:
        console.print(f'[yellow]Component "{component_name}" not found.[/yellow]')


@component_app.command("clone")
def component_clone(
    component_name: Annotated[str, typer.Argument(help="Component to clone.")],
    new_name: Annotated[str | None, typer.Option("--name", "-n", help="New name.")] = None,
    to_global: Annotated[bool, typer.Option("--to-global", help="Clone project → global.")] = False,
    to_project: Annotated[bool, typer.Option("--to-project", help="Clone global → project.")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite if exists.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clone a component between project and global scope."""
    from pbi.components import clone_component

    if not to_global and not to_project:
        console.print("[red]Error:[/red] Specify --to-global or --to-project.")
        raise typer.Exit(1)
    if to_global and to_project:
        console.print("[red]Error:[/red] Use either --to-global or --to-project, not both.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        path = clone_component(proj, component_name, to_global=to_global, new_name=new_name, overwrite=force)
    except (FileExistsError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    target_name = new_name or component_name
    direction = "global" if to_global else "project"
    console.print(f'Cloned "[cyan]{component_name}[/cyan]" → {direction} as "[cyan]{target_name}[/cyan]" → {path}')
