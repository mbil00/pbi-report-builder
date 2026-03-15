"""Semantic-model dataclasses and lookup helpers."""

from __future__ import annotations

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


@dataclass
class Measure:
    name: str
    table: str
    expression: str = ""
    format_string: str = ""
    lineage_tag: str = ""
    definition_path: Path | None = None


@dataclass
class SemanticTable:
    name: str
    columns: list[Column] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)
    definition_path: Path | None = None

    def find_column(self, name: str) -> Column:
        """Find a column by name (case-insensitive)."""
        name_lower = name.lower()
        for column in self.columns:
            if column.name.lower() == name_lower:
                return column
        available = ", ".join(f'"{c.name}"' for c in self.columns)
        raise ValueError(f'Column "{name}" not found in table "{self.name}". Available: {available}')

    def find_measure(self, name: str) -> Measure:
        """Find a measure by name (case-insensitive)."""
        name_lower = name.lower()
        for measure in self.measures:
            if measure.name.lower() == name_lower:
                return measure
        available = ", ".join(f'"{m.name}"' for m in self.measures)
        raise ValueError(f'Measure "{name}" not found in table "{self.name}". Available: {available}')


@dataclass
class SemanticModel:
    folder: Path
    tables: list[SemanticTable] = field(default_factory=list)

    @classmethod
    def load(cls, project_root: Path) -> SemanticModel:
        """Find and load the semantic model from a project root."""
        from .parser import _parse_table_tmdl

        sm_folders = list(project_root.glob("*.SemanticModel"))
        if not sm_folders:
            raise FileNotFoundError(f"No .SemanticModel folder found in {project_root}")
        sm_folder = sm_folders[0]

        model = cls(folder=sm_folder)
        tables_dir = sm_folder / "definition" / "tables"
        if tables_dir.exists():
            for tmdl_file in sorted(tables_dir.glob("*.tmdl")):
                table = _parse_table_tmdl(tmdl_file)
                if table:
                    model.tables.append(table)

        return model

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
        available = ", ".join(f'"{table.name}"' for table in self.tables)
        raise ValueError(f'Table "{name}" not found. Available: {available}')

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

        available_cols = [column.name for column in table.columns]
        available_meas = [measure.name for measure in table.measures]
        raise ValueError(
            f'Field "{prop}" not found in table "{table.name}". '
            f"Columns: {', '.join(available_cols)}. "
            f"Measures: {', '.join(available_meas)}."
        )


def _parse_field_ref(ref: str) -> tuple[str, str]:
    """Parse 'Table.Field' into (table, field)."""
    dot = ref.find(".")
    if dot == -1:
        raise ValueError(f'Invalid field reference "{ref}". Use Table.Field format.')
    return ref[:dot], ref[dot + 1:]
