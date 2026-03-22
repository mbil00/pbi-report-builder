"""Inspection and utility semantic-model commands."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .base import (
    ProjectOpt,
    console,
    get_model,
    get_project,
    model_app,
    parse_property_assignments,
    resolve_yaml_input,
)


@model_app.command("get")
def model_get(
    project: ProjectOpt = None,
) -> None:
    """Show model-level settings."""
    _, model = get_model(project)
    enabled = model.time_intelligence_enabled
    console.print("[bold]Model[/bold]")
    console.print(f"[dim]Time Intelligence:[/dim] {enabled if enabled is not None else '(none)'}")
    console.print(f"[dim]Annotations:[/dim] {len(model.annotations)}")
    console.print(f"[dim]Partitions:[/dim] {sum(len(table.partitions) for table in model.tables)}")
    console.print(f"[dim]Roles:[/dim] {len(model.roles)}")
    console.print(f"[dim]Perspectives:[/dim] {len(model.perspectives)}")


@model_app.command("set")
def model_set(
    assignments: Annotated[list[str], typer.Argument(help="Property assignments as key=value.")],
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Set model-level settings such as timeIntelligence=off."""
    from pbi.model import set_time_intelligence_enabled

    proj = get_project(project)
    try:
        pairs = parse_property_assignments(assignments)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    for prop_name, prop_value in pairs:
        if prop_name != "timeIntelligence":
            console.print('[red]Error:[/red] Property "{}" is not writable. Allowed: timeIntelligence'.format(prop_name))
            raise typer.Exit(1)
        normalized = prop_value.strip().lower()
        if normalized in {"1", "true", "on", "yes"}:
            enabled = True
        elif normalized in {"0", "false", "off", "no"}:
            enabled = False
        else:
            console.print(f'[red]Error:[/red] Invalid timeIntelligence value "{prop_value}". Use on/off, true/false, or 1/0.')
            raise typer.Exit(1)

        try:
            changed = set_time_intelligence_enabled(
                proj.root,
                enabled,
                dry_run=dry_run,
            )
        except (FileNotFoundError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        rendered = "on" if enabled else "off"
        if changed:
            console.print(f'{prefix}[dim]timeIntelligence:[/dim] [dim]->[/dim] "{rendered}"')
        else:
            console.print(f'{prefix}[dim]No change:[/dim] timeIntelligence is already "{rendered}"')


@model_app.command("search")
def model_search(
    keyword: Annotated[str, typer.Argument(help="Keyword to search for across all tables, columns, and measures.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Search for fields and measures by keyword across all tables."""
    _, model = get_model(project)
    keyword_lower = keyword.lower()

    matches: list[dict[str, str]] = []
    for sem_table in model.tables:
        if keyword_lower in sem_table.name.lower():
            matches.append(
                {
                    "ref": sem_table.name,
                    "type": "table",
                    "details": f"{len(sem_table.columns)} cols, {len(sem_table.measures)} measures",
                }
            )
        for column in sem_table.columns:
            if keyword_lower in column.name.lower():
                matches.append({"ref": f"{sem_table.name}.{column.name}", "type": "column", "details": column.data_type})
        for measure in sem_table.measures:
            if keyword_lower in measure.name.lower():
                expr = measure.expression[:40] + "..." if len(measure.expression) > 40 else measure.expression
                matches.append({"ref": f"{sem_table.name}.{measure.name}", "type": "measure", "details": expr})

    if not matches:
        console.print(f'[yellow]No fields matching "{keyword}". Try a broader search.[/yellow]')
        raise typer.Exit(0)

    if as_json:
        import json

        console.print_json(json.dumps(matches, indent=2))
        return

    table = Table(title=f'Search: "{keyword}"', box=box.SIMPLE)
    table.add_column("Reference", style="cyan")
    table.add_column("Type")
    table.add_column("Details", style="dim")
    for match in matches:
        table.add_row(match["ref"], match["type"], match["details"])
    console.print(table)


@model_app.command("apply")
def model_apply(
    yaml_file: Annotated[str | None, typer.Argument(help="YAML file describing model changes. Use '-' or omit to read from stdin.")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run", help="Preview model changes without writing TMDL files.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Apply declarative YAML changes to the semantic model."""
    from pbi.model_apply import apply_model_yaml

    proj = get_project(project)
    try:
        yaml_content = resolve_yaml_input(yaml_file)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    result = apply_model_yaml(proj.root, yaml_content, dry_run=dry_run)

    prefix = "[dim](dry run)[/dim] " if dry_run else ""
    for ref in result.model_updated:
        console.print(f"{prefix}Updated model [cyan]{ref}[/cyan]")
    for ref in result.tables_updated:
        console.print(f"{prefix}Updated table [cyan]{ref}[/cyan]")
    for ref in result.measures_created:
        console.print(f"{prefix}Created measure [cyan]{ref}[/cyan]")
    for ref in result.measures_updated:
        console.print(f"{prefix}Updated measure [cyan]{ref}[/cyan]")
    for ref in result.columns_created:
        console.print(f"{prefix}Created calculated column [cyan]{ref}[/cyan]")
    for ref in result.columns_updated:
        console.print(f"{prefix}Updated column [cyan]{ref}[/cyan]")
    for ref in result.relationships_created:
        console.print(f"{prefix}Created relationship [cyan]{ref}[/cyan]")
    for ref in result.relationships_updated:
        console.print(f"{prefix}Updated relationship [cyan]{ref}[/cyan]")
    for ref in result.hierarchies_created:
        console.print(f"{prefix}Created hierarchy [cyan]{ref}[/cyan]")
    for ref in result.hierarchies_updated:
        console.print(f"{prefix}Updated hierarchy [cyan]{ref}[/cyan]")
    for ref in result.partitions_created:
        console.print(f"{prefix}Created partition [cyan]{ref}[/cyan]")
    for ref in result.partitions_updated:
        console.print(f"{prefix}Updated partition [cyan]{ref}[/cyan]")
    for ref in result.roles_created:
        console.print(f"{prefix}Created role [cyan]{ref}[/cyan]")
    for ref in result.roles_updated:
        console.print(f"{prefix}Updated role [cyan]{ref}[/cyan]")
    for ref in result.perspectives_created:
        console.print(f"{prefix}Created perspective [cyan]{ref}[/cyan]")
    for ref in result.perspectives_updated:
        console.print(f"{prefix}Updated perspective [cyan]{ref}[/cyan]")
    for error in result.errors:
        console.print(f"[red]Error:[/red] {error}")

    if result.errors:
        raise typer.Exit(1)
    if not result.has_changes:
        console.print("[dim]No changes detected.[/dim]" if dry_run else "[dim]No changes applied.[/dim]")


@model_app.command("path")
def model_path(
    from_table: Annotated[str, typer.Argument(help="Source table name.")],
    to_table: Annotated[str, typer.Argument(help="Target table name.")],
    project: ProjectOpt = None,
) -> None:
    """Show the relationship path between two tables."""
    _, model = get_model(project)

    path = model.find_path(from_table, to_table)
    if path is None:
        console.print(f'[yellow]No relationship path found between "{from_table}" and "{to_table}".[/yellow]')
        raise typer.Exit(1)

    if not path:
        console.print(f'[dim]"{from_table}" and "{to_table}" are the same table.[/dim]')
        return

    console.print(f"[bold]Path ({len(path)} hop{'s' if len(path) != 1 else ''}):[/bold]")
    for relationship in path:
        console.print(
            f"  {relationship.from_table}.{relationship.from_column} [dim]→[/dim] "
            f"{relationship.to_table}.{relationship.to_column}"
        )


@model_app.command("fields")
def model_fields(
    table_name: Annotated[str, typer.Argument(help="Table name.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List all fields (columns + measures) for use with 'visual bind'."""
    _, model = get_model(project)
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if as_json:
        import json

        rows = []
        for column in sem_table.columns:
            if not column.is_hidden:
                rows.append({"ref": f"{sem_table.name}.{column.name}", "type": "column", "details": column.data_type})
        for measure in sem_table.measures:
            rows.append({"ref": f"{sem_table.name}.{measure.name}", "type": "measure", "details": measure.expression})
        console.print_json(json.dumps(rows, indent=2))
        return

    table = Table(title=f'Fields in "{sem_table.name}"', box=box.SIMPLE)
    table.add_column("Field Reference", style="cyan")
    table.add_column("Type")
    table.add_column("Details", style="dim")

    for column in sem_table.columns:
        if not column.is_hidden:
            table.add_row(f"{sem_table.name}.{column.name}", "column", column.data_type)
    for measure in sem_table.measures:
        expr = measure.expression[:40] + "..." if len(measure.expression) > 40 else measure.expression
        table.add_row(f"{sem_table.name}.{measure.name}", "[bold]measure[/bold]", expr)

    console.print(table)


@model_app.command("export")
def model_export_cmd(
    output: Annotated[Path | None, typer.Option("-o", "--output", help="Write to file instead of stdout.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Export the semantic model as YAML."""
    from pbi.model_export import export_model_yaml
    from ..common import resolve_output_path

    proj = get_project(project)
    try:
        yaml_str = export_model_yaml(proj.root)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if output:
        resolved = resolve_output_path(output)
        resolved.write_text(yaml_str, encoding="utf-8")
        console.print(f'Exported model to [cyan]{resolved}[/cyan]')
    else:
        console.print(yaml_str, highlight=False, end="")


@model_app.command("deps")
def model_deps(
    field: Annotated[str, typer.Argument(help="Field reference as Table.Field.")],
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Show what references a field (dependents) and what it references."""
    from pbi.model import find_field_dependents, find_field_references

    proj = get_project(project)
    try:
        dependents = find_field_dependents(proj.root, field)
        references = find_field_references(proj.root, field)
    except (FileNotFoundError, ValueError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if as_json:
        import json

        data = {
            "field": field,
            "references": [{"ref": f"{table}.{name}", "type": field_type} for table, name, field_type in references],
            "dependents": [{"ref": f"{table}.{name}", "type": field_type} for table, name, field_type in dependents],
        }
        console.print_json(json.dumps(data, indent=2))
        return

    console.print(f"[bold]{field}[/bold]")

    if references:
        console.print(f"\n[bold]References[/bold] [dim](what {field} uses)[/dim]")
        for table_name, name, field_type in references:
            console.print(f"  [cyan]{table_name}.{name}[/cyan] [dim]({field_type})[/dim]")
    else:
        console.print("\n[dim]No forward references (leaf field).[/dim]")

    if dependents:
        console.print(f"\n[bold]Dependents[/bold] [dim](what uses {field})[/dim]")
        for table_name, name, field_type in dependents:
            console.print(f"  [cyan]{table_name}.{name}[/cyan] [dim]({field_type})[/dim]")
    else:
        console.print("\n[dim]No dependents.[/dim]")


@model_app.command("check")
def model_check(
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Validate model relationships and report potential issues."""
    from pbi.model import validate_relationships

    proj = get_project(project)
    try:
        findings = validate_relationships(proj.root)
    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    if as_json:
        import json

        console.print_json(json.dumps(findings, indent=2))
        return

    if not findings:
        console.print("[green]No issues found.[/green]")
        return

    warnings = [finding for finding in findings if finding["severity"] == "warning"]
    infos = [finding for finding in findings if finding["severity"] == "info"]

    if warnings:
        console.print(f"\n[bold][yellow]Warnings ({len(warnings)})[/yellow][/bold]")
        for finding in warnings:
            console.print(f"  [yellow]![/yellow] [cyan]{finding['relationship']}[/cyan]")
            console.print(f"    {finding['message']}")

    if infos:
        console.print(f"\n[bold]Info ({len(infos)})[/bold]")
        for finding in infos:
            console.print(f"  [dim]-[/dim] [cyan]{finding['relationship']}[/cyan]")
            console.print(f"    [dim]{finding['message']}[/dim]")

    console.print(f"\n[dim]{len(warnings)} warning(s), {len(infos)} info(s)[/dim]")
