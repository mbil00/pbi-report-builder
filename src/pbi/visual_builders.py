"""Higher-level visual authoring helpers layered on top of PBIR primitives."""

from __future__ import annotations

from dataclasses import dataclass

from pbi.commands.common import resolve_field_type
from pbi.properties import VISUAL_PROPERTIES, set_property


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
    "pieChart": (360, 280),
    "pivotTable": (560, 360),
    "slicer": (220, 120),
    "stackedBarChart": (520, 320),
    "stackedColumnChart": (520, 320),
    "tableEx": (520, 320),
}

PRESET_COMPATIBILITY: dict[str, set[str]] = {
    "chart": {
        "clusteredBarChart",
        "clusteredColumnChart",
        "donutChart",
        "lineChart",
        "lineClusteredColumnComboChart",
        "pieChart",
        "stackedBarChart",
        "stackedColumnChart",
    },
    "table": {"tableEx", "pivotTable"},
    "slicer": {"slicer"},
    "card": {"cardVisual"},
}

CHART_TYPES = {
    "clusteredBarChart",
    "clusteredColumnChart",
    "lineChart",
    "lineClusteredColumnComboChart",
    "stackedBarChart",
    "stackedColumnChart",
}
PIE_TYPES = {"donutChart", "pieChart"}


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

    resolved: list[BoundField] = []
    for raw_role, field in parsed:
        canonical_role = normalize_visual_role(visual.visual_type, raw_role)
        if supported_roles is not None and canonical_role not in supported_roles:
            raise ValueError(
                f'Role "{canonical_role}" is not modeled for {visual.visual_type}. '
                f'Supported roles: {", ".join(sorted(supported_roles))}'
            )
        entity, prop, resolved_field_type = resolve_field_type(project, field, field_type)
        resolved.append(BoundField(canonical_role, entity, prop, resolved_field_type))

    validate_builder_bindings(visual.visual_type, resolved)

    for field in resolved:
        project.add_binding(
            visual,
            field.role,
            field.entity,
            field.prop,
            field_type=field.field_type,
        )

    return resolved


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


def infer_default_sort(
    project,
    visual,
    bound_fields: list[BoundField],
) -> tuple[str, str, str, str] | None:
    """Infer a useful default sort from semantic-model metadata."""
    from pbi.model import SemanticModel

    candidate = _find_sort_candidate(visual.visual_type, bound_fields)
    if candidate is None or candidate.field_type != "column":
        return None

    try:
        model = SemanticModel.load(project.root)
        table = model.find_table(candidate.entity)
        column = table.find_column(candidate.prop)
    except (FileNotFoundError, ValueError):
        return None

    if column.sort_by_column:
        return apply_initial_sort(
            project,
            visual,
            f"{table.name}.{column.sort_by_column}",
            field_type="column",
            descending=False,
        )

    if (column.data_type or "").lower() in {"date", "datetime", "datetimezone"}:
        return apply_initial_sort(
            project,
            visual,
            f"{table.name}.{column.name}",
            field_type="column",
            descending=False,
        )

    return None


def apply_auto_title(visual, bound_fields: list[BoundField]) -> str | None:
    """Apply an inferred title when the user did not provide one."""
    title = infer_auto_title(visual.visual_type, bound_fields)
    if not title:
        return None
    set_property(visual.data, "title.show", "true", VISUAL_PROPERTIES)
    set_property(visual.data, "title.text", title, VISUAL_PROPERTIES)
    visual.save()
    return title


def apply_builder_preset(
    visual,
    preset: str,
    *,
    bound_fields: list[BoundField] | None = None,
) -> list[tuple[str, str]]:
    """Apply a preset to a newly-created visual and return applied properties."""
    normalized = preset.strip().lower()
    if normalized not in PRESET_COMPATIBILITY:
        raise ValueError(
            f'Unknown preset "{preset}". Use one of: {", ".join(sorted(PRESET_COMPATIBILITY))}.'
        )
    if visual.visual_type not in PRESET_COMPATIBILITY[normalized]:
        supported = ", ".join(sorted(PRESET_COMPATIBILITY[normalized]))
        raise ValueError(
            f'Preset "{normalized}" is not supported for {visual.visual_type}. '
            f"Supported types: {supported}"
        )

    assignments = _preset_assignments(visual.visual_type, normalized, bound_fields or [])
    for prop, value in assignments:
        set_property(visual.data, prop, value, VISUAL_PROPERTIES)
    visual.save()
    return assignments


def _preset_assignments(
    visual_type: str,
    preset: str,
    bound_fields: list[BoundField],
) -> list[tuple[str, str]]:
    """Return canonical property assignments for a builder preset."""
    if preset == "chart":
        has_series = any(field.role == "Series" for field in bound_fields)
        show_legend = visual_type in PIE_TYPES or has_series
        return [
            ("background.show", "true"),
            ("border.show", "true"),
            ("border.radius", "6"),
            ("header.show", "false"),
            ("legend.show", "true" if show_legend else "false"),
        ]
    if preset == "table":
        return [
            ("background.show", "true"),
            ("border.show", "true"),
            ("border.radius", "4"),
            ("header.show", "false"),
            ("grid.horizontal", "true"),
            ("grid.vertical", "false"),
        ]
    if preset == "slicer":
        return [
            ("background.show", "true"),
            ("border.show", "true"),
            ("border.radius", "6"),
            ("header.show", "false"),
            ("slicerHeader.show", "false"),
        ]
    if preset == "card":
        return [
            ("background.show", "true"),
            ("border.show", "true"),
            ("border.radius", "8"),
            ("header.show", "false"),
        ]
    raise ValueError(f"Unsupported preset {preset}")


def _find_sort_candidate(visual_type: str, bound_fields: list[BoundField]) -> BoundField | None:
    """Pick the bound field most likely to define user-visible ordering."""
    if visual_type == "slicer":
        for field in bound_fields:
            if field.role == "Values":
                return field
        return None

    for field in bound_fields:
        if field.role == "Category":
            return field

    return None


def validate_builder_bindings(visual_type: str, bound_fields: list[BoundField]) -> None:
    """Validate common builder flows with stricter role/type guidance."""
    roles = {field.role for field in bound_fields}

    if visual_type in CHART_TYPES:
        if "Category" not in roles:
            raise ValueError(f"{visual_type} builders require a Category binding.")
        if not roles.intersection({"Y", "Y2"}):
            raise ValueError(f"{visual_type} builders require at least one value binding (Y or Y2).")
        _ensure_columns(bound_fields, {"Category", "Series", "Rows"})
        _ensure_measures(bound_fields, {"Y", "Y2", "Gradient"})
        return

    if visual_type in PIE_TYPES:
        _require_roles(visual_type, roles, {"Category", "Y"})
        _ensure_columns(bound_fields, {"Category", "Series"})
        _ensure_measures(bound_fields, {"Y"})
        return

    if visual_type == "slicer":
        _require_roles(visual_type, roles, {"Values"})
        value_fields = [field for field in bound_fields if field.role == "Values"]
        if len(value_fields) != 1:
            raise ValueError("slicer builders require exactly one Values binding.")
        _ensure_columns(bound_fields, {"Values"})
        return

    if visual_type == "tableEx":
        _require_roles(visual_type, roles, {"Values"})
        return

    if visual_type == "pivotTable":
        _require_roles(visual_type, roles, {"Values"})
        if not roles.intersection({"Rows", "Columns"}):
            raise ValueError("pivotTable builders require at least one grouping role (Rows or Columns).")
        _ensure_columns(bound_fields, {"Rows", "Columns"})
        return

    if visual_type == "cardVisual":
        _require_roles(visual_type, roles, {"Data"})
        _ensure_measures(bound_fields, {"Data"})
        _ensure_columns(bound_fields, {"Rows"})


def infer_auto_title(visual_type: str, bound_fields: list[BoundField]) -> str | None:
    """Infer a reasonable title from visual bindings."""
    if visual_type == "slicer":
        value = _first_field(bound_fields, "Values")
        return value.prop if value else None

    if visual_type == "cardVisual":
        data = _first_field(bound_fields, "Data")
        return data.prop if data else None

    if visual_type in CHART_TYPES | PIE_TYPES:
        category = _first_field(bound_fields, "Category")
        value_roles = [field for field in bound_fields if field.role in {"Y", "Y2"}]
        if category and value_roles:
            label = " and ".join(field.prop for field in value_roles[:2])
            return f"{label} by {category.prop}"
        if value_roles:
            return " and ".join(field.prop for field in value_roles[:2])

    return None


def _require_roles(visual_type: str, roles: set[str], required: set[str]) -> None:
    missing = sorted(required - roles)
    if missing:
        raise ValueError(f'{visual_type} builders require: {", ".join(missing)}.')


def _ensure_columns(bound_fields: list[BoundField], roles: set[str]) -> None:
    for field in bound_fields:
        if field.role in roles and field.field_type != "column":
            raise ValueError(f'Role "{field.role}" must use a column, not a {field.field_type}.')


def _ensure_measures(bound_fields: list[BoundField], roles: set[str]) -> None:
    for field in bound_fields:
        if field.role in roles and field.field_type != "measure":
            raise ValueError(f'Role "{field.role}" must use a measure, not a {field.field_type}.')


def _first_field(bound_fields: list[BoundField], role: str) -> BoundField | None:
    for field in bound_fields:
        if field.role == role:
            return field
    return None
