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
    "description", "displayFolder", "sortByColumn",
    "summarizeBy", "dataCategory", "formatString",
})


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

    replacement = f"\t\t{property_name}: {property_value}"
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


# ── Relationship CRUD ──────────────────────────────────────────────


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
    """Find a relationship block by from/to columns. Returns (start, end) or None."""
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("relationship "):
            block_start = i
            i += 1
            props: dict[str, str] = {}
            while i < len(lines):
                s = lines[i].strip()
                if not s:
                    i += 1
                    continue
                if not s.startswith("relationship ") and ":" in s:
                    key, _, val = s.partition(":")
                    props[key.strip()] = val.strip()
                    i += 1
                else:
                    break
            block_end = i
            fc = props.get("fromColumn", "")
            tc = props.get("toColumn", "")
            fc_dot = fc.find(".")
            tc_dot = tc.find(".")
            if fc_dot > 0 and tc_dot > 0:
                ft = _parse_tmdl_name(fc[:fc_dot])
                fcn = _parse_tmdl_name(fc[fc_dot + 1:])
                tt = _parse_tmdl_name(tc[:tc_dot])
                tcn = _parse_tmdl_name(tc[tc_dot + 1:])
                if (ft.lower() == from_table.lower() and fcn.lower() == from_column.lower()
                        and tt.lower() == to_table.lower() and tcn.lower() == to_column.lower()):
                    return block_start, block_end
        else:
            i += 1
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
        for key, val in properties.items():
            if key not in ("fromColumn", "toColumn"):
                if key == "crossFilteringBehavior":
                    val = _TMDL_CFB_MAP.get(val.lower(), val)
                lines.append(f"\t{key}: {val}")
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
    from_table, from_col = _parse_field_ref(from_field)
    to_table, to_col = _parse_field_ref(to_field)

    # Validate fields exist
    ft = loaded_model.find_table(from_table)
    ft.find_column(from_col)
    tt = loaded_model.find_table(to_table)
    tt.find_column(to_col)

    # Check for duplicates
    for rel in loaded_model.relationships:
        if (rel.from_table.lower() == ft.name.lower()
                and rel.from_column.lower() == from_col.lower()
                and rel.to_table.lower() == tt.name.lower()
                and rel.to_column.lower() == to_col.lower()):
            raise ValueError(
                f'Relationship from "{ft.name}.{from_col}" to "{tt.name}.{to_col}" already exists.'
            )

    rel_id = str(uuid.uuid4())
    block = _build_relationship_block(
        rel_id, ft.name, from_col, tt.name, to_col,
        properties=properties,
    )

    rel_path = _get_relationships_path(project_root, loaded_model)
    if rel_path.exists():
        lines = _get_tmdl_lines(rel_path, edit_session)
        # Remove trailing empty lines then append
        while lines and not lines[-1].strip():
            lines.pop()
        lines.append("")
        lines.extend(block)
        lines.append("")
    else:
        lines = block + [""]

    _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)

    from_ref = f"{ft.name}.{from_col}"
    to_ref = f"{tt.name}.{to_col}"
    return rel_id, from_ref, to_ref


def delete_relationship(
    project_root: Path,
    from_field: str,
    to_field: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str]:
    """Delete a relationship by from/to field refs. Returns (from_ref, to_ref)."""
    from .schema import _parse_field_ref

    loaded_model = model or SemanticModel.load(project_root)
    from_table, from_col = _parse_field_ref(from_field)
    to_table, to_col = _parse_field_ref(to_field)

    ft = loaded_model.find_table(from_table)
    tt = loaded_model.find_table(to_table)

    rel_path = _get_relationships_path(project_root, loaded_model)
    if not rel_path.exists():
        raise ValueError("No relationships.tmdl file found.")

    lines = _get_tmdl_lines(rel_path, edit_session)
    result = _find_relationship_block(lines, ft.name, from_col, tt.name, to_col)
    if result is None:
        raise ValueError(
            f'Relationship from "{ft.name}.{from_col}" to "{tt.name}.{to_col}" not found.'
        )

    start, end = result
    del lines[start:end]
    # Clean up extra blank lines
    while start < len(lines) and not lines[start].strip():
        del lines[start]
    if start > 0 and start < len(lines) and lines[start - 1].strip():
        lines.insert(start, "")

    _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)

    return f"{ft.name}.{from_col}", f"{tt.name}.{to_col}"


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
    """Set a property on an existing relationship. Returns (from_ref, to_ref, changed)."""
    from .schema import _parse_field_ref

    loaded_model = model or SemanticModel.load(project_root)
    from_table, from_col = _parse_field_ref(from_field)
    to_table, to_col = _parse_field_ref(to_field)

    ft = loaded_model.find_table(from_table)
    tt = loaded_model.find_table(to_table)

    rel_path = _get_relationships_path(project_root, loaded_model)
    if not rel_path.exists():
        raise ValueError("No relationships.tmdl file found.")

    lines = _get_tmdl_lines(rel_path, edit_session)
    result = _find_relationship_block(lines, ft.name, from_col, tt.name, to_col)
    if result is None:
        raise ValueError(
            f'Relationship from "{ft.name}.{from_col}" to "{tt.name}.{to_col}" not found.'
        )

    start, end = result
    replacement = f"\t{prop_name}: {prop_value}"
    # Try to update existing property
    for idx in range(start + 1, end):
        if lines[idx].strip().startswith(f"{prop_name}:"):
            if lines[idx] == replacement:
                return f"{ft.name}.{from_col}", f"{tt.name}.{to_col}", False
            lines[idx] = replacement
            _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)
            return f"{ft.name}.{from_col}", f"{tt.name}.{to_col}", True

    # Insert before fromColumn line
    for idx in range(start + 1, end):
        if lines[idx].strip().startswith("fromColumn:"):
            lines.insert(idx, replacement)
            _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)
            return f"{ft.name}.{from_col}", f"{tt.name}.{to_col}", True

    # Fallback: insert after relationship declaration
    lines.insert(start + 1, replacement)
    _commit_tmdl_lines(rel_path, lines, dry_run=dry_run, session=edit_session)
    return f"{ft.name}.{from_col}", f"{tt.name}.{to_col}", True


# ── Hierarchy CRUD ──────────────────────────────────────────────────


def _find_hierarchy_block(
    lines: list[str],
    hierarchy_name: str,
) -> tuple[int, int] | None:
    """Find a hierarchy block by name. Returns (start, end) or None."""
    for idx, line in enumerate(lines):
        stripped = line.strip()
        if _indent_level(line) == 1 and stripped.startswith("hierarchy "):
            name = _parse_tmdl_name(stripped[10:])
            if name.lower() == hierarchy_name.lower():
                end = idx + 1
                while end < len(lines):
                    next_stripped = lines[end].strip()
                    if next_stripped and _indent_level(lines[end]) <= 1 and _starts_new_table_block(next_stripped):
                        break
                    end += 1
                return idx, end
    return None


def _hierarchy_insert_index(lines: list[str]) -> int:
    """Choose where a new hierarchy block should be inserted — after measures."""
    last_measure_end: int | None = None
    last_hierarchy_end: int | None = None

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
        if stripped.startswith("hierarchy "):
            result = _find_hierarchy_block(lines, _parse_tmdl_name(stripped[10:]))
            if result:
                last_hierarchy_end = result[1]
                idx = result[1]
                continue
        idx += 1

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

    for col_name in level_columns:
        lines.append("")
        level_name = _format_tmdl_name(col_name)
        lines.append(f"\t\tlevel {level_name}")
        lines.append(f"\t\t\tlineageTag: {uuid.uuid4()}")
        lines.append(f"\t\t\tcolumn: {col_name}")

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
    """Create a new hierarchy in a table. Returns (table_name, hierarchy_name, created)."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    # Check for duplicate
    for h in table.hierarchies:
        if h.name.lower() == hierarchy_name.lower():
            raise ValueError(f'Hierarchy "{hierarchy_name}" already exists in table "{table.name}".')

    # Validate columns exist
    for col in level_columns:
        table.find_column(col)

    if not level_columns:
        raise ValueError("A hierarchy requires at least one level column.")

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    insert_at = _hierarchy_insert_index(lines)
    block = _build_hierarchy_block(hierarchy_name, level_columns)
    lines[insert_at:insert_at] = _prepare_inserted_block(lines, insert_at, block)

    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)

    return table.name, hierarchy_name, True  # noqa: delete_hierarchy end


# ── Dependency analysis ─────────────────────────────────────────


def find_field_dependents(
    project_root: Path,
    field_ref: str,
    *,
    model: SemanticModel | None = None,
) -> list[tuple[str, str, str]]:
    """Find all measures/columns that reference a field.

    Returns list of (table_name, member_name, member_type) for each dependent.
    """
    from .dax_refs import find_dependents

    loaded_model = model or SemanticModel.load(project_root)
    table_name, field_name, field_type = loaded_model.resolve_field(field_ref)
    is_measure = field_type == "measure"

    dependents: list[tuple[str, str, str]] = []
    for table in loaded_model.tables:
        for measure in table.measures:
            if table.name == table_name and measure.name == field_name:
                continue  # skip self
            if find_dependents(measure.expression, table_name, field_name, is_measure=is_measure):
                dependents.append((table.name, measure.name, "measure"))
        for column in table.columns:
            if column.kind != "calculatedColumn" or not column.expression:
                continue
            if table.name == table_name and column.name == field_name:
                continue
            if find_dependents(column.expression, table_name, field_name, is_measure=is_measure):
                dependents.append((table.name, column.name, "calculatedColumn"))

    return dependents


def find_field_references(
    project_root: Path,
    field_ref: str,
    *,
    model: SemanticModel | None = None,
) -> list[tuple[str, str, str]]:
    """Find all fields that the target references (forward dependencies).

    Returns list of (table_name, field_name, field_type).
    """
    from .dax_refs import extract_refs

    loaded_model = model or SemanticModel.load(project_root)
    table_name, field_name, field_type = loaded_model.resolve_field(field_ref)

    table = loaded_model.find_table(table_name)
    if field_type == "measure":
        member = table.find_measure(field_name)
        expression = member.expression
    else:
        member = table.find_column(field_name)
        expression = member.expression
        if not expression:
            return []

    refs = extract_refs(expression)
    resolved: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    for ref in refs:
        if ref.qualified:
            key = f"{ref.table}.{ref.name}".lower()
            if key in seen:
                continue
            seen.add(key)
            try:
                rt, rn, rtype = loaded_model.resolve_field(f"{ref.table}.{ref.name}")
                resolved.append((rt, rn, rtype))
            except ValueError:
                pass
        else:
            # Unqualified — search same table first, then all tables
            key = f"*.{ref.name}".lower()
            if key in seen:
                continue
            seen.add(key)
            found = False
            for m in table.measures:
                if m.name.lower() == ref.name.lower():
                    resolved.append((table.name, m.name, "measure"))
                    found = True
                    break
            if not found:
                for t in loaded_model.tables:
                    for m in t.measures:
                        if m.name.lower() == ref.name.lower():
                            resolved.append((t.name, m.name, "measure"))
                            found = True
                            break
                    if found:
                        break

    return resolved


# ── Rename ──────────────────────────────────────────────────────


def rename_measure(
    project_root: Path,
    table_name: str,
    old_name: str,
    new_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, str, list[str]]:
    """Rename a measure and update all DAX references.

    Returns (table_name, old_name, new_name, list of updated refs).
    """
    from .dax_refs import replace_refs as dax_replace

    loaded_model = model or SemanticModel.load(project_root)
    owns_edit_session = edit_session is None
    if edit_session is None:
        edit_session = TmdlEditSession()
    table = loaded_model.find_table(table_name)
    measure = table.find_measure(old_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    # Check new name doesn't already exist
    for m in table.measures:
        if m.name.lower() == new_name.lower():
            raise ValueError(f'Measure "{new_name}" already exists in table "{table.name}".')

    updated_refs: list[str] = []

    # 1. Rename the declaration in the source table
    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, _end = _find_member_block(lines, member_kind="measure", member_name=measure.name)
    old_formatted = _format_tmdl_name(old_name)
    new_formatted = _format_tmdl_name(new_name)
    decl_line = lines[start]
    lines[start] = decl_line.replace(f"measure {old_formatted}", f"measure {new_formatted}", 1)
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)

    # 2. Update all DAX references across the model
    for t in loaded_model.tables:
        if t.definition_path is None:
            continue
        t_lines = _get_tmdl_lines(t.definition_path, edit_session)
        changed = False

        for idx, line in enumerate(t_lines):
            if old_name.lower() not in line.lower():
                continue
            new_line = dax_replace(
                line,
                old_table=None,
                old_name=old_name,
                new_name=new_name,
            )
            # Also try qualified Table[Measure] references
            new_line = dax_replace(
                new_line,
                old_table=table.name,
                old_name=old_name,
                new_name=new_name,
            )
            if new_line != line:
                t_lines[idx] = new_line
                changed = True

        if changed:
            _commit_tmdl_lines(t.definition_path, t_lines, dry_run=dry_run, session=edit_session)
            # Find which members were affected
            for m in t.measures:
                from .dax_refs import find_dependents
                if find_dependents(m.expression, table.name, old_name, is_measure=True):
                    updated_refs.append(f"{t.name}.{m.name}")
            for c in t.columns:
                if c.expression and old_name.lower() in c.expression.lower():
                    updated_refs.append(f"{t.name}.{c.name}")

    if owns_edit_session and not dry_run:
        edit_session.flush()

    return table.name, old_name, new_name, updated_refs


def rename_column(
    project_root: Path,
    table_name: str,
    old_name: str,
    new_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, str, list[str]]:
    """Rename a calculated column and update all DAX + relationship references.

    Returns (table_name, old_name, new_name, list of updated refs).
    """
    from .dax_refs import replace_refs as dax_replace

    loaded_model = model or SemanticModel.load(project_root)
    owns_edit_session = edit_session is None
    if edit_session is None:
        edit_session = TmdlEditSession()
    table = loaded_model.find_table(table_name)
    column = table.find_column(old_name)
    if column.kind != "calculatedColumn":
        raise ValueError(
            f'Column "{table.name}.{column.name}" is a source column and cannot be renamed. '
            f'Source column names are controlled by the data source.'
        )
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    # Check new name doesn't already exist
    for c in table.columns:
        if c.name.lower() == new_name.lower():
            raise ValueError(f'Column "{new_name}" already exists in table "{table.name}".')

    updated_refs: list[str] = []

    # 1. Rename the declaration
    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, _end = _find_member_block(lines, member_kind="column", member_name=column.name)
    old_formatted = _format_tmdl_name(old_name)
    new_formatted = _format_tmdl_name(new_name)
    decl_line = lines[start]
    # Handle both `column Name` and `calculatedColumn Name`
    for keyword in ("calculatedColumn", "column"):
        old_decl = f"{keyword} {old_formatted}"
        if old_decl in decl_line:
            lines[start] = decl_line.replace(old_decl, f"{keyword} {new_formatted}", 1)
            break
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)

    # 2. Update sortByColumn references in the same table
    for c in table.columns:
        if c.sort_by_column and c.sort_by_column.lower() == old_name.lower():
            _update_member_property(
                table.definition_path,
                member_kind="column",
                member_name=c.name,
                property_name="sortByColumn",
                property_value=new_name,
                dry_run=dry_run,
                edit_session=edit_session,
            )
            updated_refs.append(f"{table.name}.{c.name} (sortByColumn)")

    # 3. Update DAX references across all tables
    for t in loaded_model.tables:
        if t.definition_path is None:
            continue
        t_lines = _get_tmdl_lines(t.definition_path, edit_session)
        changed = False

        for idx, line in enumerate(t_lines):
            if old_name.lower() not in line.lower():
                continue
            new_line = dax_replace(
                line,
                old_table=table.name,
                old_name=old_name,
                new_name=new_name,
                qualified_only=True,
            )
            if new_line != line:
                t_lines[idx] = new_line
                changed = True

        if changed:
            _commit_tmdl_lines(t.definition_path, t_lines, dry_run=dry_run, session=edit_session)
            for m in t.measures:
                if old_name.lower() in m.expression.lower():
                    updated_refs.append(f"{t.name}.{m.name}")
            for c in t.columns:
                if c.expression and old_name.lower() in c.expression.lower():
                    updated_refs.append(f"{t.name}.{c.name}")

    # 4. Update relationship references
    rel_path = _get_relationships_path(project_root, loaded_model)
    if rel_path.exists():
        rel_lines = _get_tmdl_lines(rel_path, edit_session)
        changed = False
        old_ref = _format_tmdl_field_ref(table.name, old_name)
        new_ref = _format_tmdl_field_ref(table.name, new_name)
        for idx, line in enumerate(rel_lines):
            stripped = line.strip()
            if stripped.startswith(("fromColumn:", "toColumn:")) and old_ref in line:
                rel_lines[idx] = line.replace(old_ref, new_ref)
                changed = True
                updated_refs.append(f"relationship ({stripped.split(':')[0].strip()})")
        if changed:
            _commit_tmdl_lines(rel_path, rel_lines, dry_run=dry_run, session=edit_session)

    if owns_edit_session and not dry_run:
        edit_session.flush()

    return table.name, old_name, new_name, updated_refs


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

    for rel in loaded_model.relationships:
        label = f"{rel.from_table}.{rel.from_column} -> {rel.to_table}.{rel.to_column}"

        # Check bidirectional cross-filter
        cfb = rel.properties.get("crossFilteringBehavior", "")
        if cfb == "bothDirections":
            findings.append({
                "severity": "warning",
                "relationship": label,
                "message": "Bidirectional cross-filter can cause ambiguous filter paths and performance issues.",
            })

        # Check inactive relationships
        is_active = rel.properties.get("isActive", "")
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
        jodb = rel.properties.get("joinOnDateBehavior", "")
        if jodb == "datePartOnly":
            findings.append({
                "severity": "info",
                "relationship": label,
                "message": "Uses datePartOnly join — time component is ignored in joins.",
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

def delete_hierarchy(
    project_root: Path,
    table_name: str,
    hierarchy_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Delete a hierarchy from a table. Returns (table_name, hierarchy_name, deleted)."""
    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(table_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    # Verify it exists
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
