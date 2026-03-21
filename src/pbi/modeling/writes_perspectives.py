"""TMDL write helpers for semantic-model perspectives."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .schema import Perspective, PerspectiveTable, SemanticModel
from .writes import TmdlEditSession, _commit_tmdl_lines, validate_model_object_name


@dataclass
class PerspectiveMemberSpec:
    """Requested perspective membership changes."""

    include_all_tables: list[str] = field(default_factory=list)
    columns: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    hierarchies: list[str] = field(default_factory=list)


def create_perspective(
    project_root: Path,
    perspective_name: str,
    spec: PerspectiveMemberSpec,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Create a perspective file from validated membership spec."""
    loaded_model = model or SemanticModel.load(project_root)
    validate_model_object_name(perspective_name, "perspective")
    try:
        loaded_model.find_perspective(perspective_name)
    except ValueError:
        pass
    else:
        raise ValueError(f'Perspective "{perspective_name}" already exists.')

    perspective = _build_perspective(loaded_model, perspective_name, spec)
    lines = _render_perspective_lines(perspective)
    _commit_tmdl_lines(
        _perspective_path(loaded_model, perspective_name),
        lines,
        dry_run=dry_run,
        session=edit_session,
    )
    return perspective.name, True


def set_perspective(
    project_root: Path,
    perspective_name: str,
    spec: PerspectiveMemberSpec,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Replace the full contents of one perspective."""
    loaded_model = model or SemanticModel.load(project_root)
    existing = loaded_model.find_perspective(perspective_name)
    perspective = _build_perspective(loaded_model, perspective_name, spec)
    path = existing.definition_path or _perspective_path(loaded_model, perspective_name)
    current = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    lines = _render_perspective_lines(perspective)
    if current == lines:
        return perspective.name, False
    _commit_tmdl_lines(path, lines, dry_run=dry_run, session=edit_session)
    return perspective.name, True


def delete_perspective(
    project_root: Path,
    perspective_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Delete one perspective file."""
    loaded_model = model or SemanticModel.load(project_root)
    perspective = loaded_model.find_perspective(perspective_name)
    path = perspective.definition_path or _perspective_path(loaded_model, perspective.name)
    if not path.exists():
        return perspective.name, False
    if dry_run:
        return perspective.name, True
    if edit_session is not None:
        edit_session._lines_by_path.pop(path, None)
        edit_session._dirty_paths.discard(path)
    path.unlink()
    return perspective.name, True


def _build_perspective(
    model: SemanticModel,
    perspective_name: str,
    spec: PerspectiveMemberSpec,
) -> Perspective:
    """Validate a perspective membership spec against the semantic model."""
    table_map: dict[str, PerspectiveTable] = {}

    def ensure_table(table_name: str) -> PerspectiveTable:
        table = model.find_table(table_name)
        entry = table_map.get(table.name)
        if entry is None:
            entry = PerspectiveTable(table=table.name)
            table_map[table.name] = entry
        return entry

    for table_name in spec.include_all_tables:
        entry = ensure_table(table_name)
        if entry.columns or entry.measures or entry.hierarchies:
            raise ValueError(f'Perspective table "{entry.table}" cannot mix includeAll with specific members.')
        entry.include_all = True

    for field_ref in spec.columns:
        table_name, field_name, field_type = model.resolve_field(field_ref)
        if field_type != "column":
            raise ValueError(f'Field "{field_ref}" resolves to a {field_type}, not a column.')
        entry = ensure_table(table_name)
        if entry.include_all:
            raise ValueError(f'Perspective table "{entry.table}" already uses includeAll.')
        if field_name not in entry.columns:
            entry.columns.append(field_name)

    for field_ref in spec.measures:
        table_name, field_name, field_type = model.resolve_field(field_ref)
        if field_type != "measure":
            raise ValueError(f'Field "{field_ref}" resolves to a {field_type}, not a measure.')
        entry = ensure_table(table_name)
        if entry.include_all:
            raise ValueError(f'Perspective table "{entry.table}" already uses includeAll.')
        if field_name not in entry.measures:
            entry.measures.append(field_name)

    for hierarchy_ref in spec.hierarchies:
        table_name, hierarchy_name = _parse_table_member_ref(hierarchy_ref)
        table = model.find_table(table_name)
        hierarchy = table.find_hierarchy(hierarchy_name)
        entry = ensure_table(table.name)
        if entry.include_all:
            raise ValueError(f'Perspective table "{entry.table}" already uses includeAll.')
        if hierarchy.name not in entry.hierarchies:
            entry.hierarchies.append(hierarchy.name)

    if not table_map:
        raise ValueError("Perspective membership is empty. Add at least one table, column, measure, or hierarchy.")

    ordered_tables = sorted(table_map.values(), key=lambda item: item.table.lower())
    return Perspective(name=perspective_name, tables=ordered_tables, definition_path=_perspective_path(model, perspective_name))


def _render_perspective_lines(perspective: Perspective) -> list[str]:
    """Render a perspective as TMDL lines."""
    lines = [f"perspective {_format_tmdl_name(perspective.name)}"]
    for table in perspective.tables:
        lines.append(f"\tperspectiveTable {_format_tmdl_name(table.table)}")
        if table.include_all:
            lines.append("\t\tincludeAll")
            continue
        for column in table.columns:
            lines.append(f"\t\tperspectiveColumn {_format_tmdl_name(column)}")
        for measure in table.measures:
            lines.append(f"\t\tperspectiveMeasure {_format_tmdl_name(measure)}")
        for hierarchy in table.hierarchies:
            lines.append(f"\t\tperspectiveHierarchy {_format_tmdl_name(hierarchy)}")
    return lines


def _perspective_path(model: SemanticModel, perspective_name: str) -> Path:
    return model.folder / "definition" / "perspectives" / f"{perspective_name}.tmdl"


def _parse_table_member_ref(ref: str) -> tuple[str, str]:
    dot = ref.find(".")
    if dot == -1:
        raise ValueError(f'Invalid reference "{ref}". Use Table.Name format.')
    return ref[:dot], ref[dot + 1 :]


def _format_tmdl_name(name: str) -> str:
    if name and all(ch.isalnum() or ch == "_" for ch in name):
        return name
    escaped = name.replace("'", "''")
    return f"'{escaped}'"
