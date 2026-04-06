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
from pbi.commands.catalog import catalog_app
from pbi.commands.common import (
    ProjectOpt,
    console,
    find_project,
    get_project,
    parse_property_assignments,
    resolve_yaml_input,
    resolve_output_path,
)
from pbi.commands.filters import filter_app
from pbi.commands.images import image_app
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
from pbi.project_runtime import prepare_project_runtime

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
app.add_typer(report_app, name="report")
app.add_typer(page_app, name="page")
app.add_typer(visual_app, name="visual")
app.add_typer(model_app, name="model")
app.add_typer(nav_app, name="nav")
app.add_typer(filter_app, name="filter")
app.add_typer(theme_app, name="theme")
app.add_typer(bookmark_app, name="bookmark")
app.add_typer(interaction_app, name="interaction")
app.add_typer(image_app, name="image")
app.add_typer(catalog_app, name="catalog")


def _safe_backup_path(project_root: Path, page_name: str) -> Path:
    """Build a deterministic backup filename that cannot escape the project root."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", page_name).strip("._") or "page"
    digest = hashlib.sha1(page_name.encode("utf-8")).hexdigest()[:8]
    return project_root / f".pbi-backup-{slug[:40]}-{digest}.yaml"


# ── Project info ───────────────────────────────────────────────────

@app.command()
def init(project: ProjectOpt = None) -> None:
    """Initialize project-local CLI runtime state."""
    proj = find_project(project)
    runtime = prepare_project_runtime(proj)

    if runtime.newly_installed_visuals:
        for cv in runtime.newly_installed_visuals:
            console.print(
                f'Installed plugin schema "[cyan]{cv.visual_type}[/cyan]" '
                f"({cv.role_count} roles, {cv.object_count} objects)"
            )
        console.print(f'Initialized project "[cyan]{proj.project_name}[/cyan]"')
        return

    console.print("[dim]No initialization changes needed.[/dim]")

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
        out_path = resolve_output_path(output)
        out_path.write_text(content, encoding="utf-8")
        console.print(f"Map written to [cyan]{out_path}[/cyan]")
    else:
        console.print(content, highlight=False, end="")


@app.command("export")
def export_cmd(
    page: Annotated[Optional[str], typer.Option("--page", help="Export only this page (name, display name, or index).")] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output file (default: stdout).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Export full report YAML for use with 'pbi apply'."""
    from pbi.export import export_yaml

    proj = get_project(project)

    if page:
        try:
            proj.find_page(page)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    content = export_yaml(proj, page_filter=page)

    if output:
        out_path = resolve_output_path(output)
        out_path.write_text(content, encoding="utf-8")
        console.print(f"Exported to [cyan]{out_path}[/cyan]")
    else:
        typer.echo(content, nl=False)


@app.command("apply")
def apply_cmd(
    yaml_file: Annotated[Optional[str], typer.Argument(help="YAML file to apply. Use '-' or omit to read from stdin.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show what would change without modifying files.")] = False,
    page: Annotated[Optional[str], typer.Option("--page", help="Only apply to this page.")] = None,
    overwrite: Annotated[bool, typer.Option("--overwrite", help="Full reconciliation: remove visuals not in YAML. Backs up the page first.")] = False,
    continue_on_error: Annotated[bool, typer.Option("--continue-on-error", help="Apply what is possible and report errors without rollback.")] = False,
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
        continue_on_error=continue_on_error,
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
    if result.interactions_set:
        for page_name, source, target, interaction_type in result.interactions_set:
            console.print(
                f'{prefix}Set interaction: [cyan]{source}[/cyan] [dim]->[/dim] '
                f'[cyan]{target}[/cyan] on "{page_name}" [dim]=[/dim] {interaction_type}'
            )

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

    if result.rolled_back:
        console.print("[yellow]All changes have been rolled back due to errors.[/yellow]")

    if result.errors:
        raise typer.Exit(1)
    if not result.has_changes and not dry_run:
        console.print("[dim]No changes applied.[/dim]")


@app.command("diff")
def diff_cmd(
    yaml_file: Annotated[Optional[str], typer.Argument(help="YAML file to compare against current state. Use '-' or omit to read from stdin.")] = None,
    page: Annotated[Optional[str], typer.Option("--page", help="Only diff this page.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show what 'pbi apply' would change, property by property."""
    from pbi.bookmarks import export_bookmarks
    from pbi.commands.visuals.helpers import flatten_diff_spec, flatten_visual_diff_spec
    from pbi.export import export_visual_spec, export_yaml

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
    if page is None and isinstance(spec.get("theme"), dict):
        current_theme = yaml_mod.safe_load(export_yaml(proj)).get("theme", {})
        yaml_theme = spec.get("theme", {})
        current_flat = flatten_diff_spec(current_theme)
        yaml_flat = flatten_diff_spec(yaml_theme)
        theme_diffs = []
        for key, proposed in yaml_flat.items():
            curr = str(current_flat.get(key, ""))
            proposed_text = str(proposed)
            if curr != proposed_text:
                theme_diffs.append((key, curr or "(none)", proposed_text))
        if theme_diffs:
            has_diffs = True
            console.print("\n[bold]Theme[/bold]")
            for prop, old, new in theme_diffs:
                label = f"theme.{prop}" if prop else "theme"
                console.print(f"  [cyan]{label}[/cyan]: {old} [dim]->[/dim] {new}")
    if page is None and isinstance(spec.get("report"), dict):
        current_report = yaml_mod.safe_load(export_yaml(proj)).get("report", {})
        yaml_report = spec.get("report", {})
        current_flat = flatten_diff_spec(current_report)
        yaml_flat = flatten_diff_spec(yaml_report)
        report_diffs = []
        for key, proposed in yaml_flat.items():
            curr = str(current_flat.get(key, ""))
            proposed_text = str(proposed)
            if curr != proposed_text:
                report_diffs.append((key, curr or "(none)", proposed_text))
        if report_diffs:
            has_diffs = True
            console.print("\n[bold]Report[/bold]")
            for prop, old, new in report_diffs:
                label = f"report.{prop}" if prop else "report"
                console.print(f"  [cyan]{label}[/cyan]: {old} [dim]->[/dim] {new}")
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
                    console.print(f"  [cyan]{prop}[/cyan]: {old or '(none)'} [dim]->[/dim] {new}")

    yaml_bookmarks = spec.get("bookmarks", [])
    if isinstance(yaml_bookmarks, list):
        bookmark_page = None
        if page:
            try:
                bookmark_page = proj.find_page(page)
            except ValueError:
                bookmark_page = None
        current_bookmarks = {
            entry["name"]: entry
            for entry in export_bookmarks(proj, page=bookmark_page)
            if isinstance(entry, dict) and isinstance(entry.get("name"), str)
        }

        for bookmark_spec in yaml_bookmarks:
            if not isinstance(bookmark_spec, dict):
                continue
            bookmark_name = bookmark_spec.get("name", "")
            bookmark_page_name = bookmark_spec.get("page", "")
            if page and isinstance(bookmark_page_name, str) and bookmark_page_name.lower() != page.lower():
                continue
            if not isinstance(bookmark_name, str) or not bookmark_name:
                continue

            existing = current_bookmarks.get(bookmark_name)
            if existing is None:
                console.print(f'\n[green]+ New bookmark:[/green] [cyan]{bookmark_name}[/cyan]')
                has_diffs = True
                continue

            current_flat = flatten_diff_spec(existing, ignore_keys={"name"})
            yaml_flat = flatten_diff_spec(bookmark_spec, ignore_keys={"name"})
            diffs = []
            for key, proposed in yaml_flat.items():
                curr = str(current_flat.get(key, ""))
                proposed_text = str(proposed)
                if curr != proposed_text:
                    diffs.append((key, curr or "(none)", proposed_text))

            if diffs:
                has_diffs = True
                console.print(f'\n[bold]Bookmark {bookmark_name}[/bold]')
                for prop, old, new in diffs:
                    console.print(f"  [cyan]{prop}[/cyan]: {old} [dim]->[/dim] {new}")

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
    strict: Annotated[bool, typer.Option("--strict", help="Fail on warnings as well as errors.")] = False,
    ignore_schema_warnings: Annotated[
        bool,
        typer.Option("--ignore-schema-warnings", help="Suppress schema-derived warnings from validation output."),
    ] = False,
    project: ProjectOpt = None,
) -> None:
    """Validate project files for structural errors.

    Checks JSON validity, required fields, schema consistency, and
    cross-references (page order, visual interactions, group membership).
    """
    from pbi.validate import validate_project

    proj = get_project(project)
    issues = validate_project(proj)
    if ignore_schema_warnings:
        issues = [
            issue for issue in issues
            if not (issue.level == "warning" and issue.message.startswith("Schema:"))
        ]

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
    if strict and warnings:
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
        out_path = resolve_output_path(output)
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
