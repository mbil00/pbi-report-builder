"""TMDL write helpers for semantic-model mutations."""

from __future__ import annotations

import re
import textwrap
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from .parser import _TMDL_PROPERTY_NAMES, _parse_tmdl_name
from .schema import SemanticModel


_MEMBER_PROPERTY_WHITELIST = frozenset({
    "displayFolder", "sortByColumn",
    "summarizeBy", "dataCategory", "formatString",
})

_TABLE_PROPERTY_WHITELIST = frozenset({
    "dataCategory",
})

_RESERVED_OBJECT_NAMES = frozenset({
    "aux",
    "clock$",
    "con",
    "nul",
    "prn",
})
_RESERVED_TABLE_NAMES = frozenset({
    "measures",
})

_DATATABLE_TYPE_MAP = {
    "STRING": "string",
    "TEXT": "string",
    "DOUBLE": "double",
    "DECIMAL": "double",
    "CURRENCY": "double",
    "INTEGER": "int64",
    "INT64": "int64",
    "WHOLE": "int64",
    "DATETIME": "dateTime",
    "DATE": "dateTime",
    "BOOLEAN": "boolean",
    "BOOL": "boolean",
}


@dataclass
class TmdlEditSession:
    """Buffer repeated TMDL reads/writes across one logical command."""

    _lines_by_path: dict[Path, list[str]] = field(default_factory=dict, init=False, repr=False)
    _dirty_paths: set[Path] = field(default_factory=set, init=False, repr=False)

    def get_lines(self, path: Path) -> list[str]:
        """Return a mutable line buffer for a TMDL file, loading it once."""
        lines = self._lines_by_path.get(path)
        if lines is None:
            if path.exists():
                lines = path.read_text(encoding="utf-8-sig").splitlines()
            else:
                lines = []
            self._lines_by_path[path] = lines
        return lines

    def mark_dirty(self, path: Path) -> None:
        """Mark a buffered file as needing a final write."""
        self._dirty_paths.add(path)

    def flush(self) -> None:
        """Write all dirty TMDL buffers back to disk once."""
        for path in sorted(self._dirty_paths):
            path.parent.mkdir(parents=True, exist_ok=True)
            _write_tmdl_lines(path, self._lines_by_path[path])
        self._dirty_paths.clear()


def _get_tmdl_lines(path: Path, session: TmdlEditSession | None) -> list[str]:
    """Read a TMDL file once, using the session cache when available."""
    if session is not None:
        return session.get_lines(path)
    if path.exists():
        return path.read_text(encoding="utf-8-sig").splitlines()
    return []


def validate_model_object_name(name: str, object_kind: Literal["table", "column", "measure"]) -> None:
    """Validate a semantic-model object name against documented engine constraints."""
    if not name or not name.strip():
        raise ValueError(f"{object_kind.title()} name cannot be empty.")
    if name != name.strip():
        raise ValueError(f"{object_kind.title()} name cannot have leading or trailing spaces.")
    if len(name) > 100:
        raise ValueError(f"{object_kind.title()} name cannot exceed 100 characters.")
    if any(ord(ch) == 0 or ord(ch) < 32 for ch in name):
        raise ValueError(f"{object_kind.title()} name cannot contain control characters.")

    lowered = name.lower()
    if lowered in _RESERVED_OBJECT_NAMES:
        raise ValueError(f'"{name}" is a reserved {object_kind} name.')
    if re.fullmatch(r"com[1-9]", lowered) or re.fullmatch(r"lpt[1-9]", lowered):
        raise ValueError(f'"{name}" is a reserved {object_kind} name.')
    if object_kind == "table" and lowered in _RESERVED_TABLE_NAMES:
        raise ValueError(f'"{name}" is a reserved table name.')


def validate_table_name(table_name: str) -> None:
    """Validate a table name before creating or renaming it."""
    validate_model_object_name(table_name, "table")


def validate_column_name(column_name: str) -> None:
    """Validate a column name before creating or renaming it."""
    validate_model_object_name(column_name, "column")


def validate_measure_name(measure_name: str) -> None:
    """Validate a measure name before creating or renaming it."""
    validate_model_object_name(measure_name, "measure")


def _commit_tmdl_lines(
    path: Path,
    lines: list[str],
    *,
    dry_run: bool,
    session: TmdlEditSession | None,
) -> None:
    """Persist modified TMDL lines immediately or defer via the session."""
    if dry_run:
        return
    if session is not None:
        session._lines_by_path[path] = lines
        session.mark_dirty(path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_tmdl_lines(path, lines)


def set_member_property(
    project_root: Path,
    field_ref: str,
    property_name: str,
    property_value: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, str, bool]:
    """Set a metadata property on a column or measure.

    Returns (table_name, field_name, field_type, changed).
    """
    if property_name == "description":
        raise ValueError(
            'Property "description" is not supported by Power BI TMDL for columns or measures.'
        )
    if property_name not in _MEMBER_PROPERTY_WHITELIST:
        raise ValueError(
            f'Property "{property_name}" is not writable. '
            f'Allowed: {", ".join(sorted(_MEMBER_PROPERTY_WHITELIST))}'
        )
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
        property_name=property_name,
        property_value=property_value,
        dry_run=dry_run,
        edit_session=edit_session,
    )
    return table.name, field_name, field_type, updated


def set_table_property(
    project_root: Path,
    table_name: str,
    property_name: str,
    property_value: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Set a metadata property on a table."""
    if property_name not in _TABLE_PROPERTY_WHITELIST:
        raise ValueError(
            f'Property "{property_name}" is not writable. '
            f'Allowed: {", ".join(sorted(_TABLE_PROPERTY_WHITELIST))}'
        )
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    updated = _update_table_property(
        table.definition_path,
        property_name=property_name,
        property_value=property_value,
        dry_run=dry_run,
        edit_session=edit_session,
    )
    return table.name, updated


def set_column_key(
    project_root: Path,
    field_ref: str,
    is_key: bool,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Set or clear the isKey flag on a column."""
    loaded_model = model or SemanticModel.load(project_root)
    table_name, field_name, field_type = loaded_model.resolve_field(field_ref)
    if field_type != "column":
        raise ValueError(f'Field "{field_ref}" resolves to a {field_type}, not a column.')
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    updated = _update_member_flag(
        table.definition_path,
        member_kind="column",
        member_name=field_name,
        flag_name="isKey",
        present=is_key,
        dry_run=dry_run,
        edit_session=edit_session,
    )
    return table.name, field_name, updated


def mark_as_date_table(
    project_root: Path,
    table_name: str,
    column_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Mark a table as a date table using the specified date column."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    column = table.find_column(column_name)
    if column.data_type.lower() not in {"date", "datetime"}:
        raise ValueError(
            f'Column "{table.name}.{column.name}" must use a date/dateTime data type to mark the table as a date table.'
        )

    changed = False
    _, table_changed = set_table_property(
        project_root,
        table.name,
        "dataCategory",
        "Time",
        dry_run=dry_run,
        model=loaded_model,
        edit_session=edit_session,
    )
    changed = changed or table_changed
    for existing in table.columns:
        _, _, key_changed = set_column_key(
            project_root,
            f"{table.name}.{existing.name}",
            existing.name == column.name,
            dry_run=dry_run,
            model=loaded_model,
            edit_session=edit_session,
        )
        changed = changed or key_changed
    return table.name, column.name, changed


def set_time_intelligence_enabled(
    project_root: Path,
    enabled: bool,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Set the Power BI model time-intelligence toggle."""
    loaded_model = model or SemanticModel.load(project_root)
    model_path = _get_model_tmdl_path(loaded_model)
    value = "1" if enabled else "0"
    changed = _update_model_annotation(
        model_path,
        annotation_name="__PBI_TimeIntelligenceEnabled",
        annotation_value=value,
        dry_run=dry_run,
        edit_session=edit_session,
    )
    if not enabled:
        cleanup_changed = _remove_auto_date_tables(
            loaded_model,
            dry_run=dry_run,
            edit_session=edit_session,
        )
        changed = changed or cleanup_changed
    return changed


def set_model_annotation(
    project_root: Path,
    annotation_name: str,
    annotation_value: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Set a model-level annotation."""
    loaded_model = model or SemanticModel.load(project_root)
    model_path = _get_model_tmdl_path(loaded_model)
    changed = _update_model_annotation(
        model_path,
        annotation_name=annotation_name,
        annotation_value=annotation_value,
        dry_run=dry_run,
        edit_session=edit_session,
    )
    return annotation_name, changed


def delete_model_annotation(
    project_root: Path,
    annotation_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Delete a model-level annotation."""
    loaded_model = model or SemanticModel.load(project_root)
    model_path = _get_model_tmdl_path(loaded_model)
    lines = _get_tmdl_lines(model_path, edit_session)
    for idx, line in enumerate(lines):
        if not line.strip().startswith(f"annotation {annotation_name} ="):
            continue
        del lines[idx]
        _commit_tmdl_lines(model_path, _collapse_blank_lines(lines), dry_run=dry_run, session=edit_session)
        return annotation_name, True
    return annotation_name, False


def set_field_format(
    project_root: Path,
    field_ref: str,
    format_string: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
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
        edit_session=edit_session,
    )
    return table.name, field_name, field_type, updated


def set_column_hidden(
    project_root: Path,
    field_ref: str,
    hidden: bool,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
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
        edit_session=edit_session,
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
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Create a new measure in a table TMDL file."""
    loaded_model = model or SemanticModel.load(project_root)
    validate_measure_name(measure_name)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')
    if any(measure.name.lower() == measure_name.lower() for measure in table.measures):
        raise ValueError(f'Measure "{measure_name}" already exists in table "{table.name}".')

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    insert_at = _measure_insert_index(lines)
    block = _build_measure_block(
        measure_name,
        expression,
        format_string=format_string,
        lineage_tag=str(uuid.uuid4()),
    )
    lines[insert_at:insert_at] = _prepare_inserted_block(lines, insert_at, block)
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)
    return table.name, measure_name, True


def edit_measure_expression(
    project_root: Path,
    table_name: str,
    measure_name: str,
    expression: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Replace a measure expression while preserving its metadata lines."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    measure = table.find_measure(measure_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, end = _find_member_block(lines, member_kind="measure", member_name=measure.name)
    prop_start = _measure_property_start(lines, start, end)
    new_expression_lines = _build_measure_expression_lines(measure.name, expression)
    existing_expression_lines = lines[start:prop_start]
    if existing_expression_lines == new_expression_lines:
        return table.name, measure.name, False
    lines[start:prop_start] = new_expression_lines
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)
    return table.name, measure.name, True


def delete_measure(
    project_root: Path,
    table_name: str,
    measure_name: str,
    *,
    dry_run: bool = False,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Delete an existing measure from a table TMDL file."""
    model = SemanticModel.load(project_root)
    table = model.find_table(table_name)
    measure = table.find_measure(measure_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, end = _find_member_block(lines, member_kind="measure", member_name=measure.name)
    del lines[start:end]
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    if start > 0 and start < len(lines) and lines[start - 1].strip():
        lines.insert(start, "")
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)
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
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Create a new calculated column in a table TMDL file."""
    loaded_model = model or SemanticModel.load(project_root)
    validate_column_name(column_name)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')
    if any(column.name.lower() == column_name.lower() for column in table.columns):
        raise ValueError(f'Column "{column_name}" already exists in table "{table.name}".')

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    insert_at = _column_insert_index(lines)
    block = _build_calculated_column_block(
        column_name,
        expression,
        data_type=data_type,
        format_string=format_string,
        lineage_tag=str(uuid.uuid4()),
    )
    lines[insert_at:insert_at] = _prepare_inserted_block(lines, insert_at, block)
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)
    return table.name, column_name, True


def edit_calculated_column_expression(
    project_root: Path,
    table_name: str,
    column_name: str,
    expression: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Replace a calculated-column expression while preserving metadata lines."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    column = table.find_column(column_name)
    if column.kind != "calculatedColumn":
        raise ValueError(f'Column "{table.name}.{column.name}" is a source column, not a calculated column.')
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, end = _find_member_block(lines, member_kind="column", member_name=column.name)
    prop_start = _column_property_start(lines, start, end)
    new_expression_lines = _build_calculated_column_expression_lines(column.name, expression)
    existing_expression_lines = lines[start:prop_start]
    if existing_expression_lines == new_expression_lines:
        return table.name, column.name, False
    lines[start:prop_start] = new_expression_lines
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)
    return table.name, column.name, True


def delete_calculated_column(
    project_root: Path,
    table_name: str,
    column_name: str,
    *,
    dry_run: bool = False,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Delete a calculated column. Refuses to delete source columns."""
    model = SemanticModel.load(project_root)
    table = model.find_table(table_name)
    column = table.find_column(column_name)
    if column.kind != "calculatedColumn":
        raise ValueError(f'Column "{table.name}.{column.name}" is a source column and cannot be deleted.')
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, end = _find_member_block(lines, member_kind="column", member_name=column.name)
    del lines[start:end]
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    if start > 0 and start < len(lines) and lines[start - 1].strip():
        lines.insert(start, "")
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)
    return table.name, column.name, True


def _update_member_property(
    path: Path,
    *,
    member_kind: Literal["column", "measure"],
    member_name: str,
    property_name: str,
    property_value: str,
    dry_run: bool,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Set or insert a keyed property inside a column/measure block."""
    lines = _get_tmdl_lines(path, edit_session)
    start, end = _find_member_block(lines, member_kind=member_kind, member_name=member_name)

    replacement = f"\t\t{property_name}: {_format_tmdl_property_value(property_name, property_value)}"
    for idx in range(start + 1, end):
        if lines[idx].strip().startswith(f"{property_name}:"):
            if lines[idx] == replacement:
                return False
            lines[idx] = replacement
            _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
            return True

    insert_at = _block_property_insert_index(lines, start, end)
    lines.insert(insert_at, replacement)
    _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
    return True


def _update_table_property(
    path: Path,
    *,
    property_name: str,
    property_value: str,
    dry_run: bool,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Set or insert a keyed property inside the table block."""
    lines = _get_tmdl_lines(path, edit_session)

    replacement = f"\t{property_name}: {property_value}"
    for idx in range(1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if _indent_level(lines[idx]) != 1:
            continue
        if _starts_new_table_block(stripped):
            break
        if stripped.startswith(f"{property_name}:"):
            if lines[idx] == replacement:
                return False
            lines[idx] = replacement
            _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
            return True

    insert_at = _table_property_insert_index(lines)
    lines.insert(insert_at, replacement)
    _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
    return True


def _update_member_flag(
    path: Path,
    *,
    member_kind: Literal["column", "measure"],
    member_name: str,
    flag_name: str,
    present: bool,
    dry_run: bool,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Set or clear a boolean flag line inside a member block."""
    lines = _get_tmdl_lines(path, edit_session)
    start, end = _find_member_block(lines, member_kind=member_kind, member_name=member_name)

    for idx in range(start + 1, end):
        if lines[idx].strip() == flag_name:
            if present:
                return False
            del lines[idx]
            _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
            return True

    if not present:
        return False

    insert_at = _block_property_insert_index(lines, start, end)
    lines.insert(insert_at, f"\t\t{flag_name}")
    _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
    return True


def _update_model_annotation(
    path: Path,
    *,
    annotation_name: str,
    annotation_value: str,
    dry_run: bool,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Set or insert a model-level annotation."""
    lines = _get_tmdl_lines(path, edit_session)
    replacement = f"annotation {annotation_name} = {annotation_value}"
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if not stripped.startswith(f"annotation {annotation_name} ="):
            continue
        if stripped == replacement:
            return False
        lines[idx] = replacement
        _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
        return True

    insert_at = _model_annotation_insert_index(lines)
    lines.insert(insert_at, replacement)
    _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
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
    blank_before_body: int | None = None
    for idx in range(start + 1, end):
        stripped = lines[idx].strip()
        if not stripped:
            if blank_before_body is None:
                blank_before_body = idx
            continue
        if _indent_level(lines[idx]) < 2:
            continue
        if stripped.startswith(("annotation ", "variation ")):
            return blank_before_body if blank_before_body is not None else idx
        blank_before_body = None
    if blank_before_body is not None:
        return blank_before_body
    return end


def _table_property_insert_index(lines: list[str]) -> int:
    """Choose an insertion point within a table block before members/annotations."""
    for idx in range(1, len(lines)):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if _indent_level(lines[idx]) != 1:
            continue
        if _starts_new_table_block(stripped):
            return idx
    return len(lines)


def _model_annotation_insert_index(lines: list[str]) -> int:
    """Insert model annotations before the first ref/culture section when possible."""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("ref "):
            return idx
    return len(lines)


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


def _split_top_level_args(text: str) -> list[str]:
    """Split a function call argument list on top-level commas."""
    items: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            current.append(ch)
            if in_string and i + 1 < len(text) and text[i + 1] == '"':
                current.append(text[i + 1])
                i += 2
                continue
            in_string = not in_string
            i += 1
            continue
        if not in_string:
            if ch in "([{":
                depth += 1
            elif ch in ")]}":
                depth = max(0, depth - 1)
            elif ch == "," and depth == 0:
                items.append("".join(current).strip())
                current = []
                i += 1
                continue
        current.append(ch)
        i += 1
    tail = "".join(current).strip()
    if tail:
        items.append(tail)
    return items


def _extract_function_args(expression: str, function_name: str) -> list[str] | None:
    """Return top-level arguments for a simple FUNCTION(arg1, arg2) expression."""
    stripped = textwrap.dedent(expression).strip()
    pattern = re.compile(rf"^{function_name}\s*\((.*)\)\s*$", re.IGNORECASE | re.DOTALL)
    match = pattern.match(stripped)
    if match is None:
        return None
    return _split_top_level_args(match.group(1))


def _infer_calculated_table_columns(expression: str) -> list[tuple[str, str]]:
    """Infer common calculated-table column definitions from the DAX shape."""
    row_args = _extract_function_args(expression, "ROW")
    if row_args is not None:
        columns: list[tuple[str, str]] = []
        for index in range(0, len(row_args), 2):
            if index + 1 >= len(row_args):
                break
            name_token = row_args[index].strip()
            if len(name_token) >= 2 and name_token.startswith('"') and name_token.endswith('"'):
                columns.append((name_token[1:-1].replace('""', '"'), "string"))
        return columns

    datatable_args = _extract_function_args(expression, "DATATABLE")
    if datatable_args is not None:
        columns = []
        index = 0
        while index + 1 < len(datatable_args):
            name_token = datatable_args[index].strip()
            type_token = datatable_args[index + 1].strip().upper()
            if not (len(name_token) >= 2 and name_token.startswith('"') and name_token.endswith('"')):
                break
            if type_token not in _DATATABLE_TYPE_MAP:
                break
            columns.append((name_token[1:-1].replace('""', '"'), _DATATABLE_TYPE_MAP[type_token]))
            index += 2
        return columns

    if _extract_function_args(expression, "CALENDAR") is not None or _extract_function_args(expression, "CALENDARAUTO") is not None:
        return [("Date", "dateTime")]

    if _extract_function_args(expression, "GENERATESERIES") is not None:
        return [("Value", "double")]

    addcolumns_args = _extract_function_args(expression, "ADDCOLUMNS")
    if addcolumns_args is not None and addcolumns_args:
        columns = _infer_calculated_table_columns(addcolumns_args[0])
        seen = {name.lower() for name, _data_type in columns}
        for index in range(1, len(addcolumns_args), 2):
            if index + 1 >= len(addcolumns_args):
                break
            name_token = addcolumns_args[index].strip()
            if len(name_token) < 2 or not (name_token.startswith('"') and name_token.endswith('"')):
                continue
            column_name = name_token[1:-1].replace('""', '"')
            if column_name.lower() in seen:
                continue
            columns.append((column_name, "string"))
            seen.add(column_name.lower())
        return columns

    return []


def _build_inferred_table_column_block(column_name: str, data_type: str) -> list[str]:
    """Build a minimal column block for an inferred calculated-table column."""
    source_column = column_name.replace("]", "]]")
    return [
        f"\tcolumn {_format_tmdl_name(column_name)}",
        f"\t\tdataType: {data_type}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsummarizeBy: none",
        f"\t\tsourceColumn: [{source_column}]",
    ]


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
        if stripped == "isHidden" or stripped.startswith(("annotation ", "variation ")):
            return idx
        if ":" in stripped:
            key = stripped.partition(":")[0].strip()
            if key in _TMDL_PROPERTY_NAMES:
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
    lines.extend(f"\t\t\t{line}" for line in expr_lines)
    return lines


def _column_property_start(lines: list[str], start: int, end: int) -> int:
    """Return the first metadata line inside a column block."""
    for idx in range(start + 1, end):
        stripped = lines[idx].strip()
        if not stripped:
            continue
        if _indent_level(lines[idx]) < 2:
            continue
        if stripped == "isHidden" or stripped.startswith(("annotation ", "variation ")):
            return idx
        if ":" in stripped:
            key = stripped.partition(":")[0].strip()
            if key in _TMDL_PROPERTY_NAMES:
                return idx
    return end


def _format_tmdl_name(name: str) -> str:
    """Format a TMDL identifier, quoting names with spaces or punctuation."""
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return name
    escaped = name.replace("'", "''")
    return f"'{escaped}'"


def _format_tmdl_field_ref(table: str, column: str) -> str:
    """Format a Table.Column reference for TMDL relationship blocks."""
    return f"{_format_tmdl_name(table)}.{_format_tmdl_name(column)}"


def _format_tmdl_property_value(property_name: str, property_value: str) -> str:
    """Format TMDL property values, quoting identifier-valued properties when needed."""
    if property_name == "sortByColumn":
        return _format_tmdl_name(property_value)
    return property_value


from .writes_hierarchies import create_hierarchy, delete_hierarchy
from .writes_refs import find_field_dependents, find_field_references, rename_column, rename_measure, rename_table
from .writes_relationships import (
    _get_relationships_path,
    create_relationship,
    delete_relationship,
    normalize_relationship_properties,
    set_relationship_property,
    validate_relationship_properties,
)


def _get_model_tmdl_path(model: SemanticModel) -> Path:
    """Return the semantic-model definition/model.tmdl path."""
    model_path = model.model_path or (model.folder / "definition" / "model.tmdl")
    if not model_path.exists():
        raise ValueError(f'No model.tmdl found in "{model.folder / "definition"}".')
    return model_path


def _remove_auto_date_tables(
    model: SemanticModel,
    *,
    dry_run: bool,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Remove auto-generated local/template date tables and references."""
    auto_names = [
        table.name
        for table in model.tables
        if table.name.startswith(("LocalDateTable_", "DateTableTemplate_"))
    ]
    if not auto_names:
        return False

    changed = False
    model_path = _get_model_tmdl_path(model)
    if _remove_model_table_refs(model_path, auto_names, dry_run=dry_run, edit_session=edit_session):
        changed = True

    relationships_path = _get_relationships_path(model.folder, model)
    if relationships_path.exists() and _remove_relationships_for_tables(
        relationships_path,
        auto_names,
        dry_run=dry_run,
        edit_session=edit_session,
    ):
        changed = True

    for table in model.tables:
        if table.definition_path is None:
            continue
        if table.name in auto_names:
            if not dry_run and table.definition_path.exists():
                table.definition_path.unlink()
            changed = True
            continue
        if _remove_variations_referencing_tables(
            table.definition_path,
            auto_names,
            dry_run=dry_run,
            edit_session=edit_session,
        ):
            changed = True
    return changed


def _remove_model_table_refs(
    path: Path,
    table_names: list[str],
    *,
    dry_run: bool,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Remove ref table lines for the specified tables."""
    lines = _get_tmdl_lines(path, edit_session)
    table_names_set = {name.lower() for name in table_names}
    filtered = [
        line for line in lines
        if not (
            line.strip().startswith("ref table ")
            and _parse_tmdl_name(line.strip()[10:]).lower() in table_names_set
        )
    ]
    if filtered == lines:
        return False
    _commit_tmdl_lines(path, filtered, dry_run=dry_run, session=edit_session)
    return True


def _remove_relationships_for_tables(
    path: Path,
    table_names: list[str],
    *,
    dry_run: bool,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Remove relationship blocks touching the specified tables."""
    lines = _get_tmdl_lines(path, edit_session)
    table_names_set = {name.lower() for name in table_names}
    output: list[str] = []
    idx = 0
    changed = False
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if _indent_level(line) == 0 and stripped.startswith("relationship "):
            end = idx + 1
            from_table = ""
            to_table = ""
            while end < len(lines):
                next_line = lines[end]
                next_stripped = next_line.strip()
                if next_stripped and _indent_level(next_line) == 0:
                    break
                if next_stripped.startswith("fromColumn:"):
                    ref = next_stripped.partition(":")[2].strip()
                    if "." in ref:
                        from_table = ref.split(".", 1)[0].strip("'")
                if next_stripped.startswith("toColumn:"):
                    ref = next_stripped.partition(":")[2].strip()
                    if "." in ref:
                        to_table = ref.split(".", 1)[0].strip("'")
                end += 1
            if from_table.lower() in table_names_set or to_table.lower() in table_names_set:
                changed = True
                idx = end
                continue
            output.extend(lines[idx:end])
            idx = end
            continue
        output.append(line)
        idx += 1

    if not changed:
        return False
    cleaned = _collapse_blank_lines(output)
    _commit_tmdl_lines(path, cleaned, dry_run=dry_run, session=edit_session)
    return True


def _remove_variations_referencing_tables(
    path: Path,
    table_names: list[str],
    *,
    dry_run: bool,
    edit_session: TmdlEditSession | None = None,
) -> bool:
    """Remove variation blocks referencing the specified auto date tables."""
    lines = _get_tmdl_lines(path, edit_session)
    table_names_set = {name.lower() for name in table_names}
    output: list[str] = []
    idx = 0
    changed = False
    while idx < len(lines):
        line = lines[idx]
        stripped = line.strip()
        if _indent_level(line) == 2 and stripped.startswith("variation "):
            end = idx + 1
            block = [line]
            while end < len(lines):
                next_line = lines[end]
                next_stripped = next_line.strip()
                if next_stripped and _indent_level(next_line) <= 2:
                    break
                block.append(next_line)
                end += 1
            lower_block = "\n".join(block).lower()
            if any(name in lower_block for name in table_names_set):
                changed = True
            else:
                output.extend(block)
            idx = end
            continue
        output.append(line)
        idx += 1
    if not changed:
        return False
    cleaned = _collapse_blank_lines(output)
    _commit_tmdl_lines(path, cleaned, dry_run=dry_run, session=edit_session)
    return True


def _collapse_blank_lines(lines: list[str]) -> list[str]:
    """Collapse repeated blank lines and trim leading/trailing blanks."""
    cleaned: list[str] = []
    previous_blank = True
    for line in lines:
        is_blank = not line.strip()
        if is_blank and previous_blank:
            continue
        cleaned.append(line)
        previous_blank = is_blank
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    return cleaned


# ── Calculated table creation ───────────────────────────────────


def create_calculated_table(
    project_root: Path,
    table_name: str,
    expression: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, Path, bool]:
    """Create a new calculated table with a DAX expression.

    Returns (table_name, tmdl_path, created).
    """
    loaded_model = model or SemanticModel.load(project_root)
    validate_table_name(table_name)

    # Check duplicate
    for t in loaded_model.tables:
        if t.name.lower() == table_name.lower():
            raise ValueError(f'Table "{t.name}" already exists.')

    tables_dir = loaded_model.folder / "definition" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    # Build TMDL content
    lineage = str(uuid.uuid4())
    name = _format_tmdl_name(table_name)
    normalized = textwrap.dedent(expression).strip("\n")
    expr_lines = [line.rstrip() for line in normalized.splitlines()]

    tmdl_lines = [
        f"table {name}",
        f"\tlineageTag: {lineage}",
        "",
    ]

    inferred_columns = _infer_calculated_table_columns(normalized)
    for index, (column_name, data_type) in enumerate(inferred_columns):
        tmdl_lines.extend(_build_inferred_table_column_block(column_name, data_type))
        if index != len(inferred_columns) - 1:
            tmdl_lines.append("")

    if inferred_columns:
        tmdl_lines.append("")

    # Partition block
    partition_name = _format_tmdl_name(table_name)
    if len(expr_lines) == 1:
        tmdl_lines.append(f"\tpartition {partition_name} = calculated")
        tmdl_lines.append("\t\tmode: import")
        tmdl_lines.append(f"\t\tsource = {expr_lines[0].strip()}")
    else:
        tmdl_lines.append(f"\tpartition {partition_name} = calculated")
        tmdl_lines.append("\t\tmode: import")
        tmdl_lines.append("\t\tsource =")
        for el in expr_lines:
            tmdl_lines.append(f"\t\t\t{el}")

    tmdl_lines.append("")

    safe_filename = table_name.replace(" ", "_").replace("'", "")
    tmdl_path = tables_dir / f"{safe_filename}.tmdl"

    if not dry_run:
        _write_tmdl_lines(tmdl_path, tmdl_lines)

    return table_name, tmdl_path, True


# ── Relationship validation ─────────────────────────────────────


def validate_relationships(
    project_root: Path,
    *,
    model: SemanticModel | None = None,
) -> list[dict]:
    """Validate relationships and return a list of findings.

    Each finding is a dict with keys: severity, relationship, message.
    Severity: "warning" or "info".
    """
    loaded_model = model or SemanticModel.load(project_root)
    findings: list[dict] = []

    active_adj: dict[str, set[str]] = {}
    active_tables: set[str] = set()

    for rel in loaded_model.relationships:
        label = f"{rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column}"
        normalized_props = normalize_relationship_properties(rel.properties)

        try:
            validate_relationship_properties(normalized_props)
        except ValueError as e:
            findings.append({
                "severity": "error",
                "relationship": label,
                "message": str(e),
            })

        # Check bidirectional cross-filter
        cfb = normalized_props.get("crossFilteringBehavior", "")
        if cfb == "bothDirections":
            findings.append({
                "severity": "warning",
                "relationship": label,
                "message": "Bidirectional cross-filter can cause ambiguous filter paths and performance issues.",
            })

        # Check inactive relationships
        is_active = normalized_props.get("isActive", "")
        if is_active == "false":
            findings.append({
                "severity": "info",
                "relationship": label,
                "message": "Inactive relationship — only usable via USERELATIONSHIP() in DAX.",
            })

        # Check auto-detected relationships
        if rel.id.startswith("AutoDetected_"):
            findings.append({
                "severity": "warning",
                "relationship": label,
                "message": "Auto-detected relationship — review cardinality and direction. Consider replacing with an explicit relationship.",
            })

        # Check joinOnDateBehavior (often auto-created for date tables)
        jodb = normalized_props.get("joinOnDateBehavior", "")
        if jodb == "datePartOnly":
            findings.append({
                "severity": "info",
                "relationship": label,
                "message": "Uses datePartOnly join — time component is ignored in joins.",
            })

        if is_active != "false":
            from_name = rel.from_table
            to_name = rel.to_table
            active_tables.add(from_name)
            active_tables.add(to_name)
            pair = (
                normalized_props.get("fromCardinality", "many"),
                normalized_props.get("toCardinality", "one"),
            )
            if cfb == "bothDirections" or (pair == ("one", "one") and cfb in {"", "automatic"}):
                active_adj.setdefault(from_name, set()).add(to_name)
                active_adj.setdefault(to_name, set()).add(from_name)
            else:
                active_adj.setdefault(to_name, set()).add(from_name)

    def _has_multiple_active_paths(start: str, end: str) -> bool:
        paths = 0

        def _dfs(current: str, seen: set[str]) -> None:
            nonlocal paths
            if paths >= 2:
                return
            if current == end:
                paths += 1
                return
            for neighbor in sorted(active_adj.get(current, set())):
                if neighbor in seen:
                    continue
                _dfs(neighbor, seen | {neighbor})

        _dfs(start, {start})
        return paths >= 2

    active_table_list = sorted(active_tables)
    for index, left in enumerate(active_table_list):
        for right in active_table_list[index + 1 :]:
            if _has_multiple_active_paths(left, right) or _has_multiple_active_paths(right, left):
                findings.append({
                    "severity": "error",
                    "relationship": f"{left} ↔ {right}",
                    "message": "Ambiguous active relationship paths detected between these tables.",
                })

    # Check for tables with shared column names but no relationship
    table_columns: dict[str, set[str]] = {}
    for table in loaded_model.tables:
        # Skip auto-generated date tables
        if table.name.startswith(("LocalDateTable_", "DateTableTemplate_")):
            continue
        col_names = {c.name.lower() for c in table.columns}
        table_columns[table.name] = col_names

    related_pairs: set[tuple[str, str]] = set()
    for rel in loaded_model.relationships:
        ft = rel.from_table
        tt = rel.to_table
        pair = (min(ft, tt), max(ft, tt))
        related_pairs.add(pair)

    table_names = list(table_columns.keys())
    for i, t1 in enumerate(table_names):
        for t2 in table_names[i + 1:]:
            pair = (min(t1, t2), max(t1, t2))
            if pair in related_pairs:
                continue
            shared = table_columns[t1] & table_columns[t2]
            # Filter to likely join columns (ending in ID, Key, Code, etc.)
            join_candidates = {c for c in shared if any(
                c.endswith(suffix) for suffix in ("id", "key", "code", "number")
            )}
            if join_candidates:
                col_list = ", ".join(sorted(join_candidates))
                findings.append({
                    "severity": "info",
                    "relationship": f"{t1} <-> {t2}",
                    "message": f"No relationship but shared columns: {col_list}. Consider adding a relationship.",
                })

    return findings
