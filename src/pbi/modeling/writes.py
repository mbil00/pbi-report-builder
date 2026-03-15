"""TMDL write helpers for semantic-model mutations."""

from __future__ import annotations

import re
import textwrap
import uuid
from pathlib import Path
from typing import Literal

from .parser import _parse_tmdl_name
from .schema import SemanticModel


def set_field_format(
    project_root: Path,
    field_ref: str,
    format_string: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, str, str, bool]:
    """Set the format string on a column or measure."""
    loaded_model = model or SemanticModel.load(project_root)
    table_name, field_name, field_type = loaded_model.resolve_field(field_ref)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    member_kind = "measure" if field_type == "measure" else "column"
    updated = _update_member_property(
        table.definition_path,
        member_kind=member_kind,
        member_name=field_name,
        property_name="formatString",
        property_value=format_string,
        dry_run=dry_run,
    )
    return table.name, field_name, field_type, updated


def set_column_hidden(
    project_root: Path,
    field_ref: str,
    hidden: bool,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, str, bool]:
    """Show or hide a column in TMDL."""
    loaded_model = model or SemanticModel.load(project_root)
    table_name, field_name, field_type = loaded_model.resolve_field(field_ref)
    if field_type != "column":
        raise ValueError(f'Field "{field_ref}" resolves to a {field_type}, not a column.')
    table = loaded_model.find_table(table_name)
    column = table.find_column(field_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    updated = _update_member_flag(
        table.definition_path,
        member_kind="column",
        member_name=column.name,
        flag_name="isHidden",
        present=hidden,
        dry_run=dry_run,
    )
    return table.name, column.name, updated


def create_measure(
    project_root: Path,
    table_name: str,
    measure_name: str,
    expression: str,
    *,
    format_string: str | None = None,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, str, bool]:
    """Create a new measure in a table TMDL file."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')
    if any(measure.name.lower() == measure_name.lower() for measure in table.measures):
        raise ValueError(f'Measure "{measure_name}" already exists in table "{table.name}".')

    lines = table.definition_path.read_text(encoding="utf-8-sig").splitlines()
    insert_at = _measure_insert_index(lines)
    block = _build_measure_block(
        measure_name,
        expression,
        format_string=format_string,
        lineage_tag=str(uuid.uuid4()),
    )
    lines[insert_at:insert_at] = _prepare_inserted_block(lines, insert_at, block)
    if not dry_run:
        _write_tmdl_lines(table.definition_path, lines)
    return table.name, measure_name, True


def edit_measure_expression(
    project_root: Path,
    table_name: str,
    measure_name: str,
    expression: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, str, bool]:
    """Replace a measure expression while preserving its metadata lines."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    measure = table.find_measure(measure_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    lines = table.definition_path.read_text(encoding="utf-8-sig").splitlines()
    start, end = _find_member_block(lines, member_kind="measure", member_name=measure.name)
    prop_start = _measure_property_start(lines, start, end)
    new_expression_lines = _build_measure_expression_lines(measure.name, expression)
    existing_expression_lines = lines[start:prop_start]
    if existing_expression_lines == new_expression_lines:
        return table.name, measure.name, False
    lines[start:prop_start] = new_expression_lines
    if not dry_run:
        _write_tmdl_lines(table.definition_path, lines)
    return table.name, measure.name, True


def delete_measure(
    project_root: Path,
    table_name: str,
    measure_name: str,
    *,
    dry_run: bool = False,
) -> tuple[str, str, bool]:
    """Delete an existing measure from a table TMDL file."""
    model = SemanticModel.load(project_root)
    table = model.find_table(table_name)
    measure = table.find_measure(measure_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    lines = table.definition_path.read_text(encoding="utf-8-sig").splitlines()
    start, end = _find_member_block(lines, member_kind="measure", member_name=measure.name)
    del lines[start:end]
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    if start > 0 and start < len(lines) and lines[start - 1].strip():
        lines.insert(start, "")
    if not dry_run:
        _write_tmdl_lines(table.definition_path, lines)
    return table.name, measure.name, True


def create_calculated_column(
    project_root: Path,
    table_name: str,
    column_name: str,
    expression: str,
    *,
    data_type: str,
    format_string: str | None = None,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, str, bool]:
    """Create a new calculated column in a table TMDL file."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')
    if any(column.name.lower() == column_name.lower() for column in table.columns):
        raise ValueError(f'Column "{column_name}" already exists in table "{table.name}".')

    lines = table.definition_path.read_text(encoding="utf-8-sig").splitlines()
    insert_at = _column_insert_index(lines)
    block = _build_calculated_column_block(
        column_name,
        expression,
        data_type=data_type,
        format_string=format_string,
        lineage_tag=str(uuid.uuid4()),
    )
    lines[insert_at:insert_at] = _prepare_inserted_block(lines, insert_at, block)
    if not dry_run:
        _write_tmdl_lines(table.definition_path, lines)
    return table.name, column_name, True


def edit_calculated_column_expression(
    project_root: Path,
    table_name: str,
    column_name: str,
    expression: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, str, bool]:
    """Replace a calculated-column expression while preserving metadata lines."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    column = table.find_column(column_name)
    if column.kind != "calculatedColumn":
        raise ValueError(f'Column "{table.name}.{column.name}" is a source column, not a calculated column.')
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    lines = table.definition_path.read_text(encoding="utf-8-sig").splitlines()
    start, end = _find_member_block(lines, member_kind="column", member_name=column.name)
    prop_start = _column_property_start(lines, start, end)
    new_expression_lines = _build_calculated_column_expression_lines(column.name, expression)
    existing_expression_lines = lines[start:prop_start]
    if existing_expression_lines == new_expression_lines:
        return table.name, column.name, False
    lines[start:prop_start] = new_expression_lines
    if not dry_run:
        _write_tmdl_lines(table.definition_path, lines)
    return table.name, column.name, True


def delete_calculated_column(
    project_root: Path,
    table_name: str,
    column_name: str,
    *,
    dry_run: bool = False,
) -> tuple[str, str, bool]:
    """Delete a calculated column. Refuses to delete source columns."""
    model = SemanticModel.load(project_root)
    table = model.find_table(table_name)
    column = table.find_column(column_name)
    if column.kind != "calculatedColumn":
        raise ValueError(f'Column "{table.name}.{column.name}" is a source column and cannot be deleted.')
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    lines = table.definition_path.read_text(encoding="utf-8-sig").splitlines()
    start, end = _find_member_block(lines, member_kind="column", member_name=column.name)
    del lines[start:end]
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    if start > 0 and start < len(lines) and lines[start - 1].strip():
        lines.insert(start, "")
    if not dry_run:
        _write_tmdl_lines(table.definition_path, lines)
    return table.name, column.name, True


def _update_member_property(
    path: Path,
    *,
    member_kind: Literal["column", "measure"],
    member_name: str,
    property_name: str,
    property_value: str,
    dry_run: bool,
) -> bool:
    """Set or insert a keyed property inside a column/measure block."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    start, end = _find_member_block(lines, member_kind=member_kind, member_name=member_name)

    replacement = f"\t\t{property_name}: {property_value}"
    for idx in range(start + 1, end):
        if lines[idx].strip().startswith(f"{property_name}:"):
            if lines[idx] == replacement:
                return False
            lines[idx] = replacement
            if not dry_run:
                _write_tmdl_lines(path, lines)
            return True

    insert_at = _block_property_insert_index(lines, start, end)
    lines.insert(insert_at, replacement)
    if not dry_run:
        _write_tmdl_lines(path, lines)
    return True


def _update_member_flag(
    path: Path,
    *,
    member_kind: Literal["column", "measure"],
    member_name: str,
    flag_name: str,
    present: bool,
    dry_run: bool,
) -> bool:
    """Set or clear a boolean flag line inside a member block."""
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    start, end = _find_member_block(lines, member_kind=member_kind, member_name=member_name)

    for idx in range(start + 1, end):
        if lines[idx].strip() == flag_name:
            if present:
                return False
            del lines[idx]
            if not dry_run:
                _write_tmdl_lines(path, lines)
            return True

    if not present:
        return False

    insert_at = _block_property_insert_index(lines, start, end)
    lines.insert(insert_at, f"\t\t{flag_name}")
    if not dry_run:
        _write_tmdl_lines(path, lines)
    return True


def _find_member_block(
    lines: list[str],
    *,
    member_kind: Literal["column", "measure"],
    member_name: str,
) -> tuple[int, int]:
    """Find the inclusive start/exclusive end lines for a table member block."""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if _indent_level(line) != 1:
            continue
        if not _matches_member_line(stripped, member_kind=member_kind, member_name=member_name):
            continue
        end = idx + 1
        while end < len(lines):
            stripped_next = lines[end].strip()
            if stripped_next and _indent_level(lines[end]) <= 1 and _starts_new_table_block(stripped_next):
                break
            end += 1
        return idx, end
    raise ValueError(f'{member_kind.title()} "{member_name}" not found in TMDL.')


def _matches_member_line(
    stripped: str,
    *,
    member_kind: Literal["column", "measure"],
    member_name: str,
) -> bool:
    """Return True when the stripped member declaration matches the target name."""
    candidates = ["column ", "calculatedColumn "] if member_kind == "column" else ["measure "]
    for prefix in candidates:
        if stripped.startswith(prefix):
            return _parse_tmdl_name(stripped[len(prefix) :]) == member_name
    return False


def _starts_new_table_block(stripped: str) -> bool:
    """Return True when a stripped line starts a new table-level block."""
    return stripped.startswith(("column ", "calculatedColumn ", "measure ", "partition ", "hierarchy ", "annotation "))


def _block_property_insert_index(lines: list[str], start: int, end: int) -> int:
    """Choose an insertion point within a member block before annotations/variations."""
    for idx in range(start + 1, end):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if _indent_level(lines[idx]) < 2:
            continue
        if stripped.startswith(("annotation ", "variation ")):
            return idx
    return end


def _indent_level(line: str) -> int:
    """Normalize leading tabs/spaces to the repo's logical indent depth."""
    indent = 0.0
    for ch in line:
        if ch == "\t":
            indent += 1
        elif ch == " ":
            indent += 0.25
        else:
            break
    return int(indent)


def _write_tmdl_lines(path: Path, lines: list[str]) -> None:
    """Write TMDL lines back to disk with a trailing newline."""
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _measure_insert_index(lines: list[str]) -> int:
    """Choose where a new measure block should be inserted in a table file."""
    last_measure_end: int | None = None
    first_non_measure: int | None = None

    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if _indent_level(lines[idx]) != 1:
            idx += 1
            continue
        if stripped.startswith("measure "):
            _, end = _find_member_block(lines, member_kind="measure", member_name=_parse_tmdl_name(stripped[8:]))
            last_measure_end = end
            idx = end
            continue
        if _starts_new_table_block(stripped) and first_non_measure is None:
            first_non_measure = idx
        idx += 1

    if last_measure_end is not None:
        return last_measure_end
    if first_non_measure is not None:
        return first_non_measure
    return len(lines)


def _prepare_inserted_block(lines: list[str], insert_at: int, block: list[str]) -> list[str]:
    """Normalize blank lines around an inserted block."""
    prepared = list(block)
    if insert_at > 0 and lines[insert_at - 1].strip():
        prepared.insert(0, "")
    if insert_at < len(lines) and lines[insert_at].strip():
        prepared.append("")
    return prepared


def _column_insert_index(lines: list[str]) -> int:
    """Choose where a new calculated-column block should be inserted in a table file."""
    last_column_end: int | None = None
    first_non_column: int | None = None

    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if _indent_level(lines[idx]) != 1:
            idx += 1
            continue
        if stripped.startswith(("column ", "calculatedColumn ")):
            _, end = _find_member_block(
                lines,
                member_kind="column",
                member_name=_parse_tmdl_name(stripped.split(" ", 1)[1]),
            )
            last_column_end = end
            idx = end
            continue
        if _starts_new_table_block(stripped) and first_non_column is None:
            first_non_column = idx
        idx += 1

    if last_column_end is not None:
        return last_column_end
    if first_non_column is not None:
        return first_non_column
    return len(lines)


def _build_measure_block(
    measure_name: str,
    expression: str,
    *,
    format_string: str | None,
    lineage_tag: str,
) -> list[str]:
    """Build a full measure TMDL block."""
    lines = _build_measure_expression_lines(measure_name, expression)
    if format_string:
        lines.append(f"\t\tformatString: {format_string}")
    lines.append(f"\t\tlineageTag: {lineage_tag}")
    return lines


def _build_measure_expression_lines(measure_name: str, expression: str) -> list[str]:
    """Build the declaration and expression lines for a measure."""
    normalized = textwrap.dedent(expression).strip("\n")
    expr_lines = [line.rstrip() for line in normalized.splitlines()]
    if not expr_lines or not any(line.strip() for line in expr_lines):
        raise ValueError("Measure expression cannot be empty.")

    name = _format_tmdl_name(measure_name)
    if len(expr_lines) == 1:
        return [f"\tmeasure {name} = {expr_lines[0].strip()}"]

    lines = [f"\tmeasure {name} ="]
    lines.extend(f"\t\t{line}" for line in expr_lines)
    return lines


def _measure_property_start(lines: list[str], start: int, end: int) -> int:
    """Return the first metadata line inside a measure block."""
    for idx in range(start + 1, end):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if _indent_level(lines[idx]) < 2:
            continue
        if stripped == "isHidden" or ":" in stripped or stripped.startswith("annotation "):
            return idx
    return end


def _build_calculated_column_block(
    column_name: str,
    expression: str,
    *,
    data_type: str,
    format_string: str | None,
    lineage_tag: str,
) -> list[str]:
    """Build a full calculated-column TMDL block."""
    lines = _build_calculated_column_expression_lines(column_name, expression)
    lines.append(f"\t\tdataType: {data_type}")
    if format_string:
        lines.append(f"\t\tformatString: {format_string}")
    lines.append(f"\t\tlineageTag: {lineage_tag}")
    lines.append("\t\tsummarizeBy: none")
    return lines


def _build_calculated_column_expression_lines(column_name: str, expression: str) -> list[str]:
    """Build the declaration and expression lines for a calculated column."""
    normalized = textwrap.dedent(expression).strip("\n")
    expr_lines = [line.rstrip() for line in normalized.splitlines()]
    if not expr_lines or not any(line.strip() for line in expr_lines):
        raise ValueError("Calculated column expression cannot be empty.")

    name = _format_tmdl_name(column_name)
    if len(expr_lines) == 1:
        return [f"\tcolumn {name} = {expr_lines[0].strip()}"]

    lines = [f"\tcolumn {name} ="]
    lines.extend(f"\t\t{line}" for line in expr_lines)
    return lines


def _column_property_start(lines: list[str], start: int, end: int) -> int:
    """Return the first metadata line inside a column block."""
    for idx in range(start + 1, end):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if _indent_level(lines[idx]) < 2:
            continue
        if stripped == "isHidden" or ":" in stripped or stripped.startswith(("annotation ", "variation ")):
            return idx
    return end


def _format_tmdl_name(name: str) -> str:
    """Format a TMDL identifier, quoting names with spaces or punctuation."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    escaped = name.replace("'", "''")
    return f"'{escaped}'"
