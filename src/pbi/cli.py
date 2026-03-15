"""PBI Report Builder CLI."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.table import Table
from rich.tree import Tree

from pbi.commands.bookmarks import bookmark_app
from pbi.commands.common import (
    ProjectOpt,
    console,
    get_project,
    parse_property_assignments,
    resolve_yaml_input,
    resolve_output_path,
)
from pbi.commands.filters import filter_app
from pbi.commands.interactions import interaction_app
from pbi.commands.model import model_app
from pbi.commands.navigation import nav_app
from pbi.commands.pages import page_app
from pbi.commands.reports import report_app
from pbi.commands.themes import theme_app
from pbi.commands.visuals import (
    visual_app,
    visual_arrange_app,
    visual_format_app,
    visual_sort_app,
)
from pbi.properties import (
    VISUAL_PROPERTIES,
    canonical_object_property_name,
    get_known_default,
    get_visual_objects,
    property_aliases_for,
)

def _version_callback(value: bool) -> None:
    if value:
        from pbi import __version__
        typer.echo(f"pbi {__version__}")
        raise typer.Exit()


app = typer.Typer(
    name="pbi",
    help="CLI tool for editing Power BI PBIP project files.",
    no_args_is_help=True,
)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", "-V", help="Show version and exit.", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    """CLI tool for editing Power BI PBIP project files."""
style_app = typer.Typer(help="Style preset operations.", no_args_is_help=True)
app.add_typer(report_app, name="report")
app.add_typer(page_app, name="page")
app.add_typer(visual_app, name="visual")
app.add_typer(model_app, name="model")
app.add_typer(nav_app, name="nav")
app.add_typer(filter_app, name="filter")
app.add_typer(theme_app, name="theme")
app.add_typer(style_app, name="style")
app.add_typer(bookmark_app, name="bookmark")
app.add_typer(interaction_app, name="interaction")


def _safe_backup_path(project_root: Path, page_name: str) -> Path:
    """Build a deterministic backup filename that cannot escape the project root."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", page_name).strip("._") or "page"
    digest = hashlib.sha1(page_name.encode("utf-8")).hexdigest()[:8]
    return project_root / f".pbi-backup-{slug[:40]}-{digest}.yaml"


# ── Project info ───────────────────────────────────────────────────

@app.command()
def map(
    page: Annotated[Optional[str], typer.Option("--page", help="Show only this page (name, display name, or index).")] = None,
    pages_only: Annotated[bool, typer.Option("--pages", help="Show pages only (no model).")] = False,
    model_only: Annotated[bool, typer.Option("--model", help="Show model only (no pages).")] = False,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output file (default: stdout). Use 'pbi-map.yaml' for a project index.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Generate a human-readable YAML map of the entire project."""
    from pbi.mapper import generate_map
    proj = get_project(project)
    content = generate_map(
        proj,
        page_filter=page,
        pages_only=pages_only,
        model_only=model_only,
    )

    if output:
        out_path = resolve_output_path(output, base_dir=proj.root)
        out_path.write_text(content, encoding="utf-8")
        console.print(f"Map written to [cyan]{out_path}[/cyan]")
    else:
        console.print(content, highlight=False, end="")


@app.command("apply")
def apply_cmd(
    yaml_file: Annotated[Optional[str], typer.Argument(help="YAML file to apply. Use '-' or omit to read from stdin.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show what would change without modifying files.")] = False,
    page: Annotated[Optional[str], typer.Option("--page", help="Only apply to this page.")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Full reconciliation: remove visuals not in YAML. Backs up the page first.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Apply a declarative YAML specification to the report.

    The YAML format matches the output of 'pbi page export'. By default,
    this is additive — only properties specified in the YAML are touched.
    Use --overwrite to fully reconcile a page to match the YAML (destructive).
    With --overwrite, the existing page is backed up to a .yaml file first.
    """
    from pbi.apply import apply_yaml

    proj = get_project(project)
    try:
        yaml_content = resolve_yaml_input(yaml_file)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Backup before overwrite
    if overwrite and not dry_run:
        from pbi.export import export_yaml
        import yaml as yaml_mod

        spec = yaml_mod.safe_load(yaml_content)
        pages_in_spec = []
        if isinstance(spec, dict):
            pages_in_spec = [p.get("name") for p in spec.get("pages", []) if isinstance(p, dict) and p.get("name")]

        for page_name in pages_in_spec:
            if page and page_name.lower() != page.lower():
                continue
            try:
                proj.find_page(page_name)
            except ValueError:
                continue  # Page doesn't exist yet, nothing to back up

            backup_content = export_yaml(proj, page_filter=page_name)
            backup_path = _safe_backup_path(proj.root, page_name)
            backup_path.write_text(backup_content, encoding="utf-8")
            console.print(f"[dim]Backed up \"{page_name}\" → {backup_path}[/dim]")

    result = apply_yaml(
        proj,
        yaml_content,
        page_filter=page,
        dry_run=dry_run,
        overwrite=overwrite,
    )

    # Report results
    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    if result.pages_created:
        for p in result.pages_created:
            console.print(f'{prefix}Created page "[cyan]{p}[/cyan]"')
    if result.pages_updated:
        for p in result.pages_updated:
            console.print(f'{prefix}Updated page "[cyan]{p}[/cyan]"')
    if result.visuals_created:
        for p, v in result.visuals_created:
            console.print(f'{prefix}Created visual "[cyan]{v}[/cyan]" on "{p}"')
    if result.visuals_updated:
        for p, v in result.visuals_updated:
            console.print(f'{prefix}Updated visual "[cyan]{v}[/cyan]" on "{p}"')
    if result.visuals_deleted:
        for p, v in result.visuals_deleted:
            console.print(f'{prefix}Deleted visual "[cyan]{v}[/cyan]" on "{p}" (not in YAML)')

    if result.properties_set or result.bindings_added or result.filters_added:
        parts = []
        if result.properties_set:
            parts.append(f"{result.properties_set} properties")
        if result.bindings_added:
            parts.append(f"{result.bindings_added} bindings")
        if result.filters_added:
            parts.append(f"{result.filters_added} filters")
        console.print(f"{prefix}Set {', '.join(parts)}")

    for warning in result.warnings:
        console.print(f"[yellow]Warning:[/yellow] {warning}")
    for error in result.errors:
        console.print(f"[red]Error:[/red] {error}")

    if result.errors:
        raise typer.Exit(1)
    if not result.has_changes and not dry_run:
        console.print("[dim]No changes applied.[/dim]")


@style_app.command("create")
def style_create(
    style_name: Annotated[str, typer.Argument(help="Name for the saved style preset.")],
    assignments: Annotated[list[str] | None, typer.Argument(help="Property assignments as prop=value.")] = None,
    from_visual_page: Annotated[str | None, typer.Option("--from-visual", help="Capture style from visual: page name.")] = None,
    from_visual_name: Annotated[str | None, typer.Option("--visual", help="Visual name (used with --from-visual).")] = None,
    description: Annotated[str | None, typer.Option("--description", help="Optional style description.")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Replace an existing style preset.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Save as a global style (~/.config/pbi/styles/).")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a visual style preset from assignments or an existing visual."""
    from pbi.styles import create_style, extract_style_properties

    proj = get_project(project) if not global_scope or from_visual_page else (get_project(project) if project else None)

    if from_visual_page:
        if not from_visual_name:
            console.print("[red]Error:[/red] --visual is required with --from-visual.")
            raise typer.Exit(1)
        proj = get_project(project)
        from pbi.export import export_visual_spec
        try:
            pg = proj.find_page(from_visual_page)
            vis = proj.find_visual(pg, from_visual_name)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        spec = export_visual_spec(proj, vis)
        props = extract_style_properties(spec)
        if not props:
            console.print("[yellow]Visual has no style properties to capture.[/yellow]")
            raise typer.Exit(0)
    elif assignments:
        props = dict(parse_property_assignments(assignments))
    else:
        console.print("[red]Error:[/red] Provide prop=value assignments or use --from-visual.")
        raise typer.Exit(1)

    try:
        path = create_style(
            proj,
            style_name,
            props,
            description=description,
            overwrite=force,
            global_scope=global_scope,
        )
    except (FileExistsError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    scope_label = "global " if global_scope else ""
    console.print(
        f'Saved {scope_label}style "[cyan]{style_name}[/cyan]" '
        f"({len(props)} properties) → {path}"
    )


@style_app.command("list")
def style_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Show only global styles.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List saved style presets (project + global)."""
    from pbi.styles import list_styles

    proj = get_project(project) if not global_scope else None
    styles = list_styles(proj, global_scope=global_scope)

    if not styles:
        console.print("[yellow]No styles saved. Use `pbi style create` to create one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        rows = [{"name": s.name, "properties": len(s.properties), "scope": s.scope, "description": s.description or ""} for s in styles]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Scope", style="dim")
    table.add_column("Properties")
    table.add_column("Description", style="dim")
    for style in styles:
        table.add_row(
            style.name,
            style.scope,
            str(len(style.properties)),
            style.description or "",
        )
    console.print(table)


@style_app.command("get")
def style_get(
    style_name: Annotated[str, typer.Argument(help="Style preset name.")],
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Look up in global styles only.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show one saved style preset as YAML."""
    from pbi.styles import dump_style, get_style

    proj = get_project(project) if not global_scope else None
    try:
        style = get_style(proj, style_name, global_scope=global_scope)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    typer.echo(dump_style(style), nl=False)


@style_app.command("delete")
def style_delete(
    style_name: Annotated[str, typer.Argument(help="Style preset name to delete.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Delete from global styles.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a saved style preset."""
    from pbi.styles import delete_style

    proj = get_project(project) if not global_scope else None
    if not force:
        confirm = typer.confirm(f'Delete style "{style_name}"?')
        if not confirm:
            raise typer.Abort()

    try:
        deleted = delete_style(proj, style_name, global_scope=global_scope)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if deleted:
        console.print(f'Deleted style "[cyan]{style_name}[/cyan]"')
    else:
        console.print(f'[yellow]Style "{style_name}" not found.[/yellow]')


@style_app.command("apply")
def style_apply(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str | None, typer.Argument(help="Visual name or index. Omit with --visual-type.")] = None,
    style_name: Annotated[str, typer.Option("--style", "-s", help="Style preset name to apply.")] = "",
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Apply to all visuals of this type.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Apply a saved style preset to one or more visuals."""
    from pbi.properties import set_property as set_prop
    from pbi.styles import get_style

    if not style_name:
        console.print("[red]Error:[/red] --style is required.")
        raise typer.Exit(1)
    if not visual and not visual_type:
        console.print("[red]Error:[/red] Provide a visual name or use --visual-type.")
        raise typer.Exit(1)
    if visual and visual_type:
        console.print("[red]Error:[/red] Use either a visual name or --visual-type, not both.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        style = get_style(proj, style_name)
    except (ValueError, FileNotFoundError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if visual:
        targets = [proj.find_visual(pg, visual)]
    else:
        targets = [v for v in proj.get_visuals(pg) if v.visual_type == visual_type]
        if not targets:
            console.print(f'[yellow]No visuals of type "{visual_type}" on "{pg.display_name}".[/yellow]')
            raise typer.Exit(0)

    for vis in targets:
        for prop_name, value in style.properties.items():
            try:
                set_prop(vis.data, prop_name, str(value), VISUAL_PROPERTIES)
            except ValueError:
                pass
        vis.save()

    console.print(
        f'Applied style "[cyan]{style_name}[/cyan]" ({len(style.properties)} properties) '
        f'to [cyan]{len(targets)}[/cyan] visual(s) on "{pg.display_name}"'
    )


@style_app.command("clone")
def style_clone(
    style_name: Annotated[str, typer.Argument(help="Style to clone.")],
    new_name: Annotated[str | None, typer.Option("--name", "-n", help="New name for the cloned style.")] = None,
    to_global: Annotated[bool, typer.Option("--to-global", help="Clone project style to global.")] = False,
    to_project: Annotated[bool, typer.Option("--to-project", help="Clone global style to project.")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite if exists.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clone a style between project and global scope."""
    from pbi.styles import clone_style

    if not to_global and not to_project:
        console.print("[red]Error:[/red] Specify --to-global or --to-project.")
        raise typer.Exit(1)
    if to_global and to_project:
        console.print("[red]Error:[/red] Use either --to-global or --to-project, not both.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        path = clone_style(proj, style_name, to_global=to_global, new_name=new_name, overwrite=force)
    except (FileExistsError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    target_name = new_name or style_name
    direction = "global" if to_global else "project"
    console.print(f'Cloned "[cyan]{style_name}[/cyan]" → {direction} as "[cyan]{target_name}[/cyan]" → {path}')


@app.command("diff")
def diff_cmd(
    yaml_file: Annotated[Optional[str], typer.Argument(help="YAML file to compare against current state. Use '-' or omit to read from stdin.")] = None,
    page: Annotated[Optional[str], typer.Option("--page", help="Only diff this page.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show what 'pbi apply' would change, property by property."""
    from pbi.export import export_visual_spec

    proj = get_project(project)
    try:
        yaml_content = resolve_yaml_input(yaml_file)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    import yaml as yaml_mod
    spec = yaml_mod.safe_load(yaml_content)
    if not isinstance(spec, dict) or "pages" not in spec:
        console.print("[red]Error:[/red] YAML must have a 'pages' key.")
        raise typer.Exit(1)

    has_diffs = False
    for page_spec in spec["pages"]:
        page_name = page_spec.get("name", "")
        if page and page_name.lower() != page.lower():
            continue

        try:
            pg = proj.find_page(page_name)
        except ValueError:
            console.print(f'\n[green]+ New page:[/green] [cyan]{page_name}[/cyan]')
            vis_count = len(page_spec.get("visuals", []))
            if vis_count:
                console.print(f"  {vis_count} visual(s) would be created")
            has_diffs = True
            continue

        visuals = proj.get_visuals(pg)
        vis_by_name = {v.name: v for v in visuals}
        vis_by_id = {v.folder.name: v for v in visuals}

        from pbi.commands.visuals.helpers import flatten_visual_diff_spec

        for vis_spec in page_spec.get("visuals", []):
            vis_name = vis_spec.get("name", "")
            vis_id = vis_spec.get("id", "")

            existing = vis_by_id.get(vis_id) or vis_by_name.get(vis_name)
            if not existing:
                console.print(f'\n[green]+ New visual:[/green] [cyan]{vis_name}[/cyan] on "{page_name}"')
                has_diffs = True
                continue

            # Compare current vs YAML spec
            current_spec = flatten_visual_diff_spec(export_visual_spec(proj, existing), include_core=True)
            yaml_flat = flatten_visual_diff_spec(vis_spec, include_core=True)

            diffs = []
            for key in yaml_flat:
                if key in {"id", "pbir"}:
                    continue
                curr = str(current_spec.get(key, ""))
                proposed = str(yaml_flat[key])
                if curr != proposed:
                    diffs.append((key, curr, proposed))

            if diffs:
                has_diffs = True
                console.print(f'\n[bold]{page_name}/{existing.name}[/bold]')
                for prop, old, new in diffs:
                    console.print(f"  [cyan]{prop}[/cyan]: {old or '(none)'} [dim]→[/dim] {new}")

    if not has_diffs:
        console.print("[dim]No differences found.[/dim]")


@app.command()
def info(project: ProjectOpt = None) -> None:
    """Show project overview."""
    proj = get_project(project)
    pages = proj.get_pages()
    meta = proj.get_pages_meta()

    tree = Tree(f"[bold]{proj.project_name}[/bold]")
    tree.add(f"[dim]Root:[/dim] {proj.root}")
    tree.add(f"[dim]Report:[/dim] {proj.report_folder.name}")

    pages_branch = tree.add(f"[bold]Pages[/bold] ({len(pages)})")
    for page in pages:
        visuals = proj.get_visuals(page)
        active = " [green](active)[/green]" if meta.get("activePageName") == page.name else ""
        hidden = " [yellow](hidden)[/yellow]" if page.visibility == "HiddenInViewMode" else ""
        page_node = pages_branch.add(
            f'[cyan]{page.display_name}[/cyan]{active}{hidden} '
            f'[dim]{page.width}x{page.height}[/dim]'
        )
        for v in visuals:
            pos = v.position
            name_label = f'[cyan]{v.name}[/cyan] ' if v.name != v.visual_type else ''
            page_node.add(
                f'{name_label}{v.visual_type} [dim]@ {pos.get("x", 0)},{pos.get("y", 0)} '
                f'{pos.get("width", 0)}x{pos.get("height", 0)}[/dim]'
            )

    console.print(tree)


@app.command()
def capabilities(
    status: Annotated[
        Optional[str],
        typer.Option(
            "--status",
            help="Filter by status: supported, partial, blocked, planned.",
        ),
    ] = None,
    as_json: Annotated[
        bool,
        typer.Option("--json", help="Output the capability matrix as JSON."),
    ] = False,
) -> None:
    """Show the CLI capability matrix versus PBIR/Power BI authoring features."""
    import json as json_mod
    from pbi.capabilities import list_capabilities

    valid_statuses = {"supported", "partial", "blocked", "planned"}
    if status and status not in valid_statuses:
        console.print(
            f"[red]Error:[/red] Invalid status '{status}'. "
            f"Use one of: {', '.join(sorted(valid_statuses))}"
        )
        raise typer.Exit(1)

    capabilities = list_capabilities(status=status)

    if as_json:
        console.print_json(json_mod.dumps([cap.to_dict() for cap in capabilities], indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Domain", style="cyan")
    table.add_column("Feature")
    table.add_column("Status", style="bold")
    table.add_column("Next Step", style="dim")

    status_style = {
        "supported": "[green]supported[/green]",
        "partial": "[yellow]partial[/yellow]",
        "blocked": "[red]blocked[/red]",
        "planned": "[blue]planned[/blue]",
    }

    for cap in capabilities:
        table.add_row(
            cap.domain,
            cap.feature,
            status_style.get(cap.status, cap.status),
            cap.next_step,
        )

    console.print(table)

# ── Validate command ──────────────────────────────────────────

@app.command()
def validate(
    project: ProjectOpt = None,
) -> None:
    """Validate project files for structural errors.

    Checks JSON validity, required fields, schema consistency, and
    cross-references (page order, visual interactions, group membership).
    """
    from pbi.validate import validate_project

    proj = get_project(project)
    issues = validate_project(proj)

    if not issues:
        console.print("[green]No issues found.[/green]")
        return

    errors = [i for i in issues if i.level == "error"]
    warnings = [i for i in issues if i.level == "warning"]

    if errors:
        console.print(f"\n[red bold]{len(errors)} error(s):[/red bold]")
        for issue in errors:
            console.print(f"  [red]ERROR[/red] {issue.file}: {issue.message}")

    if warnings:
        console.print(f"\n[yellow bold]{len(warnings)} warning(s):[/yellow bold]")
        for issue in warnings:
            console.print(f"  [yellow]WARN[/yellow]  {issue.file}: {issue.message}")

    if errors:
        raise typer.Exit(1)


# ── Layout calculator ─────────────────────────────────────────

calc_app = typer.Typer(help="Layout position calculators for YAML authoring.", no_args_is_help=True)
app.add_typer(calc_app, name="calc")


@calc_app.command("row")
def calc_row(
    count: Annotated[int, typer.Argument(help="Number of items in the row.")],
    width: Annotated[int, typer.Option("--width", "-w", help="Page width in pixels.")] = 1280,
    margin: Annotated[int, typer.Option("--margin", "-m", help="Left/right margin in pixels.")] = 0,
    gap: Annotated[int, typer.Option("--gap", "-g", help="Gap between items in pixels.")] = 8,
    height: Annotated[int | None, typer.Option("--height", help="Item height (for copy-paste into YAML).")] = None,
    y: Annotated[int | None, typer.Option("--y", help="Y position (for copy-paste into YAML).")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Calculate evenly-spaced positions for a horizontal row of items."""
    import json as json_mod

    if count < 1:
        console.print("[red]Error:[/red] Count must be at least 1.")
        raise typer.Exit(1)

    usable = width - 2 * margin
    total_gaps = gap * (count - 1) if count > 1 else 0
    item_width = (usable - total_gaps) / count

    if item_width <= 0:
        console.print("[red]Error:[/red] Not enough space for the requested items.")
        raise typer.Exit(1)

    items = []
    for i in range(count):
        x = margin + i * (item_width + gap)
        items.append({"index": i + 1, "x": round(x), "width": round(item_width)})

    if as_json:
        console.print_json(json_mod.dumps(items, indent=2))
        return

    console.print(f"[bold]Row layout:[/bold] {count} items, {round(item_width)}px each, gap={gap}")
    for item in items:
        pos = f"position: {item['x']}, {y if y is not None else 0}"
        size = f"size: {item['width']} x {height if height is not None else '?'}"
        console.print(f"  [dim]#{item['index']}[/dim]  {pos}  |  {size}")


@calc_app.command("grid")
def calc_grid(
    count: Annotated[int, typer.Argument(help="Total number of items.")],
    columns: Annotated[int, typer.Option("--columns", "-c", help="Number of columns.")] = 3,
    width: Annotated[int, typer.Option("--width", "-w", help="Page width in pixels.")] = 1280,
    margin: Annotated[int, typer.Option("--margin", "-m", help="Left/right/top margin in pixels.")] = 0,
    gap: Annotated[int, typer.Option("--gap", "-g", help="Gap between items in pixels.")] = 8,
    item_height: Annotated[int, typer.Option("--item-height", help="Height of each item.")] = 200,
    y: Annotated[int, typer.Option("--y", help="Starting Y position.")] = 0,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
) -> None:
    """Calculate positions for a grid layout of items."""
    import json as json_mod

    if count < 1 or columns < 1:
        console.print("[red]Error:[/red] Count and columns must be at least 1.")
        raise typer.Exit(1)

    usable = width - 2 * margin
    col_gaps = gap * (columns - 1) if columns > 1 else 0
    item_width = (usable - col_gaps) / columns

    if item_width <= 0:
        console.print("[red]Error:[/red] Not enough space for the requested columns.")
        raise typer.Exit(1)

    items = []
    for i in range(count):
        col = i % columns
        row = i // columns
        x = margin + col * (item_width + gap)
        iy = y + row * (item_height + gap)
        items.append({"index": i + 1, "x": round(x), "y": round(iy), "width": round(item_width), "height": item_height})

    if as_json:
        console.print_json(json_mod.dumps(items, indent=2))
        return

    rows = (count + columns - 1) // columns
    console.print(f"[bold]Grid layout:[/bold] {count} items, {columns} cols x {rows} rows, {round(item_width)}px wide")
    for item in items:
        pos = f"position: {item['x']}, {item['y']}"
        size = f"size: {item['width']} x {item['height']}"
        console.print(f"  [dim]#{item['index']}[/dim]  {pos}  |  {size}")


# ── Render ────────────────────────────────────────────────────────

@app.command()
def render(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output HTML file path (default: <page>.html in project root).")] = None,
    screenshot: Annotated[bool, typer.Option("--screenshot", "-s", help="Also generate a PNG screenshot via Puppeteer.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Render a page as an HTML layout mockup.

    Generates an HTML file showing visual positions, sizes, titles,
    text content, and formatting. Charts and data visuals appear as
    labeled placeholders.

    Use --screenshot to also capture a PNG via Puppeteer (requires
    Node.js and puppeteer installed globally or in the project).
    """
    from pbi.render import render_page_html, render_page_screenshot_html

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Determine output path
    if output:
        out_path = resolve_output_path(output, base_dir=proj.root)
    else:
        slug = re.sub(r"[^A-Za-z0-9._-]+", "_", pg.display_name).strip("._") or "page"
        out_path = proj.root / f"{slug}.html"

    # Write HTML
    html_content = render_page_html(proj, pg)
    out_path.write_text(html_content, encoding="utf-8")
    console.print(f'Rendered "[cyan]{pg.display_name}[/cyan]" → [cyan]{out_path}[/cyan]')

    visuals = proj.get_visuals(pg)
    visible = [v for v in visuals if not v.data.get("isHidden") and "visualGroup" not in v.data]
    console.print(f"[dim]{len(visible)} visuals, {pg.width}x{pg.height}px[/dim]")

    if screenshot:
        screenshot_path = out_path.with_suffix(".png")
        # Write a separate screenshot-optimized HTML (no body padding)
        screenshot_html_path = out_path.with_name(out_path.stem + "_screenshot.html")
        screenshot_html = render_page_screenshot_html(proj, pg)
        screenshot_html_path.write_text(screenshot_html, encoding="utf-8")

        _run_puppeteer_screenshot(screenshot_html_path, screenshot_path, pg.width, pg.height)
        # Clean up temp HTML
        screenshot_html_path.unlink(missing_ok=True)


def _run_puppeteer_screenshot(html_path: Path, output_path: Path, width: int, height: int) -> None:
    """Run Puppeteer to take a screenshot of the HTML file."""
    import subprocess

    script = f"""\
const puppeteer = require('puppeteer');
(async () => {{
  const browser = await puppeteer.launch({{
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  }});
  const page = await browser.newPage();
  await page.setViewport({{ width: {width}, height: {height}, deviceScaleFactor: 2 }});
  await page.goto('file://{html_path.resolve()}', {{ waitUntil: 'networkidle0' }});
  await page.screenshot({{
    path: '{output_path.resolve()}',
    clip: {{ x: 0, y: 0, width: {width}, height: {height} }},
  }});
  await browser.close();
}})();
"""
    # Write script next to the HTML so node_modules resolution works
    script_path = html_path.with_name("_pbi_screenshot.js")
    script_path.write_text(script, encoding="utf-8")

    try:
        result = subprocess.run(
            ["node", str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(html_path.parent),
        )
        if result.returncode != 0:
            console.print(f"[red]Error:[/red] Puppeteer failed: {result.stderr.strip()}")
            raise typer.Exit(1)
        console.print(f"Screenshot → [cyan]{output_path}[/cyan]")
    except FileNotFoundError:
        console.print("[red]Error:[/red] Node.js not found. Install Node.js and puppeteer for screenshots.")
        raise typer.Exit(1)
    except subprocess.TimeoutExpired:
        console.print("[red]Error:[/red] Puppeteer timed out.")
        raise typer.Exit(1)
    finally:
        script_path.unlink(missing_ok=True)


if __name__ == "__main__":
    app()
