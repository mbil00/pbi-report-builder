"""Visual query and sort helpers."""

from __future__ import annotations

import copy
import json
from typing import Any

from .state import (
    ApplyResult,
    PbirApplySession as _PbirApplySession,
)
from pbi.project import Project, Visual
from pbi.roles import normalize_visual_role
from pbi.roundtrip_primitives import (
    build_projection,
    match_existing_projection,
    parse_binding_items,
)
from pbi.fields import resolve_field_info


def apply_bindings(
    project: Project,
    visual: Visual,
    bindings: dict,
    result: ApplyResult,
    *,
    context: str,
    session: _PbirApplySession,
) -> None:
    """Apply data bindings from the YAML spec."""
    from pbi.columns import set_column_width
    from pbi.visual_builders import (
        BoundField,
        existing_bound_fields,
        validate_incremental_bindings,
    )

    query_state = (
        visual.data.setdefault("visual", {}).setdefault("query", {}).setdefault("queryState", {})
    )
    model = session.get_model(project)
    parsed_bindings: dict[str, tuple[list[Any], list[BoundField]]] = {}

    for role, field_ref in bindings.items():
        canonical_role = normalize_visual_role(visual.visual_type, role)
        try:
            parsed_items = parse_binding_items(
                project.root,
                field_ref,
                model=model,
            )
        except ValueError as e:
            result.errors.append(f"{context}: invalid binding for role {canonical_role}: {e}")
            return
        resolved_fields: list[BoundField] = []
        # The role's projections not yet matched to an item, to tell which
        # items keep an existing Desktop Aggregation projection.
        unmatched = list(query_state.get(canonical_role, {}).get("projections", []))
        for item in parsed_items:
            existing = match_existing_projection(unmatched, item)
            if item.hierarchy is not None:
                # Already resolved against the model by parse_binding_items.
                resolved_fields.append(
                    BoundField(canonical_role, item.entity, item.prop, item.field_type, item.data_type)
                )
                continue
            try:
                entity, prop, field_type, data_type = resolve_field_info(
                    project,
                    item.field_ref,
                    item.field_type,
                    model=model,
                    strict=True,
                )
            except ValueError as e:
                result.errors.append(f"{context}: invalid binding for role {canonical_role}: {e}")
                return
            resolved_fields.append(
                BoundField(
                    canonical_role,
                    entity,
                    prop,
                    field_type,
                    data_type,
                    aggregated=existing is not None and "Aggregation" in existing.get("field", {}),
                )
            )
        parsed_bindings[canonical_role] = (parsed_items, resolved_fields)

    candidate_fields = [
        field for field in existing_bound_fields(project, visual)
        if field.role not in parsed_bindings
    ]
    for _role, (_items, resolved_fields) in parsed_bindings.items():
        candidate_fields.extend(resolved_fields)

    try:
        validate_incremental_bindings(visual.visual_type, candidate_fields)
    except ValueError as e:
        result.errors.append(f"{context}: {e}")
        return

    for canonical_role, (parsed_items, _resolved_fields) in parsed_bindings.items():
        existing_projections = copy.deepcopy(query_state.get(canonical_role, {}).get("projections", []))
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
            role_state: dict[str, Any] = {"projections": new_projections}
            field_parameters = _kept_field_parameters(
                query_state.get(canonical_role, {}), new_projections
            )
            if field_parameters:
                role_state["fieldParameters"] = field_parameters
            query_state[canonical_role] = role_state
        else:
            query_state.pop(canonical_role, None)

    _prune_unbound_query_metadata(visual)


def _kept_field_parameters(
    role_state: dict[str, Any],
    new_projections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return the role's ``fieldParameters`` whose projections are still bound.

    Desktop marks the projections a field parameter expands to with
    ``{parameterExpr, index, length}`` (report-04 ``fd84289803c981e2182a``).
    Projections are compared on ``field`` and ``queryRef``, so a displayName
    edit keeps the entry. It stays at its ``index`` when the same run is still
    bound there; otherwise it follows the run to the one place it now sits.
    When the run is gone, or could be in more than one place, it is dropped
    rather than marking a projection the parameter did not make.
    """
    kept: list[dict[str, Any]] = []
    old_keys = [_projection_key(projection) for projection in role_state.get("projections", [])]
    new_keys = [_projection_key(projection) for projection in new_projections]
    for entry in role_state.get("fieldParameters", []):
        index, length = entry.get("index"), entry.get("length")
        if not isinstance(index, int) or not isinstance(length, int) or index < 0 or length < 1:
            continue
        run = old_keys[index : index + length]
        if len(run) != length:
            continue
        if new_keys[index : index + length] == run:
            kept.append(entry)
            continue
        starts = [
            start for start in range(len(new_keys) - length + 1)
            if new_keys[start : start + length] == run
        ]
        if len(starts) == 1:
            kept.append({**entry, "index": starts[0]})
    return kept


def _projection_key(projection: dict[str, Any]) -> tuple[str, str]:
    """Identify a projection by its field expression and query ref."""
    return (
        json.dumps(projection.get("field"), sort_keys=True),
        str(projection.get("queryRef", "")),
    )


def _prune_unbound_query_metadata(visual: Visual) -> None:
    """Remove selector-based object metadata for fields that are no longer bound."""
    query_state = (
        visual.data.get("visual", {}).get("query", {}).get("queryState", {})
    )
    bound_refs = {
        str(projection.get("queryRef", "")).lower()
        for config in query_state.values()
        if isinstance(config, dict)
        for projection in config.get("projections", [])
        if projection.get("queryRef")
    }

    objects = visual.data.get("visual", {}).get("objects")
    if not isinstance(objects, dict):
        return
    for object_name, entries in list(objects.items()):
        if not isinstance(entries, list):
            continue
        filtered = []
        for entry in entries:
            metadata = entry.get("selector", {}).get("metadata")
            if isinstance(metadata, str) and metadata and metadata.lower() not in bound_refs:
                continue
            filtered.append(entry)
        if filtered:
            objects[object_name] = filtered
        else:
            objects.pop(object_name, None)


def apply_sort(
    project: Project,
    visual: Visual,
    sort_spec: str,
    result: ApplyResult,
    *,
    context: str,
) -> None:
    """Apply sort from a spec like 'Table.Field Descending'."""
    from pbi.visual_builders import apply_initial_sort

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
        result.errors.append(f"{context}: invalid sort field: {sort_spec}")
        return
    field_type = "measure" if is_measure else "auto"
    try:
        apply_initial_sort(
            project,
            visual,
            field_ref,
            field_type=field_type,
            descending=(direction == "Descending"),
            # apply_visual persists through the session, which journals the
            # write for rollback; a direct save here would bypass it (#70).
            save=False,
        )
    except ValueError as e:
        result.errors.append(f"{context}: {e}")
        return
    result.properties_set += 1
