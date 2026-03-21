"""TMDL write helpers for semantic-model partitions."""

from __future__ import annotations

import textwrap
from pathlib import Path

from .schema import Partition, SemanticModel
from .writes import (
    TmdlEditSession,
    _collapse_blank_lines,
    _commit_tmdl_lines,
    _format_tmdl_name,
    _get_tmdl_lines,
    _indent_level,
    _prepare_inserted_block,
    _starts_new_table_block,
)

_PARTITION_SOURCE_TYPES = frozenset({"m", "calculated"})
_PARTITION_MODES = frozenset({"import", "directQuery", "default"})


def create_partition(
    project_root: Path,
    table_name: str,
    partition_name: str,
    source_expression: str,
    *,
    source_type: str,
    mode: str = "import",
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Create one partition in a table TMDL file."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')
    try:
        table.find_partition(partition_name)
    except ValueError:
        pass
    else:
        raise ValueError(f'Partition "{partition_name}" already exists in table "{table.name}".')

    partition = _build_partition(table.name, partition_name, source_expression, source_type=source_type, mode=mode, path=table.definition_path)
    lines = _get_tmdl_lines(table.definition_path, edit_session)
    insert_at = _partition_insert_index(lines)
    block = _render_partition_block(partition)
    lines[insert_at:insert_at] = _prepare_inserted_block(lines, insert_at, block)
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)
    return table.name, partition.name, True


def set_partition(
    project_root: Path,
    table_name: str,
    partition_name: str,
    *,
    source_expression: str | None = None,
    source_type: str | None = None,
    mode: str | None = None,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Update one partition in a table TMDL file."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    partition = table.find_partition(partition_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    updated = _build_partition(
        table.name,
        partition.name,
        source_expression if source_expression is not None else partition.source_expression,
        source_type=source_type or partition.source_type,
        mode=mode or partition.mode,
        path=table.definition_path,
    )
    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, end = _find_partition_block(lines, partition.name)
    block = _render_partition_block(updated)
    if lines[start:end] == block:
        return table.name, partition.name, False
    lines[start:end] = block
    _commit_tmdl_lines(table.definition_path, _collapse_blank_lines(lines), dry_run=dry_run, session=edit_session)
    return table.name, partition.name, True


def delete_partition(
    project_root: Path,
    table_name: str,
    partition_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Delete one partition from a table TMDL file."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    partition = table.find_partition(partition_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')
    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, end = _find_partition_block(lines, partition.name)
    del lines[start:end]
    _commit_tmdl_lines(table.definition_path, _collapse_blank_lines(lines), dry_run=dry_run, session=edit_session)
    return table.name, partition.name, True


def _build_partition(
    table_name: str,
    partition_name: str,
    source_expression: str,
    *,
    source_type: str,
    mode: str,
    path: Path,
) -> Partition:
    normalized_type = source_type.strip()
    normalized_mode = mode.strip()
    if normalized_type not in _PARTITION_SOURCE_TYPES:
        allowed = ", ".join(sorted(_PARTITION_SOURCE_TYPES))
        raise ValueError(f'Invalid partition sourceType "{source_type}". Allowed: {allowed}')
    if normalized_mode not in _PARTITION_MODES:
        allowed = ", ".join(sorted(_PARTITION_MODES))
        raise ValueError(f'Invalid partition mode "{mode}". Allowed: {allowed}')
    normalized_expression = textwrap.dedent(source_expression).strip("\n")
    if not normalized_expression.strip():
        raise ValueError("Partition source expression cannot be empty.")
    return Partition(
        name=partition_name,
        table=table_name,
        source_type=normalized_type,
        mode=normalized_mode,
        source_expression=normalized_expression,
        definition_path=path,
    )


def _find_partition_block(lines: list[str], partition_name: str) -> tuple[int, int]:
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if _indent_level(line) != 1 or not stripped.startswith("partition "):
            continue
        rest = stripped[len("partition "):]
        if _parse_partition_name(rest) != partition_name:
            continue
        end = idx + 1
        while end < len(lines):
            stripped_next = lines[end].strip()
            if stripped_next and _indent_level(lines[end]) <= 1 and _starts_new_table_block(stripped_next):
                break
            end += 1
        return idx, end
    raise ValueError(f'Partition "{partition_name}" not found in TMDL.')


def _partition_insert_index(lines: list[str]) -> int:
    last_partition_end: int | None = None
    first_annotation: int | None = None
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if _indent_level(line) != 1:
            continue
        if stripped.startswith("annotation ") and first_annotation is None:
            first_annotation = idx
        if not stripped.startswith("partition "):
            continue
        _, end = _find_partition_block(lines, _parse_partition_name(stripped[len("partition ") :]))
        last_partition_end = end
    if last_partition_end is not None:
        return last_partition_end
    if first_annotation is not None:
        return first_annotation
    return len(lines)


def _render_partition_block(partition: Partition) -> list[str]:
    lines = [
        f"\tpartition {_format_tmdl_name(partition.name)} = {partition.source_type}",
        f"\t\tmode: {partition.mode}",
    ]
    source_lines = partition.source_expression.splitlines()
    if len(source_lines) <= 1:
        lines.append(f"\t\tsource = {source_lines[0].strip()}")
    else:
        lines.append("\t\tsource =")
        for line in source_lines:
            lines.append(f"\t\t\t\t{line.rstrip()}")
    return lines


def _parse_partition_name(rest: str) -> str:
    from .parser import _parse_tmdl_name

    return _parse_tmdl_name(rest)
