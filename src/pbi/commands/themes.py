"""Theme CLI commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project, parse_property_assignments, resolve_output_path

theme_app = typer.Typer(help="Theme operations.", no_args_is_help=True)
theme_preset_app = typer.Typer(help="Saved theme preset operations.", no_args_is_help=True)
theme_app.add_typer(theme_preset_app, name="preset")
theme_style_app = typer.Typer(help="Visual style overrides in the theme.", no_args_is_help=True)
theme_app.add_typer(theme_style_app, name="style")


@theme_app.command("list")
def theme_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List active themes (base + custom)."""
    from pbi.themes import get_themes

    proj = get_project(project)
    themes = get_themes(proj)

    if not themes:
        console.print("[yellow]No themes configured.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        rows = [{"type": "custom" if t.is_custom else "base", "name": t.name, "source": t.source} for t in themes]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Type")
    table.add_column("Name")
    table.add_column("Source")
    for theme in themes:
        label = "custom" if theme.is_custom else "base"
        table.add_row(label, theme.name, theme.source)
    console.print(table)


@theme_app.command("apply")
def theme_apply(
    theme_file: Annotated[str, typer.Argument(help="Path to theme JSON file.")],
    project: ProjectOpt = None,
) -> None:
    """Apply a custom theme JSON file to the project."""
    import json

    from pbi.themes import apply_theme

    proj = get_project(project)
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

    proj = get_project(project)
    out_path = resolve_output_path(Path(output), base_dir=Path.cwd())

    try:
        name = export_theme(proj, out_path)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    console.print(f'Exported theme "[cyan]{name}[/cyan]" -> {out_path}')


@theme_app.command("delete")
def theme_delete(
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete the custom theme from the project (reverts to base theme)."""
    from pbi.themes import remove_theme

    proj = get_project(project)

    if not force:
        confirm = typer.confirm("Delete the custom theme?")
        if not confirm:
            raise typer.Abort()

    try:
        name = remove_theme(proj)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if name:
        console.print(f'Deleted custom theme "[cyan]{name}[/cyan]"')
    else:
        console.print("[yellow]No custom theme to delete.[/yellow]")


@theme_app.command("migrate")
def theme_migrate(
    old_theme: Annotated[str, typer.Argument(help="Path to old theme JSON file.")],
    new_theme: Annotated[str, typer.Argument(help="Path to new theme JSON file.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what would change without modifying files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Migrate visual property overrides from old theme colors to new theme colors.

    Compares the two theme JSONs to build a color mapping, then scans all
    visuals for per-visual property overrides that match old colors and
    replaces them with the corresponding new colors.
    """
    from pbi.themes import migrate_theme

    proj = get_project(project)
    old_path = Path(old_theme).resolve()
    new_path = Path(new_theme).resolve()

    for label, path in [("Old theme", old_path), ("New theme", new_path)]:
        if not path.exists():
            console.print(f"[red]Error:[/red] {label} not found: {path}")
            raise typer.Exit(1)

    result = migrate_theme(proj, old_path, new_path, dry_run=dry_run)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    if not result.replacements and not result.page_background_changes:
        console.print("[dim]No color differences found between themes.[/dim]")
        return

    for repl in result.replacements:
        if repl.count > 0:
            verb = "Would update" if dry_run else "Updated"
            console.print(
                f"{prefix}{verb} [cyan]{repl.old_color}[/cyan] [dim]->[/dim] "
                f"[cyan]{repl.new_color}[/cyan] on {repl.count} visual(s)"
            )

    if result.page_background_changes:
        verb = "Would update" if dry_run else "Updated"
        console.print(
            f"{prefix}{verb} background.color on "
            f"[cyan]{result.page_background_changes}[/cyan] page(s)"
        )

    if not result.total_changes:
        console.print("[dim]No matching color overrides found in visuals.[/dim]")


@theme_app.command("audit")
def theme_audit(
    fix: Annotated[bool, typer.Option("--fix", help="Remove redundant overrides that match the theme.")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Show what --fix would do without modifying files.")] = False,
    page: Annotated[Optional[str], typer.Option("--page", help="Audit a single page.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Audit visuals for properties that override the active theme.

    Reports redundant overrides (matching theme) and conflicts (differing from theme).
    Use --fix to remove redundant overrides so the theme controls styling.
    """
    import json

    from pbi.themes import audit_theme_overrides, fix_theme_overrides

    proj = get_project(project)

    try:
        result = audit_theme_overrides(proj, page_filter=page)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if not result.overrides:
        console.print("[dim]No per-visual overrides found that match theme properties.[/dim]")
        return

    if as_json:
        rows = [
            {
                "page": o.page_name,
                "visual": o.visual_name,
                "visualType": o.visual_type,
                "object": o.object_name,
                "property": o.property_name,
                "visualValue": o.visual_value,
                "themeValue": o.theme_value,
                "redundant": o.is_match,
            }
            for o in result.overrides
        ]
        console.print_json(json.dumps(rows, indent=2))
        return

    prefix = "[dim](dry run)[/dim] " if dry_run else ""

    # Summary
    console.print(
        f"{result.visuals_with_overrides} visual(s) override theme defaults "
        f"({result.redundant_count} redundant, {result.conflict_count} conflict)"
    )

    # Show conflicts (visual != theme)
    conflicts = [o for o in result.overrides if not o.is_match]
    if conflicts:
        conflict_table = Table(title="Conflicts (differ from theme)", box=box.SIMPLE)
        conflict_table.add_column("Page/Visual", style="cyan")
        conflict_table.add_column("Property")
        conflict_table.add_column("Visual Value")
        conflict_table.add_column("Theme Value", style="dim")
        for o in conflicts:
            conflict_table.add_row(
                f"{o.page_name}/{o.visual_name}",
                f"{o.object_name}.{o.property_name}",
                o.visual_value,
                o.theme_value,
            )
        console.print(conflict_table)

    # Show redundant (visual == theme)
    redundant = [o for o in result.overrides if o.is_match]
    if redundant:
        red_table = Table(title="Redundant (match theme, can be removed)", box=box.SIMPLE)
        red_table.add_column("Page/Visual", style="cyan")
        red_table.add_column("Property")
        red_table.add_column("Value", style="dim")
        for o in redundant:
            red_table.add_row(
                f"{o.page_name}/{o.visual_name}",
                f"{o.object_name}.{o.property_name}",
                o.visual_value,
            )
        console.print(red_table)

    if fix or dry_run:
        if not redundant:
            console.print("[dim]No redundant overrides to remove.[/dim]")
            return

        removed = fix_theme_overrides(proj, result, dry_run=dry_run)
        verb = "Would remove" if dry_run else "Removed"
        console.print(f"{prefix}{verb} [cyan]{removed}[/cyan] redundant override(s)")
    elif redundant:
        console.print(
            f"\n[yellow]Run `pbi theme audit --fix` to remove "
            f"{result.redundant_count} redundant override(s).[/yellow]"
        )


@theme_app.command("create")
def theme_create(
    name: Annotated[str, typer.Argument(help="Theme name.")],
    foreground: Annotated[Optional[str], typer.Option("--foreground", help="Primary text color (hex).")] = None,
    background: Annotated[Optional[str], typer.Option("--background", help="Page background color (hex).")] = None,
    accent: Annotated[Optional[str], typer.Option("--accent", help="Accent/tableAccent color (hex).")] = None,
    font: Annotated[Optional[str], typer.Option("--font", help="Base font family.")] = None,
    data_colors: Annotated[Optional[str], typer.Option("--data-colors", help="Comma-separated data series colors.")] = None,
    good: Annotated[Optional[str], typer.Option("--good", help="Positive sentiment color (hex).")] = None,
    bad: Annotated[Optional[str], typer.Option("--bad", help="Negative sentiment color (hex).")] = None,
    neutral: Annotated[Optional[str], typer.Option("--neutral", help="Neutral sentiment color (hex).")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Print theme JSON without applying.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Create and apply a theme from brand colors."""
    import json
    import tempfile

    from pbi.themes import apply_theme, create_theme

    kwargs: dict = {}
    if foreground:
        kwargs["foreground"] = foreground
    if background:
        kwargs["background"] = background
    if accent:
        kwargs["accent"] = accent
    if font:
        kwargs["font"] = font
    if data_colors:
        kwargs["data_colors"] = [c.strip() for c in data_colors.split(",")]
    if good:
        kwargs["good"] = good
    if bad:
        kwargs["bad"] = bad
    if neutral:
        kwargs["neutral"] = neutral

    try:
        theme_data = create_theme(name, **kwargs)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if dry_run:
        console.print_json(json.dumps(theme_data, indent=2))
        return

    proj = get_project(project)

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    ) as f:
        json.dump(theme_data, f, indent=2, ensure_ascii=False)
        tmp_path = Path(f.name)

    try:
        apply_theme(proj, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    console.print(f'Created theme "[cyan]{name}[/cyan]"')


@theme_app.command("get")
def theme_get(
    props: Annotated[Optional[list[str]], typer.Argument(help="Property or properties to read (omit for overview).")] = None,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump full theme JSON.")] = False,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show theme properties or overview."""
    import json

    from pbi.themes import get_theme_data, get_theme_property

    proj = get_project(project)

    try:
        data = get_theme_data(proj)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        console.print_json(json.dumps(data, indent=2))
        return

    if props:
        if as_json:
            result = {}
            for prop in props:
                result[prop] = get_theme_property(data, prop)
            console.print_json(json.dumps(result, indent=2))
            return

        if len(props) == 1:
            value = get_theme_property(data, props[0])
            if isinstance(value, (dict, list)):
                console.print_json(json.dumps(value, indent=2))
            else:
                console.print(str(value) if value is not None else "[dim](none)[/dim]")
            return

        table = Table(title="Theme Properties", box=box.SIMPLE)
        table.add_column("Property", style="cyan")
        table.add_column("Value")
        for prop in props:
            value = get_theme_property(data, prop)
            display = str(value) if value is not None else ""
            table.add_row(prop, display)
        console.print(table)
        return

    # Overview: palette + text classes + data colors
    if as_json:
        overview: dict = {}
        for key in ("foreground", "foregroundNeutralSecondary", "foregroundNeutralTertiary",
                     "background", "backgroundLight", "backgroundNeutral",
                     "tableAccent", "good", "neutral", "bad"):
            overview[key] = data.get(key)
        overview["dataColors"] = data.get("dataColors", [])
        overview["textClasses"] = data.get("textClasses", {})
        console.print_json(json.dumps(overview, indent=2))
        return

    # Palette table
    table = Table(title=f"Theme: {data.get('name', '?')}", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    for key in ("foreground", "foregroundNeutralSecondary", "foregroundNeutralTertiary",
                "background", "backgroundLight", "backgroundNeutral",
                "tableAccent", "hyperlink", "good", "neutral", "bad",
                "maximum", "center", "minimum"):
        val = data.get(key)
        if val is not None:
            table.add_row(key, str(val))
    console.print(table)

    # Data colors
    colors = data.get("dataColors", [])
    if colors:
        console.print(f"\n[bold]Data Colors[/bold] ({len(colors)}): {', '.join(colors[:8])}{'...' if len(colors) > 8 else ''}")

    # Text classes
    tc = data.get("textClasses", {})
    if tc:
        tc_table = Table(title="Text Classes", box=box.SIMPLE)
        tc_table.add_column("Class", style="cyan")
        tc_table.add_column("Font")
        tc_table.add_column("Size", style="dim")
        tc_table.add_column("Color")
        for cls_name in ("title", "header", "callout", "label"):
            cls = tc.get(cls_name, {})
            tc_table.add_row(
                cls_name,
                cls.get("fontFace", ""),
                str(cls.get("fontSize", "")),
                cls.get("color", ""),
            )
        console.print(tc_table)

    # Visual styles
    vs = data.get("visualStyles", {})
    if vs:
        from pbi.themes import decode_theme_style_value

        vs_table = Table(title="Visual Styles", box=box.SIMPLE)
        vs_table.add_column("Type", style="cyan")
        vs_table.add_column("Object")
        vs_table.add_column("Property")
        vs_table.add_column("Value")
        vs_table.add_column("Selector", style="dim")
        for vtype in sorted(vs.keys()):
            roles = vs[vtype]
            if not isinstance(roles, dict):
                continue
            for objects in roles.values():
                if not isinstance(objects, dict):
                    continue
                for obj_name in sorted(objects.keys()):
                    entries = objects[obj_name]
                    if not isinstance(entries, list):
                        continue
                    for entry in entries:
                        if not isinstance(entry, dict):
                            continue
                        sid = entry.get("$id", "")
                        for prop_name, raw_val in entry.items():
                            if prop_name == "$id":
                                continue
                            vs_table.add_row(
                                vtype, obj_name, prop_name,
                                str(decode_theme_style_value(raw_val)), sid,
                            )
        console.print(vs_table)


@theme_app.command("set")
def theme_set(
    assignments: Annotated[list[str], typer.Argument(help="Property assignments: prop=value [prop=value ...].")],
    no_cascade: Annotated[bool, typer.Option("--no-cascade", help="Don't cascade derived colors.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Modify properties of the active custom theme."""
    from pbi.themes import (
        get_theme_data,
        get_theme_property,
        save_theme_data,
        set_theme_property,
    )

    proj = get_project(project)

    try:
        data = get_theme_data(proj)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    changed = False
    for prop, value in pairs:
        old = get_theme_property(data, prop)
        try:
            keys = set_theme_property(data, prop, value, cascade=not no_cascade)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {prop}: {e}")
            raise typer.Exit(1)

        new = get_theme_property(data, prop)
        old_str = str(old) if old is not None else "(none)"
        new_str = str(new) if new is not None else "(none)"
        if old_str == new_str:
            console.print(f"[dim]No change:[/dim] [cyan]{prop}[/cyan] is already {new_str}")
        else:
            console.print(f"[dim]{prop}:[/dim] {old_str} [dim]->[/dim] {new_str}")
            changed = True
            # Show cascaded keys
            for key in keys[1:]:
                console.print(f"  [dim]cascaded:[/dim] [cyan]{key}[/cyan]")

    if changed:
        save_theme_data(proj, data)


@theme_app.command("properties")
def theme_properties() -> None:
    """List writable theme properties."""
    from pbi.themes import THEME_PROPERTIES

    table = Table(title="Theme Properties", box=box.SIMPLE)
    table.add_column("Property", style="cyan")
    table.add_column("Type", style="dim")
    table.add_column("Description")

    for prop_path, prop_type, desc in THEME_PROPERTIES:
        table.add_row(prop_path, prop_type, desc)

    console.print(table)


@theme_app.command("save")
def theme_save(
    name: Annotated[str, typer.Argument(help="Preset name.")],
    description: Annotated[Optional[str], typer.Option("--description", help="Preset description.")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite existing preset.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Save as global preset.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Save the active custom theme as a reusable preset."""
    from pbi.themes import get_theme_data, save_theme_preset

    proj = get_project(project)

    try:
        data = get_theme_data(proj)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        path = save_theme_preset(
            proj if not global_scope else None,
            name, data,
            description=description,
            overwrite=force,
            global_scope=global_scope,
        )
    except (FileExistsError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    scope = "global" if global_scope else "project"
    console.print(f'Saved theme preset "[cyan]{name}[/cyan]" ({scope}) -> {path}')


@theme_app.command("load")
def theme_load(
    name: Annotated[str, typer.Argument(help="Preset name to load.")],
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Load from global presets only.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Apply a saved theme preset to the project."""
    import tempfile

    from pbi.themes import apply_theme, get_theme_preset

    proj = get_project(project)

    try:
        preset = get_theme_preset(
            proj if not global_scope else None,
            name,
            global_scope=global_scope,
        )
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # Write theme data to a temp file and apply via existing infrastructure
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8",
    ) as f:
        import json

        json.dump(preset.data, f, indent=2, ensure_ascii=False)
        tmp_path = Path(f.name)

    try:
        apply_theme(proj, tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)

    console.print(f'Loaded theme preset "[cyan]{preset.name}[/cyan]" ({preset.scope})')


# ── Theme preset subcommands ────────────────────────────────────────────


@theme_preset_app.command("list")
def theme_preset_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Show only global presets.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List saved theme presets (project + global)."""
    from pbi.themes import list_theme_presets

    proj = get_project(project) if not global_scope else None
    presets = list_theme_presets(proj, global_scope=global_scope)

    if not presets:
        console.print("[yellow]No theme presets saved. Use `pbi theme save` to save one.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        rows = [
            {"name": p.name, "scope": p.scope, "description": p.description or ""}
            for p in presets
        ]
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Name", style="cyan")
    table.add_column("Scope", style="dim")
    table.add_column("Description", style="dim")
    for preset in presets:
        table.add_row(preset.name, preset.scope, preset.description or "")
    console.print(table)


@theme_preset_app.command("get")
def theme_preset_get(
    name: Annotated[str, typer.Argument(help="Preset name.")],
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Look up in global presets only.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show a saved theme preset as YAML."""
    from pbi.themes import dump_theme_preset, get_theme_preset

    proj = get_project(project) if not global_scope else None
    try:
        preset = get_theme_preset(proj, name, global_scope=global_scope)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    typer.echo(dump_theme_preset(preset), nl=False)


@theme_preset_app.command("delete")
def theme_preset_delete(
    name: Annotated[str, typer.Argument(help="Preset name to delete.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    global_scope: Annotated[bool, typer.Option("--global", "-g", help="Delete from global presets.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a saved theme preset."""
    from pbi.themes import delete_theme_preset

    proj = get_project(project) if not global_scope else None
    if not force:
        confirm = typer.confirm(f'Delete theme preset "{name}"?')
        if not confirm:
            raise typer.Abort()

    try:
        deleted = delete_theme_preset(proj, name, global_scope=global_scope)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if deleted:
        console.print(f'Deleted theme preset "[cyan]{name}[/cyan]"')
    else:
        console.print(f'[yellow]Theme preset "{name}" not found.[/yellow]')


@theme_preset_app.command("clone")
def theme_preset_clone(
    name: Annotated[str, typer.Argument(help="Preset to clone.")],
    new_name: Annotated[Optional[str], typer.Option("--name", "-n", help="New name for the clone.")] = None,
    to_global: Annotated[bool, typer.Option("--to-global", help="Clone project → global.")] = False,
    to_project: Annotated[bool, typer.Option("--to-project", help="Clone global → project.")] = False,
    force: Annotated[bool, typer.Option("--force", "-f", help="Overwrite if exists.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Clone a theme preset between project and global scope."""
    from pbi.themes import clone_theme_preset

    if not to_global and not to_project:
        console.print("[red]Error:[/red] Specify --to-global or --to-project.")
        raise typer.Exit(1)
    if to_global and to_project:
        console.print("[red]Error:[/red] Use either --to-global or --to-project, not both.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        path = clone_theme_preset(proj, name, to_global=to_global, new_name=new_name, overwrite=force)
    except (FileExistsError, FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    target_name = new_name or name
    direction = "global" if to_global else "project"
    console.print(f'Cloned "[cyan]{name}[/cyan]" → {direction} as "[cyan]{target_name}[/cyan]" → {path}')


# ── Theme style subcommands ─────────────────────────────────────────────


@theme_style_app.command("list")
def theme_style_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List visual types with style overrides in the theme."""
    from pbi.themes import get_theme_data, get_visual_style_entries, list_visual_style_types

    proj = get_project(project)
    try:
        data = get_theme_data(proj)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    types = list_visual_style_types(data)
    if not types:
        console.print("[yellow]No visual style overrides in this theme.[/yellow]")
        raise typer.Exit(0)

    if as_json:
        import json

        rows = []
        for vtype in types:
            entries = get_visual_style_entries(data, vtype) or {}
            rows.append({"visualType": vtype, "objects": sorted(entries.keys())})
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(box=box.SIMPLE)
    table.add_column("Visual Type", style="cyan")
    table.add_column("Objects")
    for vtype in types:
        entries = get_visual_style_entries(data, vtype) or {}
        table.add_row(vtype, ", ".join(sorted(entries.keys())))
    console.print(table)


@theme_style_app.command("get")
def theme_style_get(
    visual_type: Annotated[Optional[str], typer.Argument(help="Visual type (or * for global wildcard).")] = None,
    objects: Annotated[Optional[list[str]], typer.Argument(help="Object name(s) to inspect.")] = None,
    raw: Annotated[bool, typer.Option("--raw", "-r", help="Dump raw JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show visual style overrides for a type or object."""
    import json as json_mod

    from pbi.themes import decode_theme_style_value, get_theme_data, get_visual_style_entries, list_visual_style_types

    proj = get_project(project)
    try:
        data = get_theme_data(proj)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if raw:
        vs = data.get("visualStyles", {})
        if visual_type:
            vs = vs.get(visual_type, {})
        console.print_json(json_mod.dumps(vs, indent=2))
        return

    if not visual_type:
        # Summary — same as list
        types = list_visual_style_types(data)
        if not types:
            console.print("[yellow]No visual style overrides in this theme.[/yellow]")
            raise typer.Exit(0)
        table = Table(box=box.SIMPLE)
        table.add_column("Visual Type", style="cyan")
        table.add_column("Objects")
        for vtype in types:
            entries = get_visual_style_entries(data, vtype) or {}
            table.add_row(vtype, ", ".join(sorted(entries.keys())))
        console.print(table)
        return

    entries = get_visual_style_entries(data, visual_type)
    if entries is None:
        console.print(f'[yellow]No style overrides for "{visual_type}".[/yellow]')
        raise typer.Exit(0)

    if objects:
        # Show properties for specific object(s)
        table = Table(title=f"visualStyles: {visual_type}", box=box.SIMPLE)
        table.add_column("Object", style="cyan")
        table.add_column("Property")
        table.add_column("Value")
        table.add_column("Selector", style="dim")
        for obj_name in objects:
            obj_entries = entries.get(obj_name)
            if not obj_entries:
                console.print(f'[yellow]No object "{obj_name}" for "{visual_type}".[/yellow]')
                continue
            for entry in obj_entries:
                sid = entry.get("$id", "")
                for prop_name, raw_val in entry.items():
                    if prop_name == "$id":
                        continue
                    table.add_row(obj_name, prop_name, str(decode_theme_style_value(raw_val)), sid)
        console.print(table)
        return

    # Show all objects for the type
    table = Table(title=f"visualStyles: {visual_type}", box=box.SIMPLE)
    table.add_column("Object", style="cyan")
    table.add_column("Property")
    table.add_column("Value")
    table.add_column("Selector", style="dim")
    for obj_name in sorted(entries.keys()):
        for entry in entries[obj_name]:
            sid = entry.get("$id", "")
            for prop_name, raw_val in entry.items():
                if prop_name == "$id":
                    continue
                table.add_row(obj_name, prop_name, str(decode_theme_style_value(raw_val)), sid)
    console.print(table)


@theme_style_app.command("set")
def theme_style_set(
    visual_type: Annotated[str, typer.Argument(help="Visual type (or * for global wildcard).")],
    assignments: Annotated[list[str], typer.Argument(help="Assignments: object.property=value [object.property[selector]=value ...].")],
    project: ProjectOpt = None,
) -> None:
    """Set visual style properties in the theme."""
    from pbi.themes import (
        decode_theme_style_value,
        get_theme_data,
        get_visual_style_entries,
        parse_style_assignment,
        save_theme_data,
        set_visual_style_property,
    )

    proj = get_project(project)

    try:
        data = get_theme_data(proj)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    for raw in assignments:
        try:
            obj_name, prop_name, selector, value = parse_style_assignment(raw)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        # Get old value for display
        entries = get_visual_style_entries(data, visual_type)
        old_val = None
        if entries:
            obj_entries = entries.get(obj_name, [])
            for entry in obj_entries:
                if selector and entry.get("$id") != selector:
                    continue
                if not selector and "$id" in entry:
                    continue
                old_val = decode_theme_style_value(entry.get(prop_name))
                break

        try:
            set_visual_style_property(
                data, visual_type, obj_name, prop_name, value,
                selector=selector,
            )
        except ValueError as e:
            console.print(f"[red]Error:[/red] {obj_name}.{prop_name}: {e}")
            raise typer.Exit(1)

        # Get new value for display
        entries = get_visual_style_entries(data, visual_type) or {}
        new_val = None
        for entry in entries.get(obj_name, []):
            if selector and entry.get("$id") != selector:
                continue
            if not selector and "$id" in entry:
                continue
            new_val = decode_theme_style_value(entry.get(prop_name))
            break

        old_str = str(old_val) if old_val is not None else "(none)"
        new_str = str(new_val) if new_val is not None else "(none)"
        sel_label = f" [{selector}]" if selector else ""
        if old_str == new_str:
            console.print(f"[dim]No change:[/dim] [cyan]{obj_name}.{prop_name}{sel_label}[/cyan] is already {new_str}")
        else:
            console.print(f"[dim]{obj_name}.{prop_name}{sel_label}:[/dim] {old_str} [dim]->[/dim] {new_str}")

    save_theme_data(proj, data)


@theme_style_app.command("delete")
def theme_style_delete(
    visual_type: Annotated[str, typer.Argument(help="Visual type to remove overrides for.")],
    object_name: Annotated[Optional[str], typer.Argument(help="Object to remove (omit to remove entire type).")] = None,
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Remove visual style overrides from the theme."""
    from pbi.themes import delete_visual_style, get_theme_data, save_theme_data

    proj = get_project(project)

    try:
        data = get_theme_data(proj)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    target = f"{visual_type}.{object_name}" if object_name else visual_type
    if not force:
        confirm = typer.confirm(f'Delete visual style overrides for "{target}"?')
        if not confirm:
            raise typer.Abort()

    deleted = delete_visual_style(data, visual_type, object_name)
    if deleted:
        save_theme_data(proj, data)
        console.print(f'Deleted visual style overrides for "[cyan]{target}[/cyan]"')
    else:
        console.print(f'[yellow]No visual style overrides for "{target}".[/yellow]')
