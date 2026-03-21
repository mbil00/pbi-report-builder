"""Semantic-model dataclasses and lookup helpers."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Column:
    name: str
    table: str
    data_type: str = "unknown"
    is_hidden: bool = False
    source_column: str = ""
    expression: str = ""
    format_string: str = ""
    summarize_by: str = ""
    lineage_tag: str = ""
    definition_path: Path | None = None
    kind: str = "column"
    description: str = ""
    display_folder: str = ""
    sort_by_column: str = ""
    data_category: str = ""
    is_key: bool = False


@dataclass
class Measure:
    name: str
    table: str
    expression: str = ""
    format_string: str = ""
    lineage_tag: str = ""
    definition_path: Path | None = None
    description: str = ""
    display_folder: str = ""


@dataclass
class HierarchyLevel:
    name: str
    column: str
    lineage_tag: str = ""


@dataclass
class Hierarchy:
    name: str
    table: str
    levels: list[HierarchyLevel] = field(default_factory=list)
    lineage_tag: str = ""
    definition_path: Path | None = None


@dataclass
class SemanticTable:
    name: str
    columns: list[Column] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    hierarchies: list[Hierarchy] = field(default_factory=list)
    definition_path: Path | None = None
    data_category: str = ""

    @property
    def date_table_column(self) -> str | None:
        """Return the marked date-table column when present."""
        if self.data_category != "Time":
            return None
        for column in self.columns:
            if column.is_key:
                return column.name
        return None

    def find_column(self, name: str) -> Column:
        """Find a column by name (case-insensitive)."""
        name_lower = name.lower()
        for column in self.columns:
            if column.name.lower() == name_lower:
                return column
        col_names = [c.name for c in self.columns]
        close = difflib.get_close_matches(name, col_names, n=3, cutoff=0.5)
        if close:
            suggestion = ", ".join(f'"{n}"' for n in close)
            raise ValueError(f'Column "{name}" not found in table "{self.name}". Did you mean: {suggestion}?')
        available = ", ".join(f'"{n}"' for n in col_names)
        raise ValueError(f'Column "{name}" not found in table "{self.name}". Available: {available}')

    def find_hierarchy(self, name: str) -> Hierarchy:
        """Find a hierarchy by name (case-insensitive)."""
        name_lower = name.lower()
        for hierarchy in self.hierarchies:
            if hierarchy.name.lower() == name_lower:
                return hierarchy
        hier_names = [h.name for h in self.hierarchies]
        close = difflib.get_close_matches(name, hier_names, n=3, cutoff=0.5)
        if close:
            suggestion = ", ".join(f'"{n}"' for n in close)
            raise ValueError(f'Hierarchy "{name}" not found in table "{self.name}". Did you mean: {suggestion}?')
        available = ", ".join(f'"{n}"' for n in hier_names)
        raise ValueError(f'Hierarchy "{name}" not found in table "{self.name}". Available: {available}')

    def find_measure(self, name: str) -> Measure:
        """Find a measure by name (case-insensitive)."""
        name_lower = name.lower()
        for measure in self.measures:
            if measure.name.lower() == name_lower:
                return measure
        meas_names = [m.name for m in self.measures]
        close = difflib.get_close_matches(name, meas_names, n=3, cutoff=0.5)
        if close:
            suggestion = ", ".join(f'"{n}"' for n in close)
            raise ValueError(f'Measure "{name}" not found in table "{self.name}". Did you mean: {suggestion}?')
        available = ", ".join(f'"{n}"' for n in meas_names)
        raise ValueError(f'Measure "{name}" not found in table "{self.name}". Available: {available}')


@dataclass
class Relationship:
    """A model relationship between two columns."""

    id: str
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    properties: dict[str, str] = field(default_factory=dict)


@dataclass
class PerspectiveTable:
    table: str
    include_all: bool = False
    columns: list[str] = field(default_factory=list)
    measures: list[str] = field(default_factory=list)
    hierarchies: list[str] = field(default_factory=list)


@dataclass
class Perspective:
    name: str
    tables: list[PerspectiveTable] = field(default_factory=list)
    definition_path: Path | None = None

    def find_table(self, name: str) -> PerspectiveTable:
        """Find a perspective table entry by name (case-insensitive)."""
        name_lower = name.lower()
        for table in self.tables:
            if table.table.lower() == name_lower:
                return table
        available = ", ".join(f'"{table.table}"' for table in self.tables)
        raise ValueError(
            f'Table "{name}" not found in perspective "{self.name}". '
            f'Available: {available or "(none)"}'
        )


@dataclass
class SemanticModel:
    folder: Path
    tables: list[SemanticTable] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    perspectives: list[Perspective] = field(default_factory=list)
    model_path: Path | None = None
    time_intelligence_enabled: bool | None = None

    @classmethod
    def load(cls, project_root: Path) -> SemanticModel:
        """Find and load the semantic model from a project root."""
        from .parser import _parse_model_tmdl, _parse_perspective_tmdl, _parse_relationships_tmdl, _parse_table_tmdl

        sm_folders = list(project_root.glob("*.SemanticModel"))
        if not sm_folders:
            raise FileNotFoundError(f"No .SemanticModel folder found in {project_root}")
        sm_folder = sm_folders[0]

        model = cls(folder=sm_folder)
        model_path = sm_folder / "definition" / "model.tmdl"
        model.model_path = model_path if model_path.exists() else None
        if model.model_path is not None:
            model_settings = _parse_model_tmdl(model.model_path)
            model.time_intelligence_enabled = model_settings.get("time_intelligence_enabled")
        tables_dir = sm_folder / "definition" / "tables"
        if tables_dir.exists():
            for tmdl_file in sorted(tables_dir.glob("*.tmdl")):
                table = _parse_table_tmdl(tmdl_file)
                if table:
                    model.tables.append(table)

        rel_file = sm_folder / "definition" / "relationships.tmdl"
        if rel_file.exists():
            model.relationships = _parse_relationships_tmdl(rel_file)

        perspectives_dir = sm_folder / "definition" / "perspectives"
        if perspectives_dir.exists():
            for tmdl_file in sorted(perspectives_dir.glob("*.tmdl")):
                perspective = _parse_perspective_tmdl(tmdl_file)
                if perspective is not None:
                    model.perspectives.append(perspective)

        return model

    def find_relationships(
        self,
        *,
        from_table: str | None = None,
        to_table: str | None = None,
    ) -> list[Relationship]:
        """Filter relationships by from/to table (case-insensitive)."""
        results = self.relationships
        if from_table:
            ft = from_table.lower()
            results = [r for r in results if r.from_table.lower() == ft or r.to_table.lower() == ft]
        if to_table:
            tt = to_table.lower()
            results = [r for r in results if r.from_table.lower() == tt or r.to_table.lower() == tt]
        return results

    def find_path(self, from_table: str, to_table: str) -> list[Relationship] | None:
        """Find the shortest relationship path between two tables using BFS."""
        from collections import deque

        ft = from_table.lower()
        tt = to_table.lower()
        if ft == tt:
            return []

        # Build adjacency list
        adj: dict[str, list[tuple[str, Relationship]]] = {}
        for rel in self.relationships:
            f_lower = rel.from_table.lower()
            t_lower = rel.to_table.lower()
            adj.setdefault(f_lower, []).append((t_lower, rel))
            adj.setdefault(t_lower, []).append((f_lower, rel))

        # BFS
        queue: deque[tuple[str, list[Relationship]]] = deque([(ft, [])])
        visited: set[str] = {ft}
        while queue:
            current, path = queue.popleft()
            for neighbor, rel in adj.get(current, []):
                if neighbor in visited:
                    continue
                new_path = path + [rel]
                if neighbor == tt:
                    return new_path
                visited.add(neighbor)
                queue.append((neighbor, new_path))
        return None

    def find_table(self, name: str) -> SemanticTable:
        """Find a table by name (case-insensitive, partial match)."""
        name_lower = name.lower()
        for table in self.tables:
            if table.name.lower() == name_lower:
                return table
        matches = [table for table in self.tables if name_lower in table.name.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(f'"{table.name}"' for table in matches)
            raise ValueError(f'Ambiguous table "{name}". Matches: {names}')
        table_names = [t.name for t in self.tables]
        close = difflib.get_close_matches(name, table_names, n=3, cutoff=0.5)
        if close:
            suggestion = ", ".join(f'"{n}"' for n in close)
            raise ValueError(f'Table "{name}" not found. Did you mean: {suggestion}?')
        available = ", ".join(f'"{n}"' for n in table_names)
        raise ValueError(f'Table "{name}" not found. Available: {available}')

    def find_perspective(self, name: str) -> Perspective:
        """Find a perspective by name (case-insensitive)."""
        name_lower = name.lower()
        for perspective in self.perspectives:
            if perspective.name.lower() == name_lower:
                return perspective
        names = [perspective.name for perspective in self.perspectives]
        close = difflib.get_close_matches(name, names, n=3, cutoff=0.5)
        if close:
            suggestion = ", ".join(f'"{item}"' for item in close)
            raise ValueError(f'Perspective "{name}" not found. Did you mean: {suggestion}?')
        available = ", ".join(f'"{item}"' for item in names)
        raise ValueError(f'Perspective "{name}" not found. Available: {available or "(none)"}')

    def resolve_field(self, field_ref: str) -> tuple[str, str, str]:
        """Resolve 'Table.Field' to (table_name, field_name, field_type)."""
        entity, prop = _parse_field_ref(field_ref)
        table = self.find_table(entity)

        prop_lower = prop.lower()
        for column in table.columns:
            if column.name.lower() == prop_lower:
                return table.name, column.name, "column"
        for measure in table.measures:
            if measure.name.lower() == prop_lower:
                return table.name, measure.name, "measure"

        all_field_names = [c.name for c in table.columns] + [m.name for m in table.measures]
        close = difflib.get_close_matches(prop, all_field_names, n=3, cutoff=0.5)
        if close:
            suggestion = ", ".join(f'"{n}"' for n in close)
            raise ValueError(
                f'Field "{prop}" not found in table "{table.name}". Did you mean: {suggestion}?'
            )
        raise ValueError(
            f'Field "{prop}" not found in table "{table.name}". '
            f"Columns: {', '.join(c.name for c in table.columns)}. "
            f"Measures: {', '.join(m.name for m in table.measures)}."
        )


def _parse_field_ref(ref: str) -> tuple[str, str]:
    """Parse 'Table.Field' into (table, field)."""
    dot = ref.find(".")
    if dot == -1:
        raise ValueError(f'Invalid field reference "{ref}". Use Table.Field format.')
    return ref[:dot], ref[dot + 1:]
