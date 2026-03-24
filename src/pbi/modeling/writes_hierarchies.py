"""Hierarchy write helpers for semantic-model mutations."""

from __future__ import annotations

import uuid
from pathlib import Path

from .parser import _parse_tmdl_name
from .schema import SemanticModel
from .writes import (
    TmdlEditSession,
    _column_insert_index,
    _commit_tmdl_lines,
    _format_tmdl_name,
    _get_tmdl_lines,
    _indent_level,
    _prepare_inserted_block,
    _starts_new_table_block,
    _find_member_block,
)


def _find_hierarchy_block(
    lines: list[str],
    hierarchy_name: str,
) -> tuple[int, int] | None:
    """Find a hierarchy block by name."""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if _indent_level(line) == 1 and stripped.startswith("hierarchy "):
            name = _parse_tmdl_name(stripped[10:])
            if name.lower() == hierarchy_name.lower():
                end = index + 1
                while end < len(lines):
                    next_stripped = lines[end].strip()
                    if next_stripped and _indent_level(lines[end]) <= 1 and _starts_new_table_block(next_stripped):
                        break
                    end += 1
                return index, end
    return None


def _hierarchy_insert_index(lines: list[str]) -> int:
    """Choose where a new hierarchy block should be inserted."""
    last_measure_end: int | None = None
    last_hierarchy_end: int | None = None

    index = 0
    while index < len(lines):
        stripped = lines[index].strip()
        if _indent_level(lines[index]) != 1:
            index += 1
            continue
        if stripped.startswith("measure "):
            _, end = _find_member_block(
                lines,
                member_kind="measure",
                member_name=_parse_tmdl_name(stripped[8:]),
            )
            last_measure_end = end
            index = end
            continue
        if stripped.startswith("hierarchy "):
            result = _find_hierarchy_block(lines, _parse_tmdl_name(stripped[10:]))
            if result:
                last_hierarchy_end = result[1]
                index = result[1]
                continue
        index += 1

    if last_hierarchy_end is not None:
        return last_hierarchy_end
    if last_measure_end is not None:
        return last_measure_end
    return _column_insert_index(lines)


def _build_hierarchy_block(
    hierarchy_name: str,
    level_columns: list[str],
    *,
    lineage_tag: str | None = None,
) -> list[str]:
    """Build a TMDL hierarchy block."""
    name = _format_tmdl_name(hierarchy_name)
    lines = [f"\thierarchy {name}"]
    tag = lineage_tag or str(uuid.uuid4())
    lines.append(f"\t\tlineageTag: {tag}")

    for column_name in level_columns:
        lines.append("")
        level_name = _format_tmdl_name(column_name)
        lines.append(f"\t\tlevel {level_name}")
        lines.append(f"\t\t\tlineageTag: {uuid.uuid4()}")
        lines.append(f"\t\t\tcolumn: {_format_tmdl_name(column_name)}")

    return lines


def create_hierarchy(
    project_root: Path,
    table_name: str,
    hierarchy_name: str,
    level_columns: list[str],
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Create a new hierarchy in a table."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    for hierarchy in table.hierarchies:
        if hierarchy.name.lower() == hierarchy_name.lower():
            raise ValueError(f'Hierarchy "{hierarchy_name}" already exists in table "{table.name}".')

    for column_name in level_columns:
        table.find_column(column_name)
    if not level_columns:
        raise ValueError("A hierarchy requires at least one level column.")

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    insert_at = _hierarchy_insert_index(lines)
    block = _build_hierarchy_block(hierarchy_name, level_columns)
    lines[insert_at:insert_at] = _prepare_inserted_block(lines, insert_at, block)
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)

    return table.name, hierarchy_name, True


def delete_hierarchy(
    project_root: Path,
    table_name: str,
    hierarchy_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Delete a hierarchy from a table."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    table.find_hierarchy(hierarchy_name)

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    result = _find_hierarchy_block(lines, hierarchy_name)
    if result is None:
        raise ValueError(f'Hierarchy "{hierarchy_name}" not found in TMDL.')

    start, end = result
    del lines[start:end]
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    if start > 0 and start < len(lines) and lines[start - 1].strip():
        lines.insert(start, "")

    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)
    return table.name, hierarchy_name, True
