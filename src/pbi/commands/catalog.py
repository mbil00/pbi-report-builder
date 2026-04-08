"""Unified catalog commands for reusable assets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project, parse_property_assignments
from pbi.project import Project


catalog_app = typer.Typer(help="Reusable asset catalog operations.", no_args_is_help=True)


def _optional_project(project: Path | None):
    """Resolve a project if available, but allow global/bundled catalog use without one."""
    try:
        return Project.find(project)
    except (FileNotFoundError, ValueError):
        return None


@catalog_app.command("list")
def catalog_list(
    kind: Annotated[str | None, typer.Option("--kind", help="Filter by kind: visual, style, component, page.")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Filter by scope: project, global, bundled.")] = None,
    category: Annotated[str | None, typer.Option("--category", help="Filter by category.")] = None,
    tag: Annotated[str | None, typer.Option("--tag", help="Filter by tag.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List reusable assets across the unified catalog."""
    from pbi.catalog import list_catalog_items

    proj = _optional_project(project)
    try:
        items = list_catalog_items(proj, kind=kind, scope=scope, category=category, tag=tag)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not items:
        console.print("[yellow]No catalog items found.[/yellow]")
        raise typer.Exit(0)

    rows = [item.to_row() for item in items]
    if as_json:
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Kind", style="cyan")
    table.add_column("Name", style="cyan")
    table.add_column("Scope", style="dim")
    table.add_column("Category", style="dim")
    table.add_column("Summary", style="dim")
    table.add_column("Description", style="dim")
    for item in items:
        summary = item.summary or {}
        summary_bits = [f"{key}={value}" for key, value in summary.items() if value not in ("", None)]
        table.add_row(
            item.kind,
            item.name,
            item.scope,
            item.category or "",
            ", ".join(summary_bits),
            item.description or "",
        )
    console.print(table)


@catalog_app.command("get")
def catalog_get(
    ref: Annotated[str, typer.Argument(help="Catalog ref as kind/name or plain name if unique.")],
    kind: Annotated[str | None, typer.Option("--kind", help="Hint or filter by kind.")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Restrict to one scope: project, global, bundled.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show one catalog item as YAML."""
    from pbi.catalog import dump_catalog_item

    proj = _optional_project(project)
    try:
        content = dump_catalog_item(proj, ref, kind=kind, scope=scope)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(content, highlight=False, end="")


@catalog_app.command("validate")
def catalog_validate(
    kind: Annotated[str | None, typer.Option("--kind", help="Validate only one kind.")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Validate only one scope: project, global, bundled.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Validate catalog YAML files across the configured scopes."""
    from pbi.catalog import list_catalog_items, validate_catalog

    proj = _optional_project(project)
    try:
        issues = validate_catalog(proj, kind=kind, scope=scope)
        items = list_catalog_items(proj, kind=kind, scope=scope)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if as_json:
        payload = {
            "valid": not issues,
            "items": len(items),
            "issues": [issue.to_row() for issue in issues],
        }
        console.print_json(json.dumps(payload, indent=2))
        if issues:
            raise typer.Exit(1)
        return

    if not issues:
        console.print(f'Validated [cyan]{len(items)}[/cyan] catalog item(s).')
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Kind", style="cyan")
    table.add_column("Scope", style="dim")
    table.add_column("Path", style="dim")
    table.add_column("Error", style="red")
    for issue in issues:
        table.add_row(issue.kind, issue.scope, str(issue.path), issue.message)
    console.print(table)
    raise typer.Exit(1)


@catalog_app.command("register")
def catalog_register(
    yaml_path: Annotated[Path, typer.Argument(help="YAML file to register as a catalog item.")],
    kind: Annotated[str, typer.Option("--kind", help="Catalog kind to register.")] = "visual",
    name: Annotated[str | None, typer.Option("--name", "-n", help="Override the stored item name.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Override the stored item description.")] = None,
    category: Annotated[str | None, typer.Option("--category", help="Optional category label.")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag", help="Optional tag. Repeatable.")] = None,
    scope: Annotated[str, typer.Option("--scope", help="Target scope: project or global.")] = "project",
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite an existing item.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Register a new catalog item from YAML."""
    from pbi.catalog import normalize_catalog_kind
    from pbi.components import save_component_from_yaml
    from pbi.styles import register_style
    from pbi.templates import register_template
    from pbi.visual_templates import register_visual_template

    try:
        resolved_kind = normalize_catalog_kind(kind)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if scope not in {"project", "global"}:
        console.print('[red]Error:[/red] --scope must be "project" or "global".')
        raise typer.Exit(1)
    if resolved_kind != "visual" and (category is not None or tags):
        console.print("[red]Error:[/red] --category and --tag are currently supported only for visual items.")
        raise typer.Exit(1)

    proj = get_project(project) if scope == "project" else None
    try:
        if resolved_kind == "visual":
            path = register_visual_template(
                proj,
                yaml_path,
                name=name,
                description=description,
                category=category,
                tags=tags,
                overwrite=force,
                global_scope=scope == "global",
            )
        elif resolved_kind == "component":
            if not name:
                console.print("[red]Error:[/red] --name is required when registering a component.")
                raise typer.Exit(1)
            path = save_component_from_yaml(
                proj,
                yaml_path,
                name,
                description=description,
                overwrite=force,
                global_scope=scope == "global",
            )
        elif resolved_kind == "style":
            path = register_style(
                proj,
                yaml_path,
                name=name,
                description=description,
                overwrite=force,
                global_scope=scope == "global",
            )
        elif resolved_kind == "page":
            path = register_template(
                proj,
                yaml_path,
                name=name,
                description=description,
                overwrite=force,
                global_scope=scope == "global",
            )
        else:
            console.print(f'[red]Error:[/red] Catalog registration is not implemented for kind "{resolved_kind}".')
            raise typer.Exit(1)
    except (FileNotFoundError, FileExistsError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    item_name = Path(path).stem
    console.print(f'Saved [cyan]{resolved_kind}[/cyan] "[cyan]{item_name}[/cyan]" ({scope}) -> {path}')


@catalog_app.command("create")
def catalog_create(
    kind: Annotated[str, typer.Argument(help="Catalog kind to create.")],
    assignments: Annotated[list[str] | None, typer.Argument(help="Property assignments for style items as prop=value.")] = None,
    name: Annotated[str, typer.Option("--name", "-n", help="Name for the new catalog item.")] = "",
    from_visual_page: Annotated[str | None, typer.Option("--from-visual", help="Capture from visual on this page, or use this page as a page source.")] = None,
    from_visual_name: Annotated[str | None, typer.Option("--visual", help="Visual name used with --from-visual.")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Optional item description.")] = None,
    category: Annotated[str | None, typer.Option("--category", help="Optional category label.")] = None,
    tags: Annotated[list[str] | None, typer.Option("--tag", help="Optional tag. Repeatable.")] = None,
    scope: Annotated[str, typer.Option("--scope", help="Target scope: project or global.")] = "project",
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite an existing item.")] = False,
    no_parameterize: Annotated[bool, typer.Option("--no-parameterize", help="Export as frozen snapshot without auto-parameterization.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a catalog item from report state."""
    from pbi.catalog import normalize_catalog_kind
    from pbi.components import save_component
    from pbi.styles import create_style
    from pbi.styles import save_style_from_visual
    from pbi.templates import save_template
    from pbi.visual_templates import save_visual_template

    try:
        resolved_kind = normalize_catalog_kind(kind)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if scope not in {"project", "global"}:
        console.print('[red]Error:[/red] --scope must be "project" or "global".')
        raise typer.Exit(1)
    if not name:
        console.print("[red]Error:[/red] --name is required.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        if resolved_kind == "visual":
            if not from_visual_page or not from_visual_name:
                console.print("[red]Error:[/red] --from-visual and --visual are required.")
                raise typer.Exit(1)
            pg = proj.find_page(from_visual_page)
            vis = proj.find_visual(pg, from_visual_name)
            path = save_visual_template(
                proj if scope == "project" else None,
                pg,
                vis,
                name,
                description=description,
                category=category,
                tags=tags,
                overwrite=force,
                global_scope=scope == "global",
                parameterize=not no_parameterize,
            )
        elif resolved_kind == "style":
            if from_visual_page:
                if not from_visual_name:
                    console.print("[red]Error:[/red] --visual is required with --from-visual.")
                    raise typer.Exit(1)
                pg = proj.find_page(from_visual_page)
                vis = proj.find_visual(pg, from_visual_name)
                path = save_style_from_visual(
                    proj,
                    pg,
                    vis,
                    name,
                    description=description,
                    overwrite=force,
                    global_scope=scope == "global",
                )
            elif assignments:
                props = dict(parse_property_assignments(assignments))
                path = create_style(
                    None if scope == "global" else proj,
                    name,
                    props,
                    description=description,
                    overwrite=force,
                    global_scope=scope == "global",
                )
            else:
                console.print("[red]Error:[/red] Provide prop=value assignments or use --from-visual for style creation.")
                raise typer.Exit(1)
        elif resolved_kind == "component":
            if not from_visual_page or not from_visual_name:
                console.print("[red]Error:[/red] --from-visual and --visual are required.")
                raise typer.Exit(1)
            pg = proj.find_page(from_visual_page)
            vis = proj.find_visual(pg, from_visual_name)
            path = save_component(
                proj,
                pg,
                vis,
                name,
                description=description,
                overwrite=force,
                global_scope=scope == "global",
            )
        elif resolved_kind == "page":
            if not from_visual_page:
                console.print("[red]Error:[/red] --from-visual must point to the source page for page creation.")
                raise typer.Exit(1)
            pg = proj.find_page(from_visual_page)
            path = save_template(
                proj,
                pg,
                name,
                description=description,
                overwrite=force,
                global_scope=scope == "global",
            )
        else:
            console.print(f'[red]Error:[/red] Catalog create is not implemented for kind "{resolved_kind}".')
            raise typer.Exit(1)
    except (FileExistsError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f'Saved [cyan]{resolved_kind}[/cyan] "[cyan]{name}[/cyan]" ({scope}) -> {path}')


@catalog_app.command("apply")
def catalog_apply(
    ref: Annotated[str, typer.Argument(help="Catalog ref as kind/name or plain name if unique.")],
    page: Annotated[str, typer.Argument(help="Target page.")],
    x: Annotated[int, typer.Option(help="X position for the created visual.")] = 0,
    y: Annotated[int, typer.Option(help="Y position for the created visual.")] = 0,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Override the created visual name.")] = None,
    visual: Annotated[str | None, typer.Option("--visual", help="Target visual name for style application.")] = None,
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Target all visuals of this type for style application.")] = None,
    set_params: Annotated[list[str] | None, typer.Option("--set", help="Template parameters as key=value.")] = None,
    row: Annotated[int | None, typer.Option("--row", help="Stamp N component instances in a horizontal row.")] = None,
    gap: Annotated[int, typer.Option("--gap", help="Gap between row-stamped component instances.")] = 12,
    set_each: Annotated[list[str] | None, typer.Option("--set-each", help="Per-instance values as key=v1,v2,v3.")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Overwrite non-template visuals when applying a page asset.")] = False,
    kind: Annotated[str | None, typer.Option("--kind", help="Hint or filter by kind.")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Restrict lookup to one scope.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would be created without writing.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Apply a catalog item to the report."""
    from pbi.catalog import get_catalog_item
    from pbi.components import apply_component, apply_component_row, get_component
    from pbi.properties import VISUAL_PROPERTIES
    from pbi.properties import set_property as set_prop
    from pbi.styles import _load_style_file
    from pbi.templates import apply_template
    from pbi.visual_templates import apply_visual_template

    proj = get_project(project)
    try:
        item = get_catalog_item(proj, ref, kind=kind, scope=scope)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    params: dict[str, str] = {}
    if set_params:
        try:
            params = dict(parse_property_assignments(set_params))
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    try:
        if item.kind == "visual":
            from pbi.visual_stamping import validate_spec_bindings
            from pbi.visual_templates import get_visual_template, _apply_template_parameters
            import copy as _copy

            template = get_visual_template(proj, item.name, scope=item.scope, global_scope=item.scope == "global")
            resolved_spec = _copy.deepcopy(template.payload)
            _apply_template_parameters(resolved_spec, template.parameters, params or {})

            binding_warnings = validate_spec_bindings(proj, resolved_spec)
            for warning in binding_warnings:
                console.print(f"[yellow]Warning:[/yellow] {warning}")

            if dry_run:
                target_name = name or item.name
                console.print(
                    f'[dim](dry run)[/dim] Create [cyan]{item.kind}[/cyan] "[cyan]{item.name}[/cyan]" '
                    f'on "{pg.display_name}" @ {x},{y} as "{target_name}"'
                )
                if params:
                    console.print(f"[dim]Parameters:[/dim] {', '.join(f'{k}={v}' for k, v in params.items())}")
                return

            created_visual, _template = apply_visual_template(
                proj,
                pg,
                item.name,
                x=x,
                y=y,
                name=name,
                params=params or None,
                scope=item.scope,
                global_scope=item.scope == "global",
            )
            console.print(
                f'Created from [cyan]{template.name}[/cyan] -> [cyan]{created_visual.visual_type}[/cyan] '
                f'"{created_visual.name}" on "{pg.display_name}" @ {created_visual.position.get("x", 0)},{created_visual.position.get("y", 0)}'
            )
            return

        if item.kind == "component":
            prefix = "[dim](dry run)[/dim] " if dry_run else ""
            if row and row > 0:
                each_params: dict[str, list[str]] = {}
                if set_each:
                    for raw in set_each:
                        eq = raw.find("=")
                        if eq == -1:
                            console.print(f"[red]Error:[/red] Invalid --set-each format: {raw}. Use key=v1,v2,v3.")
                            raise typer.Exit(1)
                        each_params[raw[:eq]] = raw[eq + 1 :].split(",")
                for key, value in params.items():
                    if key not in each_params:
                        each_params[key] = [value] * row

                all_created = apply_component_row(
                    proj,
                    pg,
                    item.name,
                    row,
                    x=x,
                    y=y,
                    gap=gap,
                    set_each=each_params if each_params else None,
                    global_scope=item.scope == "global",
                    dry_run=dry_run,
                )
                comp = get_component(proj, item.name, global_scope=item.scope == "global")
                console.print(
                    f'{prefix}Stamped [cyan]{row}[/cyan] instances of "[cyan]{comp.name}[/cyan]" on "{pg.display_name}"'
                )
                total = sum(len(group) for group in all_created)
                console.print(f"[dim]{total} visuals created[/dim]")
                return

            created = apply_component(
                proj,
                pg,
                item.name,
                x=x,
                y=y,
                params=params if params else None,
                global_scope=item.scope == "global",
                dry_run=dry_run,
            )
            console.print(f'{prefix}Created "[cyan]{item.name}[/cyan]" on "{pg.display_name}" at ({x}, {y})')
            for created_vis in created:
                if "visualGroup" in created_vis.data:
                    continue
                pos = created_vis.position
                console.print(
                    f'  {prefix}[cyan]{created_vis.visual_type}[/cyan] "{created_vis.name}" '
                    f'[dim]({pos.get("x", 0)}, {pos.get("y", 0)}) {pos.get("width", 0)}x{pos.get("height", 0)}[/dim]'
                )
            return

        if item.kind == "page":
            result = apply_template(
                proj,
                pg,
                item.name,
                global_scope=item.scope == "global",
                overwrite=overwrite,
                dry_run=dry_run,
            )
            if result.errors:
                for error in result.errors:
                    console.print(f"[red]Error:[/red] {error}")
                raise typer.Exit(1)
            prefix = "[dim](dry run)[/dim] " if dry_run else ""
            console.print(
                f'{prefix}Applied template "[cyan]{item.name}[/cyan]" -> "{pg.display_name}" '
                f'({len(result.visuals_created)} visuals created, {len(result.visuals_updated)} visuals updated)'
            )
            if result.visuals_deleted:
                console.print(f'{prefix}Deleted [cyan]{len(result.visuals_deleted)}[/cyan] visual(s) not in template')
            return

        if item.kind == "style":
            if not visual and not visual_type:
                console.print("[red]Error:[/red] Provide --visual or --visual-type for style application.")
                raise typer.Exit(1)
            if visual and visual_type:
                console.print("[red]Error:[/red] Use either --visual or --visual-type, not both.")
                raise typer.Exit(1)
            style = _load_style_file(item.path, item.name, scope=item.scope)
            if visual:
                targets = [proj.find_visual(pg, visual)]
            else:
                targets = [candidate for candidate in proj.get_visuals(pg) if candidate.visual_type == visual_type]
                if not targets:
                    console.print(f'[yellow]No visuals of type "{visual_type}" on "{pg.display_name}".[/yellow]')
                    raise typer.Exit(0)
            if dry_run:
                console.print(
                    f'[dim](dry run)[/dim] Applied style "[cyan]{item.name}[/cyan]" '
                    f'({len(style.properties)} properties) to [cyan]{len(targets)}[/cyan] visual(s) on "{pg.display_name}"'
                )
                return
            skipped_props: list[str] = []
            for target in targets:
                skipped_props = []
                for prop_name, value in style.properties.items():
                    try:
                        set_prop(target.data, prop_name, str(value), VISUAL_PROPERTIES)
                    except ValueError:
                        skipped_props.append(prop_name)
                target.save()
            if skipped_props:
                console.print(
                    f'[yellow]Warning:[/yellow] Skipped {len(skipped_props)} incompatible '
                    f'property(ies) for {targets[0].visual_type}: {", ".join(skipped_props)}'
                )
            applied = len(style.properties) - len(skipped_props)
            console.print(
                f'Applied style "[cyan]{item.name}[/cyan]" ({applied} properties) '
                f'to [cyan]{len(targets)}[/cyan] visual(s) on "{pg.display_name}"'
            )
            return
        console.print(f'[red]Error:[/red] Catalog apply is not implemented for kind "{item.kind}".')
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@catalog_app.command("clone")
def catalog_clone(
    ref: Annotated[str, typer.Argument(help="Catalog ref as kind/name or plain name if unique.")],
    name: Annotated[str | None, typer.Option("--name", "-n", help="Optional new name for the cloned item.")] = None,
    to_global: Annotated[bool, typer.Option("--to-global", help="Clone into global scope.")] = False,
    to_project: Annotated[bool, typer.Option("--to-project", help="Clone into project scope.")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite the target item if it exists.")] = False,
    kind: Annotated[str | None, typer.Option("--kind", help="Hint or filter by kind.")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Restrict source lookup to one scope.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Clone a catalog item between scopes."""
    from pbi.catalog import get_catalog_item
    from pbi.components import clone_component
    from pbi.styles import clone_style, create_style, get_style
    from pbi.templates import clone_template
    from pbi.visual_templates import clone_visual_template

    if to_global == to_project:
        console.print("[red]Error:[/red] Use exactly one of --to-global or --to-project.")
        raise typer.Exit(1)

    proj = _optional_project(project)
    try:
        item = get_catalog_item(proj, ref, kind=kind, scope=scope)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if to_project and proj is None:
        console.print("[red]Error:[/red] Project is required for --to-project.")
        raise typer.Exit(1)

    try:
        if item.kind == "style":
            if proj is None:
                console.print("[red]Error:[/red] Project is required to clone styles.")
                raise typer.Exit(1)
            if item.scope == "bundled":
                source = get_style(proj, item.name)
                path = create_style(
                    None if to_global else proj,
                    name or item.name,
                    source.properties,
                    description=source.description,
                    overwrite=force,
                    global_scope=to_global,
                )
            else:
                path = clone_style(proj, item.name, to_global=to_global, new_name=name, overwrite=force)
        elif item.kind == "component":
            if proj is None:
                console.print("[red]Error:[/red] Project is required to clone components.")
                raise typer.Exit(1)
            path = clone_component(proj, item.name, to_global=to_global, new_name=name, overwrite=force)
        elif item.kind == "page":
            if proj is None:
                console.print("[red]Error:[/red] Project is required to clone page assets.")
                raise typer.Exit(1)
            path = clone_template(proj, item.name, to_global=to_global, new_name=name, overwrite=force)
        elif item.kind == "visual":
            path = clone_visual_template(
                proj,
                item.name,
                from_scope=item.scope,
                to_global=to_global,
                new_name=name,
                overwrite=force,
            )
        else:
            console.print(f'[red]Error:[/red] Clone is not implemented for kind "{item.kind}".')
            raise typer.Exit(1)
    except (FileExistsError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    target_name = name or Path(path).stem
    direction = "global" if to_global else "project"
    console.print(f'Cloned [cyan]{item.kind}[/cyan] "[cyan]{item.name}[/cyan]" -> {direction} as "[cyan]{target_name}[/cyan]" -> {path}')


@catalog_app.command("delete")
def catalog_delete(
    ref: Annotated[str, typer.Argument(help="Catalog ref as kind/name or plain name if unique.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Delete without confirmation.")] = False,
    kind: Annotated[str | None, typer.Option("--kind", help="Hint or filter by kind.")] = None,
    scope: Annotated[str | None, typer.Option("--scope", help="Restrict lookup to one scope.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Delete a mutable catalog item."""
    from pbi.catalog import get_catalog_item
    from pbi.components import delete_component
    from pbi.styles import delete_style
    from pbi.templates import delete_template
    from pbi.visual_templates import delete_visual_template

    proj = _optional_project(project)
    try:
        item = get_catalog_item(proj, ref, kind=kind, scope=scope)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if item.scope == "bundled":
        console.print("[red]Error:[/red] Bundled catalog items are immutable.")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f'Delete {item.kind} "{item.name}"?')
        if not confirm:
            raise typer.Abort()

    try:
        if item.kind == "style":
            deleted = delete_style(proj, item.name, global_scope=item.scope == "global")
        elif item.kind == "component":
            deleted = delete_component(proj, item.name, global_scope=item.scope == "global")
        elif item.kind == "page":
            deleted = delete_template(proj, item.name, global_scope=item.scope == "global")
        elif item.kind == "visual":
            deleted = delete_visual_template(proj, item.name, global_scope=item.scope == "global")
        else:
            console.print(f'[red]Error:[/red] Delete is not implemented for kind "{item.kind}".')
            raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if deleted:
        console.print(f'Deleted [cyan]{item.kind}[/cyan] "[cyan]{item.name}[/cyan]"')
    else:
        console.print(f'[yellow]{item.kind} "{item.name}" not found.[/yellow]')
