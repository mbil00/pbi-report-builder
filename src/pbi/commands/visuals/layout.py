"""Visual layout commands."""

from __future__ import annotations

from typing import Annotated

import typer

from ..common import ProjectOpt, console, get_project
from .app import visual_arrange_app


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

    proj = get_project(project)
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

    proj = get_project(project)
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

    proj = get_project(project)
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


@visual_arrange_app.command("align")
def visual_align(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visuals: Annotated[list[str], typer.Argument(help="Visuals to align.")],
    align: Annotated[str | None, typer.Option("--align", "-a", help="Align edges: left, right, top, bottom, center-x, center-y.")] = None,
    distribute: Annotated[str | None, typer.Option("--distribute", "-d", help="Distribute evenly: horizontal or vertical.")] = None,
    match_width: Annotated[bool, typer.Option("--match-width", help="Match all visuals to the first visual's width.")] = False,
    match_height: Annotated[bool, typer.Option("--match-height", help="Match all visuals to the first visual's height.")] = False,
    margin: Annotated[int, typer.Option("--margin", help="Outer margin from page edge for distribute.")] = 0,
    project: ProjectOpt = None,
) -> None:
    """Align, distribute, or match sizes of visuals on a page."""
    if not align and not distribute and not match_width and not match_height:
        console.print("[red]Error:[/red] Specify at least one of --align, --distribute, --match-width, or --match-height.")
        raise typer.Exit(1)
    if len(visuals) < 2:
        console.print("[red]Error:[/red] Provide at least two visuals to align.")
        raise typer.Exit(1)

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        ordered_visuals = [proj.find_visual(pg, v) for v in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    actions: list[str] = []

    if align:
        valid = {"left", "right", "top", "bottom", "center-x", "center-y"}
        if align not in valid:
            console.print(f"[red]Error:[/red] --align must be one of: {', '.join(sorted(valid))}")
            raise typer.Exit(1)

        ref = ordered_visuals[0].position
        if align == "left":
            target = ref.get("x", 0)
            for vis in ordered_visuals:
                vis.data.setdefault("position", {})["x"] = target
        elif align == "right":
            target = ref.get("x", 0) + ref.get("width", 0)
            for vis in ordered_visuals:
                w = vis.position.get("width", 0)
                vis.data.setdefault("position", {})["x"] = target - w
        elif align == "top":
            target = ref.get("y", 0)
            for vis in ordered_visuals:
                vis.data.setdefault("position", {})["y"] = target
        elif align == "bottom":
            target = ref.get("y", 0) + ref.get("height", 0)
            for vis in ordered_visuals:
                h = vis.position.get("height", 0)
                vis.data.setdefault("position", {})["y"] = target - h
        elif align == "center-x":
            target = ref.get("x", 0) + ref.get("width", 0) / 2
            for vis in ordered_visuals:
                w = vis.position.get("width", 0)
                vis.data.setdefault("position", {})["x"] = int(target - w / 2)
        elif align == "center-y":
            target = ref.get("y", 0) + ref.get("height", 0) / 2
            for vis in ordered_visuals:
                h = vis.position.get("height", 0)
                vis.data.setdefault("position", {})["y"] = int(target - h / 2)
        actions.append(f"aligned {align}")

    if distribute:
        if distribute not in {"horizontal", "vertical"}:
            console.print("[red]Error:[/red] --distribute must be 'horizontal' or 'vertical'.")
            raise typer.Exit(1)

        if distribute == "horizontal":
            page_width = pg.width
            total_width = sum(vis.position.get("width", 0) for vis in ordered_visuals)
            available = page_width - 2 * margin - total_width
            gap = available / max(len(ordered_visuals) - 1, 1)
            cursor = margin
            for vis in ordered_visuals:
                vis.data.setdefault("position", {})["x"] = int(cursor)
                cursor += vis.position.get("width", 0) + gap
        else:
            page_height = pg.height
            total_height = sum(vis.position.get("height", 0) for vis in ordered_visuals)
            available = page_height - 2 * margin - total_height
            gap = available / max(len(ordered_visuals) - 1, 1)
            cursor = margin
            for vis in ordered_visuals:
                vis.data.setdefault("position", {})["y"] = int(cursor)
                cursor += vis.position.get("height", 0) + gap
        actions.append(f"distributed {distribute}")

    if match_width:
        target = ordered_visuals[0].position.get("width", 0)
        for vis in ordered_visuals:
            vis.data.setdefault("position", {})["width"] = target
        actions.append(f"matched width={target}")

    if match_height:
        target = ordered_visuals[0].position.get("height", 0)
        for vis in ordered_visuals:
            vis.data.setdefault("position", {})["height"] = target
        actions.append(f"matched height={target}")

    for vis in ordered_visuals:
        vis.save()

    console.print(
        f'Aligned [cyan]{len(ordered_visuals)}[/cyan] visuals on "{pg.display_name}": '
        f'{", ".join(actions)}'
    )
