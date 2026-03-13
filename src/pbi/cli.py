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
    PAGE_PROPERTIES,
    get_property,
    set_property,
    list_properties,
)

app = typer.Typer(
    name="pbi",
    help="CLI tool for editing Power BI PBIP project files.",
    no_args_is_help=True,
)
page_app = typer.Typer(help="Page operations.", no_args_is_help=True)
visual_app = typer.Typer(help="Visual operations.", no_args_is_help=True)
model_app = typer.Typer(help="Semantic model operations.", no_args_is_help=True)
filter_app = typer.Typer(help="Filter operations.", no_args_is_help=True)
theme_app = typer.Typer(help="Theme operations.", no_args_is_help=True)
app.add_typer(page_app, name="page")
app.add_typer(visual_app, name="visual")
app.add_typer(model_app, name="model")
app.add_typer(filter_app, name="filter")
app.add_typer(theme_app, name="theme")

console = Console()

ProjectOpt = Annotated[
    Optional[Path],
    typer.Option("--project", "-p", help="Path to PBIP project (default: auto-detect from cwd)."),
]


def _get_project(project: Path | None) -> Project:
    try:
        return Project.find(project)
    except FileNotFoundError as e:
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


# ── Page commands ──────────────────────────────────────────────────

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
    prop: Annotated[Optional[str], typer.Argument(help="Property to read (omit for all).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Show page details or a specific property."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if prop:
        value = get_property(pg.data, prop, PAGE_PROPERTIES)
        console.print(value)
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
    prop: Annotated[str, typer.Argument(help="Property path (e.g. 'width', 'displayName').")],
    value: Annotated[str, typer.Argument(help="New value.")],
    project: ProjectOpt = None,
) -> None:
    """Set a page property."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    old = get_property(pg.data, prop, PAGE_PROPERTIES)
    try:
        set_property(pg.data, prop, value, PAGE_PROPERTIES)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    pg.save()
    new = get_property(pg.data, prop, PAGE_PROPERTIES)
    console.print(f"[dim]{prop}:[/dim] {old} [dim]→[/dim] {new}")


@page_app.command("props")
def page_props() -> None:
    """List available page properties."""
    table = Table(title="Page Properties", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for name, vtype, desc in list_properties(PAGE_PROPERTIES):
        table.add_row(name, vtype, desc)

    console.print(table)


@page_app.command("create")
def page_create(
    name: Annotated[str, typer.Argument(help="Display name for the new page.")],
    width: Annotated[int, typer.Option(help="Page width in pixels.")] = 1280,
    height: Annotated[int, typer.Option(help="Page height in pixels.")] = 720,
    display_option: Annotated[str, typer.Option("--display", help="FitToPage, FitToWidth, or ActualSize.")] = "FitToPage",
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
    prop: Annotated[Optional[str], typer.Argument(help="Property to read (omit for overview).")] = None,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Show raw JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show visual details or a specific property."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        import json
        console.print_json(json.dumps(vis.data, indent=2))
        return

    if prop:
        value = get_property(vis.data, prop, VISUAL_PROPERTIES)
        console.print(value)
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
    from pbi.properties import decode_pbi_value
    for section, _ in [("visualContainerObjects", "Container"), ("objects", "Chart")]:
        section_data = vis.data.get("visual", {}).get(section, {})
        if section_data:
            table.add_section()
            for obj_name, entries in section_data.items():
                if entries and isinstance(entries, list) and entries[0].get("properties"):
                    for pname, pval in entries[0]["properties"].items():
                        decoded = decode_pbi_value(pval)
                        table.add_row(f"{obj_name}.{pname}", str(decoded))

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


@visual_app.command("set")
def visual_set(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value or prop value (single pair).")],
    project: ProjectOpt = None,
    measure: Annotated[str | None, typer.Option("--measure", "-m", help="Target a specific measure (queryRef) for per-measure formatting.")] = None,
) -> None:
    """Set visual properties. Supports batch: prop=value prop=value ...

    Use --measure to target per-measure formatting (e.g. accent bar color per measure
    in cardVisual). The measure reference is the queryRef of the measure.
    """
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Parse assignments — support both "prop=value" and legacy "prop value" (2 args)
    pairs: list[tuple[str, str]] = []
    if len(assignments) == 2 and "=" not in assignments[0] and "=" not in assignments[1]:
        # Legacy: pbi visual set page visual prop value
        pairs.append((assignments[0], assignments[1]))
    else:
        for arg in assignments:
            eq = arg.find("=")
            if eq == -1:
                console.print(f"[red]Error:[/red] Invalid assignment '{arg}'. Use prop=value format.")
                raise typer.Exit(1)
            pairs.append((arg[:eq], arg[eq + 1:]))

    for prop, value in pairs:
        old = get_property(vis.data, prop, VISUAL_PROPERTIES, measure_ref=measure)
        try:
            set_property(vis.data, prop, value, VISUAL_PROPERTIES, measure_ref=measure)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {prop}: {e}")
            raise typer.Exit(1)
        new = get_property(vis.data, prop, VISUAL_PROPERTIES, measure_ref=measure)
        label = f"{prop} ({measure})" if measure else prop
        console.print(f"[dim]{label}:[/dim] {old} [dim]→[/dim] {new}")

    vis.save()


@visual_app.command("set-all")
def visual_set_all(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value ...")],
    type_filter: Annotated[str | None, typer.Option("--type", "-t", help="Only apply to visuals of this type (e.g. slicer, card, tableEx).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Set properties on multiple visuals at once.

    Applies the same property assignments to all visuals on a page, or only
    to visuals of a specific type with --type.
    """
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    visuals = proj.get_visuals(pg)
    if type_filter:
        visuals = [v for v in visuals if v.visual_type == type_filter]
        if not visuals:
            console.print(f'[yellow]No visuals of type "{type_filter}" on page "{pg.display_name}".[/yellow]')
            raise typer.Exit(0)

    # Skip group containers
    visuals = [v for v in visuals if "visualGroup" not in v.data]

    # Parse assignments
    pairs: list[tuple[str, str]] = []
    for arg in assignments:
        eq = arg.find("=")
        if eq == -1:
            console.print(f"[red]Error:[/red] Invalid assignment '{arg}'. Use prop=value format.")
            raise typer.Exit(1)
        pairs.append((arg[:eq], arg[eq + 1:]))

    count = 0
    for vis in visuals:
        for prop, value in pairs:
            try:
                set_property(vis.data, prop, value, VISUAL_PROPERTIES)
            except ValueError as e:
                console.print(f"[red]Error:[/red] {vis.name}: {prop}: {e}")
                continue
        vis.save()
        count += 1

    scope = f'type={type_filter}' if type_filter else "all"
    props_str = ", ".join(f"{p}={v}" for p, v in pairs)
    console.print(f'Applied [{props_str}] to [cyan]{count}[/cyan] visuals ({scope})')


@visual_app.command("move")
def visual_move(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    x: Annotated[int, typer.Argument(help="X coordinate.")],
    y: Annotated[int, typer.Argument(help="Y coordinate.")],
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
    width: Annotated[int, typer.Argument(help="Width.")],
    height: Annotated[int, typer.Argument(help="Height.")],
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
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    vis = proj.create_visual(pg, visual_type, x=x, y=y, width=width, height=height)
    if name:
        vis.data["name"] = name
        vis.save()
    display = name or vis.name
    console.print(
        f'Created [cyan]{visual_type}[/cyan] "{display}" on "{pg.display_name}" '
        f"@ {x},{y} {width}x{height}"
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
    target: Annotated[str, typer.Argument(help="Target visual (paste style TO).")],
    to_page: Annotated[Optional[str], typer.Option("--to-page", help="Target page if different from source.")] = None,
    container_only: Annotated[bool, typer.Option("--container-only", help="Copy only container formatting (title, border, background, shadow, etc.).")] = False,
    chart_only: Annotated[bool, typer.Option("--chart-only", help="Copy only chart formatting (legend, axes, labels, etc.).")] = False,
    project: ProjectOpt = None,
) -> None:
    """Copy formatting from one visual to another (format painter).

    Copies visual styling without affecting data bindings, filters, sort, or position.
    By default copies both container and chart formatting. Use --container-only or
    --chart-only to limit scope.
    """
    import copy

    if container_only and chart_only:
        console.print("[red]Error:[/red] --container-only and --chart-only are mutually exclusive.")
        raise typer.Exit(1)

    proj = _get_project(project)
    try:
        src_page = proj.find_page(page)
        src_vis = proj.find_visual(src_page, source)
        tgt_page = proj.find_page(to_page) if to_page else src_page
        tgt_vis = proj.find_visual(tgt_page, target)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    copied = []
    src_visual = src_vis.data.get("visual", {})

    # Container formatting (visualContainerObjects)
    if not chart_only:
        container = src_visual.get("visualContainerObjects")
        if container:
            tgt_vis.data.setdefault("visual", {})["visualContainerObjects"] = copy.deepcopy(container)
            copied.append("container")
        else:
            # Remove from target if source has none
            tgt_vis.data.get("visual", {}).pop("visualContainerObjects", None)

    # Chart formatting (objects)
    if not container_only:
        objects = src_visual.get("objects")
        if objects:
            tgt_vis.data.setdefault("visual", {})["objects"] = copy.deepcopy(objects)
            copied.append("chart")
        else:
            tgt_vis.data.get("visual", {}).pop("objects", None)

    if not copied:
        console.print("[yellow]Source visual has no formatting to copy.[/yellow]")
        raise typer.Exit(0)

    tgt_vis.save()
    scope = " + ".join(copied)
    tgt_label = f'"{tgt_vis.name}"'
    if to_page:
        tgt_label += f' on "{tgt_page.display_name}"'
    console.print(
        f'Copied [cyan]{scope}[/cyan] formatting: '
        f'"{src_vis.name}" → {tgt_label}'
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
    measure: Annotated[bool, typer.Option("--measure", "-m", help="Treat field as a measure (fact) instead of column (dimension).")] = False,
    project: ProjectOpt = None,
) -> None:
    """Bind a column (dimension) or measure (fact) to a visual's data role."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Parse Table.Field
    dot = field.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Field must be in Table.Field format (e.g. Product.Category)")
        raise typer.Exit(1)
    entity, prop = field[:dot], field[dot + 1:]

    # Auto-detect field type from semantic model if not forced
    field_type = "measure" if measure else "column"
    if not measure:
        try:
            from pbi.model import SemanticModel
            model = SemanticModel.load(proj.root)
            _, resolved_prop, resolved_type = model.resolve_field(field)
            field_type = resolved_type
            prop = resolved_prop  # Use canonical name from model
        except (FileNotFoundError, ValueError):
            pass  # No model available, use user's specification

    proj.add_binding(vis, role, entity, prop, field_type=field_type)
    kind = "measure" if field_type == "measure" else "column"
    console.print(
        f'Bound [cyan]{entity}.{prop}[/cyan] ({kind}) → '
        f'{vis.visual_type} role "[bold]{role}[/bold]"'
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
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    removed = proj.remove_binding(vis, role, field_ref=field)
    if removed:
        target = f" ({field})" if field else ""
        console.print(f'Removed {removed} binding(s) from role "[bold]{role}[/bold]"{target}')
    else:
        console.print(f'[yellow]No bindings found for role "{role}"[/yellow]')


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
    from pbi.roles import VISUAL_ROLES

    if visual_type:
        vtype_lower = visual_type.lower()
        matches = {k: v for k, v in VISUAL_ROLES.items() if vtype_lower in k.lower()}
        if not matches:
            console.print(f'[red]Unknown visual type "{visual_type}".[/red]')
            console.print("[dim]Use 'pbi visual types' to see all known types.[/dim]")
            raise typer.Exit(1)
        for vtype, roles in matches.items():
            table = Table(title=vtype, box=box.SIMPLE)
            table.add_column("Role", style="bold cyan")
            table.add_column("Description")
            table.add_column("Multi", style="dim", justify="center")
            for role in roles:
                table.add_row(role["name"], role["description"], role["multi"])
            console.print(table)
        return

    table = Table(title="Visual Types & Data Roles", box=box.SIMPLE)
    table.add_column("Visual Type", style="cyan")
    table.add_column("Roles")

    for vtype, roles in sorted(VISUAL_ROLES.items()):
        role_names = ", ".join(r["name"] for r in roles)
        table.add_row(vtype, role_names)

    console.print(table)
    console.print("\n[dim]Use 'pbi visual types <type>' for detailed role info.[/dim]")


@visual_app.command("sort")
def visual_sort(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    field: Annotated[Optional[str], typer.Argument(help="Sort field as Table.Field (omit to show current sort).")] = None,
    asc: Annotated[bool, typer.Option("--asc", help="Sort ascending (default is descending).")] = False,
    clear: Annotated[bool, typer.Option("--clear", help="Remove sort definition.")] = False,
    measure: Annotated[bool, typer.Option("--measure", "-m", help="Treat field as a measure.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set, show, or clear a visual's sort definition."""
    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if clear:
        if proj.clear_sort(vis):
            console.print("Sort definition removed.")
        else:
            console.print("[dim]No sort definition to remove.[/dim]")
        return

    if field is None:
        # Show current sort
        sorts = proj.get_sort(vis)
        if not sorts:
            console.print("[dim]No sort definition.[/dim]")
            return
        for entity, prop, ftype, direction in sorts:
            kind = " (measure)" if ftype == "measure" else ""
            console.print(f"[cyan]{entity}.{prop}[/cyan]{kind} {direction}")
        return

    # Parse Table.Field
    dot = field.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Field must be Table.Field format.")
        raise typer.Exit(1)
    entity, prop = field[:dot], field[dot + 1:]

    # Auto-detect field type from semantic model
    field_type = "measure" if measure else "column"
    if not measure:
        try:
            from pbi.model import SemanticModel
            model = SemanticModel.load(proj.root)
            _, prop, field_type = model.resolve_field(field)
        except (FileNotFoundError, ValueError):
            pass

    descending = not asc  # --asc overrides default --desc
    proj.set_sort(vis, entity, prop, field_type=field_type, descending=descending)
    direction = "Descending" if descending else "Ascending"
    console.print(
        f'Sort set: [cyan]{entity}.{prop}[/cyan] {direction}'
    )


@visual_app.command("format")
def visual_format(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    prop: Annotated[Optional[str], typer.Argument(help="Property as object.prop (e.g. dataPoint.fill). Omit to show all.")] = None,
    measure: Annotated[Optional[str], typer.Option("--measure", help="Measure ref (Table.Measure) for color-by-measure.")] = None,
    gradient: Annotated[bool, typer.Option("--gradient", help="Use gradient (color scale) mode.")] = False,
    input_field: Annotated[Optional[str], typer.Option("--input", help="Input field for gradient (Table.Field).")] = None,
    min_color: Annotated[Optional[str], typer.Option("--min-color", help="Gradient minimum color (#hex).")] = None,
    min_value: Annotated[Optional[float], typer.Option("--min-value", help="Gradient minimum value.")] = None,
    mid_color: Annotated[Optional[str], typer.Option("--mid-color", help="Gradient midpoint color (#hex). Makes 3-stop.")] = None,
    mid_value: Annotated[Optional[float], typer.Option("--mid-value", help="Gradient midpoint value.")] = None,
    max_color: Annotated[Optional[str], typer.Option("--max-color", help="Gradient maximum color (#hex).")] = None,
    max_value: Annotated[Optional[float], typer.Option("--max-value", help="Gradient maximum value.")] = None,
    clear: Annotated[bool, typer.Option("--clear", help="Remove conditional formatting from this property.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set, show, or clear conditional formatting on a visual property."""
    from pbi.formatting import (
        get_conditional_formats,
        build_measure_format, build_gradient_format, GradientStop,
        set_conditional_format, clear_conditional_format,
    )

    proj = _get_project(project)
    try:
        pg = proj.find_page(page)
        vis = proj.find_visual(pg, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Show mode — no property specified
    if prop is None:
        formats = get_conditional_formats(vis.data)
        if not formats:
            console.print("[dim]No conditional formatting on this visual.[/dim]")
            return
        tbl = Table(title="Conditional Formatting", box=box.SIMPLE)
        tbl.add_column("Property", style="cyan")
        tbl.add_column("Type")
        tbl.add_column("Field", style="bold")
        tbl.add_column("Details", style="dim")
        for f in formats:
            tbl.add_row(f"{f.object_name}.{f.property_name}", f.format_type, f.field_ref, f.details)
        console.print(tbl)
        return

    # Parse object.property
    dot = prop.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Property must be object.prop format (e.g. dataPoint.fill).")
        raise typer.Exit(1)
    obj_name, prop_name = prop[:dot], prop[dot + 1:]

    # Clear mode
    if clear:
        if clear_conditional_format(vis.data, obj_name, prop_name):
            vis.save()
            console.print(f"Cleared conditional formatting from [cyan]{prop}[/cyan].")
        else:
            console.print(f"[dim]No conditional formatting on {prop}.[/dim]")
        return

    # Validate: exactly one of --measure or --gradient
    if measure and gradient:
        console.print("[red]Error:[/red] Use either --measure or --gradient, not both.")
        raise typer.Exit(1)
    if not measure and not gradient:
        console.print("[red]Error:[/red] Specify --measure or --gradient.")
        raise typer.Exit(1)

    # Measure mode
    if measure:
        m_dot = measure.find(".")
        if m_dot == -1:
            console.print("[red]Error:[/red] --measure must be Table.Measure format.")
            raise typer.Exit(1)
        m_entity, m_prop = measure[:m_dot], measure[m_dot + 1:]
        value = build_measure_format(m_entity, m_prop)
        set_conditional_format(vis.data, obj_name, prop_name, value)
        vis.save()
        console.print(
            f"Set [cyan]{prop}[/cyan] = measure [bold]{m_entity}.{m_prop}[/bold]"
        )
        return

    # Gradient mode
    if not input_field:
        console.print("[red]Error:[/red] --gradient requires --input (Table.Field).")
        raise typer.Exit(1)
    if min_color is None or min_value is None or max_color is None or max_value is None:
        console.print("[red]Error:[/red] --gradient requires --min-color, --min-value, --max-color, --max-value.")
        raise typer.Exit(1)

    i_dot = input_field.find(".")
    if i_dot == -1:
        console.print("[red]Error:[/red] --input must be Table.Field format.")
        raise typer.Exit(1)
    i_entity, i_prop = input_field[:i_dot], input_field[i_dot + 1:]

    min_c = min_color if min_color.startswith("#") else f"#{min_color}"
    max_c = max_color if max_color.startswith("#") else f"#{max_color}"

    mid_stop = None
    if mid_color is not None and mid_value is not None:
        mid_c = mid_color if mid_color.startswith("#") else f"#{mid_color}"
        mid_stop = GradientStop(mid_c, mid_value)
    elif mid_color is not None or mid_value is not None:
        console.print("[red]Error:[/red] Both --mid-color and --mid-value are required for 3-stop gradient.")
        raise typer.Exit(1)

    value = build_gradient_format(
        i_entity, i_prop,
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
    console.print(
        f"Set [cyan]{prop}[/cyan] = gradient by [bold]{i_entity}.{i_prop}[/bold] [{stops}]"
    )


@visual_app.command("column")
def visual_column(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    column: Annotated[Optional[str], typer.Argument(help="Column: Table.Field, display name, or index. Omit to list all.")] = None,
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
    """List, resize, rename, or format table/matrix columns."""
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
            console.print("[dim]No columns (is this a table/matrix visual?).[/dim]")
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


@visual_app.command("props")
def visual_props() -> None:
    """List available visual properties."""
    table = Table(title="Visual Properties", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for name, vtype, desc in list_properties(VISUAL_PROPERTIES):
        table.add_row(name, vtype, desc)

    console.print(table)
    console.print(
        "\n[dim]You can also use raw JSON paths "
        "(e.g. 'visual.objects.legend[0].properties.show')[/dim]"
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

@filter_app.command("list")
def filter_list(
    page: Annotated[Optional[str], typer.Option("--page", help="Page name (omit for report-level).")] = None,
    visual: Annotated[Optional[str], typer.Option("--visual", help="Visual name (requires --page).")] = None,
    project: ProjectOpt = None,
) -> None:
    """List filters at report, page, or visual level."""
    from pbi.filters import load_level_data, get_filters, parse_filter

    proj = _get_project(project)
    try:
        data, level, _ = load_level_data(proj, page, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    filters = get_filters(data)
    if not filters:
        console.print(f"[dim]No filters at {level} level.[/dim]")
        return

    table = Table(title=f"{level.title()} Filters", box=box.SIMPLE)
    table.add_column("Field", style="cyan")
    table.add_column("Type")
    table.add_column("Values/Condition")
    table.add_column("Hidden", style="dim", justify="center")
    table.add_column("Locked", style="dim", justify="center")

    for f in filters:
        info = parse_filter(f, level)
        table.add_row(
            f"{info.field_entity}.{info.field_prop}",
            info.filter_type,
            ", ".join(info.values) if info.values else "-",
            "yes" if info.is_hidden else "",
            "yes" if info.is_locked else "",
        )

    console.print(table)


@filter_app.command("add")
def filter_add(
    field: Annotated[str, typer.Argument(help="Field as Table.Field (e.g. Product.Category).")],
    values: Annotated[Optional[str], typer.Option("--values", "-v", help="Comma-separated values for categorical filter.")] = None,
    min_val: Annotated[Optional[str], typer.Option("--min", help="Minimum value for range filter.")] = None,
    max_val: Annotated[Optional[str], typer.Option("--max", help="Maximum value for range filter.")] = None,
    topn: Annotated[Optional[int], typer.Option("--topn", help="Top N items count.")] = None,
    topn_by: Annotated[Optional[str], typer.Option("--topn-by", help="Order-by field for TopN (Table.Measure).")] = None,
    bottom: Annotated[bool, typer.Option("--bottom", help="Use Bottom N instead of Top N.")] = False,
    relative: Annotated[Optional[str], typer.Option("--relative", help="Relative date: 'InLast 7 Days', 'InThis 1 Months', 'InNext 2 Weeks'.")] = None,
    include_today: Annotated[bool, typer.Option("--include-today/--no-include-today", help="Include today in relative date filter.")] = True,
    page: Annotated[Optional[str], typer.Option("--page", help="Page name (omit for report-level).")] = None,
    visual: Annotated[Optional[str], typer.Option("--visual", help="Visual name (requires --page).")] = None,
    hidden: Annotated[bool, typer.Option("--hidden", help="Hide filter in view mode.")] = False,
    locked: Annotated[bool, typer.Option("--locked", help="Lock filter in view mode.")] = False,
    measure: Annotated[bool, typer.Option("--measure", "-m", help="Field is a measure.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Add a filter. Use --values for categorical, --min/--max for range, --topn for Top N, --relative for relative date."""
    from pbi.filters import (
        load_level_data, save_level_data,
        add_categorical_filter, add_range_filter,
        add_topn_filter, add_relative_date_filter,
    )

    has_categorical = values is not None
    has_range = min_val is not None or max_val is not None
    has_topn = topn is not None
    has_relative = relative is not None
    filter_count = sum([has_categorical, has_range, has_topn, has_relative])

    if filter_count == 0:
        console.print("[red]Error:[/red] Specify --values (categorical), --min/--max (range), --topn (Top N), or --relative (relative date).")
        raise typer.Exit(1)
    if filter_count > 1:
        console.print("[red]Error:[/red] Use only one filter type per command.")
        raise typer.Exit(1)

    dot = field.find(".")
    if dot == -1:
        console.print("[red]Error:[/red] Field must be Table.Field format.")
        raise typer.Exit(1)
    entity, prop = field[:dot], field[dot + 1:]

    # Auto-detect field type from model
    field_type = "measure" if measure else "column"
    if not measure:
        try:
            from pbi.model import SemanticModel
            proj_obj = _get_project(project)
            model = SemanticModel.load(proj_obj.root)
            _, prop, field_type = model.resolve_field(field)
        except (FileNotFoundError, ValueError):
            pass

    proj = _get_project(project)
    try:
        data, level, target = load_level_data(proj, page, visual)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if has_categorical:
        val_list = [v.strip() for v in values.split(",")]
        add_categorical_filter(
            data, entity, prop, val_list,
            field_type=field_type, is_hidden=hidden, is_locked=locked,
        )
        save_level_data(data, target)
        console.print(
            f'Added categorical filter on [cyan]{entity}.{prop}[/cyan] '
            f'= [{", ".join(val_list)}] at {level} level'
        )
    elif has_range:
        add_range_filter(
            data, entity, prop, min_val=min_val, max_val=max_val,
            field_type=field_type, is_hidden=hidden,
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
    elif has_topn:
        if not topn_by:
            console.print("[red]Error:[/red] --topn requires --topn-by (Table.Measure) to specify the order-by field.")
            raise typer.Exit(1)
        by_dot = topn_by.find(".")
        if by_dot == -1:
            console.print("[red]Error:[/red] --topn-by must be Table.Field format.")
            raise typer.Exit(1)
        order_entity, order_prop = topn_by[:by_dot], topn_by[by_dot + 1:]
        order_field_type = "measure"  # TopN order-by is typically a measure
        try:
            from pbi.model import SemanticModel
            model = SemanticModel.load(proj.root)
            _, order_prop, order_field_type = model.resolve_field(topn_by)
        except (FileNotFoundError, ValueError):
            pass
        direction = "Bottom" if bottom else "Top"
        add_topn_filter(
            data, entity, prop, n=topn,
            order_entity=order_entity, order_prop=order_prop,
            order_field_type=order_field_type, direction=direction,
            field_type=field_type, is_hidden=hidden,
        )
        save_level_data(data, target)
        console.print(
            f'Added {direction} {topn} filter on [cyan]{entity}.{prop}[/cyan] '
            f'by {order_entity}.{order_prop} at {level} level'
        )
    elif has_relative:
        # Parse "InLast 7 Days" format
        parts = relative.split()
        if len(parts) != 3:
            console.print("[red]Error:[/red] --relative must be 'Operator Count Unit' (e.g. 'InLast 7 Days').")
            console.print("[dim]Operators: InLast, InThis, InNext[/dim]")
            console.print("[dim]Units: Days, Weeks, Months, Quarters, Years[/dim]")
            raise typer.Exit(1)
        rel_op, rel_count_str, rel_unit = parts
        valid_ops = ("InLast", "InThis", "InNext")
        valid_units = ("Days", "Weeks", "Months", "Quarters", "Years")
        if rel_op not in valid_ops:
            console.print(f"[red]Error:[/red] Operator must be one of: {', '.join(valid_ops)}")
            raise typer.Exit(1)
        if rel_unit not in valid_units:
            console.print(f"[red]Error:[/red] Unit must be one of: {', '.join(valid_units)}")
            raise typer.Exit(1)
        try:
            rel_count = int(rel_count_str)
        except ValueError:
            console.print(f"[red]Error:[/red] Count must be an integer, got '{rel_count_str}'.")
            raise typer.Exit(1)
        add_relative_date_filter(
            data, entity, prop,
            operator=rel_op, time_units_count=rel_count,
            time_unit_type=rel_unit, include_today=include_today,
            field_type=field_type, is_hidden=hidden,
        )
        save_level_data(data, target)
        console.print(
            f'Added relative date filter on [cyan]{entity}.{prop}[/cyan] '
            f'{rel_op.lower()} {rel_count} {rel_unit.lower()} at {level} level'
        )


@filter_app.command("remove")
def filter_remove(
    field: Annotated[str, typer.Argument(help="Filter field (Table.Field) or filter name to remove.")],
    page: Annotated[Optional[str], typer.Option("--page", help="Page name (omit for report-level).")] = None,
    visual: Annotated[Optional[str], typer.Option("--visual", help="Visual name (requires --page).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Remove a filter by field reference or filter name."""
    from pbi.filters import load_level_data, save_level_data, remove_filter

    proj = _get_project(project)
    try:
        data, level, target = load_level_data(proj, page, visual)
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


if __name__ == "__main__":
    app()
