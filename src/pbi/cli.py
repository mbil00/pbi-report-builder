"""PBI Report Builder CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.table import Table
from rich.tree import Tree

from pbi.commands.bookmarks import bookmark_app
from pbi.commands.common import ProjectOpt, console, get_project, parse_property_assignments
from pbi.commands.filters import filter_app
from pbi.commands.interactions import interaction_app
from pbi.commands.model import model_app
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
app.add_typer(filter_app, name="filter")
app.add_typer(theme_app, name="theme")
app.add_typer(style_app, name="style")
app.add_typer(bookmark_app, name="bookmark")
app.add_typer(interaction_app, name="interaction")


# ── Project info ───────────────────────────────────────────────────

@app.command()
def map(
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output file (default: stdout). Use 'pbi-map.yaml' for a project index.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Generate a human-readable YAML map of the entire project."""
    from pbi.mapper import generate_map
    proj = get_project(project)
    content = generate_map(proj)

    if output:
        out_path = output if output.is_absolute() else proj.root / output
        out_path.write_text(content, encoding="utf-8")
        console.print(f"Map written to [cyan]{out_path}[/cyan]")
    else:
        console.print(content, highlight=False, end="")


@app.command("apply")
def apply_cmd(
    yaml_file: Annotated[Path, typer.Argument(help="YAML file to apply.")],
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
    import shutil
    import tempfile

    from pbi.apply import apply_yaml

    proj = get_project(project)

    # Resolve file path
    yaml_path = yaml_file if yaml_file.is_absolute() else Path.cwd() / yaml_file
    if not yaml_path.exists():
        console.print(f"[red]Error:[/red] File not found: {yaml_path}")
        raise typer.Exit(1)

    yaml_content = yaml_path.read_text(encoding="utf-8")

    # Backup before overwrite
    if overwrite and not dry_run:
        from pbi.export import export_yaml
        import yaml as yaml_mod

        spec = yaml_mod.safe_load(yaml_content)
        pages_in_spec = [p.get("name") for p in spec.get("pages", []) if p.get("name")]

        for page_name in pages_in_spec:
            if page and page_name.lower() != page.lower():
                continue
            try:
                existing_page = proj.find_page(page_name)
            except ValueError:
                continue  # Page doesn't exist yet, nothing to back up

            backup_content = export_yaml(proj, page_filter=page_name)
            backup_path = proj.root / f".pbi-backup-{page_name}.yaml"
            backup_path.write_text(backup_content, encoding="utf-8")
            console.print(f"[dim]Backed up \"{page_name}\" → {backup_path}[/dim]")

    snapshot_dir: Path | None = None
    temp_dir: tempfile.TemporaryDirectory[str] | None = None
    if overwrite and not dry_run:
        temp_dir = tempfile.TemporaryDirectory()
        snapshot_dir = Path(temp_dir.name) / "definition"
        shutil.copytree(proj.definition_folder, snapshot_dir)

    result = apply_yaml(
        proj,
        yaml_content,
        page_filter=page,
        dry_run=dry_run,
        overwrite=overwrite,
    )

    if result.errors and snapshot_dir is not None:
        shutil.rmtree(proj.definition_folder)
        shutil.copytree(snapshot_dir, proj.definition_folder)
        console.print("[dim]Rolled back failed overwrite apply.[/dim]")

    if temp_dir is not None:
        temp_dir.cleanup()

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
    assignments: Annotated[list[str], typer.Argument(help="Property assignments as prop=value.")],
    description: Annotated[str | None, typer.Option("--description", help="Optional style description.")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Replace an existing style preset.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create a project-scoped visual style preset."""
    from pbi.styles import create_style

    if not assignments:
        console.print("[red]Error:[/red] Provide at least one prop=value assignment.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        props = dict(parse_property_assignments(assignments))
        path = create_style(
            proj,
            style_name,
            props,
            description=description,
            overwrite=force,
        )
    except (FileExistsError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f'Saved style "[cyan]{style_name}[/cyan]" '
        f"({len(props)} properties) → {path}"
    )


@style_app.command("list")
def style_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List saved style presets."""
    from pbi.styles import list_styles

    proj = get_project(project)
    styles = list_styles(proj)

    if not styles:
        console.print("[yellow]No styles saved. Use `pbi style create` to create one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        rows = [{"name": s.name, "properties": len(s.properties), "description": s.description or ""} for s in styles]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Properties")
    table.add_column("Description", style="dim")
    table.add_column("File", style="dim")
    for style in styles:
        table.add_row(
            style.name,
            str(len(style.properties)),
            style.description or "",
            style.path.name,
        )
    console.print(table)


@style_app.command("get")
def style_get(
    style_name: Annotated[str, typer.Argument(help="Style preset name.")],
    project: ProjectOpt = None,
) -> None:
    """Show one saved style preset as YAML."""
    from pbi.styles import dump_style, get_style

    proj = get_project(project)
    try:
        style = get_style(proj, style_name)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    typer.echo(dump_style(style), nl=False)


@style_app.command("delete")
def style_delete(
    style_name: Annotated[str, typer.Argument(help="Style preset name to delete.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a saved style preset."""
    from pbi.styles import delete_style

    proj = get_project(project)
    if not force:
        confirm = typer.confirm(f'Delete style "{style_name}"?')
        if not confirm:
            raise typer.Abort()

    try:
        deleted = delete_style(proj, style_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if deleted:
        console.print(f'Deleted style "[cyan]{style_name}[/cyan]"')
    else:
        console.print(f'[yellow]Style "{style_name}" not found.[/yellow]')


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


if __name__ == "__main__":
    app()
