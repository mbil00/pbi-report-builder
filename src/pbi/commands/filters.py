"""Filter CLI commands."""

from __future__ import annotations

from typing import Annotated

import typer
from rich import box
from rich.table import Table

from .common import ProjectOpt, console, get_project

filter_app = typer.Typer(help="Filter operations.", no_args_is_help=True)


def _normalize_field_type(field_type: str) -> str:
    valid = {"auto", "column", "measure"}
    if field_type not in valid:
        raise ValueError(f"Invalid field type '{field_type}'. Use one of: auto, column, measure.")
    return field_type


def _load_filter_model(project):
    """Best-effort semantic model loader for filter typing."""
    try:
        from pbi.model import SemanticModel

        proj_obj = get_project(project)
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

    entity, prop = field[:dot], field[dot + 1 :]
    mode = _normalize_field_type(field_type)
    if mode == "measure":
        return entity, prop, "measure", None
    if model is None:
        return entity, prop, "column" if mode == "auto" else mode, None

    # Resolve via model when available (for auto-detect and data type lookup)
    try:
        resolved_entity, resolved_prop, resolved_field_type = model.resolve_field(field)
    except (ValueError, KeyError):
        return entity, prop, mode or "column", None

    # Override resolved field type if user explicitly specified column/measure
    effective_type = mode if mode in {"column", "measure"} else resolved_field_type

    data_type = None
    if effective_type == "column":
        try:
            table = model.find_table(resolved_entity)
            for column in table.columns:
                if column.name == resolved_prop:
                    data_type = column.data_type
                    break
        except (ValueError, KeyError):
            pass
    return resolved_entity, resolved_prop, effective_type, data_type


def _resolve_scope(
    page_opt: str | None,
    visual_opt: str | None,
) -> tuple[str | None, str | None]:
    """Derive page_ref and visual_ref from --page/--visual flags."""
    if visual_opt and not page_opt:
        raise ValueError("--visual requires --page.")
    return page_opt, visual_opt


@filter_app.command("list")
def filter_list(
    page_opt: Annotated[str | None, typer.Option("--page", help="Page name (narrows to page scope).")] = None,
    visual_opt: Annotated[str | None, typer.Option("--visual", help="Visual name (narrows to visual scope, requires --page).")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Output as JSON.")] = False,
    project: ProjectOpt = None,
) -> None:
    """List filters. Defaults to report level; use --page/--visual to narrow scope."""
    from pbi.filters import filter_field_refs, get_filters, load_level_data, parse_filter

    proj = get_project(project)
    try:
        page_ref, visual_ref = _resolve_scope(page_opt, visual_opt)
        data, level, _ = load_level_data(proj, page_ref, visual_ref)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    filters = get_filters(data)
    if not filters:
        console.print(f"[dim]No filters at {level} level.[/dim]")
        return

    if as_json:
        import json as json_mod

        rows = []
        for filter_obj in filters:
            info = parse_filter(filter_obj, level)
            field_refs = filter_field_refs(filter_obj)
            rows.append({
                "name": info.name or None,
                "field": ", ".join(field_refs) if field_refs else None,
                "type": info.filter_type,
                "values": info.values if info.values else [],
                "hidden": info.is_hidden,
                "locked": info.is_locked,
            })
        console.print_json(json_mod.dumps(rows, indent=2))
        return

    table = Table(title=f"{level.title()} Filters", box=box.SIMPLE)
    table.add_column("Name", style="dim")
    table.add_column("Field", style="cyan")
    table.add_column("Type")
    table.add_column("Values/Condition")
    table.add_column("Hidden", style="dim", justify="center")
    table.add_column("Locked", style="dim", justify="center")

    for filter_obj in filters:
        info = parse_filter(filter_obj, level)
        field_refs = filter_field_refs(filter_obj)
        field_label = ", ".join(field_refs) if field_refs else filter_obj.get("displayName", "(tuple)")
        table.add_row(
            info.name or "-",
            field_label,
            info.filter_type,
            ", ".join(info.values) if info.values else "-",
            "yes" if info.is_hidden else "",
            "yes" if info.is_locked else "",
        )

    console.print(table)


@filter_app.command("create")
def filter_create(
    field: Annotated[str | None, typer.Argument(help="Filter field as Table.Field (omit for --mode tuple).")] = None,
    page_opt: Annotated[str | None, typer.Option("--page", help="Page name (narrows to page scope).")] = None,
    visual_opt: Annotated[str | None, typer.Option("--visual", help="Visual name (narrows to visual scope, requires --page).")] = None,
    value: Annotated[list[str] | None, typer.Option("--value", help="Value for categorical/include/exclude filters. Repeatable.")] = None,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="Filter mode: categorical, include, exclude, range, topn, relative, or tuple.",
        ),
    ] = "categorical",
    min_val: Annotated[str | None, typer.Option("--min", help="Minimum value for range filter.")] = None,
    max_val: Annotated[str | None, typer.Option("--max", help="Maximum value for range filter.")] = None,
    topn: Annotated[int | None, typer.Option("--topn", help="Top N items count.")] = None,
    topn_by: Annotated[str | None, typer.Option("--topn-by", help="Order-by field for Top N (Table.Field).")] = None,
    direction: Annotated[str, typer.Option("--direction", help="Top N direction: top or bottom.")] = "top",
    operator: Annotated[str | None, typer.Option("--operator", help="Relative operator: InLast, InThis, or InNext.")] = None,
    count: Annotated[int | None, typer.Option("--count", help="Relative time unit count.")] = None,
    unit: Annotated[str | None, typer.Option("--unit", help="Relative unit: Minutes, Hours, Days, Weeks, Months, Quarters, or Years.")] = None,
    include_today: Annotated[bool, typer.Option("--include-today/--no-include-today", help="Include today for relative date filters when supported.")] = True,
    hidden: Annotated[bool, typer.Option("--hidden", help="Hide filter in view mode.")] = False,
    locked: Annotated[bool, typer.Option("--locked", help="Lock filter in view mode.")] = False,
    field_type: Annotated[str, typer.Option("--field-type", help="Field type: auto, column, or measure.")] = "auto",
    row: Annotated[list[str] | None, typer.Option("--row", help="Tuple row as comma-separated Field=Value pairs. Repeatable.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Create a filter. Defaults to report level; use --page/--visual to narrow scope."""
    from pbi.filters import (
        TupleField,
        add_blank_filter,
        add_categorical_filter,
        add_exclude_filter,
        add_include_filter,
        add_not_blank_filter,
        add_range_filter,
        add_relative_date_filter,
        add_relative_time_filter,
        add_topn_filter,
        add_tuple_filter,
        load_level_data,
        save_level_data,
    )

    valid_modes = {"categorical", "include", "exclude", "range", "topn", "relative", "tuple", "blank", "not-blank"}
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
    proj = get_project(project)

    try:
        page_ref, visual_ref = _resolve_scope(page_opt, visual_opt)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # For non-tuple modes, field is required
    if mode != "tuple":
        if not field:
            console.print("[red]Error:[/red] Field argument is required (use Table.Field format). Omit only for --mode tuple.")
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
        if not val_list and mode in {"include", "exclude"}:
            console.print("[red]Error:[/red] Include/exclude filters require at least one --value.")
            raise typer.Exit(1)
        if not val_list and mode == "categorical":
            # Empty categorical: add field to filter pane with no selections
            from pbi.filters import add_empty_categorical_filter
            add_empty_categorical_filter(
                data,
                entity,
                prop,
                field_type=resolved_field_type,
                is_hidden=hidden,
                is_locked=locked,
            )
            save_level_data(data, target)
            console.print(
                f'Added empty categorical filter on [cyan]{entity}.{prop}[/cyan] at {level} level'
            )
            return
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
        values_str = ", ".join(val_list)
        console.print(
            f'Added {label} filter on [cyan]{entity}.{prop}[/cyan] '
            f'= \\[{values_str}] at {level} level'
        )
        return

    if mode in {"blank", "not-blank"}:
        add_fn_null = add_blank_filter if mode == "blank" else add_not_blank_filter
        add_fn_null(
            data,
            entity,
            prop,
            field_type=resolved_field_type,
            is_hidden=hidden,
            is_locked=locked,
        )
        save_level_data(data, target)
        label = "blank" if mode == "blank" else "not-blank"
        console.print(
            f'Added {label} filter on [cyan]{entity}.{prop}[/cyan] at {level} level'
        )
        return

    if mode == "range":
        if min_val is None and max_val is None:
            console.print("[red]Error:[/red] Range filters require --min, --max, or both.")
            raise typer.Exit(1)
        add_range_filter(
            data,
            entity,
            prop,
            min_val=min_val,
            max_val=max_val,
            field_type=resolved_field_type,
            is_hidden=hidden,
            is_locked=locked,
            data_type=data_type,
        )
        save_level_data(data, target)
        bounds: list[str] = []
        if min_val is not None:
            bounds.append(f">= {min_val}")
        if max_val is not None:
            bounds.append(f"<= {max_val}")
        console.print(
            f'Added range filter on [cyan]{entity}.{prop}[/cyan] '
            f'{" and ".join(bounds)} at {level} level'
        )
        return

    if mode == "topn":
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
                data,
                entity,
                prop,
                n=topn,
                order_entity=order_entity,
                order_prop=order_prop,
                order_field_type=order_field_type,
                direction=direction_label,
                field_type=resolved_field_type,
                is_hidden=hidden,
                is_locked=locked,
            )
        except (NotImplementedError, ValueError) as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
        save_level_data(data, target)
        console.print(
            f'Added {direction_label} {topn} filter on [cyan]{entity}.{prop}[/cyan] '
            f'by {order_entity}.{order_prop} at {level} level'
        )
        return

    if mode == "relative":
        if operator is None or count is None or unit is None:
            console.print("[red]Error:[/red] Relative filters require --operator, --count, and --unit.")
            raise typer.Exit(1)
        valid_ops = ("InLast", "InThis", "InNext")
        valid_units = ("Minutes", "Hours", "Days", "Weeks", "Months", "Quarters", "Years")
        if operator not in valid_ops:
            console.print(f"[red]Error:[/red] Operator must be one of: {', '.join(valid_ops)}")
            raise typer.Exit(1)
        if unit not in valid_units:
            console.print(f"[red]Error:[/red] Unit must be one of: {', '.join(valid_units)}")
            raise typer.Exit(1)
        try:
            if unit in ("Minutes", "Hours"):
                add_relative_time_filter(
                    data,
                    entity,
                    prop,
                    operator=operator,
                    time_units_count=count,
                    time_unit_type=unit,
                    field_type=resolved_field_type,
                    is_hidden=hidden,
                    is_locked=locked,
                )
            else:
                add_relative_date_filter(
                    data,
                    entity,
                    prop,
                    operator=operator,
                    time_units_count=count,
                    time_unit_type=unit,
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
            f'{operator.lower()} {count} {unit.lower()} at {level} level'
        )
        return

    # Tuple mode
    if not row:
        console.print("[red]Error:[/red] Tuple filters require at least one --row.")
        raise typer.Exit(1)

    parsed_rows = []
    for row_spec in row:
        parsed_fields = []
        for part in row_spec.split(","):
            assignment = part.strip()
            eq = assignment.find("=")
            if eq == -1:
                console.print(f"[red]Error:[/red] Invalid tuple assignment '{assignment}'. Use Field=Value.")
                raise typer.Exit(1)
            field_ref = assignment[:eq].strip()
            literal = assignment[eq + 1 :].strip()
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


@filter_app.command("delete")
def filter_delete(
    field: Annotated[str, typer.Argument(help="Filter field reference or name to remove.")],
    page_opt: Annotated[str | None, typer.Option("--page", help="Page name (narrows to page scope).")] = None,
    visual_opt: Annotated[str | None, typer.Option("--visual", help="Visual name (narrows to visual scope, requires --page).")] = None,
    project: ProjectOpt = None,
) -> None:
    """Delete a filter by field reference or filter name."""
    from pbi.filters import load_level_data, remove_filter, save_level_data

    proj = get_project(project)
    try:
        page_ref, visual_ref = _resolve_scope(page_opt, visual_opt)
        data, level, target = load_level_data(proj, page_ref, visual_ref)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    removed = remove_filter(data, field)
    if removed:
        save_level_data(data, target)
        console.print(f'Deleted {removed} filter(s) matching "{field}" at {level} level')
    else:
        console.print(f'[yellow]No filter matching "{field}" found at {level} level.[/yellow]')
