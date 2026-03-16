"""Export semantic model as YAML for round-tripping through model apply."""

from __future__ import annotations

from pathlib import Path

import yaml

from pbi.model import SemanticModel


def export_model_yaml(
    project_root: Path,
    *,
    model: SemanticModel | None = None,
) -> str:
    """Export the full semantic model as YAML."""
    loaded_model = model or SemanticModel.load(project_root)
    spec: dict = {}

    # Measures
    measures_section: dict = {}
    for table in loaded_model.tables:
        table_measures = []
        for m in table.measures:
            entry: dict = {"name": m.name, "expression": m.expression}
            if m.format_string:
                entry["format"] = m.format_string
            if m.description:
                entry["description"] = m.description
            if m.display_folder:
                entry["displayFolder"] = m.display_folder
            table_measures.append(entry)
        if table_measures:
            measures_section[table.name] = table_measures
    if measures_section:
        spec["measures"] = measures_section

    # Columns (only non-default properties)
    columns_section: dict = {}
    for table in loaded_model.tables:
        table_columns: dict = {}
        for c in table.columns:
            entry = {}
            if c.kind == "calculatedColumn":
                entry["type"] = "calculated"
                if c.expression:
                    entry["expression"] = c.expression
                if c.data_type and c.data_type != "unknown":
                    entry["dataType"] = c.data_type
            if c.format_string:
                entry["format"] = c.format_string
            if c.is_hidden:
                entry["hidden"] = True
            if c.summarize_by and c.summarize_by != "none":
                entry["summarizeBy"] = c.summarize_by
            if c.description:
                entry["description"] = c.description
            if c.display_folder:
                entry["displayFolder"] = c.display_folder
            if c.sort_by_column:
                entry["sortByColumn"] = c.sort_by_column
            if c.data_category:
                entry["dataCategory"] = c.data_category
            if entry:
                table_columns[c.name] = entry
        if table_columns:
            columns_section[table.name] = table_columns
    if columns_section:
        spec["columns"] = columns_section

    # Relationships
    relationships_section: list = []
    for rel in loaded_model.relationships:
        entry = {
            "from": f"{rel.from_table}.{rel.from_column}",
            "to": f"{rel.to_table}.{rel.to_column}",
        }
        for key, val in rel.properties.items():
            entry[key] = val
        relationships_section.append(entry)
    if relationships_section:
        spec["relationships"] = relationships_section

    # Hierarchies
    hierarchies_section: dict = {}
    for table in loaded_model.tables:
        table_hierarchies = []
        for h in table.hierarchies:
            hier_entry: dict = {
                "name": h.name,
                "levels": [lv.column for lv in h.levels],
            }
            table_hierarchies.append(hier_entry)
        if table_hierarchies:
            hierarchies_section[table.name] = table_hierarchies
    if hierarchies_section:
        spec["hierarchies"] = hierarchies_section

    return yaml.dump(spec, default_flow_style=False, sort_keys=False, allow_unicode=True)
