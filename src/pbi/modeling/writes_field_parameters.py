"""Field parameter table creation for Power BI semantic models."""

from __future__ import annotations

import uuid
from pathlib import Path

from .schema import SemanticModel
from .writes import _format_tmdl_name, _write_tmdl_lines, validate_table_name


def _format_dax_field_ref(table: str, field: str) -> str:
    """Format a DAX NAMEOF reference: NAMEOF('Table'[Field])."""
    escaped_table = table.replace("'", "''")
    return f"NAMEOF('{escaped_table}'[{field}])"


def create_field_parameter(
    project_root: Path,
    parameter_name: str,
    fields: list[str],
    labels: list[str] | None,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
) -> tuple[str, Path, bool]:
    """Create a field parameter table with the correct TMDL structure.

    Returns (table_name, tmdl_path, created).
    """
    validate_table_name(parameter_name)

    if not fields:
        raise ValueError("At least one field is required.")

    if labels is not None and len(labels) != len(fields):
        raise ValueError(
            f"Labels count ({len(labels)}) must match fields count ({len(fields)})."
        )

    loaded_model = model or SemanticModel.load(project_root)

    # Check duplicate
    for t in loaded_model.tables:
        if t.name.lower() == parameter_name.lower():
            raise ValueError(f'Table "{t.name}" already exists.')

    # Resolve fields and auto-generate labels
    resolved: list[tuple[str, str, str]] = []  # (label, table, field)
    for i, field_ref in enumerate(fields):
        dot = field_ref.find(".")
        if dot == -1:
            raise ValueError(f"Field must be Table.Field format: {field_ref}")
        table_name = field_ref[:dot]
        field_name = field_ref[dot + 1:]

        try:
            sem_table = loaded_model.find_table(table_name)
        except ValueError as e:
            raise ValueError(f"Field parameter: {e}") from e

        field_found = False
        for col in sem_table.columns:
            if col.name.lower() == field_name.lower():
                field_found = True
                field_name = col.name
                table_name = sem_table.name
                break
        if not field_found:
            for meas in sem_table.measures:
                if meas.name.lower() == field_name.lower():
                    field_found = True
                    field_name = meas.name
                    table_name = sem_table.name
                    break
        if not field_found:
            raise ValueError(f'Field "{field_ref}" not found in model.')

        label = labels[i] if labels else field_name
        resolved.append((label, table_name, field_name))

    # Build TMDL
    tmdl_name = _format_tmdl_name(parameter_name)
    lines: list[str] = [
        f"table {tmdl_name}",
        "\tisParameterType",
        f"\tlineageTag: {uuid.uuid4()}",
        "",
    ]

    # Name column (display label, sorted by order)
    order_col_name = _format_tmdl_name(f"{parameter_name} Order")
    lines.extend([
        f"\tcolumn {tmdl_name}",
        "\t\tdataType: string",
        "\t\tisHidden",
        "\t\tisNameInferred",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsourceColumn: [Name]",
        f"\t\tsortByColumn: {order_col_name}",
        "",
        "\t\tannotation SummarizationType = None",
        "",
    ])

    # Fields column (NAMEOF values)
    fields_col_name = _format_tmdl_name(f"{parameter_name} Fields")
    lines.extend([
        f"\tcolumn {fields_col_name}",
        "\t\tdataType: string",
        "\t\tisHidden",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsourceColumn: [Value]",
        "",
        "\t\tannotation SummarizationType = None",
        "",
        '\t\tannotation PBI_ChangedProperties = ["IsHidden"]',
        "",
    ])

    # Order column (ordinal)
    lines.extend([
        f"\tcolumn {order_col_name}",
        "\t\tdataType: int64",
        "\t\tisHidden",
        f"\t\tlineageTag: {uuid.uuid4()}",
        "\t\tsourceColumn: [Ordinal]",
        "",
        "\t\tannotation SummarizationType = None",
        "",
        '\t\tannotation PBI_ChangedProperties = ["IsHidden"]',
        "",
    ])

    # DAX table constructor partition
    dax_rows = []
    for i, (label, table, field) in enumerate(resolved):
        escaped_label = label.replace('"', '""')
        nameof = _format_dax_field_ref(table, field)
        dax_rows.append(f'("{escaped_label}", {nameof}, {i})')

    partition_name = _format_tmdl_name(parameter_name)
    lines.append(f"\tpartition {partition_name} = calculated")
    lines.append("\t\tmode: import")
    lines.append("\t\tsource =")
    lines.append("\t\t\t{")
    for i, row in enumerate(dax_rows):
        suffix = "," if i < len(dax_rows) - 1 else ""
        lines.append(f"\t\t\t{row}{suffix}")
    lines.append("\t\t\t}")
    lines.append("")

    # Write file
    tables_dir = loaded_model.folder / "definition" / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    safe_filename = parameter_name.replace(" ", "_").replace("'", "")
    tmdl_path = tables_dir / f"{safe_filename}.tmdl"

    if not dry_run:
        _write_tmdl_lines(tmdl_path, lines)

    return parameter_name, tmdl_path, True
