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

    model_section: dict = {}
    if loaded_model.time_intelligence_enabled is not None:
        model_section["timeIntelligence"] = loaded_model.time_intelligence_enabled
    annotations = {
        key: value
        for key, value in loaded_model.annotations.items()
        if key != "__PBI_TimeIntelligenceEnabled"
    }
    if annotations:
        model_section["annotations"] = annotations
    if model_section:
        spec["model"] = model_section

    tables_section: dict = {}
    for table in loaded_model.tables:
        entry: dict = {}
        if table.data_category:
            entry["dataCategory"] = table.data_category
        if table.date_table_column:
            entry["dateTable"] = table.date_table_column
        if entry:
            tables_section[table.name] = entry
    if tables_section:
        spec["tables"] = tables_section

    # Measures
    measures_section: dict = {}
    for table in loaded_model.tables:
        table_measures = []
        for m in table.measures:
            entry: dict = {"name": m.name, "expression": m.expression}
            if m.format_string:
                entry["format"] = m.format_string
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

    partitions_section: dict = {}
    for table in loaded_model.tables:
        if not table.partitions:
            continue
        partitions_section[table.name] = [
            {
                "name": partition.name,
                "sourceType": partition.source_type,
                "mode": partition.mode,
                "source": partition.source_expression,
            }
            for partition in table.partitions
        ]
    if partitions_section:
        spec["partitions"] = partitions_section

    roles_section: dict = {}
    for role in loaded_model.roles:
        entry: dict = {"permission": role.model_permission}
        if role.table_permissions:
            entry["filters"] = {
                item.table: item.filter_expression
                for item in role.table_permissions
            }
        if role.members:
            members: list[dict] = []
            for member in role.members:
                member_entry: dict = {"name": member.name}
                if member.member_type != "user":
                    member_entry["type"] = member.member_type
                if member.identity_provider:
                    member_entry["identityProvider"] = member.identity_provider
                members.append(member_entry)
            entry["members"] = members
        roles_section[role.name] = entry
    if roles_section:
        spec["roles"] = roles_section

    perspectives_section: dict = {}
    for perspective in loaded_model.perspectives:
        tables_entry: dict = {}
        for perspective_table in perspective.tables:
            entry: dict = {}
            if perspective_table.include_all:
                entry["includeAll"] = True
            if perspective_table.columns:
                entry["columns"] = perspective_table.columns
            if perspective_table.measures:
                entry["measures"] = perspective_table.measures
            if perspective_table.hierarchies:
                entry["hierarchies"] = perspective_table.hierarchies
            tables_entry[perspective_table.table] = entry
        perspectives_section[perspective.name] = {"tables": tables_entry}
    if perspectives_section:
        spec["perspectives"] = perspectives_section

    return yaml.dump(spec, default_flow_style=False, sort_keys=False, allow_unicode=True)
