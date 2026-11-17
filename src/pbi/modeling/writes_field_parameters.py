"""Field parameter tables for Power BI semantic models.

A field parameter is a calculated table whose partition is a DAX table
constructor of ``("Label", NAMEOF('Table'[Field]), ordinal)`` rows. New tables
are written in the shape Power BI Desktop saves (``Metric Selector`` in the
``report-04-desktop-shapes`` fixture):

- the display column ``'<name>'`` (``sourceColumn: [Value1]``), sorted by the
  order column and grouped by the fields column (``relatedColumnDetails``);
- the hidden fields column ``'<name> Fields'`` (``[Value2]``), which carries
  ``extendedProperty ParameterMetadata`` with ``"kind": 2``;
- the hidden order column ``'<name> Order'`` (``[Value3]``);
- the ``calculated`` partition and the table's ``annotation PBI_Id``.

Tables written by older ``pbi`` versions (an ``isParameterType`` flag and
``[Name]/[Value]/[Ordinal]`` columns) are still read as field parameters.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from .schema import SemanticModel, SemanticTable
from .writes import (
    TmdlEditSession,
    _add_model_table_ref,
    _format_tmdl_name,
    _new_table_tmdl_path,
    _write_tmdl_lines,
    validate_table_name,
)


@dataclass(frozen=True)
class FieldParameterField:
    """One row of a field parameter: the label shown and the field it selects."""

    label: str
    table: str
    field: str

    @property
    def ref(self) -> str:
        return f"{self.table}.{self.field}"


# ("Label", NAMEOF('Table'[Field]), 0) — Desktop always quotes the table name;
# an unquoted name is accepted too. Doubled quotes / brackets are escapes.
_ROW_PATTERN = re.compile(
    r"""\(\s*
        "(?P<label>(?:[^"]|"")*)"\s*,\s*
        NAMEOF\s*\(\s*
            (?:'(?P<qtable>(?:[^']|'')+)'|(?P<table>[A-Za-z_][A-Za-z0-9_]*))
            \s*\[(?P<field>(?:[^\]]|\]\])+)\]\s*
        \)\s*,\s*
        (?P<ordinal>-?\d+)\s*
    \)""",
    re.VERBOSE,
)


def parse_field_parameter_source(source: str) -> list[FieldParameterField] | None:
    """Read the rows of a field parameter's DAX table constructor.

    Rows come back in ordinal order. Returns None unless the whole expression
    is a ``{ row, row, ... }`` constructor of three-value rows, so a table
    this can't read in full is never mistaken for a field parameter.
    """
    text = source.strip()
    if not (text.startswith("{") and text.endswith("}")):
        return None
    body = text[1:-1]
    rows: list[tuple[int, FieldParameterField]] = []
    pos = 0
    while True:
        match = _ROW_PATTERN.match(body, _skip_space(body, pos))
        if match is None:
            break
        table = match["qtable"].replace("''", "'") if match["qtable"] is not None else match["table"]
        rows.append((
            int(match["ordinal"]),
            FieldParameterField(
                label=match["label"].replace('""', '"'),
                table=table,
                field=match["field"].replace("]]", "]"),
            ),
        ))
        pos = _skip_space(body, match.end())
        if pos < len(body) and body[pos] == ",":
            pos += 1
            continue
        break
    if not rows or body[_skip_space(body, pos):]:
        return None
    return [row for _, row in sorted(rows, key=lambda item: item[0])]


def _skip_space(text: str, pos: int) -> int:
    while pos < len(text) and text[pos].isspace():
        pos += 1
    return pos


def field_parameter_fields(table: SemanticTable) -> list[FieldParameterField] | None:
    """The rows of a field parameter table, or None when it isn't one this can read."""
    if not table.is_field_parameter or len(table.partitions) != 1:
        return None
    partition = table.partitions[0]
    if partition.source_type != "calculated":
        return None
    return parse_field_parameter_source(partition.source_expression)


def field_parameter_source(fields: list[FieldParameterField]) -> str:
    """Render the partition DAX the way Desktop writes it."""
    rows = []
    for ordinal, entry in enumerate(fields):
        label = entry.label.replace('"', '""')
        table = entry.table.replace("'", "''")
        field = entry.field.replace("]", "]]")
        rows.append(f"""    ("{label}", NAMEOF('{table}'[{field}]), {ordinal})""")
    return "{\n" + ",\n".join(rows) + "\n}"


def resolve_field_parameter_fields(
    model: SemanticModel,
    fields: list[str],
    labels: list[str | None] | None,
) -> list[FieldParameterField]:
    """Resolve ``Table.Field`` refs to model columns/measures, pairing each with its label."""
    if not fields:
        raise ValueError("At least one field is required.")
    if labels is not None and len(labels) != len(fields):
        raise ValueError(
            f"Labels count ({len(labels)}) must match fields count ({len(fields)})."
        )

    resolved: list[FieldParameterField] = []
    for i, field_ref in enumerate(fields):
        sem_table, match = _resolve_field_ref(model, field_ref)
        label = labels[i] if labels and labels[i] is not None else match
        if "\n" in label or "\r" in label:
            raise ValueError(f"Label for {field_ref} must be a single line: {label!r}")
        resolved.append(FieldParameterField(label=label, table=sem_table.name, field=match))
    return resolved


def _field_name(table: SemanticTable, name: str) -> str | None:
    """The column or measure of ``table`` called ``name`` (case-insensitive)."""
    names = [col.name for col in table.columns] + [meas.name for meas in table.measures]
    return next((item for item in names if item.lower() == name.lower()), None)


def _resolve_field_ref(model: SemanticModel, field_ref: str) -> tuple[SemanticTable, str]:
    """Split ``Table.Field`` where a table name may itself contain dots.

    A split whose table name matches exactly and whose rest names one of its
    fields wins (``Sales.Data.Revenue`` -> ``'Sales.Data'[Revenue]``). Without
    one, the ref splits at the first dot and the table lookup may be partial.
    """
    if "." not in field_ref:
        raise ValueError(f"Field must be Table.Field format: {field_ref}")
    exact = []
    for table in model.tables:
        prefix = table.name + "."
        if len(field_ref) > len(prefix) and field_ref[: len(prefix)].lower() == prefix.lower():
            name = _field_name(table, field_ref[len(prefix):])
            if name is not None:
                exact.append((table, name))
    if len(exact) > 1:
        options = ", ".join(f"'{table.name}'[{name}]" for table, name in exact)
        raise ValueError(f'Field "{field_ref}" is ambiguous: {options}')
    if exact:
        return exact[0]

    table_name, _, field_name = field_ref.partition(".")
    try:
        sem_table = model.find_table(table_name)
    except ValueError as e:
        raise ValueError(f"Field parameter: {e}") from e
    name = _field_name(sem_table, field_name)
    if name is None:
        raise ValueError(f'Field "{field_ref}" not found in model.')
    return sem_table, name


def exportable_field_parameter_fields(
    model: SemanticModel, table: SemanticTable
) -> list[FieldParameterField] | None:
    """The rows to export under ``fieldParameters:``, or None to export the table as is.

    Rows are listed only when applying them back is a no-op: every label is
    one line and every ``Table.Field`` ref resolves to the field it came from.
    Otherwise (a removed field, other casing, a multi-line label) the table
    round-trips through ``columns:`` / ``partitions:`` like any other.
    """
    rows = field_parameter_fields(table)
    if not rows:
        return None
    try:
        resolved = resolve_field_parameter_fields(
            model, [row.ref for row in rows], [row.label for row in rows]
        )
    except ValueError:
        return None
    return rows if resolved == rows else None


def create_field_parameter(
    project_root: Path,
    parameter_name: str,
    fields: list[str],
    labels: list[str] | None,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, Path, bool]:
    """Create a field parameter table in Desktop's TMDL shape.

    Returns (table_name, tmdl_path, created).
    """
    validate_table_name(parameter_name)

    loaded_model = model or SemanticModel.load(project_root)

    for t in loaded_model.tables:
        if t.name.lower() == parameter_name.lower():
            raise ValueError(f'Table "{t.name}" already exists.')

    resolved = resolve_field_parameter_fields(loaded_model, fields, labels)
    lines = _field_parameter_lines(parameter_name, resolved)

    tmdl_path = _new_table_tmdl_path(loaded_model, parameter_name, edit_session)

    if not dry_run:
        tmdl_path.parent.mkdir(parents=True, exist_ok=True)
        if edit_session is not None:
            edit_session.replace_file(tmdl_path, lines)
        else:
            _write_tmdl_lines(tmdl_path, lines)
    _add_model_table_ref(loaded_model, parameter_name, dry_run=dry_run, edit_session=edit_session)

    return parameter_name, tmdl_path, True


def set_field_parameter_fields(
    project_root: Path,
    parameter_name: str,
    fields: list[str],
    labels: list[str | None] | None,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Replace the rows of an existing field parameter table.

    Only the partition's DAX changes; the columns stay as written. Returns
    (table_name, changed): unchanged when the rows (labels, fields and order)
    already match.
    """
    from .writes_partitions import set_partition

    loaded_model = model or SemanticModel.load(project_root)
    table = loaded_model.find_table(parameter_name)
    if not table.is_field_parameter:
        raise ValueError(f'Table "{table.name}" already exists and is not a field parameter.')

    resolved = resolve_field_parameter_fields(loaded_model, fields, labels)
    if field_parameter_fields(table) == resolved:
        return table.name, False
    if len(table.partitions) != 1:
        raise ValueError(
            f'Field parameter "{table.name}" has {len(table.partitions)} partitions; expected one.'
        )

    _, _, changed = set_partition(
        project_root,
        table.name,
        table.partitions[0].name,
        source_expression=field_parameter_source(resolved),
        source_type="calculated",
        dry_run=dry_run,
        model=loaded_model,
        edit_session=edit_session,
    )
    return table.name, changed


def _field_parameter_lines(parameter_name: str, fields: list[FieldParameterField]) -> list[str]:
    """The TMDL of a new field parameter table, as Desktop writes ``Metric Selector``."""
    table_name = _format_tmdl_name(parameter_name)
    fields_column = _format_tmdl_name(f"{parameter_name} Fields")
    order_column = _format_tmdl_name(f"{parameter_name} Order")
    lines = [
        f"table {table_name}",
        f"\tlineageTag: {uuid.uuid4()}",
        "",
        f"\tcolumn {table_name}",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value1]",
        f"\t\tsortByColumn: {order_column}",
        "",
        "\t\trelatedColumnDetails",
        f"\t\t\tgroupByColumn: {fields_column}",
        "",
        "\t\tannotation SummarizationSetBy = Automatic",
        "",
        f"\tcolumn {fields_column}",
        "\t\tisHidden",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value2]",
        f"\t\tsortByColumn: {order_column}",
        "",
        "\t\textendedProperty ParameterMetadata =",
        "\t\t\t\t{",
        '\t\t\t\t  "version": 3,',
        '\t\t\t\t  "kind": 2',
        "\t\t\t\t}",
        "",
        "\t\tannotation SummarizationSetBy = Automatic",
        "",
        f"\tcolumn {order_column}",
        "\t\tisHidden",
        "\t\tformatString: 0",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsummarizeBy: sum",
        "\t\tsourceColumn: [Value3]",
        "",
        "\t\tannotation SummarizationSetBy = Automatic",
        "",
        f"\tpartition {table_name} = calculated",
        "\t\tmode: import",
        "\t\tsource =",
        *(f"\t\t\t\t{line}" for line in field_parameter_source(fields).splitlines()),
        "",
        f"\tannotation PBI_Id = {uuid.uuid4().hex}",
        "",
    ]
    return lines
