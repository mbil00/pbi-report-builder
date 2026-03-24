"""CLI commands for custom visual plugin discovery and schema registration."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Optional

import typer
from rich import box
from rich.table import Table

from pbi.commands.common import ProjectOpt, console, get_project

visual_plugin_app = typer.Typer(
    help="Custom visual plugin operations.",
    no_args_is_help=True,
)


@visual_plugin_app.command("scan")
def custom_visual_scan(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Scan the report for custom visuals not in the built-in schema."""
    from pbi.custom_visuals import scan_custom_visuals

    proj = get_project(project)
    results = scan_custom_visuals(proj)

    if as_json:
        console.print_json(json.dumps(
            [
                {
                    "visualType": r.visual_type,
                    "count": r.visual_count,
                    "pbivizFound": r.pbiviz_path is not None,
                    "pbivizPath": str(r.pbiviz_path) if r.pbiviz_path else None,
                    "schemaInstalled": r.schema_installed,
                }
                for r in results
            ],
            indent=2,
        ))
        return

    if not results:
        console.print("[dim]No custom visuals found. All visuals use built-in types.[/dim]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE, title="Custom Visuals")
    table.add_column("Visual Type", style="cyan")
    table.add_column("Count", justify="right")
    table.add_column(".pbiviz", style="dim")
    table.add_column("Schema", style="dim")

    for r in results:
        pbiviz_status = "[green]found[/green]" if r.pbiviz_path else "[yellow]not found[/yellow]"
        schema_status = "[green]installed[/green]" if r.schema_installed else ""
        table.add_row(
            r.visual_type,
            str(r.visual_count),
            pbiviz_status,
            schema_status,
        )

    console.print(table)

    installable = [r for r in results if r.pbiviz_path and not r.schema_installed]
    if installable:
        types = ", ".join(r.visual_type for r in installable)
        console.print(
            f"\n[dim]Run [/dim]`pbi visual plugin install`[dim] to extract and register schemas for: {types}[/dim]"
        )


@visual_plugin_app.command("install")
def custom_visual_install(
    pbiviz_file: Annotated[
        Optional[Path],
        typer.Argument(help="Path to a .pbiviz file. If omitted, installs all found in the project."),
    ] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Extract capabilities from .pbiviz files and register schemas.

    Without arguments, finds all .pbiviz files in CustomVisuals/ and
    RegisteredResources/ and installs their schemas.

    With a file argument, installs that specific .pbiviz file's schema.
    """
    from pbi.custom_visuals import install_all_from_project, install_custom_visual

    proj = get_project(project)

    if pbiviz_file is not None:
        path = Path(pbiviz_file).resolve()
        if not path.exists():
            console.print(f"[red]Error:[/red] File not found: {path}")
            raise typer.Exit(1)
        try:
            result = install_custom_visual(proj, path)
        except (ValueError, KeyError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        results = [result]
    else:
        results = install_all_from_project(proj)

    if as_json:
        console.print_json(json.dumps(
            [
                {
                    "visualType": r.visual_type,
                    "displayName": r.display_name,
                    "roles": r.role_count,
                    "objects": r.object_count,
                    "properties": r.property_count,
                }
                for r in results
            ],
            indent=2,
        ))
        return

    if not results:
        console.print("[yellow]No .pbiviz files found in the project.[/yellow]")
        console.print("[dim]Place .pbiviz files in CustomVisuals/ or RegisteredResources/, or pass a file path.[/dim]")
        raise typer.Exit(0)

    for r in results:
        console.print(
            f'Installed "[cyan]{r.visual_type}[/cyan]" '
            f"[dim]({r.display_name} — {r.role_count} roles, "
            f"{r.object_count} objects, {r.property_count} properties)[/dim]"
        )

    console.print(f"\n[dim]Schemas saved to .pbi-custom-schemas/. "
                  f"Properties and roles are now available for these visual types.[/dim]")


@visual_plugin_app.command("list")
def custom_visual_list(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List installed custom visual schemas."""
    from pbi.custom_visuals import load_custom_schemas

    proj = get_project(project)
    schemas = load_custom_schemas(proj.root)

    if as_json:
        rows = []
        for vtype, schema in sorted(schemas.items()):
            objects = schema.get("objects", {})
            rows.append({
                "visualType": vtype,
                "roles": len(schema.get("dataRoles", {})),
                "objects": len(objects),
                "properties": sum(len(v) for v in objects.values()),
            })
        console.print_json(json.dumps(rows, indent=2))
        return

    if not schemas:
        console.print("[yellow]No custom visual schemas installed.[/yellow]")
        console.print("[dim]Use `pbi visual plugin scan` to find custom visuals, "
                      "then `pbi visual plugin install` to register their schemas.[/dim]")
        raise typer.Exit(0)

    table = Table(box=box.SIMPLE, title="Installed Custom Visual Schemas")
    table.add_column("Visual Type", style="cyan")
    table.add_column("Roles", justify="right")
    table.add_column("Objects", justify="right")
    table.add_column("Properties", justify="right")

    for vtype, schema in sorted(schemas.items()):
        objects = schema.get("objects", {})
        table.add_row(
            vtype,
            str(len(schema.get("dataRoles", {}))),
            str(len(objects)),
            str(sum(len(v) for v in objects.values())),
        )

    console.print(table)


@visual_plugin_app.command("remove")
def custom_visual_remove(
    visual_type: Annotated[str, typer.Argument(help="Visual type to remove schema for.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Remove an installed custom visual schema."""
    proj = get_project(project)
    schema_dir = proj.root / ".pbi-custom-schemas"
    schema_file = schema_dir / f"{visual_type}.json"

    if not schema_file.exists():
        console.print(f'[red]Error:[/red] No schema installed for "{visual_type}".')
        raise typer.Exit(1)

    if not force:
        confirm = typer.confirm(f'Remove schema for "{visual_type}"?')
        if not confirm:
            raise typer.Abort()

    schema_file.unlink()
    console.print(f'Removed schema for "[cyan]{visual_type}[/cyan]"')
