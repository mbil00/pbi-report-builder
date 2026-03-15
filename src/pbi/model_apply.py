"""Declarative YAML apply engine for semantic model changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pbi.model import (
    Column,
    Measure,
    SemanticModel,
    create_calculated_column,
    create_measure,
    edit_calculated_column_expression,
    edit_measure_expression,
    set_column_hidden,
    set_field_format,
)


@dataclass
class ModelApplyResult:
    """Summary of what changed during a model apply operation."""

    measures_created: list[str] = field(default_factory=list)
    measures_updated: list[str] = field(default_factory=list)
    columns_created: list[str] = field(default_factory=list)
    columns_updated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.measures_created
            or self.measures_updated
            or self.columns_created
            or self.columns_updated
        )


def apply_model_yaml(
    project_root: Path,
    yaml_content: str,
    *,
    dry_run: bool = False,
) -> ModelApplyResult:
    """Apply declarative model changes from YAML."""
    result = ModelApplyResult()

    try:
        spec = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        result.errors.append(f"Invalid YAML: {e}")
        return result

    if not isinstance(spec, dict):
        result.errors.append("YAML must be a mapping.")
        return result

    try:
        model = SemanticModel.load(project_root)
    except FileNotFoundError as e:
        result.errors.append(str(e))
        return result

    measures_spec = spec.get("measures")
    if measures_spec is not None:
        _apply_measures(project_root, measures_spec, result, dry_run=dry_run, model=model)

    columns_spec = spec.get("columns")
    if columns_spec is not None:
        _apply_columns(project_root, columns_spec, result, dry_run=dry_run, model=model)

    if measures_spec is None and columns_spec is None:
        result.errors.append("YAML must include 'measures' and/or 'columns'.")

    return result


def _apply_measures(
    project_root: Path,
    measures_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
) -> None:
    """Apply declarative measure changes."""
    if not isinstance(measures_spec, dict):
        result.errors.append("'measures' must be a mapping of table name to measure list.")
        return

    for table_name, entries in measures_spec.items():
        if not isinstance(entries, list):
            result.errors.append(f"measures.{table_name}: expected a list of measure specs.")
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                result.errors.append(f"measures.{table_name}: each measure must be a mapping.")
                continue
            name = entry.get("name")
            expression = entry.get("expression")
            fmt = entry.get("format")
            if not isinstance(name, str) or not name.strip():
                result.errors.append(f"measures.{table_name}: measure entry missing non-empty 'name'.")
                continue
            if not isinstance(expression, str) or not expression.strip():
                result.errors.append(f"measures.{table_name}.{name}: missing non-empty 'expression'.")
                continue

            try:
                table = model.find_table(str(table_name))
                existing = _find_measure(table, name)
                changed = False
                if existing is None:
                    create_measure(
                        project_root,
                        table.name,
                        name,
                        expression,
                        format_string=fmt if isinstance(fmt, str) else None,
                        dry_run=dry_run,
                        model=model,
                    )
                    if not dry_run:
                        table.measures.append(
                            Measure(
                                name=name,
                                table=table.name,
                                expression=expression,
                                format_string=fmt if isinstance(fmt, str) else "",
                                definition_path=table.definition_path,
                            )
                        )
                    result.measures_created.append(f"{table.name}.{name}")
                    continue

                table_name_resolved, measure_name, expr_changed = edit_measure_expression(
                    project_root,
                    table.name,
                    existing.name,
                    expression,
                    dry_run=dry_run,
                    model=model,
                )
                changed = changed or expr_changed
                if expr_changed and not dry_run:
                    existing.expression = expression
                if isinstance(fmt, str):
                    _, _, _, fmt_changed = set_field_format(
                        project_root,
                        f"{table_name_resolved}.{measure_name}",
                        fmt,
                        dry_run=dry_run,
                        model=model,
                    )
                    changed = changed or fmt_changed
                    if fmt_changed and not dry_run:
                        existing.format_string = fmt
                if changed:
                    result.measures_updated.append(f"{table_name_resolved}.{measure_name}")
            except (FileNotFoundError, ValueError) as e:
                result.errors.append(f"measures.{table_name}.{name}: {e}")


def _apply_columns(
    project_root: Path,
    columns_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
) -> None:
    """Apply declarative column changes."""
    if not isinstance(columns_spec, dict):
        result.errors.append("'columns' must be a mapping of table name to column specs.")
        return

    for table_name, entries in columns_spec.items():
        if not isinstance(entries, dict):
            result.errors.append(f"columns.{table_name}: expected a mapping of column names to specs.")
            continue
        for column_name, entry in entries.items():
            if not isinstance(entry, dict):
                result.errors.append(f"columns.{table_name}.{column_name}: expected a mapping.")
                continue
            try:
                _apply_column_entry(
                    project_root,
                    str(table_name),
                    str(column_name),
                    entry,
                    result,
                    dry_run=dry_run,
                    model=model,
                )
            except (FileNotFoundError, ValueError) as e:
                result.errors.append(f"columns.{table_name}.{column_name}: {e}")


def _apply_column_entry(
    project_root: Path,
    table_name: str,
    column_name: str,
    entry: dict[str, Any],
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
) -> None:
    """Apply one declarative column spec."""
    table = model.find_table(table_name)
    existing = _find_column(table, column_name)

    requested_type = entry.get("type")
    expression = entry.get("expression")
    data_type = entry.get("dataType")
    fmt = entry.get("format")
    hidden = entry.get("hidden")

    is_calculated_request = (
        requested_type == "calculated"
        or expression is not None
        or data_type is not None
    )

    changed = False
    if is_calculated_request:
        if existing is None:
            if not isinstance(expression, str) or not expression.strip():
                raise ValueError("calculated columns require a non-empty 'expression'.")
            if not isinstance(data_type, str) or not data_type.strip():
                raise ValueError("calculated columns require a non-empty 'dataType'.")
            create_calculated_column(
                project_root,
                table.name,
                column_name,
                expression,
                data_type=data_type,
                format_string=fmt if isinstance(fmt, str) else None,
                dry_run=dry_run,
                model=model,
            )
            if not dry_run:
                existing = Column(
                    name=column_name,
                    table=table.name,
                    data_type=data_type,
                    is_hidden=False,
                    expression=expression,
                    format_string=fmt if isinstance(fmt, str) else "",
                    definition_path=table.definition_path,
                    kind="calculatedColumn",
                )
                table.columns.append(existing)
            result.columns_created.append(f"{table.name}.{column_name}")
            if isinstance(hidden, bool):
                hidden_changed = False
                if dry_run:
                    hidden_changed = hidden
                else:
                    _, _, hidden_changed = set_column_hidden(
                        project_root,
                        f"{table.name}.{column_name}",
                        hidden,
                        dry_run=dry_run,
                        model=model,
                    )
                    if hidden_changed and existing is not None:
                        existing.is_hidden = hidden
                if hidden_changed and f"{table.name}.{column_name}" not in result.columns_updated:
                    result.columns_updated.append(f"{table.name}.{column_name}")
            return

        if existing.kind != "calculatedColumn":
            raise ValueError("cannot convert a source column into a calculated column.")
        if isinstance(expression, str) and expression.strip():
            _, _, expr_changed = edit_calculated_column_expression(
                project_root,
                table.name,
                existing.name,
                expression,
                dry_run=dry_run,
                model=model,
            )
            changed = changed or expr_changed
            if expr_changed and not dry_run:
                existing.expression = expression
    else:
        if existing is None:
            raise ValueError("source columns are not created by model apply.")

    if isinstance(fmt, str):
        _, _, _, fmt_changed = set_field_format(
            project_root,
            f"{table.name}.{column_name}",
            fmt,
            dry_run=dry_run,
            model=model,
        )
        changed = changed or fmt_changed
        if fmt_changed and not dry_run and existing is not None:
            existing.format_string = fmt
    if isinstance(hidden, bool):
        _, _, hidden_changed = set_column_hidden(
            project_root,
            f"{table.name}.{column_name}",
            hidden,
            dry_run=dry_run,
            model=model,
        )
        changed = changed or hidden_changed
        if hidden_changed and not dry_run and existing is not None:
            existing.is_hidden = hidden
    if changed:
        result.columns_updated.append(f"{table.name}.{column_name}")


def _find_measure(table, name: str):
    """Return a measure by name or None."""
    for measure in table.measures:
        if measure.name.lower() == name.lower():
            return measure
    return None


def _find_column(table, name: str):
    """Return a column by name or None."""
    for column in table.columns:
        if column.name.lower() == name.lower():
            return column
    return None
