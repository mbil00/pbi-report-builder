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


_TMDL_CFB_MAP = {"singledirection": "oneDirection", "single": "oneDirection"}


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
                if key == "crossFilteringBehavior":
                    value = _TMDL_CFB_MAP.get(value.lower(), value)
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

    rel_id = str(uuid.uuid4())
    block = _build_relationship_block(
        rel_id,
        source_table.name,
        from_column,
        target_table.name,
        to_column,
        properties=properties,
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

    start, end = result
    replacement = f"\t{prop_name}: {prop_value}"
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
