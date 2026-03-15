"""PBI Report Builder CLI."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
from rich import box

from pbi.project import Project
from pbi.properties import (
    VISUAL_PROPERTIES,
    REPORT_PROPERTIES,
    PAGE_PROPERTIES,
    canonical_object_property_name,
    get_property,
    get_known_default,
    property_aliases_for,
    set_property,
    list_properties,
    get_visual_objects,
)
from pbi.schema_refs import REPORT_SCHEMA

app = typer.Typer(
    name="pbi",
    help="CLI tool for editing Power BI PBIP project files.",
    no_args_is_help=True,
)
page_app = typer.Typer(help="Page operations.", no_args_is_help=True)
page_drillthrough_app = typer.Typer(help="Page drillthrough operations.", no_args_is_help=True)
page_tooltip_app = typer.Typer(help="Page tooltip operations.", no_args_is_help=True)
visual_app = typer.Typer(help="Visual operations.", no_args_is_help=True)
visual_arrange_app = typer.Typer(help="Visual layout operations.", no_args_is_help=True)
visual_sort_app = typer.Typer(help="Visual sort operations.", no_args_is_help=True)
visual_format_app = typer.Typer(help="Visual conditional formatting operations.", no_args_is_help=True)
model_app = typer.Typer(help="Semantic model operations.", no_args_is_help=True)
filter_app = typer.Typer(help="Filter operations.", no_args_is_help=True)
theme_app = typer.Typer(help="Theme operations.", no_args_is_help=True)
style_app = typer.Typer(help="Style preset operations.", no_args_is_help=True)
bookmark_app = typer.Typer(help="Bookmark operations.", no_args_is_help=True)
interaction_app = typer.Typer(help="Visual interaction operations.", no_args_is_help=True)
report_app = typer.Typer(help="Report metadata operations.", no_args_is_help=True)
app.add_typer(report_app, name="report")
app.add_typer(page_app, name="page")
app.add_typer(visual_app, name="visual")
app.add_typer(model_app, name="model")
app.add_typer(filter_app, name="filter")
app.add_typer(theme_app, name="theme")
app.add_typer(style_app, name="style")
app.add_typer(bookmark_app, name="bookmark")
app.add_typer(interaction_app, name="interaction")
page_app.add_typer(page_drillthrough_app, name="drillthrough")
page_app.add_typer(page_tooltip_app, name="tooltip")
visual_app.add_typer(visual_sort_app, name="sort")
visual_app.add_typer(visual_format_app, name="format")
visual_app.add_typer(visual_arrange_app, name="arrange")

console = Console()

ProjectOpt = Annotated[
    Optional[Path],
    typer.Option("--project", "-p", help="Path to PBIP project (default: auto-detect from cwd)."),
]


def _get_project(project: Path | None) -> Project:
    try:
        return Project.find(project)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


def _parse_property_assignments(assignments: list[str]) -> list[tuple[str, str]]:
    """Parse canonical prop=value pairs."""
    pairs: list[tuple[str, str]] = []
    for arg in assignments:
        eq = arg.find("=")
        if eq == -1:
            raise ValueError(f"Invalid assignment '{arg}'. Use prop=value format.")
        pairs.append((arg[:eq], arg[eq + 1:]))
    return pairs


def _normalize_field_type(field_type: str) -> str:
    valid = {"auto", "column", "measure"}
    if field_type not in valid:
        raise ValueError(f"Invalid field type '{field_type}'. Use one of: auto, column, measure.")
    return field_type


def _resolve_field_type(
    proj: Project,
    field: str,
    field_type: str,
) -> tuple[str, str, str]:
    dot = field.find(".")
    if dot == -1:
        raise ValueError("Field must be Table.Field format.")
    entity, prop = field[:dot], field[dot + 1:]
    mode = _normalize_field_type(field_type)
    if mode != "auto":
        return entity, prop, mode
    try:
        from pbi.model import SemanticModel

        model = SemanticModel.load(proj.root)
        entity, prop, mode = model.resolve_field(field)
    except (FileNotFoundError, ValueError):
        mode = "column"
    return entity, prop, mode


def _resolve_filter_scope(
    proj: Project,
    scope: str,
    page: str | None,
    visual: str | None,
):
    from pbi.filters import load_level_data

    valid_scopes = {"report", "page", "visual"}
    if scope not in valid_scopes:
        console.print(
            f"[red]Error:[/red] Invalid scope '{scope}'. "
            f"Use one of: {', '.join(sorted(valid_scopes))}."
        )
        raise typer.Exit(1)

    if scope == "report":
        page_ref = None
        visual_ref = None
    elif scope == "page":
        if page is None:
            console.print("[red]Error:[/red] Page scope requires <page>.")
            raise typer.Exit(1)
        if visual is not None:
            console.print("[red]Error:[/red] Page scope does not accept a visual target.")
            raise typer.Exit(1)
        page_ref = page
        visual_ref = None
    else:
        if page is None or visual is None:
            console.print("[red]Error:[/red] Visual scope requires <page> and <visual>.")
            raise typer.Exit(1)
        page_ref = page
        visual_ref = visual

    try:
        return load_level_data(proj, page_ref, visual_ref)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


# ── Project info ───────────────────────────────────────────────────

@app.command()
def map(
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output file (default: stdout). Use 'pbi-map.yaml' for a project index.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Generate a human-readable YAML map of the entire project."""
    from pbi.mapper import generate_map
    proj = _get_project(project)
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

    proj = _get_project(project)

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

    proj = _get_project(project)
    try:
        props = dict(_parse_property_assignments(assignments))
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
    project: ProjectOpt = None,
) -> None:
    """List saved style presets."""
    from pbi.styles import list_styles

    proj = _get_project(project)
    styles = list_styles(proj)

    if not styles:
        console.print("[yellow]No styles saved. Use `pbi style create` to create one.[/yellow]")
        raise typer.Exit(0)

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


@style_app.command("show")
def style_show(
    style_name: Annotated[str, typer.Argument(help="Style preset name.")],
    project: ProjectOpt = None,
) -> None:
    """Show one saved style preset as YAML."""
    from pbi.styles import dump_style, get_style

    proj = _get_project(project)
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

    proj = _get_project(project)
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
    proj = _get_project(project)
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
            page_node.add(
                f'{v.visual_type} [dim]@ {pos.get("x", 0)},{pos.get("y", 0)} '
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

# ── Page commands ──────────────────────────────────────────────────

@report_app.command("get")
def report_get(
    props: Annotated[list[str] | None, typer.Argument(help="Property or properties to read (omit for overview).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show report metadata or one or more report properties."""
    proj = _get_project(project)
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
    from pbi.project import _write_json

    proj = _get_project(project)
    data = proj.get_report_meta()
    data.setdefault("$schema", REPORT_SCHEMA)
    data.setdefault("layoutOptimization", "None")
    data.setdefault("themeCollection", {})

    try:
        pairs = _parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for prop, value in pairs:
        old = get_property(data, prop, REPORT_PROPERTIES)
        try:
            set_property(data, prop, value, REPORT_PROPERTIES)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {prop}: {e}")
            raise typer.Exit(1)
        new = get_property(data, prop, REPORT_PROPERTIES)
        console.print(f"[dim]{prop}:[/dim] {old} [dim]→[/dim] {new}")

    _write_json(proj.definition_folder / "report.json", data)


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

@page_app.command("list")
def page_list(project: ProjectOpt = None) -> None:
    """List all pages."""
    proj = _get_project(project)
    pages = proj.get_pages()
    meta = proj.get_pages_meta()

    table = Table(box=box.SIMPLE)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan")
    table.add_column("Size", style="dim")
    table.add_column("Display", style="dim")
    table.add_column("Visibility")
    table.add_column("Visuals", justify="right")

    for i, page in enumerate(pages, 1):
        visuals = proj.get_visuals(page)
        active = meta.get("activePageName") == page.name
        vis_text = "AlwaysVisible" if page.visibility == "AlwaysVisible" else "[yellow]Hidden[/yellow]"
        name = f"[bold]{page.display_name}[/bold]" if active else page.display_name
        table.add_row(
            str(i),
            name,
            f"{page.width}x{page.height}",
            page.display_option,
            vis_text,
            str(len(visuals)),
        )

    console.print(table)


@page_app.command("get")
def page_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    props: Annotated[list[str] | None, typer.Argument(help="Property or properties to read (omit for overview).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show page details or one or more specific properties."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if props:
        if len(props) == 1:
            value = get_property(pg.data, props[0], PAGE_PROPERTIES)
            console.print(value)
            return

        table = Table(title=pg.display_name, box=box.SIMPLE)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        for prop in props:
            value = get_property(pg.data, prop, PAGE_PROPERTIES)
            table.add_row(prop, "" if value is None else str(value))
        console.print(table)
        return

    table = Table(title=pg.display_name, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Folder", pg.name)
    table.add_row("Display Name", pg.display_name)
    table.add_row("Width", str(pg.width))
    table.add_row("Height", str(pg.height))
    table.add_row("Display Option", pg.display_option)
    table.add_row("Visibility", pg.visibility)

    if pg.data.get("type"):
        table.add_row("Type", pg.data["type"])

    console.print(table)


@page_app.command("set")
def page_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    project: ProjectOpt = None,
) -> None:
    """Set page properties."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        pairs = _parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for prop, value in pairs:
        old = get_property(pg.data, prop, PAGE_PROPERTIES)
        try:
            set_property(pg.data, prop, value, PAGE_PROPERTIES)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {prop}: {e}")
            raise typer.Exit(1)
        new = get_property(pg.data, prop, PAGE_PROPERTIES)
        console.print(f"[dim]{prop}:[/dim] {old} [dim]→[/dim] {new}")

    pg.save()


@page_app.command("properties")
def page_props() -> None:
    """List available page properties."""
    table = Table(title="Page Properties", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for name, vtype, desc, _group, _enums in list_properties(PAGE_PROPERTIES):
        table.add_row(name, vtype, desc)

    console.print(table)


@page_app.command("create")
def page_create(
    name: Annotated[str, typer.Argument(help="Display name for the new page.")],
    width: Annotated[int, typer.Option(help="Page width in pixels.")] = 1280,
    height: Annotated[int, typer.Option(help="Page height in pixels.")] = 720,
    display_option: Annotated[str, typer.Option("--display-option", help="FitToPage, FitToWidth, or ActualSize.")] = "FitToPage",
    project: ProjectOpt = None,
) -> None:
    """Create a new page."""
    proj = _get_project(project)
    pg = proj.create_page(name, width=width, height=height, display_option=display_option)
    console.print(f'Created page "[cyan]{pg.display_name}[/cyan]" ({pg.name})')


@page_app.command("copy")
def page_copy(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    name: Annotated[str, typer.Argument(help="Display name for the copy.")],
    project: ProjectOpt = None,
) -> None:
    """Copy/duplicate a page with all its visuals."""
    proj = _get_project(project)
    try:
        source = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    new_page = proj.copy_page(source, name)
    visuals = proj.get_visuals(new_page)
    console.print(
        f'Copied "[cyan]{source.display_name}[/cyan]" → '
        f'"[cyan]{new_page.display_name}[/cyan]" ({len(visuals)} visuals)'
    )


@page_app.command("delete")
def page_delete(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a page and all its visuals."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    if not force:
        confirm = typer.confirm(
            f'Delete page "{pg.display_name}" with {len(visuals)} visual(s)?'
        )
        if not confirm:
            raise typer.Abort()

    proj.delete_page(pg)
    console.print(f'Deleted page "[cyan]{pg.display_name}[/cyan]"')


@page_app.command("export")
def page_export(
    page: Annotated[Optional[str], typer.Argument(help="Page name (omit to export all pages).")] = None,
    output: Annotated[Optional[Path], typer.Option("-o", "--output", help="Output file (default: stdout).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Export page(s) as detailed YAML for use with 'pbi apply'.

    The output includes all properties, bindings, sort definitions, and filters
    in a format that can be directly fed back to 'pbi apply' for round-trip editing.
    """
    from pbi.export import export_yaml

    proj = _get_project(project)

    if page:
        try:
            proj.find_page(page)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    content = export_yaml(proj, page_filter=page)

    if output:
        out_path = output if output.is_absolute() else proj.root / output
        out_path.write_text(content, encoding="utf-8")
        console.print(f"Exported to [cyan]{out_path}[/cyan]")
    else:
        typer.echo(content, nl=False)


@page_app.command("save-template")
def page_save_template(
    page: Annotated[str, typer.Argument(help="Page to save as template.")],
    template_name: Annotated[str, typer.Argument(help="Name for the template.")],
    project: ProjectOpt = None,
) -> None:
    """Save a page's layout and formatting as a reusable template."""
    from pbi.templates import save_template

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    try:
        path = save_template(proj, pg, template_name, visuals)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    console.print(
        f'Saved template "[cyan]{template_name}[/cyan]" '
        f"({len(visuals)} visuals) → {path}"
    )


@page_app.command("apply-template")
def page_apply_template(
    page: Annotated[str, typer.Argument(help="Target page to apply template to.")],
    template_name: Annotated[str, typer.Argument(help="Template name to apply.")],
    project: ProjectOpt = None,
) -> None:
    """Apply a saved template to a page (creates visuals with matching layout/style)."""
    from pbi.templates import apply_template

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        created = apply_template(proj, pg, template_name)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(
        f'Applied template "[cyan]{template_name}[/cyan]" → '
        f'"{pg.display_name}" ({len(created)} visuals created)'
    )


@page_app.command("templates")
def page_templates(
    project: ProjectOpt = None,
) -> None:
    """List available page templates."""
    from pbi.templates import list_templates

    proj = _get_project(project)
    templates = list_templates(proj)

    if not templates:
        console.print("[yellow]No templates saved. Use `pbi page save-template` to create one.[/yellow]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Visuals")
    table.add_column("Page Size")
    table.add_column("File", style="dim")
    for t in templates:
        table.add_row(t["name"], str(t["visuals"]), t["size"], t["file"])
    console.print(table)


@page_app.command("delete-template")
def page_delete_template(
    template_name: Annotated[str, typer.Argument(help="Template name to delete.")],
    project: ProjectOpt = None,
) -> None:
    """Delete a saved page template."""
    from pbi.templates import delete_template

    proj = _get_project(project)
    try:
        deleted = delete_template(proj, template_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    if deleted:
        console.print(f'Deleted template "[cyan]{template_name}[/cyan]"')
    else:
        console.print(f'[yellow]Template "{template_name}" not found.[/yellow]')


@page_drillthrough_app.command("set")
def page_set_drillthrough(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    fields: Annotated[list[str], typer.Argument(help="Drillthrough fields as Table.Field (e.g. Product.Category).")],
    cross_report: Annotated[bool, typer.Option("--cross-report", help="Enable cross-report drillthrough.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Configure a page as a drillthrough target.

    The page becomes hidden and accepts filter context from source visuals
    through the specified fields. Users right-click a data point to drill through.
    """
    from pbi.drillthrough import configure_drillthrough

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    parsed: list[tuple[str, str, str]] = []
    for field in fields:
        dot = field.find(".")
        if dot == -1:
            console.print(f"[red]Error:[/red] Field '{field}' must be Table.Field format.")
            raise typer.Exit(1)
        entity, prop = field[:dot], field[dot + 1:]
        field_type = "column"
        try:
            from pbi.model import SemanticModel
            model = SemanticModel.load(proj.root)
            entity, prop, field_type = model.resolve_field(field)
        except (FileNotFoundError, ValueError):
            pass
        parsed.append((entity, prop, field_type))

    configure_drillthrough(pg, parsed, cross_report=cross_report)
    pg.save()

    field_list = ", ".join(fields)
    cross = " (cross-report)" if cross_report else ""
    console.print(
        f'Configured "[cyan]{pg.display_name}[/cyan]" as drillthrough page{cross}: {field_list}'
    )


@page_drillthrough_app.command("clear")
def page_clear_drillthrough(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Remove drillthrough configuration from a page."""
    from pbi.drillthrough import clear_drillthrough

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if clear_drillthrough(pg):
        pg.save()
        console.print(f'Removed drillthrough from "[cyan]{pg.display_name}[/cyan]"')
    else:
        console.print("[yellow]Page is not configured as drillthrough.[/yellow]")


@page_tooltip_app.command("set")
def page_set_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    fields: Annotated[Optional[list[str]], typer.Argument(help="Auto-match fields as Table.Field (optional).")] = None,
    width: Annotated[int, typer.Option("-W", "--width", help="Tooltip page width.")] = 320,
    height: Annotated[int, typer.Option("-H", "--height", help="Tooltip page height.")] = 240,
    project: ProjectOpt = None,
) -> None:
    """Configure a page as a custom tooltip page.

    Tooltip pages are shown on hover over data points. Default size is 320x240.
    Optionally specify fields for automatic tooltip matching.
    Link visuals to this tooltip with: pbi visual set <page> <visual> tooltip.type=ReportPage tooltip.section=<page-id>
    """
    from pbi.drillthrough import configure_tooltip_page

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    parsed: list[tuple[str, str, str]] = []
    if fields:
        for field in fields:
            dot = field.find(".")
            if dot == -1:
                console.print(f"[red]Error:[/red] Field '{field}' must be Table.Field format.")
                raise typer.Exit(1)
            entity, prop = field[:dot], field[dot + 1:]
            field_type = "column"
            try:
                from pbi.model import SemanticModel
                model = SemanticModel.load(proj.root)
                entity, prop, field_type = model.resolve_field(field)
            except (FileNotFoundError, ValueError):
                pass
            parsed.append((entity, prop, field_type))

    configure_tooltip_page(pg, parsed or None, width=width, height=height)
    pg.save()

    console.print(
        f'Configured "[cyan]{pg.display_name}[/cyan]" as tooltip page ({width}x{height})'
    )


@page_tooltip_app.command("clear")
def page_clear_tooltip(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Remove tooltip configuration from a page."""
    from pbi.drillthrough import clear_tooltip_page

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if clear_tooltip_page(pg):
        pg.save()
        console.print(f'Removed tooltip config from "[cyan]{pg.display_name}[/cyan]"')
    else:
        console.print("[yellow]Page is not configured as a tooltip page.[/yellow]")


# ── Visual commands ────────────────────────────────────────────────

@visual_app.command("list")
def visual_list(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """List all visuals on a page."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)

    table = Table(title=f"Visuals on \"{pg.display_name}\"", box=box.SIMPLE)
    table.add_column("#", style="dim", width=3)
    table.add_column("Name", style="cyan", max_width=24)
    table.add_column("Type")
    table.add_column("Position", style="dim")
    table.add_column("Size", style="dim")
    table.add_column("Z", style="dim", justify="right")

    for i, v in enumerate(visuals, 1):
        pos = v.position
        hidden = " [yellow](hidden)[/yellow]" if v.data.get("isHidden") else ""
        table.add_row(
            str(i),
            f"{v.name[:24]}{hidden}",
            v.visual_type,
            f'{pos.get("x", 0)}, {pos.get("y", 0)}',
            f'{pos.get("width", 0)}x{pos.get("height", 0)}',
            str(pos.get("z", 0)),
        )

    console.print(table)


@visual_app.command("get")
def visual_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    props: Annotated[list[str] | None, typer.Argument(help="Property or properties to read (omit for overview).")] = None,
    all_props: Annotated[bool, typer.Option("--all-props", help="Show all explicit registered and object properties.")] = False,
    defaults: Annotated[bool, typer.Option("--defaults", help="Show effective values using explicit values plus known defaults.")] = False,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Show raw JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show visual details or one or more specific properties."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw and props:
        console.print("[red]Error:[/red] --raw cannot be combined with explicit properties.")
        raise typer.Exit(1)
    if raw and all_props:
        console.print("[red]Error:[/red] --raw cannot be combined with --all-props.")
        raise typer.Exit(1)
    if raw and defaults:
        console.print("[red]Error:[/red] --raw cannot be combined with --defaults.")
        raise typer.Exit(1)
    if props and all_props:
        console.print("[red]Error:[/red] Explicit properties cannot be combined with --all-props.")
        raise typer.Exit(1)

    if raw:
        import json
        console.print_json(json.dumps(vis.data, indent=2))
        return

    if all_props or defaults:
        rows = _collect_effective_visual_property_rows(
            vis.data,
            include_core=all_props,
            include_defaults=defaults,
        )
        table = Table(title=f"{vis.name}", box=box.SIMPLE)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        if defaults:
            table.add_column("Source", style="dim")
        for prop_name, value, source in rows:
            if defaults:
                table.add_row(prop_name, value, source)
            else:
                table.add_row(prop_name, value)
        console.print(table)
        return

    if props:
        if len(props) == 1 and not defaults:
            value = get_property(vis.data, props[0], VISUAL_PROPERTIES)
            console.print(value)
            return

        table = Table(title=f"{vis.name}", box=box.SIMPLE)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        if defaults:
            table.add_column("Source", style="dim")
        for prop in props:
            value, source = _resolve_visual_property_value(vis.data, prop, include_defaults=defaults)
            if defaults:
                table.add_row(prop, "" if value is None else str(value), source)
            else:
                table.add_row(prop, "" if value is None else str(value))
        console.print(table)
        return

    # Overview
    pos = vis.position
    table = Table(title=f"{vis.visual_type}", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Name", vis.name)
    table.add_row("Folder", vis.folder.name)
    table.add_row("Type", vis.visual_type)
    table.add_row("Position", f'{pos.get("x", 0)}, {pos.get("y", 0)}')
    table.add_row("Size", f'{pos.get("width", 0)} x {pos.get("height", 0)}')
    table.add_row("Z-Order", str(pos.get("z", 0)))
    table.add_row("Hidden", str(vis.data.get("isHidden", False)))

    # Show container formatting if present
    object_rows = _collect_visual_property_rows(vis.data, include_core=False)
    if object_rows:
        table.add_section()
        for prop_name, value in object_rows:
            table.add_row(prop_name, value)

    # Show data bindings summary
    query = vis.data.get("visual", {}).get("query", {}).get("queryState", {})
    if query:
        table.add_section()
        for role, config in query.items():
            projections = config.get("projections", [])
            fields = []
            for p in projections:
                ref = p.get("queryRef", p.get("nativeQueryRef", "?"))
                fields.append(ref)
            table.add_row(f"[dim]Data:[/dim] {role}", ", ".join(fields))

    # Show sort definition
    sorts = proj.get_sort(vis)
    if sorts:
        table.add_section()
        for entity, sort_prop, ftype, direction in sorts:
            kind = " (measure)" if ftype == "measure" else ""
            table.add_row("[dim]Sort:[/dim]", f"{entity}.{sort_prop}{kind} {direction}")

    console.print(table)


def _collect_visual_property_rows(
    visual_data: dict,
    *,
    include_core: bool = True,
) -> list[tuple[str, str]]:
    """Collect explicit visual properties for inspection views."""
    rows: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    if include_core:
        for prop_name, prop_def in VISUAL_PROPERTIES.items():
            if not prop_def.json_path:
                continue
            value = get_property(visual_data, prop_name, VISUAL_PROPERTIES)
            if value is None:
                continue
            key = (prop_name, str(value))
            if key in seen:
                continue
            seen.add(key)
            rows.append((prop_name, str(value)))

    from pbi.properties import decode_pbi_value

    for section in ("visualContainerObjects", "objects"):
        section_data = visual_data.get("visual", {}).get(section, {})
        if not isinstance(section_data, dict):
            continue
        for obj_name, entries in section_data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                selector = entry.get("selector", {})
                selector_name = selector.get("metadata") or selector.get("id")
                for prop_name, raw_value in entry.get("properties", {}).items():
                    decoded = decode_pbi_value(raw_value)
                    canonical = canonical_object_property_name(
                        obj_name,
                        prop_name,
                        VISUAL_PROPERTIES,
                        objects_path=section,
                        selector=selector.get("id"),
                    )
                    label = canonical
                    if selector_name:
                        label = f"{label} [{selector_name}]"
                    key = (label, str(decoded))
                    if key in seen:
                        continue
                    seen.add(key)
                    rows.append((label, str(decoded)))

    return rows


def _resolve_visual_property_value(
    visual_data: dict,
    prop_name: str,
    *,
    include_defaults: bool = False,
) -> tuple[object | None, str]:
    """Resolve an explicit or known-default value for a single visual property."""
    value = get_property(visual_data, prop_name, VISUAL_PROPERTIES)
    if value is not None:
        return value, "explicit"
    if include_defaults:
        visual_type = visual_data.get("visual", {}).get("visualType")
        default = get_known_default(prop_name, VISUAL_PROPERTIES, visual_type=visual_type)
        if default is not None:
            return default, "default"
    return None, ""


def _collect_effective_visual_property_rows(
    visual_data: dict,
    *,
    include_core: bool,
    include_defaults: bool,
) -> list[tuple[str, str, str]]:
    """Collect effective visual properties with their source."""
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    visual_type = visual_data.get("visual", {}).get("visualType")

    explicit_rows = _collect_visual_property_rows(visual_data, include_core=include_core)
    for prop_name, value in explicit_rows:
        rows.append((prop_name, value, "explicit"))
        seen.add(prop_name)

    if not include_defaults:
        return rows

    for prop_name, prop_def in sorted(VISUAL_PROPERTIES.items()):
        group = "core" if prop_def.json_path else "container"
        if not include_core and group == "core":
            continue
        if prop_def.visual_types and visual_type not in prop_def.visual_types:
            continue
        if prop_name in seen:
            continue
        default = get_known_default(prop_name, VISUAL_PROPERTIES, visual_type=visual_type)
        if default is None:
            continue
        rows.append((prop_name, str(default), "default"))

    return rows


def _collect_visual_property_map(
    visual_data: dict,
    *,
    include_core: bool = True,
) -> dict[str, str]:
    """Collect explicit visual properties as a label->value mapping."""
    return dict(_collect_visual_property_rows(visual_data, include_core=include_core))


@visual_app.command("get-page")
def visual_get_page(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Only include visuals of this type.")] = None,
    all_props: Annotated[bool, typer.Option("--all-props", help="Include core properties like position and hidden state.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show explicit properties for every visual on a page."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    if visual_type:
        visuals = [v for v in visuals if v.visual_type == visual_type]

    table = Table(title=f'Visual Properties on "{pg.display_name}"', box=box.SIMPLE)
    table.add_column("Visual", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    row_count = 0
    for vis in visuals:
        for prop_name, value in _collect_visual_property_rows(vis.data, include_core=all_props):
            table.add_row(vis.name, vis.visual_type, prop_name, value)
            row_count += 1

    if row_count == 0:
        console.print("[dim]No explicit visual properties matched the current filters.[/dim]")
        return

    console.print(table)


@visual_app.command("diff")
def visual_diff(
    left_page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    left_visual: Annotated[str, typer.Argument(help="Source visual name, type, or index.")],
    right_page: Annotated[str, typer.Argument(help="Comparison page name, display name, or index.")],
    right_visual: Annotated[str, typer.Argument(help="Comparison visual name, type, or index.")],
    all_props: Annotated[bool, typer.Option("--all-props", help="Include core properties like position and hidden state.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Compare canonical exported visual specs between two visuals."""
    from pbi.export import export_visual_spec

    proj = _get_project(project)
    try:
        left_pg = proj.find_page(left_page)
        left_vis = proj.find_visual(left_pg, left_visual)
        right_pg = proj.find_page(right_page)
        right_vis = proj.find_visual(right_pg, right_visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    left_props = _flatten_visual_diff_spec(
        export_visual_spec(proj, left_vis),
        include_core=all_props,
    )
    right_props = _flatten_visual_diff_spec(
        export_visual_spec(proj, right_vis),
        include_core=all_props,
    )

    ordered_keys: list[str] = []
    for prop_name in [*left_props.keys(), *right_props.keys()]:
        if prop_name not in ordered_keys:
            ordered_keys.append(prop_name)

    rows = []
    for prop_name in ordered_keys:
        left_value = left_props.get(prop_name, "")
        right_value = right_props.get(prop_name, "")
        if left_value == right_value:
            continue
        rows.append((prop_name, left_value, right_value))

    if not rows:
        console.print("[dim]No property differences found.[/dim]")
        return

    table = Table(
        title=f"{left_vis.name} vs {right_vis.name}",
        box=box.SIMPLE,
    )
    table.add_column("Property", style="cyan")
    table.add_column(f"{left_pg.display_name}/{left_vis.name}")
    table.add_column(f"{right_pg.display_name}/{right_vis.name}")
    for prop_name, left_value, right_value in rows:
        table.add_row(prop_name, left_value, right_value)
    console.print(table)


def _flatten_visual_diff_spec(
    visual_spec: dict,
    *,
    include_core: bool,
) -> dict[str, str]:
    """Flatten a canonical exported visual spec into path/value rows for diffing."""
    import copy

    filtered = copy.deepcopy(visual_spec)
    filtered.pop("id", None)
    filtered.pop("name", None)
    if not include_core:
        for key in ("position", "size", "isHidden"):
            filtered.pop(key, None)
    else:
        position = filtered.get("position")
        if isinstance(position, str):
            parts = [part.strip() for part in position.split(",", 1)]
            if len(parts) == 2:
                filtered["position"] = {"x": parts[0], "y": parts[1]}
        size = filtered.get("size")
        if isinstance(size, str):
            parts = [part.strip() for part in size.lower().split("x", 1)]
            if len(parts) == 2:
                filtered["size"] = {"width": parts[0], "height": parts[1]}

    rows: dict[str, str] = {}
    _flatten_diff_value(filtered, rows)
    return rows


def _flatten_diff_value(
    value: object,
    rows: dict[str, str],
    *,
    prefix: str = "",
) -> None:
    """Recursively flatten a nested exported spec into dotted paths."""
    if isinstance(value, dict):
        if not value and prefix:
            rows[prefix] = "{}"
            return
        for key, child in value.items():
            child_prefix = key if not prefix else f"{prefix}.{key}"
            _flatten_diff_value(child, rows, prefix=child_prefix)
        return

    if isinstance(value, list):
        if not value:
            rows[prefix] = "[]"
            return
        for index, child in enumerate(value):
            child_prefix = f"{prefix}[{index}]"
            _flatten_diff_value(child, rows, prefix=child_prefix)
        return

    rows[prefix] = _stringify_diff_value(value)


def _stringify_diff_value(value: object) -> str:
    """Stringify scalar values for visual diff output."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _prepare_visual_property_updates(
    data: dict,
    pairs: list[tuple[str, str]],
    *,
    measure_ref: str | None = None,
) -> tuple[dict, list[tuple[str, object, object]]]:
    """Apply a property batch to a copy of the visual for validation."""
    import copy

    updated = copy.deepcopy(data)
    changes: list[tuple[str, object, object]] = []
    for prop, value in pairs:
        old = get_property(updated, prop, VISUAL_PROPERTIES, measure_ref=measure_ref)
        try:
            set_property(updated, prop, value, VISUAL_PROPERTIES, measure_ref=measure_ref)
        except ValueError as e:
            raise ValueError(f"{prop}: {e}") from e
        new = get_property(updated, prop, VISUAL_PROPERTIES, measure_ref=measure_ref)
        changes.append((prop, old, new))
    return updated, changes


@visual_app.command("set")
def visual_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    project: ProjectOpt = None,
    for_measure: Annotated[str | None, typer.Option("--for-measure", help="Target a specific measure queryRef for per-measure formatting.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show what would change without saving.")] = False,
) -> None:
    """Set visual properties."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        pairs = _parse_property_assignments(assignments)
        updated, changes = _prepare_visual_property_updates(vis.data, pairs, measure_ref=for_measure)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for prop, old, new in changes:
        label = f"{prop} ({for_measure})" if for_measure else prop
        if dry_run:
            console.print(f"Would set {label}: {old} [dim]→[/dim] {new}")
        else:
            console.print(f"[dim]{label}:[/dim] {old} [dim]→[/dim] {new}")

    if dry_run:
        return

    vis.data = updated
    vis.save()


@visual_app.command("set-all")
def visual_set_all(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value ...")],
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Only apply to visuals of this type (e.g. slicer, cardVisual, tableEx).")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Validate and show what would change without saving.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set properties on multiple visuals at once.

    Applies the same property assignments to all visuals on a page, or only
    to visuals of a specific type with --visual-type.
    """
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    if visual_type:
        visuals = [v for v in visuals if v.visual_type == visual_type]
        if not visuals:
            console.print(f'[yellow]No visuals of type "{visual_type}" on page "{pg.display_name}".[/yellow]')
            raise typer.Exit(0)

    # Skip group containers
    visuals = [v for v in visuals if "visualGroup" not in v.data]

    try:
        pairs = _parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    prepared: list[tuple[object, dict, list[tuple[str, object, object]]]] = []
    for vis in visuals:
        try:
            updated, changes = _prepare_visual_property_updates(vis.data, pairs)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {vis.name}: {e}")
            raise typer.Exit(1)
        prepared.append((vis, updated, changes))

    if dry_run:
        totals: dict[str, int] = {}
        for _vis, _updated, changes in prepared:
            for prop, old, new in changes:
                if old != new:
                    totals[prop] = totals.get(prop, 0) + 1
        if not totals:
            console.print("[dim]No changes would be applied.[/dim]")
            return
        for prop, count in totals.items():
            console.print(f"Would set {prop} on [cyan]{count}[/cyan] visual(s)")
        return

    count = 0
    for vis, updated, _changes in prepared:
        vis.data = updated
        vis.save()
        count += 1

    scope = f'visual-type={visual_type}' if visual_type else "all"
    props_str = " ".join(f"{p}={v}" for p, v in pairs)
    console.print(f'Applied {props_str} to [cyan]{count}[/cyan] visuals ({scope})')


@visual_app.command("move")
def visual_move(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    x: Annotated[int, typer.Option("--x", help="X position.")],
    y: Annotated[int, typer.Option("--y", help="Y position.")],
    project: ProjectOpt = None,
) -> None:
    """Move a visual to a new position."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old_x = vis.position.get("x", 0)
    old_y = vis.position.get("y", 0)
    vis.data.setdefault("position", {})["x"] = x
    vis.data["position"]["y"] = y
    vis.save()
    console.print(f"[dim]Moved:[/dim] {old_x},{old_y} [dim]→[/dim] {x},{y}")


@visual_app.command("resize")
def visual_resize(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    width: Annotated[int, typer.Option("-W", "--width", help="Width.")],
    height: Annotated[int, typer.Option("-H", "--height", help="Height.")],
    project: ProjectOpt = None,
) -> None:
    """Resize a visual."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old_w = vis.position.get("width", 0)
    old_h = vis.position.get("height", 0)
    vis.data.setdefault("position", {})["width"] = width
    vis.data["position"]["height"] = height
    vis.save()
    console.print(f"[dim]Resized:[/dim] {old_w}x{old_h} [dim]→[/dim] {width}x{height}")


@visual_app.command("create")
def visual_create(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual_type: Annotated[str, typer.Argument(help="Visual type (e.g. clusteredColumnChart, card, table, slicer).")],
    x: Annotated[int, typer.Option(help="X position.")] = 0,
    y: Annotated[int, typer.Option(help="Y position.")] = 0,
    width: Annotated[int, typer.Option("-W", "--width", help="Width.")] = 300,
    height: Annotated[int, typer.Option("-H", "--height", help="Height.")] = 200,
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Friendly name for the visual.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Create a new visual on a page."""
    from pbi.roles import is_known_visual_type, normalize_visual_type

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    canonical_visual_type = normalize_visual_type(visual_type)
    if visual_type != canonical_visual_type:
        console.print(
            f'[dim]Using canonical visual type [cyan]{canonical_visual_type}[/cyan] '
            f'for alias "{visual_type}".[/dim]'
        )
    elif not is_known_visual_type(visual_type):
        console.print(
            f'[yellow]Warning:[/yellow] "{visual_type}" is not in the CLI visual catalog. '
            "Creating a raw visual container."
        )

    vis = proj.create_visual(
        pg,
        canonical_visual_type,
        x=x,
        y=y,
        width=width,
        height=height,
    )
    if name:
        vis.data["name"] = name
        vis.save()
    display = name or vis.name
    console.print(
        f'Created [cyan]{canonical_visual_type}[/cyan] "{display}" on "{pg.display_name}" '
        f"@ {x},{y} {width}x{height}"
    )


@visual_arrange_app.command("row")
def visual_arrange_row(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to arrange left-to-right.")],
    x: Annotated[int, typer.Option("--x", help="Starting X position.")] = 0,
    y: Annotated[int, typer.Option("--y", help="Shared Y position.")] = 0,
    gap: Annotated[int, typer.Option("--gap", help="Horizontal gap between visuals.")] = 16,
    project: ProjectOpt = None,
) -> None:
    """Arrange visuals in a horizontal row using their current widths."""
    if len(visuals) < 2:
        console.print("[red]Error:[/red] Provide at least two visuals to arrange.")
        raise typer.Exit(1)

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        ordered_visuals = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    cursor_x = x
    for vis in ordered_visuals:
        width = int(vis.position.get("width", 0))
        vis.data.setdefault("position", {})["x"] = cursor_x
        vis.data["position"]["y"] = y
        vis.save()
        cursor_x += width + gap

    console.print(
        f'Arranged [cyan]{len(ordered_visuals)}[/cyan] visuals in a row on "{pg.display_name}" '
        f"starting at {x},{y} with gap {gap}"
    )


@visual_arrange_app.command("grid")
def visual_arrange_grid(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to arrange in reading order.")],
    columns: Annotated[int, typer.Option("--columns", help="Number of visuals per row.")] = 2,
    x: Annotated[int, typer.Option("--x", help="Starting X position.")] = 0,
    y: Annotated[int, typer.Option("--y", help="Starting Y position.")] = 0,
    column_gap: Annotated[int, typer.Option("--column-gap", help="Horizontal gap between visuals.")] = 16,
    row_gap: Annotated[int, typer.Option("--row-gap", help="Vertical gap between rows.")] = 16,
    project: ProjectOpt = None,
) -> None:
    """Arrange visuals in a wrapped grid using their current sizes."""
    if len(visuals) < 2:
        console.print("[red]Error:[/red] Provide at least two visuals to arrange.")
        raise typer.Exit(1)
    if columns < 1:
        console.print("[red]Error:[/red] --columns must be at least 1.")
        raise typer.Exit(1)

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        ordered_visuals = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    cursor_x = x
    cursor_y = y
    row_height = 0

    for index, vis in enumerate(ordered_visuals):
        width = int(vis.position.get("width", 0))
        height = int(vis.position.get("height", 0))
        vis.data.setdefault("position", {})["x"] = cursor_x
        vis.data["position"]["y"] = cursor_y
        vis.save()

        row_height = max(row_height, height)
        is_last_in_row = (index + 1) % columns == 0
        if is_last_in_row:
            cursor_x = x
            cursor_y += row_height + row_gap
            row_height = 0
        else:
            cursor_x += width + column_gap

    console.print(
        f'Arranged [cyan]{len(ordered_visuals)}[/cyan] visuals in a [cyan]{columns}[/cyan]-column grid '
        f'on "{pg.display_name}" starting at {x},{y}'
    )


@visual_arrange_app.command("column")
def visual_arrange_column(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to arrange top-to-bottom.")],
    x: Annotated[int, typer.Option("--x", help="Shared X position.")] = 0,
    y: Annotated[int, typer.Option("--y", help="Starting Y position.")] = 0,
    gap: Annotated[int, typer.Option("--gap", help="Vertical gap between visuals.")] = 16,
    project: ProjectOpt = None,
) -> None:
    """Arrange visuals in a vertical column using their current heights."""
    if len(visuals) < 2:
        console.print("[red]Error:[/red] Provide at least two visuals to arrange.")
        raise typer.Exit(1)

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        ordered_visuals = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    cursor_y = y
    for vis in ordered_visuals:
        height = int(vis.position.get("height", 0))
        vis.data.setdefault("position", {})["x"] = x
        vis.data["position"]["y"] = cursor_y
        vis.save()
        cursor_y += height + gap

    console.print(
        f'Arranged [cyan]{len(ordered_visuals)}[/cyan] visuals in a column on "{pg.display_name}" '
        f"starting at {x},{y} with gap {gap}"
    )


@visual_app.command("copy")
def visual_copy(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Source visual name, type, or index.")],
    to_page: Annotated[Optional[str], typer.Option("--to-page", help="Target page (default: same page).")] = None,
    name: Annotated[Optional[str], typer.Option("--name", help="Name for the copy.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Copy/duplicate a visual, optionally to a different page."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
        target = proj.find_page(to_page) if to_page else pg
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    new_vis = proj.copy_visual(vis, target, new_name=name)
    dest = f' to "{target.display_name}"' if to_page else ""
    console.print(
        f'Copied [cyan]{vis.visual_type}[/cyan] "{vis.name}"{dest} → "{new_vis.name}"'
    )


@visual_app.command("paste-style")
def visual_paste_style(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    source: Annotated[str, typer.Argument(help="Source visual (copy style FROM).")],
    target: Annotated[Optional[str], typer.Argument(help="Target visual (paste style TO). Omit with --visual-type to style multiple visuals.")] = None,
    to_page: Annotated[Optional[str], typer.Option("--to-page", help="Target page if different from source.")] = None,
    visual_type: Annotated[str | None, typer.Option("--visual-type", help="Apply to all target-page visuals of this type.")] = None,
    scope: Annotated[str, typer.Option("--scope", help="Copy scope: all, container, or chart.")] = "all",
    project: ProjectOpt = None,
) -> None:
    """Copy formatting from one visual to another (format painter).

    Copies visual styling without affecting data bindings, filters, sort, or position.
    By default copies both container and chart formatting. Use --scope to limit it.
    """
    import copy

    if scope not in {"all", "container", "chart"}:
        console.print("[red]Error:[/red] --scope must be 'all', 'container', or 'chart'.")
        raise typer.Exit(1)
    if target and visual_type:
        console.print("[red]Error:[/red] Use either an explicit target or --visual-type, not both.")
        raise typer.Exit(1)
    if not target and not visual_type:
        console.print("[red]Error:[/red] Provide a target visual or use --visual-type for batch style copy.")
        raise typer.Exit(1)

    proj = _get_project(project)
    try:
        src_page = proj.find_page(page)
        src_vis = proj.find_visual(src_page, source)
        tgt_page = proj.find_page(to_page) if to_page else src_page
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        if target:
            target_visuals = [proj.find_visual(tgt_page, target)]
        else:
            target_visuals = [
                vis for vis in proj.get_visuals(tgt_page)
                if vis.visual_type == visual_type and "visualGroup" not in vis.data
            ]
            if tgt_page.folder == src_page.folder:
                target_visuals = [vis for vis in target_visuals if vis.folder != src_vis.folder]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not target_visuals:
        if visual_type:
            console.print(
                f'[yellow]No target visuals of type "{visual_type}" on page "{tgt_page.display_name}".[/yellow]'
            )
            raise typer.Exit(0)
        console.print(f'[yellow]Target visual "{target}" not found.[/yellow]')
        raise typer.Exit(0)

    copied = []
    src_visual = src_vis.data.get("visual", {})
    container = None
    objects = None

    # Container formatting (visualContainerObjects)
    if scope in {"all", "container"}:
        container = src_visual.get("visualContainerObjects")
        if container:
            copied.append("container")

    # Chart formatting (objects)
    if scope in {"all", "chart"}:
        objects = src_visual.get("objects")
        if objects:
            copied.append("chart")

    if not copied:
        console.print("[yellow]Source visual has no formatting to copy.[/yellow]")
        raise typer.Exit(0)

    for tgt_vis in target_visuals:
        if scope in {"all", "container"}:
            if container:
                tgt_vis.data.setdefault("visual", {})["visualContainerObjects"] = copy.deepcopy(container)
            else:
                tgt_vis.data.get("visual", {}).pop("visualContainerObjects", None)
        if scope in {"all", "chart"}:
            if objects:
                tgt_vis.data.setdefault("visual", {})["objects"] = copy.deepcopy(objects)
            else:
                tgt_vis.data.get("visual", {}).pop("objects", None)
        tgt_vis.save()

    scope = " + ".join(copied)
    if target:
        tgt_label = f'"{target_visuals[0].name}"'
        if to_page:
            tgt_label += f' on "{tgt_page.display_name}"'
        console.print(
            f'Copied [cyan]{scope}[/cyan] formatting: '
            f'"{src_vis.name}" → {tgt_label}'
        )
        return

    console.print(
        f'Copied [cyan]{scope}[/cyan] formatting from "{src_vis.name}" to '
        f'[cyan]{len(target_visuals)}[/cyan] "{visual_type}" visual(s) on "{tgt_page.display_name}"'
    )


@visual_app.command("rename")
def visual_rename(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    name: Annotated[str, typer.Argument(help="New friendly name for the visual.")],
    project: ProjectOpt = None,
) -> None:
    """Give a visual a friendly name for easier CLI reference."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old_name = vis.name
    vis.data["name"] = name
    vis.save()
    console.print(f'Renamed "{old_name}" → "[cyan]{name}[/cyan]"')


@visual_app.command("delete")
def visual_delete(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a visual."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f'Delete {vis.visual_type} "{vis.name}"?')
        if not confirm:
            raise typer.Abort()

    proj.delete_visual(vis)
    console.print(f'Deleted [cyan]{vis.visual_type}[/cyan] "{vis.name}"')


@visual_app.command("group")
def visual_group(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to group (at least 2).")],
    name: Annotated[Optional[str], typer.Option("--name", "-n", help="Group display name.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Group visuals together into a visual group."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis_list = [proj.find_visual(pg, v) for v in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        group = proj.create_group(pg, vis_list, display_name=name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    names = ", ".join(f'"{v.name}"' for v in vis_list)
    console.print(f'Grouped {names} → "[cyan]{group.name}[/cyan]"')


@visual_app.command("ungroup")
def visual_ungroup(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    group: Annotated[str, typer.Argument(help="Group name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Ungroup a visual group, freeing its children."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        grp = proj.find_visual(pg, group)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        children = proj.ungroup(pg, grp)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    names = ", ".join(f'"{c.name}"' for c in children)
    console.print(f'Ungrouped "[cyan]{grp.name}[/cyan]": freed {names or "no children"}')


@visual_app.command("bind")
def visual_bind(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    role: Annotated[str, typer.Argument(help="Data role (e.g. Category, Y, Values, Rows, Series).")],
    field: Annotated[str, typer.Argument(help="Field reference as Table.Field (e.g. Product.Category).")],
    field_type: Annotated[str, typer.Option("--field-type", help="Field type: auto, column, or measure.")] = "auto",
    project: ProjectOpt = None,
) -> None:
    """Bind a column (dimension) or measure (fact) to a visual's data role."""
    from pbi.roles import get_visual_type_info, normalize_visual_role

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        entity, prop, resolved_field_type = _resolve_field_type(proj, field, field_type)
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
    if info and info.status == "role-backed":
        supported_roles = {entry["name"] for entry in info.roles}
        if canonical_role not in supported_roles:
            console.print(
                f'[yellow]Warning:[/yellow] Role "{canonical_role}" is not modeled for '
                f'{vis.visual_type}. Supported roles: {", ".join(sorted(supported_roles))}'
            )

    proj.add_binding(vis, canonical_role, entity, prop, field_type=resolved_field_type)
    kind = "measure" if resolved_field_type == "measure" else "column"
    console.print(
        f'Bound [cyan]{entity}.{prop}[/cyan] ({kind}) → '
        f'{vis.visual_type} role "[bold]{canonical_role}[/bold]"'
    )


@visual_app.command("unbind")
def visual_unbind(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    role: Annotated[str, typer.Argument(help="Data role to unbind from.")],
    field: Annotated[Optional[str], typer.Argument(help="Specific field to remove (Table.Field). Omit to remove entire role.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Remove data bindings from a visual."""
    from pbi.roles import normalize_visual_role

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    canonical_role = normalize_visual_role(vis.visual_type, role)
    removed = proj.remove_binding(vis, canonical_role, field_ref=field)
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
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    bindings = proj.get_bindings(vis)
    if not bindings:
        console.print("[dim]No data bindings.[/dim]")
        return

    table = Table(title=f"Bindings on {vis.visual_type}", box=box.SIMPLE)
    table.add_column("Role", style="bold")
    table.add_column("Table", style="cyan")
    table.add_column("Field")
    table.add_column("Type", style="dim")

    for role, entity, prop, ftype in bindings:
        table.add_row(role, entity, prop, ftype)

    console.print(table)


@visual_app.command("types")
def visual_types(
    visual_type: Annotated[Optional[str], typer.Argument(help="Show roles for a specific visual type.")] = None,
) -> None:
    """List known visual types and their data roles."""
    from pbi.roles import get_visual_type_info, list_visual_type_info, normalize_visual_type

    if visual_type:
        normalized = normalize_visual_type(visual_type)
        all_types = list_visual_type_info()
        matches = [
            info for info in all_types
            if normalized.lower() in info.visual_type.lower()
        ]
        if not matches:
            console.print(f'[red]Unknown visual type "{visual_type}".[/red]')
            console.print("[dim]Use 'pbi visual types' to see all known types.[/dim]")
            raise typer.Exit(1)
        for info in matches:
            table = Table(title=info.visual_type, box=box.SIMPLE)
            table.add_column("Role", style="bold cyan")
            table.add_column("Description")
            table.add_column("Multi", style="dim", justify="center")
            for role in info.roles:
                table.add_row(role["name"], role["description"], role["multi"])
            console.print(table)
            console.print(f"[dim]Status:[/dim] {info.status}")
            console.print(f"[dim]{info.note}[/dim]")
        return

    table = Table(title="Visual Types & Data Roles", box=box.SIMPLE)
    table.add_column("Visual Type", style="cyan")
    table.add_column("Status", style="dim")
    table.add_column("Roles")

    for info in list_visual_type_info():
        role_names = ", ".join(r["name"] for r in info.roles) if info.roles else "-"
        table.add_row(info.visual_type, info.status, role_names)

    console.print(table)
    console.print("\n[dim]role-backed = role metadata modeled; sample-backed = observed in exported PBIR but binding roles are not modeled yet.[/dim]")
    console.print("[dim]Use 'pbi visual types <type>' for detailed role info.[/dim]")


@visual_sort_app.command("get")
def visual_sort_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show a visual's sort definition."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    sorts = proj.get_sort(vis)
    if not sorts:
        console.print("[dim]No sort definition.[/dim]")
        return
    for entity, prop, ftype, direction in sorts:
        kind = " (measure)" if ftype == "measure" else ""
        console.print(f"[cyan]{entity}.{prop}[/cyan]{kind} {direction}")


@visual_sort_app.command("set")
def visual_sort_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    field: Annotated[str, typer.Argument(help="Sort field as Table.Field.")],
    direction: Annotated[str, typer.Option("--direction", help="Sort direction: asc or desc.")] = "desc",
    field_type: Annotated[str, typer.Option("--field-type", help="Field type: auto, column, or measure.")] = "auto",
    project: ProjectOpt = None,
) -> None:
    """Set a visual's sort definition."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if direction not in {"asc", "desc"}:
        console.print("[red]Error:[/red] --direction must be 'asc' or 'desc'.")
        raise typer.Exit(1)

    try:
        entity, prop, resolved_field_type = _resolve_field_type(proj, field, field_type)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    descending = direction == "desc"
    proj.set_sort(vis, entity, prop, field_type=resolved_field_type, descending=descending)
    console.print(f'Sort set: [cyan]{entity}.{prop}[/cyan] {"Descending" if descending else "Ascending"}')


@visual_sort_app.command("clear")
def visual_sort_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Clear a visual's sort definition."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if proj.clear_sort(vis):
        console.print("Sort definition removed.")
    else:
        console.print("[dim]No sort definition to remove.[/dim]")


@visual_format_app.command("get")
def visual_format_get(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show conditional formatting on a visual."""
    from pbi.formatting import get_conditional_formats

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    formats = get_conditional_formats(vis.data)
    if not formats:
        console.print("[dim]No conditional formatting on this visual.[/dim]")
        return
    tbl = Table(title="Conditional Formatting", box=box.SIMPLE)
    tbl.add_column("Property", style="cyan")
    tbl.add_column("Mode")
    tbl.add_column("Source", style="bold")
    tbl.add_column("Details", style="dim")
    for f in formats:
        tbl.add_row(f"{f.object_name}.{f.property_name}", f.format_type, f.field_ref, f.details)
    console.print(tbl)


@visual_format_app.command("set")
def visual_format_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    prop: Annotated[str, typer.Argument(help="Property as object.prop (e.g. dataPoint.fill).")],
    mode: Annotated[str, typer.Option("--mode", help="Formatting mode: measure or gradient.")],
    source: Annotated[str, typer.Option("--source", help="Source field: Table.Measure for measure mode, Table.Field for gradient mode.")],
    min_color: Annotated[Optional[str], typer.Option("--min-color", help="Gradient minimum color (#hex).")] = None,
    min_value: Annotated[Optional[float], typer.Option("--min-value", help="Gradient minimum value.")] = None,
    mid_color: Annotated[Optional[str], typer.Option("--mid-color", help="Gradient midpoint color (#hex).")] = None,
    mid_value: Annotated[Optional[float], typer.Option("--mid-value", help="Gradient midpoint value.")] = None,
    max_color: Annotated[Optional[str], typer.Option("--max-color", help="Gradient maximum color (#hex).")] = None,
    max_value: Annotated[Optional[float], typer.Option("--max-value", help="Gradient maximum value.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set conditional formatting on a visual property."""
    from pbi.formatting import (
        GradientStop,
        build_gradient_format,
        build_measure_format,
        set_conditional_format,
    )

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    dot = prop.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Property must be object.prop format (e.g. dataPoint.fill).")
        raise typer.Exit(1)
    obj_name, prop_name = prop[:dot], prop[dot + 1:]

    if mode not in {"measure", "gradient"}:
        console.print("[red]Error:[/red] --mode must be 'measure' or 'gradient'.")
        raise typer.Exit(1)

    if mode == "measure":
        src_dot = source.find(".")
        if src_dot == -1:
            console.print("[red]Error:[/red] --source must be Table.Measure format for --mode measure.")
            raise typer.Exit(1)
        src_entity, src_prop = source[:src_dot], source[src_dot + 1:]
        value = build_measure_format(src_entity, src_prop)
        set_conditional_format(vis.data, obj_name, prop_name, value)
        vis.save()
        console.print(f"Set [cyan]{prop}[/cyan] = measure [bold]{src_entity}.{src_prop}[/bold]")
        return

    if min_color is None or min_value is None or max_color is None or max_value is None:
        console.print("[red]Error:[/red] Gradient mode requires --min-color, --min-value, --max-color, and --max-value.")
        raise typer.Exit(1)

    src_dot = source.find(".")
    if src_dot == -1:
        console.print("[red]Error:[/red] --source must be Table.Field format for --mode gradient.")
        raise typer.Exit(1)
    src_entity, src_prop = source[:src_dot], source[src_dot + 1:]

    min_c = min_color if min_color.startswith("#") else f"#{min_color}"
    max_c = max_color if max_color.startswith("#") else f"#{max_color}"
    mid_stop = None
    if mid_color is not None and mid_value is not None:
        mid_c = mid_color if mid_color.startswith("#") else f"#{mid_color}"
        mid_stop = GradientStop(mid_c, mid_value)
    elif mid_color is not None or mid_value is not None:
        console.print("[red]Error:[/red] Both --mid-color and --mid-value are required for a 3-stop gradient.")
        raise typer.Exit(1)

    value = build_gradient_format(
        src_entity,
        src_prop,
        min_stop=GradientStop(min_c, min_value),
        max_stop=GradientStop(max_c, max_value),
        mid_stop=mid_stop,
    )
    set_conditional_format(vis.data, obj_name, prop_name, value)
    vis.save()

    stops = f"{min_c}@{min_value}"
    if mid_stop:
        stops += f" -> {mid_stop.color}@{mid_stop.value}"
    stops += f" -> {max_c}@{max_value}"
    console.print(f"Set [cyan]{prop}[/cyan] = gradient by [bold]{src_entity}.{src_prop}[/bold] [{stops}]")


@visual_format_app.command("clear")
def visual_format_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name or index.")],
    prop: Annotated[str, typer.Argument(help="Property as object.prop (e.g. dataPoint.fill).")],
    project: ProjectOpt = None,
) -> None:
    """Clear conditional formatting from a visual property."""
    from pbi.formatting import clear_conditional_format

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    dot = prop.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Property must be object.prop format (e.g. dataPoint.fill).")
        raise typer.Exit(1)
    obj_name, prop_name = prop[:dot], prop[dot + 1:]

    if clear_conditional_format(vis.data, obj_name, prop_name):
        vis.save()
        console.print(f"Cleared conditional formatting from [cyan]{prop}[/cyan].")
    else:
        console.print(f"[dim]No conditional formatting on {prop}.[/dim]")


@visual_app.command("column")
def visual_column(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    column: Annotated[Optional[str], typer.Argument(help="Field: Table.Field, display name, or index. Omit to list all projection-backed fields.")] = None,
    width: Annotated[Optional[float], typer.Option("--width", "-w", help="Column width in pixels.")] = None,
    rename: Annotated[Optional[str], typer.Option("--rename", help="Rename column header.")] = None,
    align: Annotated[Optional[str], typer.Option("--align", help="Column alignment: Left, Center, Right.")] = None,
    font_color: Annotated[Optional[str], typer.Option("--font-color", help="Column font color (#hex).")] = None,
    back_color: Annotated[Optional[str], typer.Option("--back-color", help="Column background color (#hex).")] = None,
    display_units: Annotated[Optional[int], typer.Option("--display-units", help="Label display units (0=auto, 1=none, 1000=K, 1000000=M, etc.).")] = None,
    precision: Annotated[Optional[int], typer.Option("--precision", help="Decimal places.")] = None,
    clear_width: Annotated[bool, typer.Option("--clear-width", help="Remove column width override.")] = False,
    clear_format: Annotated[bool, typer.Option("--clear-format", help="Remove per-column formatting.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List, resize, rename, or format projection-backed visual fields."""
    from pbi.columns import (
        get_columns, find_column,
        set_column_width, rename_column, set_column_format,
        clear_column_width, clear_column_format,
    )

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # List mode — no column specified
    if column is None:
        columns = get_columns(vis)
        if not columns:
            console.print("[dim]No projection-backed fields on this visual.[/dim]")
            return
        tbl = Table(title=f"Columns on {vis.visual_type}", box=box.SIMPLE)
        tbl.add_column("#", style="dim", width=3)
        tbl.add_column("Field", style="cyan")
        tbl.add_column("Display Name")
        tbl.add_column("Type", style="dim")
        tbl.add_column("Width", justify="right")
        tbl.add_column("Formatting", style="dim")
        for i, col in enumerate(columns, 1):
            display = col.display_name or col.prop
            width_str = str(int(col.width)) if col.width else "-"
            fmt_parts = []
            if "alignment" in col.formatting:
                fmt_parts.append(f"align:{col.formatting['alignment']}")
            if "fontColor" in col.formatting:
                fmt_parts.append(f"color:{col.formatting['fontColor']}")
            fmt_str = ", ".join(fmt_parts) if fmt_parts else "-"
            tbl.add_row(str(i), f"{col.entity}.{col.prop}", display, col.field_type, width_str, fmt_str)
        console.print(tbl)
        return

    # Find the target column
    try:
        col = find_column(vis, column)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    changed = False

    # Clear operations
    if clear_width:
        if clear_column_width(vis, col.query_ref):
            console.print(f"Cleared width override on [cyan]{col.entity}.{col.prop}[/cyan].")
            changed = True
        else:
            console.print("[dim]No width override to clear.[/dim]")

    if clear_format:
        if clear_column_format(vis, col.query_ref):
            console.print(f"Cleared formatting on [cyan]{col.entity}.{col.prop}[/cyan].")
            changed = True
        else:
            console.print("[dim]No column formatting to clear.[/dim]")

    # Set operations
    if width is not None:
        set_column_width(vis, col.query_ref, width)
        console.print(f"[dim]{col.entity}.{col.prop} width:[/dim] {int(width)}")
        changed = True

    if rename is not None:
        old_name = col.display_name or col.prop
        rename_column(vis, col.query_ref, rename)
        console.print(f"[dim]{col.entity}.{col.prop}:[/dim] {old_name} [dim]→[/dim] {rename}")
        changed = True

    has_format = any(x is not None for x in [align, font_color, back_color, display_units, precision])
    if has_format:
        set_column_format(
            vis, col.query_ref,
            alignment=align, font_color=font_color, back_color=back_color,
            display_units=display_units, precision=precision,
        )
        parts = []
        if align: parts.append(f"align={align}")
        if font_color: parts.append(f"fontColor={font_color}")
        if back_color: parts.append(f"backColor={back_color}")
        if display_units is not None: parts.append(f"displayUnits={display_units}")
        if precision is not None: parts.append(f"precision={precision}")
        console.print(f"[dim]{col.entity}.{col.prop} format:[/dim] {', '.join(parts)}")
        changed = True

    if changed:
        vis.save()
    elif not clear_width and not clear_format:
        # No options given — show column details
        display = col.display_name or col.prop
        console.print(f"[bold]{col.entity}.{col.prop}[/bold]")
        console.print(f"  Role: {col.role}")
        console.print(f"  Type: {col.field_type}")
        console.print(f"  Display name: {display}")
        console.print(f"  Query ref: {col.query_ref}")
        if col.width:
            console.print(f"  Width: {int(col.width)}")
        if col.formatting:
            for k, v in col.formatting.items():
                console.print(f"  {k}: {v}")


@visual_app.command("properties")
def visual_props(
    visual_type: Annotated[Optional[str], typer.Option("--visual-type", help="Show only properties for this visual type.")] = None,
    group: Annotated[Optional[str], typer.Option("--group", "-g", help="Filter by group: position, core, container, chart.")] = None,
    match: Annotated[Optional[str], typer.Option("--match", help="Filter properties by name, alias, or description text.")] = None,
    show_aliases: Annotated[bool, typer.Option("--show-aliases", help="Show accepted raw/alias input forms for each property.")] = False,
) -> None:
    """List available visual properties.

    Use --visual-type to show properties for a specific visual type (e.g. --visual-type clusteredColumnChart).
    Use --group to filter by property group (position, core, container, chart).
    """
    props = list_properties(VISUAL_PROPERTIES, group=group, visual_type=visual_type)
    if match:
        needle = match.lower()
        filtered = []
        for name, vtype, desc, prop_group, enum_values in props:
            aliases = property_aliases_for(name, VISUAL_PROPERTIES)
            if (
                needle in name.lower()
                or needle in desc.lower()
                or any(needle in alias.lower() for alias in aliases)
            ):
                filtered.append((name, vtype, desc, prop_group, enum_values))
        props = filtered

    if not props:
        filters = []
        if visual_type:
            filters.append(f'type="{visual_type}"')
        if group:
            filters.append(f'group="{group}"')
        if match:
            filters.append(f'match="{match}"')
        console.print(f'[yellow]No properties match filters: {", ".join(filters)}[/yellow]')
        return

    title = "Visual Properties"
    if visual_type:
        title += f" ({visual_type})"
    if group:
        title += f" [{group}]"

    table = Table(title=title, box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Group", style="dim")
    table.add_column("Description")
    table.add_column("Values", style="dim")
    if show_aliases:
        table.add_column("Accepted Input", style="dim", overflow="fold")

    current_group = None
    for name, vtype, desc, prop_group, enum_values in props:
        if prop_group != current_group:
            if current_group is not None:
                table.add_section()
            current_group = prop_group
        vals = ", ".join(enum_values) if enum_values else ""
        row = [name, vtype, prop_group or "", desc, vals]
        if show_aliases:
            aliases = property_aliases_for(name, VISUAL_PROPERTIES)
            row.append(", ".join(aliases))
        table.add_row(*row)

    console.print(table)
    console.print(
        "\n[dim]Use 'chart:<object>.<prop>' for unregistered chart properties. "
        "Use --visual-type <visualType> to filter by chart type.[/dim]"
    )


@visual_app.command("objects")
def visual_objects(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    project: ProjectOpt = None,
) -> None:
    """Show all chart formatting objects currently set on a visual.

    Introspects visual.objects to show what properties are configured,
    including values from all selector entries. Useful for discovering
    what can be modified with 'chart:<object>.<prop>' syntax.
    """
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    chart_objects = get_visual_objects(vis.data)
    if not chart_objects:
        console.print(f"[dim]No chart objects on {vis.visual_type} \"{vis.name}\".[/dim]")
        return

    table = Table(title=f"Chart Objects on {vis.visual_type}", box=box.SIMPLE)
    table.add_column("Object", style="cyan")
    table.add_column("Property", style="bold")
    table.add_column("Value")

    for obj_key in sorted(chart_objects):
        props = chart_objects[obj_key]
        first = True
        for prop_name, value in sorted(props.items()):
            obj_label = obj_key if first else ""
            table.add_row(obj_label, prop_name, str(value))
            first = False
        table.add_section()

    console.print(table)
    console.print(
        f"\n[dim]Set with: pbi visual set {page} {visual} chart:<object>.<prop>=<value>[/dim]"
    )


# ── Model commands ─────────────────────────────────────────────────

def _get_model(project: Path | None):
    from pbi.model import SemanticModel
    proj = _get_project(project)
    try:
        return proj, SemanticModel.load(proj.root)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


@model_app.command("tables")
def model_tables(project: ProjectOpt = None) -> None:
    """List tables in the semantic model."""
    _, model = _get_model(project)

    table = Table(title="Semantic Model Tables", box=box.SIMPLE)
    table.add_column("Table", style="cyan")
    table.add_column("Columns", justify="right")
    table.add_column("Measures", justify="right")

    for t in model.tables:
        table.add_row(t.name, str(len(t.columns)), str(len(t.measures)))

    console.print(table)


@model_app.command("columns")
def model_columns(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    show_hidden: Annotated[bool, typer.Option("--hidden", help="Show hidden columns.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List columns (dimensions) in a table."""
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    cols = sem_table.columns
    if not show_hidden:
        cols = [c for c in cols if not c.is_hidden]

    table = Table(title=f'Columns in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Column", style="cyan")
    table.add_column("Data Type", style="dim")
    table.add_column("Source Column", style="dim")

    for c in cols:
        table.add_row(c.name, c.data_type, c.source_column)

    console.print(table)
    hidden_count = len(sem_table.columns) - len(cols)
    if hidden_count:
        console.print(f"[dim]({hidden_count} hidden columns, use --hidden to show)[/dim]")


@model_app.command("measures")
def model_measures(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    project: ProjectOpt = None,
) -> None:
    """List measures (facts) in a table."""
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    table = Table(title=f'Measures in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Measure", style="cyan")
    table.add_column("Expression", max_width=60)
    table.add_column("Format", style="dim")

    for m in sem_table.measures:
        expr = m.expression[:57] + "..." if len(m.expression) > 60 else m.expression
        table.add_row(m.name, expr, m.format_string)

    console.print(table)


@model_app.command("fields")
def model_fields(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    project: ProjectOpt = None,
) -> None:
    """List all fields (columns + measures) for use with 'visual bind'."""
    _, model = _get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    table = Table(title=f'Fields in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Field Reference", style="cyan")
    table.add_column("Type")
    table.add_column("Details", style="dim")

    for c in sem_table.columns:
        if not c.is_hidden:
            table.add_row(
                f"{sem_table.name}.{c.name}",
                "column",
                c.data_type,
            )
    for m in sem_table.measures:
        expr = m.expression[:40] + "..." if len(m.expression) > 40 else m.expression
        table.add_row(
            f"{sem_table.name}.{m.name}",
            "[bold]measure[/bold]",
            expr,
        )

    console.print(table)


# ── Filter commands ─────────────────────────────────────────────────


def _load_filter_model(project: Path | None):
    """Best-effort semantic model loader for filter typing."""
    try:
        from pbi.model import SemanticModel

        proj_obj = _get_project(project)
        return SemanticModel.load(proj_obj.root)
    except (FileNotFoundError, ValueError):
        return None


def _resolve_filter_field(
    field: str,
    *,
    field_type: str,
    model,
) -> tuple[str, str, str, str | None]:
    """Resolve a filter field into entity, prop, field_type, data_type."""
    dot = field.find(".")
    if dot == -1:
        raise ValueError("Field must be Table.Field format.")

    entity, prop = field[:dot], field[dot + 1:]
    mode = _normalize_field_type(field_type)
    if mode == "measure":
        return entity, prop, "measure", None
    if mode == "column" or model is None:
        return entity, prop, "column", None

    resolved_entity, resolved_prop, resolved_field_type = model.resolve_field(field)
    data_type = None
    if resolved_field_type == "column":
        table = model.find_table(resolved_entity)
        for col in table.columns:
            if col.name == resolved_prop:
                data_type = col.data_type
                break
    return resolved_entity, resolved_prop, resolved_field_type, data_type

@filter_app.command("list")
def filter_list(
    scope: Annotated[str, typer.Argument(help="Target scope: report, page, or visual.")],
    targets: Annotated[list[str], typer.Argument(help="Scope targets: none for report, <page> for page, <page> <visual> for visual.")] = [],
    project: ProjectOpt = None,
) -> None:
    """List filters at report, page, or visual level."""
    from pbi.filters import filter_field_refs, load_level_data, get_filters, parse_filter

    proj = _get_project(project)
    if scope == "report":
        if targets:
            console.print("[red]Error:[/red] Report scope does not accept page or visual targets.")
            raise typer.Exit(1)
        page_ref = None
        visual_ref = None
    elif scope == "page":
        if len(targets) != 1:
            console.print("[red]Error:[/red] Page scope requires exactly <page>.")
            raise typer.Exit(1)
        page_ref = targets[0]
        visual_ref = None
    elif scope == "visual":
        if len(targets) != 2:
            console.print("[red]Error:[/red] Visual scope requires exactly <page> <visual>.")
            raise typer.Exit(1)
        page_ref, visual_ref = targets
    else:
        console.print("[red]Error:[/red] Scope must be 'report', 'page', or 'visual'.")
        raise typer.Exit(1)

    try:
        data, level, _ = load_level_data(proj, page_ref, visual_ref)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    filters = get_filters(data)
    if not filters:
        console.print(f"[dim]No filters at {level} level.[/dim]")
        return

    table = Table(title=f"{level.title()} Filters", box=box.SIMPLE)
    table.add_column("Name", style="dim")
    table.add_column("Field", style="cyan")
    table.add_column("Type")
    table.add_column("Values/Condition")
    table.add_column("Hidden", style="dim", justify="center")
    table.add_column("Locked", style="dim", justify="center")

    for f in filters:
        info = parse_filter(f, level)
        field_refs = filter_field_refs(f)
        field_label = ", ".join(field_refs) if field_refs else f.get("displayName", "(tuple)")
        table.add_row(
            info.name or "-",
            field_label,
            info.filter_type,
            ", ".join(info.values) if info.values else "-",
            "yes" if info.is_hidden else "",
            "yes" if info.is_locked else "",
        )

    console.print(table)


@filter_app.command("add")
def filter_add(
    scope: Annotated[str, typer.Argument(help="Target scope: report, page, or visual.")],
    targets: Annotated[list[str], typer.Argument(help="Target arguments followed by the filter field. For non-tuple modes: report <field>, page <page> <field>, visual <page> <visual> <field>. For tuple mode: omit the field and use --row.")] = [],
    value: Annotated[Optional[list[str]], typer.Option("--value", help="Value for categorical/include/exclude filters. Repeatable.")] = None,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="Filter mode: categorical, include, exclude, range, topn, relative, or tuple.",
        ),
    ] = "categorical",
    min_val: Annotated[Optional[str], typer.Option("--min", help="Minimum value for range filter.")] = None,
    max_val: Annotated[Optional[str], typer.Option("--max", help="Maximum value for range filter.")] = None,
    topn: Annotated[Optional[int], typer.Option("--topn", help="Top N items count.")] = None,
    topn_by: Annotated[Optional[str], typer.Option("--topn-by", help="Order-by field for Top N (Table.Field).")] = None,
    direction: Annotated[str, typer.Option("--direction", help="Top N direction: top or bottom.")] = "top",
    operator: Annotated[Optional[str], typer.Option("--operator", help="Relative operator: InLast, InThis, or InNext.")] = None,
    count: Annotated[Optional[int], typer.Option("--count", help="Relative time unit count.")] = None,
    unit: Annotated[Optional[str], typer.Option("--unit", help="Relative unit: Minutes, Hours, Days, Weeks, Months, Quarters, or Years.")] = None,
    include_today: Annotated[bool, typer.Option("--include-today/--no-include-today", help="Include today for relative date filters when supported.")] = True,
    hidden: Annotated[bool, typer.Option("--hidden", help="Hide filter in view mode.")] = False,
    locked: Annotated[bool, typer.Option("--locked", help="Lock filter in view mode.")] = False,
    field_type: Annotated[str, typer.Option("--field-type", help="Field type: auto, column, or measure.")] = "auto",
    row: Annotated[Optional[list[str]], typer.Option("--row", help="Tuple row as comma-separated Field=Value pairs. Repeatable.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Add a filter.

    Schema-backed writes currently support categorical, include, exclude,
    tuple, range, Top N, Relative Date, and Relative Time filters.
    Passthrough remains blocked until this CLI has a
    Microsoft-schema-valid PBIR implementation for that filter type.
    """
    from pbi.filters import (
        load_level_data, save_level_data,
        add_categorical_filter, add_exclude_filter, add_include_filter, add_range_filter,
        add_relative_date_filter, add_relative_time_filter, add_topn_filter,
    )

    valid_modes = {"categorical", "include", "exclude", "range", "topn", "relative", "tuple"}
    if mode not in valid_modes:
        console.print(
            f"[red]Error:[/red] Invalid --mode '{mode}'. "
            f"Use one of: {', '.join(sorted(valid_modes))}."
        )
        raise typer.Exit(1)

    if direction not in {"top", "bottom"}:
        console.print("[red]Error:[/red] --direction must be 'top' or 'bottom'.")
        raise typer.Exit(1)

    model = _load_filter_model(project)

    proj = _get_project(project)
    if mode == "tuple":
        if scope == "report":
            if targets:
                console.print("[red]Error:[/red] Tuple filters at report scope do not accept target arguments.")
                raise typer.Exit(1)
            page_ref = None
            visual_ref = None
        elif scope == "page":
            if len(targets) != 1:
                console.print("[red]Error:[/red] Tuple filters at page scope require exactly <page>.")
                raise typer.Exit(1)
            page_ref = targets[0]
            visual_ref = None
        elif scope == "visual":
            if len(targets) != 2:
                console.print("[red]Error:[/red] Tuple filters at visual scope require exactly <page> <visual>.")
                raise typer.Exit(1)
            page_ref, visual_ref = targets
        else:
            console.print("[red]Error:[/red] Scope must be 'report', 'page', or 'visual'.")
            raise typer.Exit(1)
    else:
        if scope == "report":
            if len(targets) != 1:
                console.print("[red]Error:[/red] Report scope requires exactly <field>.")
                raise typer.Exit(1)
            page_ref = None
            visual_ref = None
            field = targets[0]
        elif scope == "page":
            if len(targets) != 2:
                console.print("[red]Error:[/red] Page scope requires exactly <page> <field>.")
                raise typer.Exit(1)
            page_ref = targets[0]
            visual_ref = None
            field = targets[1]
        elif scope == "visual":
            if len(targets) != 3:
                console.print("[red]Error:[/red] Visual scope requires exactly <page> <visual> <field>.")
                raise typer.Exit(1)
            page_ref, visual_ref, field = targets
        else:
            console.print("[red]Error:[/red] Scope must be 'report', 'page', or 'visual'.")
            raise typer.Exit(1)

        try:
            entity, prop, resolved_field_type, data_type = _resolve_filter_field(
                field,
                field_type=field_type,
                model=model,
            )
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    try:
        data, level, target = load_level_data(proj, page_ref, visual_ref)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if mode in {"categorical", "include", "exclude"}:
        val_list = value or []
        if not val_list:
            console.print("[red]Error:[/red] Categorical/include/exclude filters require at least one --value.")
            raise typer.Exit(1)
        add_fn = {
            "categorical": add_categorical_filter,
            "include": add_include_filter,
            "exclude": add_exclude_filter,
        }[mode]
        add_fn(
            data,
            entity,
            prop,
            val_list,
            field_type=resolved_field_type,
            is_hidden=hidden,
            is_locked=locked,
            data_type=data_type,
        )
        save_level_data(data, target)
        label = "categorical" if mode == "categorical" else mode
        console.print(
            f'Added {label} filter on [cyan]{entity}.{prop}[/cyan] '
            f'= [{", ".join(val_list)}] at {level} level'
        )
    elif mode == "range":
        if min_val is None and max_val is None:
            console.print("[red]Error:[/red] Range filters require --min, --max, or both.")
            raise typer.Exit(1)
        add_range_filter(
            data, entity, prop, min_val=min_val, max_val=max_val,
            field_type=resolved_field_type, is_hidden=hidden, is_locked=locked, data_type=data_type,
        )
        save_level_data(data, target)
        bounds = []
        if min_val is not None:
            bounds.append(f">= {min_val}")
        if max_val is not None:
            bounds.append(f"<= {max_val}")
        console.print(
            f'Added range filter on [cyan]{entity}.{prop}[/cyan] '
            f'{" and ".join(bounds)} at {level} level'
        )
    elif mode == "topn":
        if topn is None:
            console.print("[red]Error:[/red] Top N filters require --topn.")
            raise typer.Exit(1)
        if not topn_by:
            console.print("[red]Error:[/red] --topn requires --topn-by (Table.Field) to specify the order-by field.")
            raise typer.Exit(1)
        if resolved_field_type != "column":
            console.print("[red]Error:[/red] Top N filters require a column target field.")
            raise typer.Exit(1)
        try:
            order_entity, order_prop, order_field_type, _ = _resolve_filter_field(
                topn_by,
                field_type="auto",
                model=model,
            )
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        direction_label = "Bottom" if direction == "bottom" else "Top"
        try:
            add_topn_filter(
                data, entity, prop, n=topn,
                order_entity=order_entity, order_prop=order_prop,
                order_field_type=order_field_type, direction=direction_label,
                field_type=resolved_field_type, is_hidden=hidden, is_locked=locked,
            )
        except (NotImplementedError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        save_level_data(data, target)
        console.print(
            f'Added {direction_label} {topn} filter on [cyan]{entity}.{prop}[/cyan] '
            f'by {order_entity}.{order_prop} at {level} level'
        )
    elif mode == "relative":
        if operator is None or count is None or unit is None:
            console.print("[red]Error:[/red] Relative filters require --operator, --count, and --unit.")
            raise typer.Exit(1)
        rel_op = operator
        rel_count = count
        rel_unit = unit
        valid_ops = ("InLast", "InThis", "InNext")
        valid_units = ("Minutes", "Hours", "Days", "Weeks", "Months", "Quarters", "Years")
        if rel_op not in valid_ops:
            console.print(f"[red]Error:[/red] Operator must be one of: {', '.join(valid_ops)}")
            raise typer.Exit(1)
        if rel_unit not in valid_units:
            console.print(f"[red]Error:[/red] Unit must be one of: {', '.join(valid_units)}")
            raise typer.Exit(1)
        try:
            if rel_unit in ("Minutes", "Hours"):
                add_relative_time_filter(
                    data,
                    entity,
                    prop,
                    operator=rel_op,
                    time_units_count=rel_count,
                    time_unit_type=rel_unit,
                    field_type=resolved_field_type,
                    is_hidden=hidden,
                    is_locked=locked,
                )
            else:
                add_relative_date_filter(
                    data,
                    entity,
                    prop,
                    operator=rel_op,
                    time_units_count=rel_count,
                    time_unit_type=rel_unit,
                    include_today=include_today,
                    field_type=resolved_field_type,
                    is_hidden=hidden,
                    is_locked=locked,
                )
        except (NotImplementedError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        save_level_data(data, target)
        console.print(
            f'Added relative filter on [cyan]{entity}.{prop}[/cyan] '
            f'{rel_op.lower()} {rel_count} {rel_unit.lower()} at {level} level'
        )
    else:
        if not row:
            console.print("[red]Error:[/red] Tuple filters require at least one --row.")
            raise typer.Exit(1)
        from pbi.filters import TupleField, add_tuple_filter

        parsed_rows: list[list[TupleField]] = []
        for row_spec in row:
            parsed_fields: list[TupleField] = []
            for part in row_spec.split(","):
                assignment = part.strip()
                eq = assignment.find("=")
                if eq == -1:
                    console.print(
                        f"[red]Error:[/red] Invalid tuple assignment '{assignment}'. Use Field=Value."
                    )
                    raise typer.Exit(1)
                field_ref = assignment[:eq].strip()
                literal = assignment[eq + 1:].strip()
                try:
                    row_entity, row_prop, row_field_type, row_data_type = _resolve_filter_field(
                        field_ref,
                        field_type="auto",
                        model=model,
                    )
                except ValueError as e:
                    console.print(f"[red]Error:[/red] {e}")
                    raise typer.Exit(1)
                parsed_fields.append(
                    TupleField(
                        entity=row_entity,
                        prop=row_prop,
                        value=literal,
                        field_type=row_field_type,
                        data_type=row_data_type,
                    )
                )
            parsed_rows.append(parsed_fields)

        try:
            add_tuple_filter(data, parsed_rows, is_hidden=hidden, is_locked=locked)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        save_level_data(data, target)
        console.print(f'Added tuple filter with [cyan]{len(parsed_rows)}[/cyan] row(s) at {level} level')


@filter_app.command("remove")
def filter_remove(
    scope: Annotated[str, typer.Argument(help="Target scope: report, page, or visual.")],
    targets: Annotated[list[str], typer.Argument(help="Target arguments followed by the filter name or field to remove. report <filter>, page <page> <filter>, visual <page> <visual> <filter>.")],
    project: ProjectOpt = None,
) -> None:
    """Remove a filter by field reference or filter name."""
    from pbi.filters import load_level_data, save_level_data, remove_filter

    proj = _get_project(project)
    if scope == "report":
        if len(targets) != 1:
            console.print("[red]Error:[/red] Report scope requires exactly <filter>.")
            raise typer.Exit(1)
        page_ref = None
        visual_ref = None
        field = targets[0]
    elif scope == "page":
        if len(targets) != 2:
            console.print("[red]Error:[/red] Page scope requires exactly <page> <filter>.")
            raise typer.Exit(1)
        page_ref = targets[0]
        visual_ref = None
        field = targets[1]
    elif scope == "visual":
        if len(targets) != 3:
            console.print("[red]Error:[/red] Visual scope requires exactly <page> <visual> <filter>.")
            raise typer.Exit(1)
        page_ref, visual_ref, field = targets
    else:
        console.print("[red]Error:[/red] Scope must be 'report', 'page', or 'visual'.")
        raise typer.Exit(1)

    try:
        data, level, target = load_level_data(proj, page_ref, visual_ref)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    removed = remove_filter(data, field)
    if removed:
        save_level_data(data, target)
        console.print(f'Removed {removed} filter(s) matching "{field}" at {level} level')
    else:
        console.print(f'[yellow]No filter matching "{field}" found at {level} level.[/yellow]')


# ── Theme commands ─────────────────────────────────────────────

@theme_app.command("list")
def theme_list(
    project: ProjectOpt = None,
) -> None:
    """List active themes (base + custom)."""
    from pbi.themes import get_themes

    proj = _get_project(project)
    themes = get_themes(proj)

    if not themes:
        console.print("[yellow]No themes configured.[/yellow]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE)
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Source")
    for t in themes:
        label = "custom" if t.is_custom else "base"
        table.add_row(label, t.name, t.source)
    console.print(table)


@theme_app.command("apply")
def theme_apply(
    theme_file: Annotated[str, typer.Argument(help="Path to theme JSON file.")],
    project: ProjectOpt = None,
) -> None:
    """Apply a custom theme JSON file to the project."""
    import json
    from pbi.themes import apply_theme

    proj = _get_project(project)
    path = Path(theme_file).resolve()
    if not path.exists():
        console.print(f"[red]Error:[/red] File not found: {path}")
        raise typer.Exit(1)

    try:
        name = apply_theme(proj, path)
    except (json.JSONDecodeError, ValueError) as e:
        console.print(f"[red]Error:[/red] Invalid theme file: {e}")
        raise typer.Exit(1)

    console.print(f'Applied theme "[cyan]{name}[/cyan]"')


@theme_app.command("export")
def theme_export(
    output: Annotated[str, typer.Argument(help="Output path for the theme JSON file.")],
    project: ProjectOpt = None,
) -> None:
    """Export the active custom theme to a standalone JSON file."""
    from pbi.themes import export_theme

    proj = _get_project(project)
    out_path = Path(output).resolve()

    try:
        name = export_theme(proj, out_path)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f'Exported theme "[cyan]{name}[/cyan]" → {out_path}')


@theme_app.command("remove")
def theme_remove(
    project: ProjectOpt = None,
) -> None:
    """Remove the custom theme from the project (reverts to base theme)."""
    from pbi.themes import remove_theme

    proj = _get_project(project)
    name = remove_theme(proj)

    if name:
        console.print(f'Removed custom theme "[cyan]{name}[/cyan]"')
    else:
        console.print("[yellow]No custom theme to remove.[/yellow]")


# ── Interaction commands ───────────────────────────────────────

@interaction_app.command("list")
def interaction_list(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    project: ProjectOpt = None,
) -> None:
    """List visual interactions on a page."""
    from pbi.interactions import get_interactions

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    interactions = get_interactions(pg)
    if not interactions:
        console.print("[dim]No custom interactions (all using default behavior).[/dim]")
        return

    table = Table(title=f'Interactions on "{pg.display_name}"', box=box.SIMPLE)
    table.add_column("Source", style="cyan")
    table.add_column("Target", style="cyan")
    table.add_column("Type")

    for entry in interactions:
        table.add_row(entry.get("source", ""), entry.get("target", ""), entry.get("type", ""))

    console.print(table)


@interaction_app.command("set")
def interaction_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    source: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target: Annotated[str, typer.Argument(help="Target visual name or index.")],
    mode: Annotated[str, typer.Option("--mode", help="Interaction mode: DataFilter, HighlightFilter, or NoFilter.")],
    project: ProjectOpt = None,
) -> None:
    """Set interaction between two visuals."""
    from pbi.interactions import set_interaction

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        src_vis = proj.find_visual(pg, source)
        tgt_vis = proj.find_visual(pg, target)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if mode not in {"DataFilter", "HighlightFilter", "NoFilter"}:
        console.print("[red]Error:[/red] --mode must be DataFilter, HighlightFilter, or NoFilter.")
        raise typer.Exit(1)

    try:
        set_interaction(pg, src_vis.name, tgt_vis.name, mode)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    pg.save()
    console.print(
        f'Set interaction: [cyan]{src_vis.name}[/cyan] → '
        f'[cyan]{tgt_vis.name}[/cyan] = [bold]{mode}[/bold]'
    )


@interaction_app.command("clear")
def interaction_clear(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    source: Annotated[str, typer.Argument(help="Source visual name or index.")],
    target: Annotated[Optional[str], typer.Argument(help="Target visual (omit to remove all from source).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Remove custom interactions from a visual."""
    from pbi.interactions import remove_interaction

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        src_vis = proj.find_visual(pg, source)
        tgt_vis = proj.find_visual(pg, target) if target else None
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    removed = remove_interaction(pg, src_vis.name, tgt_vis.name if tgt_vis else None)
    if removed:
        pg.save()
        scope = f'→ "{tgt_vis.name}"' if tgt_vis else "(all targets)"
        console.print(f'Removed {removed} interaction(s) from [cyan]{src_vis.name}[/cyan] {scope}')
    else:
        console.print("[yellow]No matching interactions found.[/yellow]")


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

    proj = _get_project(project)
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


# ── Bookmark commands ──────────────────────────────────────────

@bookmark_app.command("list")
def bookmark_list(
    project: ProjectOpt = None,
) -> None:
    """List all bookmarks in the project."""
    from pbi.bookmarks import list_bookmarks

    proj = _get_project(project)
    bookmarks = list_bookmarks(proj)

    if not bookmarks:
        console.print("[yellow]No bookmarks. Use `pbi bookmark create` to add one.[/yellow]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Display Name")
    table.add_column("Active Page")
    table.add_column("Targets", style="dim")
    table.add_column("Options", style="dim")

    for bm in bookmarks:
        targets = ", ".join(bm.target_visuals) if bm.target_visuals else "all"
        opts = []
        if bm.suppress_data:
            opts.append("no-data")
        if bm.suppress_display:
            opts.append("no-display")
        table.add_row(
            bm.name[:16] + "..." if len(bm.name) > 16 else bm.name,
            bm.display_name,
            bm.active_section[:16] + "..." if len(bm.active_section) > 16 else bm.active_section,
            targets,
            ", ".join(opts) or "-",
        )

    console.print(table)


@bookmark_app.command("get")
def bookmark_get(
    bookmark: Annotated[str, typer.Argument(help="Bookmark name or display name.")],
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Show raw JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show bookmark details."""
    import json as json_mod
    from pbi.bookmarks import get_bookmark

    proj = _get_project(project)
    try:
        data = get_bookmark(proj, bookmark)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        console.print_json(json_mod.dumps(data, indent=2))
        return

    exploration = data.get("explorationState", {})
    options = data.get("options", {})

    table = Table(title=data.get("displayName", ""), box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")

    table.add_row("Name", data.get("name", ""))
    table.add_row("Display Name", data.get("displayName", ""))
    table.add_row("Active Section", exploration.get("activeSection", ""))

    # Options
    if options:
        table.add_section()
        if options.get("suppressActiveSection"):
            table.add_row("Suppress Active Section", "true")
        if options.get("suppressData"):
            table.add_row("Suppress Data", "true")
        if options.get("suppressDisplay"):
            table.add_row("Suppress Display", "true")
        if options.get("applyOnlyToTargetVisuals"):
            targets = options.get("targetVisualNames", [])
            table.add_row("Target Visuals", ", ".join(targets))

    # Visual states
    sections = exploration.get("sections", {})
    for section_name, section_data in sections.items():
        containers = section_data.get("visualContainers", {})
        if containers:
            table.add_section()
            for vis_name, vis_state in containers.items():
                single = vis_state.get("singleVisual", {})
                display_state = single.get("display", {})
                mode = display_state.get("mode", "normal")
                table.add_row(f"[dim]{section_name}[/dim] {vis_name}", mode)

    console.print(table)


@bookmark_app.command("create")
def bookmark_create(
    name: Annotated[str, typer.Argument(help="Display name for the bookmark.")],
    page: Annotated[str, typer.Argument(help="Page to bookmark (name, display name, or index).")],
    hide: Annotated[Optional[list[str]], typer.Option("--hide", help="Visual names to hide in this bookmark.")] = None,
    target: Annotated[Optional[list[str]], typer.Option("--target", help="Only apply bookmark to these visuals.")] = None,
    capture_data: Annotated[bool, typer.Option("--capture-data/--no-capture-data", help="Capture data and filter state.")] = True,
    capture_display: Annotated[bool, typer.Option("--capture-display/--no-capture-display", help="Capture display state.")] = True,
    capture_page: Annotated[bool, typer.Option("--capture-page/--no-capture-page", help="Capture the active page.")] = True,
    project: ProjectOpt = None,
) -> None:
    """Create a bookmark capturing page state.

    By default captures the active page and all visual states. Use --hide to
    mark specific visuals as hidden. Use --target to limit bookmark scope.
    """
    from pbi.bookmarks import create_bookmark

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    data = create_bookmark(
        proj,
        display_name=name,
        page=pg,
        visuals=visuals,
        hidden_visuals=hide,
        target_visuals=target,
        suppress_data=not capture_data,
        suppress_display=not capture_display,
        suppress_active_section=not capture_page,
    )

    hidden_count = len(hide) if hide else 0
    console.print(
        f'Created bookmark "[cyan]{name}[/cyan]" on page "{pg.display_name}"'
        f'{f" ({hidden_count} hidden)" if hidden_count else ""}'
    )


@bookmark_app.command("set")
def bookmark_set(
    bookmark: Annotated[str, typer.Argument(help="Bookmark name or display name.")],
    hide: Annotated[Optional[list[str]], typer.Option("--hide", help="Visual names to set as hidden.")] = None,
    show: Annotated[Optional[list[str]], typer.Option("--show", help="Visual names to set as visible.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Update visual visibility in an existing bookmark."""
    from pbi.bookmarks import update_bookmark_visuals

    proj = _get_project(project)

    if not hide and not show:
        console.print("[red]Error:[/red] Specify --hide or --show to update visual states.")
        raise typer.Exit(1)

    try:
        data = update_bookmark_visuals(
            proj,
            bookmark,
            hidden_visuals=hide,
            visible_visuals=show,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    changes = []
    if hide:
        changes.append(f"hidden: {', '.join(hide)}")
    if show:
        changes.append(f"visible: {', '.join(show)}")
    console.print(
        f'Updated bookmark "[cyan]{data.get("displayName", bookmark)}[/cyan]": '
        f'{"; ".join(changes)}'
    )


@bookmark_app.command("delete")
def bookmark_delete(
    bookmark: Annotated[str, typer.Argument(help="Bookmark name or display name.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a bookmark."""
    from pbi.bookmarks import delete_bookmark

    proj = _get_project(project)

    if not force:
        confirm = typer.confirm(f'Delete bookmark "{bookmark}"?')
        if not confirm:
            raise typer.Abort()

    try:
        display_name = delete_bookmark(proj, bookmark)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f'Deleted bookmark "[cyan]{display_name}[/cyan]"')


if __name__ == "__main__":
    app()
