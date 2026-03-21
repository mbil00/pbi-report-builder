"""Declarative YAML apply engine for semantic model changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pbi.model import (
    Column,
    Measure,
    PerspectiveMemberSpec,
    RoleMember,
    RoleSpec,
    RoleTablePermission,
    SemanticModel,
    TmdlEditSession,
    create_calculated_column,
    create_hierarchy,
    create_measure,
    create_partition,
    create_perspective,
    create_role,
    create_relationship,
    delete_hierarchy,
    edit_calculated_column_expression,
    edit_measure_expression,
    mark_as_date_table,
    set_model_annotation,
    set_table_property,
    set_time_intelligence_enabled,
    set_column_hidden,
    set_field_format,
    set_member_property,
    set_partition,
    set_perspective,
    set_role,
    set_relationship_property,
)


@dataclass
class ModelApplyResult:
    """Summary of what changed during a model apply operation."""

    model_updated: list[str] = field(default_factory=list)
    tables_updated: list[str] = field(default_factory=list)
    measures_created: list[str] = field(default_factory=list)
    measures_updated: list[str] = field(default_factory=list)
    columns_created: list[str] = field(default_factory=list)
    columns_updated: list[str] = field(default_factory=list)
    relationships_created: list[str] = field(default_factory=list)
    relationships_updated: list[str] = field(default_factory=list)
    hierarchies_created: list[str] = field(default_factory=list)
    hierarchies_updated: list[str] = field(default_factory=list)
    partitions_created: list[str] = field(default_factory=list)
    partitions_updated: list[str] = field(default_factory=list)
    roles_created: list[str] = field(default_factory=list)
    roles_updated: list[str] = field(default_factory=list)
    perspectives_created: list[str] = field(default_factory=list)
    perspectives_updated: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(
            self.model_updated
            or self.tables_updated
            or
            self.measures_created
            or self.measures_updated
            or self.columns_created
            or self.columns_updated
            or self.relationships_created
            or self.relationships_updated
            or self.hierarchies_created
            or self.hierarchies_updated
            or self.partitions_created
            or self.partitions_updated
            or self.roles_created
            or self.roles_updated
            or self.perspectives_created
            or self.perspectives_updated
        )


def apply_model_yaml(
    project_root: Path,
    yaml_content: str,
    *,
    dry_run: bool = False,
) -> ModelApplyResult:
    """Apply declarative model changes from YAML."""
    result = ModelApplyResult()
    edit_session = TmdlEditSession()

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
        _apply_measures(
            project_root,
            measures_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    columns_spec = spec.get("columns")
    if columns_spec is not None:
        _apply_columns(
            project_root,
            columns_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    relationships_spec = spec.get("relationships")
    if relationships_spec is not None:
        _apply_relationships(
            project_root,
            relationships_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    hierarchies_spec = spec.get("hierarchies")
    if hierarchies_spec is not None:
        _apply_hierarchies(
            project_root,
            hierarchies_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    partitions_spec = spec.get("partitions")
    if partitions_spec is not None:
        _apply_partitions(
            project_root,
            partitions_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    roles_spec = spec.get("roles")
    if roles_spec is not None:
        _apply_roles(
            project_root,
            roles_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    perspectives_spec = spec.get("perspectives")
    if perspectives_spec is not None:
        _apply_perspectives(
            project_root,
            perspectives_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    model_spec = spec.get("model")
    if model_spec is not None:
        _apply_model_settings(
            project_root,
            model_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    tables_spec = spec.get("tables")
    if tables_spec is not None:
        _apply_tables(
            project_root,
            tables_spec,
            result,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )

    known_keys = {"model", "tables", "measures", "columns", "relationships", "hierarchies", "partitions", "roles", "perspectives"}
    if not known_keys.intersection(spec.keys()):
        result.errors.append(f"YAML must include at least one of: {', '.join(sorted(known_keys))}.")

    if not dry_run:
        edit_session.flush()

    return result


def _apply_model_settings(
    project_root: Path,
    model_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
) -> None:
    """Apply model-level settings."""
    if not isinstance(model_spec, dict):
        result.errors.append("'model' must be a mapping.")
        return

    changed = False

    if "timeIntelligence" in model_spec:
        value = model_spec["timeIntelligence"]
        if not isinstance(value, bool):
            result.errors.append("model.timeIntelligence: expected a boolean.")
        else:
            try:
                changed = set_time_intelligence_enabled(
                    project_root,
                    value,
                    dry_run=dry_run,
                    model=model,
                    edit_session=edit_session,
                )
                if changed:
                    result.model_updated.append("Model")
            except (FileNotFoundError, ValueError) as e:
                result.errors.append(f"model.timeIntelligence: {e}")

    annotations = model_spec.get("annotations")
    if annotations is not None:
        if not isinstance(annotations, dict):
            result.errors.append("model.annotations: expected a mapping.")
        else:
            for name, value in annotations.items():
                if not isinstance(value, str):
                    result.errors.append(f"model.annotations.{name}: expected a string.")
                    continue
                try:
                    _, annotation_changed = set_model_annotation(
                        project_root,
                        str(name),
                        value,
                        dry_run=dry_run,
                        model=model,
                        edit_session=edit_session,
                    )
                    changed = changed or annotation_changed
                except (FileNotFoundError, ValueError) as e:
                    result.errors.append(f"model.annotations.{name}: {e}")
            if changed and "Model" not in result.model_updated:
                result.model_updated.append("Model")


def _apply_tables(
    project_root: Path,
    tables_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
) -> None:
    """Apply table-level metadata such as dataCategory/dateTable."""
    if not isinstance(tables_spec, dict):
        result.errors.append("'tables' must be a mapping of table name to table specs.")
        return

    for table_name, entry in tables_spec.items():
        if not isinstance(entry, dict):
            result.errors.append(f"tables.{table_name}: expected a mapping.")
            continue
        try:
            table = model.find_table(str(table_name))
        except ValueError as e:
            result.errors.append(f"tables.{table_name}: {e}")
            continue

        changed = False
        data_category = entry.get("dataCategory")
        if isinstance(data_category, str):
            try:
                _, prop_changed = set_table_property(
                    project_root,
                    table.name,
                    "dataCategory",
                    data_category,
                    dry_run=dry_run,
                    model=model,
                    edit_session=edit_session,
                )
                changed = changed or prop_changed
            except (FileNotFoundError, ValueError) as e:
                result.errors.append(f"tables.{table_name}.dataCategory: {e}")
                continue

        date_table = entry.get("dateTable")
        if isinstance(date_table, str):
            try:
                _, _, date_changed = mark_as_date_table(
                    project_root,
                    table.name,
                    date_table,
                    dry_run=dry_run,
                    model=model,
                    edit_session=edit_session,
                )
                changed = changed or date_changed
            except (FileNotFoundError, ValueError) as e:
                result.errors.append(f"tables.{table_name}.dateTable: {e}")
                continue

        if changed:
            result.tables_updated.append(table.name)


def _apply_measures(
    project_root: Path,
    measures_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
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

            try:
                table = model.find_table(str(table_name))
                existing = _find_measure(table, name)
                has_expression = isinstance(expression, str) and bool(expression.strip())
                changed = False
                if existing is None:
                    if not has_expression:
                        result.errors.append(f"measures.{table_name}.{name}: missing non-empty 'expression'.")
                        continue
                    create_measure(
                        project_root,
                        table.name,
                        name,
                        expression,
                        format_string=fmt if isinstance(fmt, str) else None,
                        dry_run=dry_run,
                        model=model,
                        edit_session=edit_session,
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

                table_name_resolved = table.name
                measure_name = existing.name
                if has_expression:
                    table_name_resolved, measure_name, expr_changed = edit_measure_expression(
                        project_root,
                        table.name,
                        existing.name,
                        expression,
                        dry_run=dry_run,
                        model=model,
                        edit_session=edit_session,
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
                        edit_session=edit_session,
                    )
                    changed = changed or fmt_changed
                    if fmt_changed and not dry_run:
                        existing.format_string = fmt
                ref = f"{table_name_resolved}.{measure_name}"
                for meta_key, tmdl_key in (("displayFolder", "displayFolder"),):
                    meta_val = entry.get(meta_key)
                    if isinstance(meta_val, str):
                        _, _, _, meta_changed = set_member_property(
                            project_root, ref, tmdl_key, meta_val,
                            dry_run=dry_run, model=model, edit_session=edit_session,
                        )
                        changed = changed or meta_changed
                        if meta_changed and not dry_run:
                            existing.display_folder = meta_val
                if isinstance(entry.get("description"), str):
                    result.errors.append(
                        f'measures.{table_name}.{name}.description: Property "description" is not supported by Power BI TMDL for columns or measures.'
                    )
                if changed:
                    result.measures_updated.append(ref)
            except (FileNotFoundError, ValueError) as e:
                result.errors.append(f"measures.{table_name}.{name}: {e}")


def _apply_columns(
    project_root: Path,
    columns_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
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
                    edit_session=edit_session,
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
    edit_session: TmdlEditSession,
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
                edit_session=edit_session,
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
                        edit_session=edit_session,
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
                edit_session=edit_session,
            )
            changed = changed or expr_changed
            if expr_changed and not dry_run:
                existing.expression = expression
    else:
        if existing is None:
            raise ValueError("source columns are not created by model apply.")

    ref = f"{table.name}.{column_name}"
    if isinstance(fmt, str):
        _, _, _, fmt_changed = set_field_format(
            project_root,
            ref,
            fmt,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )
        changed = changed or fmt_changed
        if fmt_changed and not dry_run and existing is not None:
            existing.format_string = fmt
    if isinstance(hidden, bool):
        _, _, hidden_changed = set_column_hidden(
            project_root,
            ref,
            hidden,
            dry_run=dry_run,
            model=model,
            edit_session=edit_session,
        )
        changed = changed or hidden_changed
        if hidden_changed and not dry_run and existing is not None:
            existing.is_hidden = hidden
    for meta_key, tmdl_key in (
        ("displayFolder", "displayFolder"),
        ("sortByColumn", "sortByColumn"),
        ("summarizeBy", "summarizeBy"),
        ("dataCategory", "dataCategory"),
    ):
        meta_val = entry.get(meta_key)
        if isinstance(meta_val, str):
            _, _, _, meta_changed = set_member_property(
                project_root, ref, tmdl_key, meta_val,
                dry_run=dry_run, model=model, edit_session=edit_session,
            )
            changed = changed or meta_changed
            if meta_changed and not dry_run and existing is not None:
                if meta_key == "displayFolder":
                    existing.display_folder = meta_val
                elif meta_key == "sortByColumn":
                    existing.sort_by_column = meta_val
                elif meta_key == "summarizeBy":
                    existing.summarize_by = meta_val
                elif meta_key == "dataCategory":
                    existing.data_category = meta_val
    if isinstance(entry.get("description"), str):
        result.errors.append(
            f'columns.{table_name}.{column_name}.description: Property "description" is not supported by Power BI TMDL for columns or measures.'
        )
    if changed:
        result.columns_updated.append(ref)


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


def _apply_relationships(
    project_root: Path,
    relationships_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
) -> None:
    """Apply declarative relationship changes."""
    if not isinstance(relationships_spec, list):
        result.errors.append("'relationships' must be a list.")
        return

    for entry in relationships_spec:
        if not isinstance(entry, dict):
            result.errors.append("Each relationship must be a mapping with 'from' and 'to'.")
            continue
        from_ref = entry.get("from")
        to_ref = entry.get("to")
        if not isinstance(from_ref, str) or not isinstance(to_ref, str):
            result.errors.append("Each relationship requires 'from' and 'to' as Table.Column strings.")
            continue

        try:
            # Check if relationship already exists
            from pbi.modeling.schema import _parse_field_ref

            from_table, from_col = _parse_field_ref(from_ref)
            to_table, to_col = _parse_field_ref(to_ref)

            existing = None
            for rel in model.relationships:
                if (rel.from_table.lower() == from_table.lower()
                        and rel.from_column.lower() == from_col.lower()
                        and rel.to_table.lower() == to_table.lower()
                        and rel.to_column.lower() == to_col.lower()):
                    existing = rel
                    break

            # Collect non-key properties
            prop_keys = {k for k in entry if k not in ("from", "to")}
            label = f"{from_ref} -> {to_ref}"

            if existing is None:
                props = {k: str(entry[k]) for k in prop_keys}
                create_relationship(
                    project_root, from_ref, to_ref,
                    properties=props if props else None,
                    dry_run=dry_run, model=model, edit_session=edit_session,
                )
                result.relationships_created.append(label)
            else:
                changed = False
                for key in prop_keys:
                    val = str(entry[key])
                    if existing.properties.get(key) != val:
                        set_relationship_property(
                            project_root, from_ref, to_ref, key, val,
                            dry_run=dry_run, model=model, edit_session=edit_session,
                        )
                        changed = True
                if changed:
                    result.relationships_updated.append(label)
        except (FileNotFoundError, ValueError) as e:
            result.errors.append(f"relationships ({from_ref} -> {to_ref}): {e}")


def _apply_hierarchies(
    project_root: Path,
    hierarchies_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
) -> None:
    """Apply declarative hierarchy changes."""
    if not isinstance(hierarchies_spec, dict):
        result.errors.append("'hierarchies' must be a mapping of table name to hierarchy list.")
        return

    for table_name, entries in hierarchies_spec.items():
        if not isinstance(entries, list):
            result.errors.append(f"hierarchies.{table_name}: expected a list of hierarchy specs.")
            continue

        for entry in entries:
            if not isinstance(entry, dict):
                result.errors.append(f"hierarchies.{table_name}: each entry must be a mapping.")
                continue
            name = entry.get("name")
            levels = entry.get("levels")
            if not isinstance(name, str) or not name.strip():
                result.errors.append(f"hierarchies.{table_name}: entry missing non-empty 'name'.")
                continue
            if not isinstance(levels, list) or not levels:
                result.errors.append(f"hierarchies.{table_name}.{name}: missing non-empty 'levels' list.")
                continue

            try:
                table = model.find_table(str(table_name))
                level_cols = [str(lv) for lv in levels]

                # Check if hierarchy exists
                existing = None
                for h in table.hierarchies:
                    if h.name.lower() == name.lower():
                        existing = h
                        break

                label = f"{table.name}.{name}"
                if existing is None:
                    create_hierarchy(
                        project_root, table.name, name, level_cols,
                        dry_run=dry_run, model=model, edit_session=edit_session,
                    )
                    result.hierarchies_created.append(label)
                else:
                    existing_cols = [lv.column for lv in existing.levels]
                    if existing_cols != level_cols:
                        delete_hierarchy(
                            project_root, table.name, existing.name,
                            dry_run=dry_run, model=model, edit_session=edit_session,
                        )
                        # Remove from in-memory model so create doesn't see duplicate
                        table.hierarchies = [h for h in table.hierarchies if h.name.lower() != name.lower()]
                        create_hierarchy(
                            project_root, table.name, name, level_cols,
                            dry_run=dry_run, model=model, edit_session=edit_session,
                        )
                        result.hierarchies_updated.append(label)
            except (FileNotFoundError, ValueError) as e:
                result.errors.append(f"hierarchies.{table_name}.{name}: {e}")


def _apply_partitions(
    project_root: Path,
    partitions_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
) -> None:
    """Apply declarative partition changes."""
    if not isinstance(partitions_spec, dict):
        result.errors.append("'partitions' must be a mapping of table name to partition specs.")
        return

    for table_name, entries in partitions_spec.items():
        if not isinstance(entries, list):
            result.errors.append(f"partitions.{table_name}: expected a list.")
            continue
        try:
            table = model.find_table(str(table_name))
        except ValueError as e:
            result.errors.append(f"partitions.{table_name}: {e}")
            continue

        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                result.errors.append(f"partitions.{table_name}[{index}]: expected a mapping.")
                continue
            name = entry.get("name")
            source_type = entry.get("sourceType")
            source = entry.get("source")
            mode = entry.get("mode", "import")
            if not isinstance(name, str) or not name.strip():
                result.errors.append(f"partitions.{table_name}[{index}].name: expected a non-empty string.")
                continue
            if not isinstance(source_type, str):
                result.errors.append(f"partitions.{table_name}[{index}].sourceType: expected a string.")
                continue
            if not isinstance(source, str):
                result.errors.append(f"partitions.{table_name}[{index}].source: expected a string.")
                continue
            if not isinstance(mode, str):
                result.errors.append(f"partitions.{table_name}[{index}].mode: expected a string.")
                continue

            try:
                try:
                    existing = table.find_partition(name)
                except ValueError:
                    existing = None
                if existing is None:
                    table_label, partition_label, created = create_partition(
                        project_root,
                        table.name,
                        name,
                        source,
                        source_type=source_type,
                        mode=mode,
                        dry_run=dry_run,
                        model=model,
                        edit_session=edit_session,
                    )
                    if created:
                        result.partitions_created.append(f"{table_label}.{partition_label}")
                else:
                    table_label, partition_label, changed = set_partition(
                        project_root,
                        table.name,
                        existing.name,
                        source_expression=source,
                        source_type=source_type,
                        mode=mode,
                        dry_run=dry_run,
                        model=model,
                        edit_session=edit_session,
                    )
                    if changed:
                        result.partitions_updated.append(f"{table_label}.{partition_label}")
            except (FileNotFoundError, ValueError) as e:
                result.errors.append(f"partitions.{table_name}[{index}]: {e}")


def _apply_roles(
    project_root: Path,
    roles_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
) -> None:
    """Apply declarative role and RLS changes."""
    if not isinstance(roles_spec, dict):
        result.errors.append("'roles' must be a mapping of role name to role specs.")
        return

    for role_name, entry in roles_spec.items():
        if not isinstance(entry, dict):
            result.errors.append(f"roles.{role_name}: expected a mapping.")
            continue

        permission = entry.get("permission", "read")
        if not isinstance(permission, str):
            result.errors.append(f"roles.{role_name}.permission: expected a string.")
            continue

        filters_spec = entry.get("filters", {})
        if filters_spec in (None, {}):
            filters_spec = {}
        if not isinstance(filters_spec, dict):
            result.errors.append(f"roles.{role_name}.filters: expected a mapping of table name to DAX expression.")
            continue

        members_spec = entry.get("members", [])
        if members_spec in (None, []):
            members_spec = []
        if not isinstance(members_spec, list):
            result.errors.append(f"roles.{role_name}.members: expected a list.")
            continue

        table_permissions: list[RoleTablePermission] = []
        invalid = False
        for table_name, expression in filters_spec.items():
            if not isinstance(expression, str):
                result.errors.append(f"roles.{role_name}.filters.{table_name}: expected a string.")
                invalid = True
                continue
            table_permissions.append(RoleTablePermission(table=str(table_name), filter_expression=expression))

        members: list[RoleMember] = []
        for index, member_entry in enumerate(members_spec):
            if not isinstance(member_entry, dict):
                result.errors.append(f"roles.{role_name}.members[{index}]: expected a mapping.")
                invalid = True
                continue
            member_name = member_entry.get("name")
            if not isinstance(member_name, str) or not member_name.strip():
                result.errors.append(f"roles.{role_name}.members[{index}].name: expected a non-empty string.")
                invalid = True
                continue
            member_type = member_entry.get("type", "user")
            if not isinstance(member_type, str):
                result.errors.append(f"roles.{role_name}.members[{index}].type: expected a string.")
                invalid = True
                continue
            identity_provider = member_entry.get("identityProvider")
            if identity_provider is not None and not isinstance(identity_provider, str):
                result.errors.append(f"roles.{role_name}.members[{index}].identityProvider: expected a string.")
                invalid = True
                continue
            members.append(
                RoleMember(
                    name=member_name,
                    member_type=member_type,
                    identity_provider=identity_provider,
                )
            )

        if invalid:
            continue

        spec = RoleSpec(
            model_permission=permission,
            table_permissions=table_permissions,
            members=members,
        )

        try:
            try:
                existing = model.find_role(str(role_name))
            except ValueError:
                existing = None

            if existing is None:
                name, created = create_role(
                    project_root,
                    str(role_name),
                    spec,
                    dry_run=dry_run,
                    model=model,
                    edit_session=edit_session,
                )
                if created:
                    result.roles_created.append(name)
            else:
                name, changed = set_role(
                    project_root,
                    existing.name,
                    spec,
                    dry_run=dry_run,
                    model=model,
                    edit_session=edit_session,
                )
                if changed:
                    result.roles_updated.append(name)
        except (FileNotFoundError, ValueError) as e:
            result.errors.append(f"roles.{role_name}: {e}")


def _apply_perspectives(
    project_root: Path,
    perspectives_spec: Any,
    result: ModelApplyResult,
    *,
    dry_run: bool,
    model: SemanticModel,
    edit_session: TmdlEditSession,
) -> None:
    """Apply declarative perspective changes."""
    if not isinstance(perspectives_spec, dict):
        result.errors.append("'perspectives' must be a mapping of perspective name to perspective specs.")
        return

    for perspective_name, entry in perspectives_spec.items():
        if not isinstance(entry, dict):
            result.errors.append(f"perspectives.{perspective_name}: expected a mapping.")
            continue
        tables = entry.get("tables")
        if not isinstance(tables, dict):
            result.errors.append(f"perspectives.{perspective_name}.tables: expected a mapping.")
            continue

        spec = PerspectiveMemberSpec()
        invalid = False
        for table_name, table_entry in tables.items():
            if not isinstance(table_entry, dict):
                result.errors.append(f"perspectives.{perspective_name}.tables.{table_name}: expected a mapping.")
                invalid = True
                continue

            if table_entry.get("includeAll") is True:
                spec.include_all_tables.append(str(table_name))

            for key, target in (
                ("columns", spec.columns),
                ("measures", spec.measures),
                ("hierarchies", spec.hierarchies),
            ):
                values = table_entry.get(key, [])
                if values in (None, []):
                    continue
                if not isinstance(values, list) or not all(isinstance(item, str) for item in values):
                    result.errors.append(
                        f"perspectives.{perspective_name}.tables.{table_name}.{key}: expected a list of strings."
                    )
                    invalid = True
                    continue
                target.extend(f"{table_name}.{item}" for item in values)
        if invalid:
            continue

        try:
            try:
                existing = model.find_perspective(str(perspective_name))
            except ValueError:
                existing = None

            if existing is None:
                name, created = create_perspective(
                    project_root,
                    str(perspective_name),
                    spec,
                    dry_run=dry_run,
                    model=model,
                    edit_session=edit_session,
                )
                if created:
                    result.perspectives_created.append(name)
            else:
                name, changed = set_perspective(
                    project_root,
                    existing.name,
                    spec,
                    dry_run=dry_run,
                    model=model,
                    edit_session=edit_session,
                )
                if changed:
                    result.perspectives_updated.append(name)
        except (FileNotFoundError, ValueError) as e:
            result.errors.append(f"perspectives.{perspective_name}: {e}")
