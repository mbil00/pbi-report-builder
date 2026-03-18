"""Visual query and sort helpers."""

from __future__ import annotations

import copy
from typing import Any

from .state import (
    ApplyResult,
    ApplySession as _ApplySession,
)
from pbi.project import Project, Visual
from pbi.roles import normalize_visual_role
from pbi.roundtrip import (
    build_projection,
    match_existing_projection,
    parse_binding_items,
)


def apply_bindings(
    project: Project,
    visual: Visual,
    bindings: dict,
    result: ApplyResult,
    *,
    session: _ApplySession,
) -> None:
    """Apply data bindings from the YAML spec."""
    from pbi.columns import set_column_width

    query_state = (
        visual.data.setdefault("visual", {}).setdefault("query", {}).setdefault("queryState", {})
    )

    for role, field_ref in bindings.items():
        canonical_role = normalize_visual_role(visual.visual_type, role)
        existing_projections = copy.deepcopy(query_state.get(canonical_role, {}).get("projections", []))
        try:
            parsed_items = parse_binding_items(
                project.root,
                field_ref,
                model=session.get_model(project),
            )
        except ValueError as e:
            result.errors.append(f"Invalid binding: {e}")
            continue
        new_projections: list[dict[str, Any]] = []

        for item in parsed_items:
            projection = match_existing_projection(existing_projections, item)
            if projection is None:
                projection = build_projection(item)
            else:
                projection = copy.deepcopy(projection)
            if item.display_name is not None:
                projection["displayName"] = item.display_name
            new_projections.append(projection)
            result.bindings_added += 1

            if item.width is not None:
                query_ref = projection.get("queryRef", f"{item.entity}.{item.prop}")
                set_column_width(visual, query_ref, item.width)

        if new_projections:
            query_state[canonical_role] = {"projections": new_projections}
        else:
            query_state.pop(canonical_role, None)


def apply_sort(
    project: Project,
    visual: Visual,
    sort_spec: str,
    result: ApplyResult,
) -> None:
    """Apply sort from a spec like 'Table.Field Descending'."""
    text = str(sort_spec).strip()
    if not text:
        return

    is_measure = "(measure)" in text
    text = text.replace("(measure)", "").strip()

    direction = "Descending"
    for suffix in ("Ascending", "ascending", "asc", "Descending", "descending", "desc"):
        if text.endswith(f" {suffix}"):
            direction = "Ascending" if suffix.lower() in ("ascending", "asc") else "Descending"
            text = text[: -len(suffix)].strip()
            break

    field_ref = text
    dot = field_ref.find(".")
    if dot == -1:
        result.errors.append(f"Invalid sort field: {sort_spec}")
        return

    entity = field_ref[:dot]
    prop = field_ref[dot + 1 :]
    field_type = "measure" if is_measure else "column"

    project.set_sort(
        visual,
        entity,
        prop,
        field_type=field_type,
        descending=(direction == "Descending"),
    )
    result.properties_set += 1
