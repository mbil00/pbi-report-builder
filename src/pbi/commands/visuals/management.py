"""Visual lifecycle and grouping commands."""

from __future__ import annotations

from typing import Annotated

import typer

from ..common import ProjectOpt, console, get_project
from .app import visual_app
from .helpers import resolve_visual_target, _set_visual_image_source
from pbi.textbox import set_textbox_content
from pbi.visual_builders import (
    apply_auto_title,
    apply_builder_preset,
    apply_initial_sort,
    apply_role_bindings,
    infer_default_sort,
    get_default_visual_size,
)


@visual_app.command("create")
def visual_create(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual_type: Annotated[str | None, typer.Argument(help="Visual type (e.g. clusteredColumnChart, card, table, slicer). Omit with --from.")] = None,
    x: Annotated[int, typer.Option(help="X position.")] = 0,
    y: Annotated[int, typer.Option(help="Y position.")] = 0,
    width: Annotated[int | None, typer.Option("-W", "--width", help="Width.")] = None,
    height: Annotated[int | None, typer.Option("-H", "--height", help="Height.")] = None,
    name: Annotated[str | None, typer.Option("--name", "-n", help="Friendly name for the visual.")] = None,
    title: Annotated[str | None, typer.Option("--title", help="Set title text (also enables title.show).")] = None,
    text: Annotated[str | None, typer.Option("--text", help="Set textbox body content during creation.")] = None,
    image: Annotated[str | None, typer.Option("--image", help="Bind an image visual to a registered resource name or path.")] = None,
    bind: Annotated[list[str], typer.Option("--bind", help="Bind a role as Role=Table.Field. Repeat to create a usable visual in one command.")] = [],
    preset: Annotated[str | None, typer.Option("--preset", help="Apply a builder preset for common visual families: chart, table, slicer, card.")] = None,
    sort: Annotated[str | None, typer.Option("--sort", help="Set initial sort field as Table.Field.")] = None,
    descending: Annotated[bool, typer.Option("--descending/--ascending", help="Sort direction for --sort (default: ascending).")] = False,
    auto_sort: Annotated[bool, typer.Option("--auto-sort/--no-auto-sort", help="Infer initial sort from semantic-model metadata when --sort is omitted.")] = True,
    field_type: Annotated[str, typer.Option("--field-type", help="Field type used for --bind/--sort: auto, column, or measure.")] = "auto",
    from_ref: Annotated[str | None, typer.Option("--from", help="Reference visual as 'page/visual' to copy type, style, and bindings from.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Create a new visual on a page. Use --from to clone from a reference visual."""
    from pbi.roles import get_visual_roles, is_known_visual_type, normalize_visual_type

    proj = get_project(project)
    try:
        pg = proj.find_page(page)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    # --from: copy from reference visual
    if from_ref:
        if bind:
            console.print("[red]Error:[/red] --bind cannot be combined with --from.")
            raise typer.Exit(1)
        if preset:
            console.print("[red]Error:[/red] --preset cannot be combined with --from.")
            raise typer.Exit(1)
        if sort:
            console.print("[red]Error:[/red] --sort cannot be combined with --from.")
            raise typer.Exit(1)
        if not auto_sort:
            console.print("[red]Error:[/red] --no-auto-sort cannot be combined with --from.")
            raise typer.Exit(1)
        if "/" not in from_ref:
            console.print("[red]Error:[/red] --from must be 'page/visual' format.")
            raise typer.Exit(1)
        ref_page_name, ref_visual_name = from_ref.split("/", 1)
        try:
            ref_page = proj.find_page(ref_page_name)
            ref_visual = proj.find_visual(ref_page, ref_visual_name)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

        ref_pos = ref_visual.position
        w = width if width is not None else ref_pos.get("width", 300)
        h = height if height is not None else ref_pos.get("height", 200)
        new_vis = proj.copy_visual(ref_visual, pg, new_name=name)
        # Override position
        new_vis.data["position"]["x"] = x
        new_vis.data["position"]["y"] = y
        new_vis.data["position"]["width"] = w
        new_vis.data["position"]["height"] = h
        new_vis.save()
        display = name or new_vis.name
        console.print(
            f'Created [cyan]{new_vis.visual_type}[/cyan] "{display}" on "{pg.display_name}" '
            f'from "{ref_visual.name}" @ {x},{y} {w}x{h}'
        )
        return

    if image and visual_type is None:
        visual_type = "image"

    if not visual_type:
        console.print("[red]Error:[/red] Visual type is required (or use --from to clone).")
        raise typer.Exit(1)

    canonical_visual_type = normalize_visual_type(visual_type)
    default_w, default_h = get_default_visual_size(canonical_visual_type)
    w = width if width is not None else default_w
    h = height if height is not None else default_h
    if image and canonical_visual_type != "image":
        console.print('[red]Error:[/red] --image can only be used with an image visual.')
        raise typer.Exit(1)
    if text is not None and canonical_visual_type != "textbox":
        console.print('[red]Error:[/red] --text can only be used with a textbox visual.')
        raise typer.Exit(1)
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

    vis = proj.create_visual(pg, canonical_visual_type, x=x, y=y, width=w, height=h)
    if name:
        from pbi.project import sanitize_visual_name
        vis.data["name"] = sanitize_visual_name(name)

    if title:
        from pbi.properties import VISUAL_PROPERTIES, set_property

        set_property(vis.data, "title.show", "true", VISUAL_PROPERTIES)
        set_property(vis.data, "title.text", title, VISUAL_PROPERTIES)

    if image:
        try:
            _set_visual_image_source(vis.data, proj, image)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    if text is not None:
        set_textbox_content(vis.data, text=text)

    if name or title or image or text is not None:
        vis.save()

    bound_fields = []
    if bind:
        try:
            bound_fields = apply_role_bindings(proj, vis, bind, field_type=field_type)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            proj.delete_visual(vis)
            raise typer.Exit(1)

    inferred_title: str | None = None
    if bind and not title:
        inferred_title = apply_auto_title(vis, bound_fields)

    applied_preset: list[tuple[str, str]] = []
    if preset:
        try:
            applied_preset = apply_builder_preset(vis, preset, bound_fields=bound_fields)
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            proj.delete_visual(vis)
            raise typer.Exit(1)

    sort_details: tuple[str, str, str, str] | None = None
    sort_is_auto = False
    if sort:
        try:
            sort_details = apply_initial_sort(
                proj,
                vis,
                sort,
                field_type=field_type,
                descending=descending,
            )
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            proj.delete_visual(vis)
            raise typer.Exit(1)
    elif auto_sort and bound_fields:
        sort_details = infer_default_sort(proj, vis, bound_fields)
        sort_is_auto = sort_details is not None

    display = name or vis.name
    console.print(
        f'Created [cyan]{canonical_visual_type}[/cyan] "{display}" on "{pg.display_name}" '
        f"@ {x},{y} {w}x{h}"
    )

    if bound_fields:
        bindings_str = ", ".join(
            f'{field.role}={field.entity}.{field.prop}'
            for field in bound_fields
        )
        console.print(f"[dim]Bindings:[/dim] {bindings_str}")

    if inferred_title:
        console.print(f"[dim]Title:[/dim] {inferred_title} [dim](auto)[/dim]")

    if applied_preset:
        console.print(f"[dim]Preset:[/dim] {preset}")

    if sort_details is not None:
        sort_entity, sort_prop, _field_type, direction = sort_details
        suffix = " [dim](auto)[/dim]" if sort_is_auto else ""
        console.print(f"[dim]Sort:[/dim] {sort_entity}.{sort_prop} {direction}{suffix}")

    # Show scaffolded roles so the agent knows what to bind
    roles = get_visual_roles(canonical_visual_type)
    if roles:
        role_names = [r["name"] + (" (multi)" if r["multi"] else "") for r in roles]
        console.print(f'[dim]Roles: {", ".join(role_names)}[/dim]')


@visual_app.command("copy")
def visual_copy(
    page: Annotated[str, typer.Argument(help="Source page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Source visual name, type, or index.")],
    to_page: Annotated[str | None, typer.Option("--to-page", help="Target page (default: same page).")] = None,
    name: Annotated[str | None, typer.Option("--name", help="Name for the copy.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Copy/duplicate a visual, optionally to a different page."""
    proj, pg, vis = resolve_visual_target(project, page, visual)
    try:
        target = proj.find_page(to_page) if to_page else pg
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    new_vis = proj.copy_visual(vis, target, new_name=name)
    dest = f' to "{target.display_name}"' if to_page else ""
    console.print(f'Copied [cyan]{vis.visual_type}[/cyan] "{vis.name}"{dest} -> "{new_vis.name}"')


@visual_app.command("rename")
def visual_rename(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    name: Annotated[str, typer.Argument(help="New friendly name for the visual.")],
    project: ProjectOpt = None,
) -> None:
    """Give a visual a friendly name for easier CLI reference."""
    proj, pg, vis = resolve_visual_target(project, page, visual)

    from pbi.project import sanitize_visual_name

    old_name = vis.name
    safe = sanitize_visual_name(name)
    vis.data["name"] = safe
    vis.save()

    # Cascade rename to children if this is a group container
    if "visualGroup" in vis.data:
        for child in proj.get_visuals(pg):
            if child.data.get("parentGroupName") == old_name:
                child.data["parentGroupName"] = safe
                child.save()

    console.print(f'Renamed "{old_name}" [dim]->[/dim] "[cyan]{safe}[/cyan]"')


@visual_app.command("delete")
def visual_delete(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    visual: Annotated[str, typer.Argument(help="Visual name, type, or index.")],
    force: Annotated[bool, typer.Option("--force", "-f", help="Skip confirmation.")] = False,
    project: ProjectOpt = None,
) -> None:
    """Delete a visual."""
    proj, _pg, vis = resolve_visual_target(project, page, visual)

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
    name: Annotated[str | None, typer.Option("--name", "-n", help="Group display name.")] = None,
    project: ProjectOpt = None,
) -> None:
    """Group visuals together into a visual group."""
    proj = get_project(project)
    try:
        pg = proj.find_page(page)
        vis_list = [proj.find_visual(pg, visual) for visual in visuals]
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    try:
        group = proj.create_group(pg, vis_list, display_name=name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    names = ", ".join(f'"{vis.name}"' for vis in vis_list)
    console.print(f'Grouped {names} -> "[cyan]{group.name}[/cyan]"')


@visual_app.command("ungroup")
def visual_ungroup(
    page: Annotated[str, typer.Argument(help="Page name, display name, or index.")],
    group: Annotated[str, typer.Argument(help="Group name or index.")],
    project: ProjectOpt = None,
) -> None:
    """Ungroup a visual group, freeing its children."""
    proj, pg, grp = resolve_visual_target(project, page, group)

    try:
        children = proj.ungroup(pg, grp)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)

    names = ", ".join(f'"{child.name}"' for child in children)
    console.print(f'Ungrouped "[cyan]{grp.name}[/cyan]": freed {names or "no children"}')
