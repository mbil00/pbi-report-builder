"""Semantic model discovery and TMDL parsing."""

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


@dataclass
class Measure:
    name: str
    table: str
    expression: str = ""
    format_string: str = ""


@dataclass
class SemanticTable:
    name: str
    columns: list[Column] = field(default_factory=list)
    measures: list[Measure] = field(default_factory=list)


@dataclass
class SemanticModel:
    folder: Path
    tables: list[SemanticTable] = field(default_factory=list)

    @classmethod
    def load(cls, project_root: Path) -> SemanticModel:
        """Find and load the semantic model from a project root."""
        # Look for .SemanticModel folders
        sm_folders = list(project_root.glob("*.SemanticModel"))
        if not sm_folders:
            raise FileNotFoundError(
                f"No .SemanticModel folder found in {project_root}"
            )
        sm_folder = sm_folders[0]

        model = cls(folder=sm_folder)

        # Parse TMDL tables
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
        for t in self.tables:
            if t.name.lower() == name_lower:
                return t
        matches = [t for t in self.tables if name_lower in t.name.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(f'"{t.name}"' for t in matches)
            raise ValueError(f'Ambiguous table "{name}". Matches: {names}')
        available = ", ".join(f'"{t.name}"' for t in self.tables)
        raise ValueError(f'Table "{name}" not found. Available: {available}')

    def resolve_field(self, field_ref: str) -> tuple[str, str, str]:
        """Resolve 'Table.Field' to (table_name, field_name, field_type).

        field_type is 'column' or 'measure'.
        """
        entity, prop = _parse_field_ref(field_ref)
        table = self.find_table(entity)

        prop_lower = prop.lower()
        for c in table.columns:
            if c.name.lower() == prop_lower:
                return table.name, c.name, "column"
        for m in table.measures:
            if m.name.lower() == prop_lower:
                return table.name, m.name, "measure"

        available_cols = [c.name for c in table.columns]
        available_meas = [m.name for m in table.measures]
        raise ValueError(
            f'Field "{prop}" not found in table "{table.name}". '
            f"Columns: {', '.join(available_cols)}. "
            f"Measures: {', '.join(available_meas)}."
        )


def _parse_field_ref(ref: str) -> tuple[str, str]:
    """Parse 'Table.Field' or 'Table.\"Field Name\"' into (table, field)."""
    dot = ref.find(".")
    if dot == -1:
        raise ValueError(
            f'Invalid field reference "{ref}". Use Table.Field format.'
        )
    return ref[:dot], ref[dot + 1:]


def _parse_tmdl_name(text: str) -> str:
    """Parse a TMDL name — handles 'quoted names' and unquoted."""
    text = text.strip()
    if text.startswith("'"):
        end = text.index("'", 1)
        return text[1:end]
    return text.split()[0].rstrip("=").strip()


def _parse_table_tmdl(path: Path) -> SemanticTable | None:
    """Parse a single .tmdl table file."""
    content = path.read_text(encoding="utf-8-sig")
    lines = content.splitlines()

    table_name = None
    columns: list[Column] = []
    measures: list[Measure] = []

    current_type: str | None = None  # "column" or "measure"
    current_name: str = ""
    current_props: dict[str, str] = {}
    current_expr: str = ""

    def _flush() -> None:
        nonlocal current_type, current_name, current_props, current_expr
        if current_type == "column" and table_name:
            columns.append(Column(
                name=current_name,
                table=table_name,
                data_type=current_props.get("dataType", "unknown"),
                is_hidden="isHidden" in current_props,
                source_column=current_props.get("sourceColumn", ""),
            ))
        elif current_type == "measure" and table_name:
            measures.append(Measure(
                name=current_name,
                table=table_name,
                expression=current_expr.strip(),
                format_string=current_props.get("formatString", ""),
            ))
        current_type = None
        current_name = ""
        current_props = {}
        current_expr = ""

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("///"):
            continue

        # Detect indent level (tabs)
        indent = 0
        for ch in line:
            if ch == "\t":
                indent += 1
            elif ch == " ":
                indent += 0.25  # 4 spaces = 1 tab level
            else:
                break
        indent = int(indent)

        # Table declaration (indent 0)
        if indent == 0 and stripped.startswith("table "):
            table_name = _parse_tmdl_name(stripped[6:])
            continue

        # New member at indent 1 — flush previous
        if indent == 1:
            if stripped.startswith("column ") or stripped.startswith("calculatedColumn "):
                _flush()
                keyword = "calculatedColumn " if stripped.startswith("calc") else "column "
                current_type = "column"
                current_name = _parse_tmdl_name(stripped[len(keyword):])
                continue
            elif stripped.startswith("measure "):
                _flush()
                current_type = "measure"
                rest = stripped[8:]
                current_name = _parse_tmdl_name(rest)
                eq_pos = rest.find("=")
                if eq_pos >= 0:
                    current_expr = rest[eq_pos + 1:].strip()
                continue
            elif stripped.startswith(("partition ", "hierarchy ", "annotation ")):
                _flush()
                current_type = None
                continue

        # Properties at indent 2+
        if current_type and indent >= 2:
            if stripped == "isHidden":
                current_props["isHidden"] = "true"
            elif ":" in stripped and not stripped.startswith("```"):
                key, _, val = stripped.partition(":")
                current_props[key.strip()] = val.strip()
            elif current_type == "measure":
                # Continuation of DAX expression
                current_expr += "\n" + stripped

    _flush()

    if table_name is None:
        return None

    return SemanticTable(name=table_name, columns=columns, measures=measures)
