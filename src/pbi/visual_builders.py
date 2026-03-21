"""Higher-level visual authoring helpers layered on top of PBIR primitives."""

from __future__ import annotations

from dataclasses import dataclass

from pbi.commands.common import resolve_field_type


@dataclass(frozen=True)
class BoundField:
    """A field bound to a visual role."""

    role: str
    entity: str
    prop: str
    field_type: str


DEFAULT_VISUAL_SIZES: dict[str, tuple[int, int]] = {
    "cardVisual": (260, 120),
    "clusteredBarChart": (520, 320),
    "clusteredColumnChart": (520, 320),
    "donutChart": (360, 280),
    "lineChart": (520, 320),
    "lineClusteredColumnComboChart": (640, 360),
    "pivotTable": (560, 360),
    "slicer": (220, 120),
    "tableEx": (520, 320),
}


def get_default_visual_size(visual_type: str) -> tuple[int, int]:
    """Return a sensible default size for common visual types."""
    return DEFAULT_VISUAL_SIZES.get(visual_type, (300, 200))


def parse_role_bindings(bindings: list[str]) -> list[tuple[str, str]]:
    """Parse repeated --bind ROLE=Table.Field options."""
    parsed: list[tuple[str, str]] = []
    for spec in bindings:
        eq = spec.find("=")
        if eq <= 0 or eq == len(spec) - 1:
            raise ValueError(f'Invalid binding "{spec}". Use Role=Table.Field.')
        parsed.append((spec[:eq], spec[eq + 1 :]))
    return parsed


def apply_role_bindings(
    project,
    visual,
    bindings: list[str],
    *,
    field_type: str = "auto",
) -> list[BoundField]:
    """Bind one or more fields to a visual, validating known role-backed types."""
    from pbi.roles import get_visual_type_info, normalize_visual_role

    parsed = parse_role_bindings(bindings)
    info = get_visual_type_info(visual.visual_type)
    supported_roles = {entry["name"] for entry in info.roles} if info and info.status == "role-backed" else None

    applied: list[BoundField] = []
    for raw_role, field in parsed:
        canonical_role = normalize_visual_role(visual.visual_type, raw_role)
        if supported_roles is not None and canonical_role not in supported_roles:
            raise ValueError(
                f'Role "{canonical_role}" is not modeled for {visual.visual_type}. '
                f'Supported roles: {", ".join(sorted(supported_roles))}'
            )
        entity, prop, resolved_field_type = resolve_field_type(project, field, field_type)
        project.add_binding(
            visual,
            canonical_role,
            entity,
            prop,
            field_type=resolved_field_type,
        )
        applied.append(BoundField(canonical_role, entity, prop, resolved_field_type))

    return applied


def apply_initial_sort(
    project,
    visual,
    field: str,
    *,
    field_type: str = "auto",
    descending: bool = False,
) -> tuple[str, str, str, str]:
    """Apply an initial sort and return the resolved field details."""
    entity, prop, resolved_field_type = resolve_field_type(project, field, field_type)
    project.set_sort(visual, entity, prop, field_type=resolved_field_type, descending=descending)
    direction = "Descending" if descending else "Ascending"
    return entity, prop, resolved_field_type, direction
