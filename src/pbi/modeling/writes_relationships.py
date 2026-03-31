"""Relationship write helpers for semantic-model mutations."""

from __future__ import annotations

import uuid
from pathlib import Path

from .parser import _parse_tmdl_name
from .schema import SemanticModel
from .writes import (
    TmdlEditSession,
    _commit_tmdl_lines,
    _format_tmdl_field_ref,
    _get_tmdl_lines,
)


def _get_relationships_path(project_root: Path, model: SemanticModel | None = None) -> Path:
    """Return the path to the relationships.tmdl file."""
    loaded_model = model or SemanticModel.load(project_root)
    return loaded_model.folder / "definition" / "relationships.tmdl"


def _find_relationship_block(
    lines: list[str],
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
) -> tuple[int, int] | None:
    """Find a relationship block by from/to columns."""
    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if stripped.startswith("relationship "):
            block_start = index
            index += 1
            props: dict[str, str] = {}
            while index < len(lines):
                current = lines[index].strip()
                if not current:
                    index += 1
                    continue
                if not current.startswith("relationship ") and ":" in current:
                    key, _, value = current.partition(":")
                    props[key.strip()] = value.strip()
                    index += 1
                else:
                    break
            block_end = index
            from_column_ref = props.get("fromColumn", "")
            to_column_ref = props.get("toColumn", "")
            from_dot = from_column_ref.find(".")
            to_dot = to_column_ref.find(".")
            if from_dot > 0 and to_dot > 0:
                parsed_from_table = _parse_tmdl_name(from_column_ref[:from_dot])
                parsed_from_column = _parse_tmdl_name(from_column_ref[from_dot + 1 :])
                parsed_to_table = _parse_tmdl_name(to_column_ref[:to_dot])
                parsed_to_column = _parse_tmdl_name(to_column_ref[to_dot + 1 :])
                if (
                    parsed_from_table.lower() == from_table.lower()
                    and parsed_from_column.lower() == from_column.lower()
                    and parsed_to_table.lower() == to_table.lower()
                    and parsed_to_column.lower() == to_column.lower()
                ):
                    return block_start, block_end
        else:
            index += 1
    return None


_TMDL_DIRECTION_MAP = {
    "single": "oneDirection",
    "singledirection": "oneDirection",
    "onedirection": "oneDirection",
    "both": "bothDirections",
    "bothdirections": "bothDirections",
    "automatic": "automatic",
}
_TMDL_SECURITY_FILTER_MAP = {
    "single": "oneDirection",
    "singledirection": "oneDirection",
    "onedirection": "oneDirection",
    "both": "bothDirections",
    "bothdirections": "bothDirections",
}
_TMDL_JOIN_ON_DATE_MAP = {
    "datepartonly": "datePartOnly",
}
_RELATIONSHIP_PROPERTY_ALIASES = {
    "referentialIntegrity": "relyOnReferentialIntegrity",
}
_CANONICAL_RELATIONSHIP_PROPERTIES = {
    "crossFilteringBehavior",
    "securityFilteringBehavior",
    "fromCardinality",
    "toCardinality",
    "isActive",
    "joinOnDateBehavior",
    "relyOnReferentialIntegrity",
}
_VALID_CROSS_FILTER_VALUES = {"oneDirection", "bothDirections", "automatic"}
_VALID_SECURITY_FILTER_VALUES = {"oneDirection", "bothDirections"}
_VALID_CARDINALITY_VALUES = {"one", "many"}
_VALID_BOOLEAN_VALUES = {"true", "false"}


def _canonical_relationship_property_name(name: str) -> str:
    stripped = str(name).strip()
    if stripped in _RELATIONSHIP_PROPERTY_ALIASES:
        return _RELATIONSHIP_PROPERTY_ALIASES[stripped]
    lowered = stripped.lower()
    for candidate in _CANONICAL_RELATIONSHIP_PROPERTIES:
        if candidate.lower() == lowered:
            return candidate
    return stripped


def normalize_relationship_properties(properties: dict[str, str] | None) -> dict[str, str]:
    """Normalize writable relationship properties to canonical stored values."""
    normalized: dict[str, str] = {}
    for raw_key, value in (properties or {}).items():
        key = _canonical_relationship_property_name(raw_key)
        text = str(value).strip()
        if key == "crossFilteringBehavior":
            normalized[key] = _TMDL_DIRECTION_MAP.get(text.lower(), text)
        elif key == "securityFilteringBehavior":
            normalized[key] = _TMDL_SECURITY_FILTER_MAP.get(text.lower(), text)
        elif key in {"fromCardinality", "toCardinality", "isActive", "relyOnReferentialIntegrity"}:
            normalized[key] = text.lower()
        elif key == "joinOnDateBehavior":
            normalized[key] = _TMDL_JOIN_ON_DATE_MAP.get(text.lower(), text)
        else:
            normalized[key] = text
    return normalized


def validate_relationship_properties(properties: dict[str, str] | None) -> None:
    """Validate writable relationship semantics before persisting them."""
    normalized = normalize_relationship_properties(properties)

    unknown_keys = sorted(key for key in normalized if key not in _CANONICAL_RELATIONSHIP_PROPERTIES)
    if unknown_keys:
        known = ", ".join(sorted(_CANONICAL_RELATIONSHIP_PROPERTIES))
        unknown = ", ".join(unknown_keys)
        raise ValueError(f"Unknown relationship property: {unknown}. Valid properties: {known}.")

    cross_filter = normalized.get("crossFilteringBehavior")
    if cross_filter and cross_filter not in _VALID_CROSS_FILTER_VALUES:
        raise ValueError(
            f'Invalid crossFilteringBehavior "{cross_filter}". '
            "Valid values: oneDirection, bothDirections, automatic."
        )

    security_filter = normalized.get("securityFilteringBehavior")
    if security_filter and security_filter not in _VALID_SECURITY_FILTER_VALUES:
        raise ValueError(
            f'Invalid securityFilteringBehavior "{security_filter}". '
            "Valid values: oneDirection, bothDirections."
        )

    is_active = normalized.get("isActive")
    if is_active and is_active not in _VALID_BOOLEAN_VALUES:
        raise ValueError(f'Invalid isActive "{is_active}". Use true or false.')

    referential_integrity = normalized.get("relyOnReferentialIntegrity")
    if referential_integrity and referential_integrity not in _VALID_BOOLEAN_VALUES:
        raise ValueError(
            f'Invalid relyOnReferentialIntegrity "{referential_integrity}". Use true or false.'
        )

    from_cardinality = normalized.get("fromCardinality")
    to_cardinality = normalized.get("toCardinality")
    for key, value in (
        ("fromCardinality", from_cardinality),
        ("toCardinality", to_cardinality),
    ):
        if value and value not in _VALID_CARDINALITY_VALUES:
            raise ValueError(f'Invalid {key} "{value}". Valid values: one, many.')

    if from_cardinality and not to_cardinality:
        raise ValueError("Set both fromCardinality and toCardinality together.")
    if to_cardinality and not from_cardinality:
        raise ValueError("Set both fromCardinality and toCardinality together.")

    if from_cardinality and to_cardinality:
        pair = (from_cardinality, to_cardinality)
        if pair not in {("many", "one"), ("many", "many"), ("one", "one")}:
            raise ValueError(
                "Invalid cardinality orientation. Use fromCardinality=many and toCardinality=one "
                "for standard many-to-one relationships, many/many for many-to-many, or one/one "
                "for one-to-one."
            )
        if pair == ("one", "one") and cross_filter == "oneDirection":
            raise ValueError(
                "One-to-one relationships cannot use crossFilteringBehavior=oneDirection. "
                "Use bothDirections or omit the cross-filter setting."
            )

    if security_filter == "bothDirections":
        pair = (
            normalized.get("fromCardinality", "many"),
            normalized.get("toCardinality", "one"),
        )
        if cross_filter == "oneDirection" or (not cross_filter and pair != ("one", "one")):
            raise ValueError(
                "securityFilteringBehavior=bothDirections requires bidirectional cross filtering. "
                "Use crossFilteringBehavior=bothDirections or a one-to-one relationship."
            )


def _build_relationship_block(
    rel_id: str,
    from_table: str,
    from_column: str,
    to_table: str,
    to_column: str,
    *,
    properties: dict[str, str] | None = None,
) -> list[str]:
    """Build a TMDL relationship block."""
    lines = [f"relationship {rel_id}"]
    if properties:
        for key, value in properties.items():
            if key not in ("fromColumn", "toColumn"):
                lines.append(f"\t{key}: {value}")
    lines.append(f"\tfromColumn: {_format_tmdl_field_ref(from_table, from_column)}")
    lines.append(f"\ttoColumn: {_format_tmdl_field_ref(to_table, to_column)}")
    return lines


def create_relationship(
    project_root: Path,
    from_field: str,
    to_field: str,
    *,
    properties: dict[str, str] | None = None,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, str]:
    """Create a new relationship. Returns (rel_id, from_ref, to_ref)."""
    from .schema import _parse_field_ref

    loaded_model = model or SemanticModel.load(project_root)
    from_table, from_column = _parse_field_ref(from_field)
    to_table, to_column = _parse_field_ref(to_field)

    source_table = loaded_model.find_table(from_table)
    source_table.find_column(from_column)
    target_table = loaded_model.find_table(to_table)
    target_table.find_column(to_column)

    for relationship in loaded_model.relationships:
        if (
            relationship.from_table.lower() == source_table.name.lower()
            and relationship.from_column.lower() == from_column.lower()
            and relationship.to_table.lower() == target_table.name.lower()
            and relationship.to_column.lower() == to_column.lower()
        ):
            raise ValueError(
                f'Relationship from "{source_table.name}.{from_column}" to "{target_table.name}.{to_column}" already exists.'
            )

    normalized_properties = normalize_relationship_properties(properties)
    validate_relationship_properties(normalized_properties)

    rel_id = str(uuid.uuid4())
    block = _build_relationship_block(
        rel_id,
        source_table.name,
        from_column,
        target_table.name,
        to_column,
        properties=normalized_properties,
    )

    rel_path = _get_relationships_path(project_root, loaded_model)
    if rel_path.exists():
        lines = _get_tmdl_lines(rel_path, edit_session)
        while lines and not lines[-1].strip():
            lines.pop()
        lines.append("")
        lines.extend(block)
        lines.append("")
    else:
        lines = block + [""]

    _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)

    return rel_id, f"{source_table.name}.{from_column}", f"{target_table.name}.{to_column}"


def delete_relationship(
    project_root: Path,
    from_field: str,
    to_field: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str]:
    """Delete a relationship by from/to field refs."""
    from .schema import _parse_field_ref

    loaded_model = model or SemanticModel.load(project_root)
    from_table, from_column = _parse_field_ref(from_field)
    to_table, to_column = _parse_field_ref(to_field)

    source_table = loaded_model.find_table(from_table)
    target_table = loaded_model.find_table(to_table)

    rel_path = _get_relationships_path(project_root, loaded_model)
    if not rel_path.exists():
        raise ValueError("No relationships.tmdl file found.")

    lines = _get_tmdl_lines(rel_path, edit_session)
    result = _find_relationship_block(lines, source_table.name, from_column, target_table.name, to_column)
    if result is None:
        raise ValueError(
            f'Relationship from "{source_table.name}.{from_column}" to "{target_table.name}.{to_column}" not found.'
        )

    start, end = result
    del lines[start:end]
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    if start > 0 and start < len(lines) and lines[start - 1].strip():
        lines.insert(start, "")

    _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)

    return f"{source_table.name}.{from_column}", f"{target_table.name}.{to_column}"


def set_relationship_property(
    project_root: Path,
    from_field: str,
    to_field: str,
    prop_name: str,
    prop_value: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Set a property on an existing relationship."""
    from .schema import _parse_field_ref

    loaded_model = model or SemanticModel.load(project_root)
    from_table, from_column = _parse_field_ref(from_field)
    to_table, to_column = _parse_field_ref(to_field)

    source_table = loaded_model.find_table(from_table)
    target_table = loaded_model.find_table(to_table)

    rel_path = _get_relationships_path(project_root, loaded_model)
    if not rel_path.exists():
        raise ValueError("No relationships.tmdl file found.")

    lines = _get_tmdl_lines(rel_path, edit_session)
    result = _find_relationship_block(lines, source_table.name, from_column, target_table.name, to_column)
    if result is None:
        raise ValueError(
            f'Relationship from "{source_table.name}.{from_column}" to "{target_table.name}.{to_column}" not found.'
        )

    current_properties: dict[str, str] = {}
    for relationship in loaded_model.relationships:
        if (
            relationship.from_table.lower() == source_table.name.lower()
            and relationship.from_column.lower() == from_column.lower()
            and relationship.to_table.lower() == target_table.name.lower()
            and relationship.to_column.lower() == to_column.lower()
        ):
            current_properties.update(relationship.properties)
            break

    normalized_value = normalize_relationship_properties({prop_name: prop_value}).get(prop_name, prop_value)
    candidate_properties = dict(current_properties)
    candidate_properties[prop_name] = normalized_value
    validate_relationship_properties(candidate_properties)

    start, end = result
    replacement = f"\t{prop_name}: {normalized_value}"
    for index in range(start + 1, end):
        if lines[index].strip().startswith(f"{prop_name}:"):
            if lines[index] == replacement:
                return f"{source_table.name}.{from_column}", f"{target_table.name}.{to_column}", False
            lines[index] = replacement
            _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)
            return f"{source_table.name}.{from_column}", f"{target_table.name}.{to_column}", True

    for index in range(start + 1, end):
        if lines[index].strip().startswith("fromColumn:"):
            lines.insert(index, replacement)
            _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)
            return f"{source_table.name}.{from_column}", f"{target_table.name}.{to_column}", True

    lines.insert(start + 1, replacement)
    _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)
    return f"{source_table.name}.{from_column}", f"{target_table.name}.{to_column}", True
