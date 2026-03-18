"""Dependency and rename helpers for semantic-model mutations."""

from __future__ import annotations

from pathlib import Path

from .schema import SemanticModel
from .writes_relationships import _get_relationships_path
from .writes import (
    TmdlEditSession,
    _commit_tmdl_lines,
    _find_member_block,
    _format_tmdl_field_ref,
    _format_tmdl_name,
    _get_tmdl_lines,
    _update_member_property,
)


def find_field_dependents(
    project_root: Path,
    field_ref: str,
    *,
    model: SemanticModel | None = None,
) -> list[tuple[str, str, str]]:
    """Find all measures/columns that reference a field."""
    from .dax_refs import find_dependents

    loaded_model = model or SemanticModel.load(project_root)
    table_name, field_name, field_type = loaded_model.resolve_field(field_ref)
    is_measure = field_type == "measure"

    dependents: list[tuple[str, str, str]] = []
    for table in loaded_model.tables:
        for measure in table.measures:
            if table.name == table_name and measure.name == field_name:
                continue
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
    """Find all fields that the target references."""
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
                resolved_table, resolved_name, resolved_type = loaded_model.resolve_field(f"{ref.table}.{ref.name}")
                resolved.append((resolved_table, resolved_name, resolved_type))
            except ValueError:
                pass
        else:
            key = f"*.{ref.name}".lower()
            if key in seen:
                continue
            seen.add(key)
            found = False
            for measure in table.measures:
                if measure.name.lower() == ref.name.lower():
                    resolved.append((table.name, measure.name, "measure"))
                    found = True
                    break
            if not found:
                for model_table in loaded_model.tables:
                    for measure in model_table.measures:
                        if measure.name.lower() == ref.name.lower():
                            resolved.append((model_table.name, measure.name, "measure"))
                            found = True
                            break
                    if found:
                        break

    return resolved


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
    """Rename a measure and update all DAX references."""
    from .dax_refs import find_dependents, replace_refs as dax_replace

    loaded_model = model or SemanticModel.load(project_root)
    owns_edit_session = edit_session is None
    if edit_session is None:
        edit_session = TmdlEditSession()
    table = loaded_model.find_table(table_name)
    measure = table.find_measure(old_name)
    if table.definition_path is None:
        raise ValueError(f'Table "{table.name}" has no TMDL definition file.')

    for existing in table.measures:
        if existing.name.lower() == new_name.lower():
            raise ValueError(f'Measure "{new_name}" already exists in table "{table.name}".')

    updated_refs: list[str] = []

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, _end = _find_member_block(lines, member_kind="measure", member_name=measure.name)
    old_formatted = _format_tmdl_name(old_name)
    new_formatted = _format_tmdl_name(new_name)
    lines[start] = lines[start].replace(f"measure {old_formatted}", f"measure {new_formatted}", 1)
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)

    for model_table in loaded_model.tables:
        if model_table.definition_path is None:
            continue
        table_lines = _get_tmdl_lines(model_table.definition_path, edit_session)
        changed = False

        for index, line in enumerate(table_lines):
            if old_name.lower() not in line.lower():
                continue
            new_line = dax_replace(line, old_table=None, old_name=old_name, new_name=new_name)
            new_line = dax_replace(new_line, old_table=table.name, old_name=old_name, new_name=new_name)
            if new_line != line:
                table_lines[index] = new_line
                changed = True

        if changed:
            _commit_tmdl_lines(model_table.definition_path, table_lines, dry_run=dry_run, session=edit_session)
            for model_measure in model_table.measures:
                if find_dependents(model_measure.expression, table.name, old_name, is_measure=True):
                    updated_refs.append(f"{model_table.name}.{model_measure.name}")
            for column in model_table.columns:
                if column.expression and old_name.lower() in column.expression.lower():
                    updated_refs.append(f"{model_table.name}.{column.name}")

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
    """Rename a calculated column and update all DAX + relationship references."""
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

    for existing in table.columns:
        if existing.name.lower() == new_name.lower():
            raise ValueError(f'Column "{new_name}" already exists in table "{table.name}".')

    updated_refs: list[str] = []

    lines = _get_tmdl_lines(table.definition_path, edit_session)
    start, _end = _find_member_block(lines, member_kind="column", member_name=column.name)
    old_formatted = _format_tmdl_name(old_name)
    new_formatted = _format_tmdl_name(new_name)
    decl_line = lines[start]
    for keyword in ("calculatedColumn", "column"):
        old_decl = f"{keyword} {old_formatted}"
        if old_decl in decl_line:
            lines[start] = decl_line.replace(old_decl, f"{keyword} {new_formatted}", 1)
            break
    _commit_tmdl_lines(table.definition_path, lines, dry_run=dry_run, session=edit_session)

    for existing in table.columns:
        if existing.sort_by_column and existing.sort_by_column.lower() == old_name.lower():
            _update_member_property(
                table.definition_path,
                member_kind="column",
                member_name=existing.name,
                property_name="sortByColumn",
                property_value=new_name,
                dry_run=dry_run,
                edit_session=edit_session,
            )
            updated_refs.append(f"{table.name}.{existing.name} (sortByColumn)")

    for model_table in loaded_model.tables:
        if model_table.definition_path is None:
            continue
        table_lines = _get_tmdl_lines(model_table.definition_path, edit_session)
        changed = False

        for index, line in enumerate(table_lines):
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
                table_lines[index] = new_line
                changed = True

        if changed:
            _commit_tmdl_lines(model_table.definition_path, table_lines, dry_run=dry_run, session=edit_session)
            for measure in model_table.measures:
                if old_name.lower() in measure.expression.lower():
                    updated_refs.append(f"{model_table.name}.{measure.name}")
            for model_column in model_table.columns:
                if model_column.expression and old_name.lower() in model_column.expression.lower():
                    updated_refs.append(f"{model_table.name}.{model_column.name}")

    rel_path = _get_relationships_path(project_root, loaded_model)
    if rel_path.exists():
        rel_lines = _get_tmdl_lines(rel_path, edit_session)
        changed = False
        old_ref = _format_tmdl_field_ref(table.name, old_name)
        new_ref = _format_tmdl_field_ref(table.name, new_name)
        for index, line in enumerate(rel_lines):
            stripped = line.strip()
            if stripped.startswith(("fromColumn:", "toColumn:")) and old_ref in line:
                rel_lines[index] = line.replace(old_ref, new_ref)
                changed = True
                updated_refs.append(f"relationship ({stripped.split(':')[0].strip()})")
        if changed:
            _commit_tmdl_lines(rel_path, rel_lines, dry_run=dry_run, session=edit_session)

    if owns_edit_session and not dry_run:
        edit_session.flush()

    return table.name, old_name, new_name, updated_refs
