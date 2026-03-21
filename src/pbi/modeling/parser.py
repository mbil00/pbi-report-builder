"""TMDL parsing helpers for semantic-model metadata."""

from __future__ import annotations

from pathlib import Path

from .schema import (
    Column,
    Hierarchy,
    HierarchyLevel,
    Measure,
    ModelRole,
    Perspective,
    PerspectiveTable,
    Relationship,
    RoleMember,
    RoleTablePermission,
    SemanticTable,
)

# Known TMDL property names that can appear inside column/measure blocks.
# Used to distinguish metadata lines from DAX expression continuation.
_TMDL_PROPERTY_NAMES = frozenset({
    "dataType", "formatString", "lineageTag", "summarizeBy",
    "sourceColumn", "isDefaultLabel", "isKey", "isNameInferred",
    "isDataTypeInferred", "sortByColumn", "changedProperties",
    "displayFolder", "description", "dataCategory", "expression",
    "isAvailableInMdx", "isDefaultImage", "isDefaultMeasure",
    "isUnique", "defaultValue",
})


def _parse_tmdl_name(text: str) -> str:
    """Parse a TMDL name, handling quoted and unquoted identifiers."""
    text = text.strip()
    if text.startswith("'"):
        chars: list[str] = []
        i = 1
        while i < len(text):
            ch = text[i]
            if ch == "'":
                if i + 1 < len(text) and text[i + 1] == "'":
                    chars.append("'")
                    i += 2
                    continue
                return "".join(chars)
            chars.append(ch)
            i += 1
        return "".join(chars)
    return text.split()[0].rstrip("=").strip()


def _parse_table_tmdl(path: Path) -> SemanticTable | None:
    """Parse a single table TMDL file."""
    content = path.read_text(encoding="utf-8-sig")
    lines = content.splitlines()

    table_name = None
    table_props: dict[str, str] = {}
    columns: list[Column] = []
    measures: list[Measure] = []
    hierarchies: list[Hierarchy] = []

    current_type: str | None = None
    current_name = ""
    current_props: dict[str, str] = {}
    current_expr = ""

    # Hierarchy parsing state
    current_levels: list[HierarchyLevel] = []
    current_level_name: str | None = None
    current_level_props: dict[str, str] = {}

    def _flush_level() -> None:
        nonlocal current_level_name, current_level_props
        if current_level_name is not None:
            current_levels.append(
                HierarchyLevel(
                    name=current_level_name,
                    column=current_level_props.get("column", current_level_name),
                    lineage_tag=current_level_props.get("lineageTag", ""),
                )
            )
        current_level_name = None
        current_level_props = {}

    def _flush() -> None:
        nonlocal current_type, current_name, current_props, current_expr
        nonlocal current_levels
        if current_type == "column" and table_name:
            columns.append(
                Column(
                    name=current_name,
                    table=table_name,
                    data_type=current_props.get("dataType", "unknown"),
                    is_hidden="isHidden" in current_props,
                    source_column=current_props.get("sourceColumn", ""),
                    expression=current_expr.strip(),
                    format_string=current_props.get("formatString", ""),
                    summarize_by=current_props.get("summarizeBy", ""),
                    lineage_tag=current_props.get("lineageTag", ""),
                    definition_path=path,
                    kind=current_props.get("__kind", "column"),
                    description=current_props.get("description", ""),
                    display_folder=current_props.get("displayFolder", ""),
                    sort_by_column=current_props.get("sortByColumn", ""),
                    data_category=current_props.get("dataCategory", ""),
                    is_key="isKey" in current_props,
                )
            )
        elif current_type == "measure" and table_name:
            measures.append(
                Measure(
                    name=current_name,
                    table=table_name,
                    expression=current_expr.strip(),
                    format_string=current_props.get("formatString", ""),
                    lineage_tag=current_props.get("lineageTag", ""),
                    definition_path=path,
                    description=current_props.get("description", ""),
                    display_folder=current_props.get("displayFolder", ""),
                )
            )
        elif current_type == "hierarchy" and table_name:
            _flush_level()
            hierarchies.append(
                Hierarchy(
                    name=current_name,
                    table=table_name,
                    levels=list(current_levels),
                    lineage_tag=current_props.get("lineageTag", ""),
                    definition_path=path,
                )
            )
            current_levels = []
        current_type = None
        current_name = ""
        current_props = {}
        current_expr = ""

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("///"):
            continue

        indent = 0
        for ch in line:
            if ch == "\t":
                indent += 1
            elif ch == " ":
                indent += 0.25
            else:
                break
        indent = int(indent)

        if indent == 0 and stripped.startswith("table "):
            table_name = _parse_tmdl_name(stripped[6:])
            continue

        if indent == 1:
            if ":" in stripped and current_type is None:
                key, _, val = stripped.partition(":")
                key = key.strip()
                if key in {"dataCategory"}:
                    table_props[key] = val.strip()
                    continue
            if stripped.startswith("column ") or stripped.startswith("calculatedColumn "):
                _flush()
                is_calculated = stripped.startswith("calculatedColumn ")
                keyword = "calculatedColumn " if is_calculated else "column "
                current_type = "column"
                rest = stripped[len(keyword):]
                current_name = _parse_tmdl_name(rest)
                eq_pos = rest.find("=")
                current_props["__kind"] = "calculatedColumn" if (is_calculated or eq_pos >= 0) else "column"
                if eq_pos >= 0:
                    current_expr = rest[eq_pos + 1 :].strip()
                continue
            if stripped.startswith("measure "):
                _flush()
                current_type = "measure"
                rest = stripped[8:]
                current_name = _parse_tmdl_name(rest)
                eq_pos = rest.find("=")
                if eq_pos >= 0:
                    current_expr = rest[eq_pos + 1 :].strip()
                continue
            if stripped.startswith("hierarchy "):
                _flush()
                current_type = "hierarchy"
                current_name = _parse_tmdl_name(stripped[10:])
                current_levels = []
                continue
            if stripped.startswith(("partition ", "annotation ")):
                _flush()
                current_type = None
                continue

        if current_type == "hierarchy" and indent >= 2:
            if indent == 2:
                if stripped.startswith("level "):
                    _flush_level()
                    current_level_name = _parse_tmdl_name(stripped[6:])
                elif ":" in stripped:
                    key, _, val = stripped.partition(":")
                    key = key.strip()
                    if key == "lineageTag":
                        current_props["lineageTag"] = val.strip()
            elif indent >= 3:
                if ":" in stripped:
                    key, _, val = stripped.partition(":")
                    key = key.strip()
                    if key in ("column", "lineageTag"):
                        current_level_props[key] = val.strip()
            continue

        if current_type and indent >= 2:
            if stripped == "isHidden":
                current_props["isHidden"] = "true"
            elif stripped == "isKey":
                current_props["isKey"] = "true"
            elif stripped.startswith(("annotation ", "variation ")):
                pass  # skip nested blocks
            elif ":" in stripped and not stripped.startswith("```"):
                key = stripped.partition(":")[0].strip()
                if key in _TMDL_PROPERTY_NAMES:
                    _, _, val = stripped.partition(":")
                    current_props[key] = val.strip()
                elif current_type == "measure" or (
                    current_type == "column" and current_props.get("__kind") == "calculatedColumn"
                ):
                    current_expr += "\n" + stripped
            elif current_type == "measure" or (
                current_type == "column" and current_props.get("__kind") == "calculatedColumn"
            ):
                current_expr += "\n" + stripped

    _flush()

    if table_name is None:
        return None

    return SemanticTable(
        name=table_name, columns=columns, measures=measures,
        hierarchies=hierarchies, definition_path=path,
        data_category=table_props.get("dataCategory", ""),
    )


def _parse_model_tmdl(path: Path) -> dict[str, bool | None]:
    """Parse model-level settings needed by the CLI."""
    settings: dict[str, bool | None] = {"time_intelligence_enabled": None}
    content = path.read_text(encoding="utf-8-sig")
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("annotation "):
            continue
        rest = stripped[len("annotation "):]
        name, sep, value = rest.partition("=")
        if not sep:
            continue
        if name.strip() != "__PBI_TimeIntelligenceEnabled":
            continue
        normalized = value.strip().strip('"').lower()
        if normalized in {"1", "true"}:
            settings["time_intelligence_enabled"] = True
        elif normalized in {"0", "false"}:
            settings["time_intelligence_enabled"] = False
    return settings


def _parse_perspective_tmdl(path: Path) -> Perspective | None:
    """Parse one perspective TMDL file."""
    content = path.read_text(encoding="utf-8-sig")
    lines = content.splitlines()

    perspective_name: str | None = None
    tables: list[PerspectiveTable] = []
    current_table: PerspectiveTable | None = None

    def _flush_table() -> None:
        nonlocal current_table
        if current_table is not None:
            tables.append(current_table)
        current_table = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("///"):
            continue

        indent = 0
        for ch in line:
            if ch == "\t":
                indent += 1
            elif ch == " ":
                indent += 0.25
            else:
                break
        indent = int(indent)

        if indent == 0 and stripped.startswith("perspective "):
            perspective_name = _parse_tmdl_name(stripped[len("perspective "):])
            continue

        if indent == 1 and stripped.startswith("perspectiveTable "):
            _flush_table()
            current_table = PerspectiveTable(table=_parse_tmdl_name(stripped[len("perspectiveTable "):]))
            continue

        if current_table is None or indent < 2:
            continue

        if stripped == "includeAll":
            current_table.include_all = True
        elif stripped.startswith("perspectiveColumn "):
            current_table.columns.append(_parse_tmdl_name(stripped[len("perspectiveColumn "):]))
        elif stripped.startswith("perspectiveMeasure "):
            current_table.measures.append(_parse_tmdl_name(stripped[len("perspectiveMeasure "):]))
        elif stripped.startswith("perspectiveHierarchy "):
            current_table.hierarchies.append(_parse_tmdl_name(stripped[len("perspectiveHierarchy "):]))

    _flush_table()

    if perspective_name is None:
        return None

    return Perspective(name=perspective_name, tables=tables, definition_path=path)


def _parse_role_tmdl(path: Path) -> ModelRole | None:
    """Parse one role TMDL file."""
    content = path.read_text(encoding="utf-8-sig")
    lines = content.splitlines()

    role_name: str | None = None
    model_permission = "read"
    table_permissions: list[RoleTablePermission] = []
    members: list[RoleMember] = []
    current_member: RoleMember | None = None

    def _flush_member() -> None:
        nonlocal current_member
        if current_member is not None:
            members.append(current_member)
        current_member = None

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("///"):
            continue

        indent = 0
        for ch in line:
            if ch == "\t":
                indent += 1
            elif ch == " ":
                indent += 0.25
            else:
                break
        indent = int(indent)

        if indent == 0 and stripped.startswith("role "):
            _flush_member()
            role_name = _parse_tmdl_name(stripped[len("role "):])
            continue

        if indent == 1 and stripped.startswith("modelPermission:"):
            _flush_member()
            model_permission = stripped.partition(":")[2].strip()
            continue

        if indent == 1 and stripped.startswith("tablePermission "):
            _flush_member()
            rest = stripped[len("tablePermission "):]
            table_part, sep, expression = rest.partition("=")
            if not sep:
                continue
            table_permissions.append(
                RoleTablePermission(
                    table=_parse_tmdl_name(table_part.strip()),
                    filter_expression=expression.strip(),
                )
            )
            continue

        if indent == 1 and stripped.startswith("member "):
            _flush_member()
            rest = stripped[len("member "):]
            name_part, sep, member_type = rest.partition("=")
            current_member = RoleMember(
                name=_parse_tmdl_name(name_part.strip()),
                member_type=(member_type.strip() if sep else "user") or "user",
            )
            continue

        if current_member is not None and indent >= 2 and stripped.startswith("identityProvider"):
            _, _, value = stripped.partition("=")
            current_member.identity_provider = value.strip()

    _flush_member()

    if role_name is None:
        return None

    return ModelRole(
        name=role_name,
        model_permission=model_permission,
        table_permissions=table_permissions,
        members=members,
        definition_path=path,
    )


def _parse_relationships_tmdl(path: Path) -> list[Relationship]:
    """Parse a relationships.tmdl file into Relationship objects."""
    content = path.read_text(encoding="utf-8-sig")
    lines = content.splitlines()
    relationships: list[Relationship] = []

    current_id: str | None = None
    current_props: dict[str, str] = {}

    def _flush() -> None:
        nonlocal current_id, current_props
        if current_id is not None:
            from_ref = current_props.get("fromColumn", "")
            to_ref = current_props.get("toColumn", "")
            from_dot = from_ref.find(".")
            to_dot = to_ref.find(".")
            if from_dot > 0 and to_dot > 0:
                relationships.append(Relationship(
                    id=current_id,
                    from_table=from_ref[:from_dot],
                    from_column=from_ref[from_dot + 1:],
                    to_table=to_ref[:to_dot],
                    to_column=to_ref[to_dot + 1:],
                    properties={k: v for k, v in current_props.items()
                                if k not in ("fromColumn", "toColumn")},
                ))
        current_id = None
        current_props = {}

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("relationship "):
            _flush()
            current_id = stripped[len("relationship "):].strip()
            continue

        if current_id is not None and ":" in stripped:
            key, _, val = stripped.partition(":")
            current_props[key.strip()] = val.strip()

    _flush()
    return relationships
