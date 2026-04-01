"""Investigation helpers for locating semantic-model entities in TMDL files."""

from __future__ import annotations

from pathlib import Path
import difflib
from datetime import datetime, UTC
import json
from typing import Any

from .parser import _parse_tmdl_field_ref, _parse_tmdl_name
from .schema import SemanticModel


def _indent_level(line: str) -> int:
    indent = 0.0
    for ch in line:
        if ch == "\t":
            indent += 1
        elif ch == " ":
            indent += 0.25
        else:
            break
    return int(indent)


def _read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8-sig").splitlines()


def _snippet(lines: list[str], start_line: int, end_line: int, *, max_lines: int = 20) -> str:
    block = lines[start_line - 1:end_line]
    if len(block) > max_lines:
        block = block[:max_lines]
        block.append("...")
    return "\n".join(block).rstrip()


def _entity_record(
    *,
    ref: str,
    kind: str,
    path: Path,
    start_line: int,
    end_line: int,
    line_text: str,
    snippet: str,
    **extra: Any,
) -> dict[str, Any]:
    record = {
        "ref": ref,
        "kind": kind,
        "path": str(path),
        "line": start_line,
        "endLine": end_line,
        "lineText": line_text.strip(),
        "snippet": snippet,
    }
    record.update(extra)
    return record


def _finalize_file_blocks(blocks: list[dict[str, Any]], lines: list[str]) -> None:
    for idx, block in enumerate(blocks):
        if idx + 1 < len(blocks):
            end_line = blocks[idx + 1]["line"] - 1
        else:
            end_line = len(lines)
        block["endLine"] = end_line
        block["snippet"] = _snippet(lines, block["line"], end_line)


def _scan_table_file(path: Path) -> dict[str, Any]:
    lines = _read_lines(path)
    table_name: str | None = None
    table_line = 1
    members: list[dict[str, Any]] = []
    levels: list[dict[str, Any]] = []
    current_hierarchy: str | None = None

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("///"):
            continue
        indent = _indent_level(line)

        if indent == 0 and stripped.startswith("table "):
            table_name = _parse_tmdl_name(stripped[len("table "):])
            table_line = line_no
            continue

        if table_name is None:
            continue

        if indent == 1:
            current_hierarchy = None
            if stripped.startswith("column "):
                members.append(
                    {
                        "kind": "column",
                        "name": _parse_tmdl_name(stripped[len("column "):]),
                        "line": line_no,
                        "lineText": stripped,
                    }
                )
            elif stripped.startswith("calculatedColumn "):
                members.append(
                    {
                        "kind": "calculatedColumn",
                        "name": _parse_tmdl_name(stripped[len("calculatedColumn "):]),
                        "line": line_no,
                        "lineText": stripped,
                    }
                )
            elif stripped.startswith("measure "):
                members.append(
                    {
                        "kind": "measure",
                        "name": _parse_tmdl_name(stripped[len("measure "):]),
                        "line": line_no,
                        "lineText": stripped,
                    }
                )
            elif stripped.startswith("hierarchy "):
                current_hierarchy = _parse_tmdl_name(stripped[len("hierarchy "):])
                members.append(
                    {
                        "kind": "hierarchy",
                        "name": current_hierarchy,
                        "line": line_no,
                        "lineText": stripped,
                    }
                )
            elif stripped.startswith("partition "):
                members.append(
                    {
                        "kind": "partition",
                        "name": _parse_tmdl_name(stripped[len("partition "):]),
                        "line": line_no,
                        "lineText": stripped,
                    }
                )
            continue

        if indent == 2 and current_hierarchy and stripped.startswith("level "):
            levels.append(
                {
                    "kind": "level",
                    "hierarchy": current_hierarchy,
                    "name": _parse_tmdl_name(stripped[len("level "):]),
                    "line": line_no,
                    "lineText": stripped,
                }
            )

    _finalize_file_blocks(members, lines)
    _finalize_file_blocks(levels, lines)

    table_end = members[0]["line"] - 1 if members else len(lines)
    table_record = {
        "name": table_name or path.stem.removesuffix(".tmdl"),
        "path": path,
        "line": table_line,
        "endLine": table_end,
        "lineText": lines[table_line - 1].strip() if lines else "",
        "snippet": _snippet(lines, table_line, table_end),
        "members": members,
        "levels": levels,
    }
    return table_record


def _scan_model_file(path: Path) -> list[dict[str, Any]]:
    lines = _read_lines(path)
    annotations: list[dict[str, Any]] = []
    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped.startswith("annotation "):
            continue
        rest = stripped[len("annotation "):]
        name, _, value = rest.partition("=")
        annotations.append(
            _entity_record(
                ref=f"annotation:{name.strip()}",
                kind="annotation",
                path=path,
                start_line=line_no,
                end_line=line_no,
                line_text=stripped,
                snippet=stripped,
                name=name.strip(),
                value=value.strip(),
            )
        )
    return annotations


def _scan_relationships_file(path: Path) -> list[dict[str, Any]]:
    lines = _read_lines(path)
    relationships: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush(next_line: int | None = None) -> None:
        nonlocal current
        if current is None:
            return
        end_line = (next_line - 1) if next_line is not None else len(lines)
        current["endLine"] = end_line
        current["snippet"] = _snippet(lines, current["line"], end_line)
        from_ref = current.get("fromRef", "")
        to_ref = current.get("toRef", "")
        try:
            from_table, from_column = _parse_tmdl_field_ref(from_ref)
            to_table, to_column = _parse_tmdl_field_ref(to_ref)
            current["fromTable"] = from_table
            current["fromColumn"] = from_column
            current["toTable"] = to_table
            current["toColumn"] = to_column
            current["ref"] = f"relationship:{from_table}.{from_column}->{to_table}.{to_column}"
        except ValueError:
            current["ref"] = f'relationship:{current["id"]}'
        relationships.append(current)
        current = None

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("relationship "):
            flush(line_no)
            current = {
                "kind": "relationship",
                "id": stripped[len("relationship "):].strip(),
                "path": str(path),
                "line": line_no,
                "lineText": stripped,
                "properties": {},
            }
            continue
        if current is not None and ":" in stripped:
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            current["properties"][key] = value
            if key == "fromColumn":
                current["fromRef"] = value
            elif key == "toColumn":
                current["toRef"] = value

    flush()
    return relationships


def _scan_role_file(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    lines = _read_lines(path)
    role_name: str | None = None
    role_line = 1
    members: list[dict[str, Any]] = []

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("///"):
            continue
        indent = _indent_level(line)
        if indent == 0 and stripped.startswith("role "):
            role_name = _parse_tmdl_name(stripped[len("role "):])
            role_line = line_no
            continue
        if role_name is None or indent != 1:
            continue
        if stripped.startswith("tablePermission "):
            table_part, _, _ = stripped[len("tablePermission "):].partition("=")
            members.append(
                {
                    "kind": "roleTablePermission",
                    "name": _parse_tmdl_name(table_part.strip()),
                    "line": line_no,
                    "lineText": stripped,
                }
            )
        elif stripped.startswith("member "):
            member_part, _, member_type = stripped[len("member "):].partition("=")
            members.append(
                {
                    "kind": "roleMember",
                    "name": _parse_tmdl_name(member_part.strip()),
                    "memberType": member_type.strip() or "user",
                    "line": line_no,
                    "lineText": stripped,
                }
            )

    if role_name is None:
        return None, []

    _finalize_file_blocks(members, lines)
    role_end = members[0]["line"] - 1 if members else len(lines)
    role = {
        "name": role_name,
        "path": path,
        "line": role_line,
        "endLine": role_end,
        "lineText": lines[role_line - 1].strip() if lines else "",
        "snippet": _snippet(lines, role_line, role_end),
    }
    return role, members


def _scan_perspective_file(path: Path) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    lines = _read_lines(path)
    perspective_name: str | None = None
    perspective_line = 1
    members: list[dict[str, Any]] = []
    current_table: str | None = None

    for line_no, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("///"):
            continue
        indent = _indent_level(line)
        if indent == 0 and stripped.startswith("perspective "):
            perspective_name = _parse_tmdl_name(stripped[len("perspective "):])
            perspective_line = line_no
            continue
        if perspective_name is None:
            continue
        if indent == 1 and stripped.startswith("perspectiveTable "):
            current_table = _parse_tmdl_name(stripped[len("perspectiveTable "):])
            members.append(
                {
                    "kind": "perspectiveTable",
                    "name": current_table,
                    "line": line_no,
                    "lineText": stripped,
                }
            )
            continue
        if current_table is None or indent != 2:
            continue
        if stripped.startswith("perspectiveColumn "):
            members.append(
                {
                    "kind": "perspectiveColumn",
                    "table": current_table,
                    "name": _parse_tmdl_name(stripped[len("perspectiveColumn "):]),
                    "line": line_no,
                    "lineText": stripped,
                }
            )
        elif stripped.startswith("perspectiveMeasure "):
            members.append(
                {
                    "kind": "perspectiveMeasure",
                    "table": current_table,
                    "name": _parse_tmdl_name(stripped[len("perspectiveMeasure "):]),
                    "line": line_no,
                    "lineText": stripped,
                }
            )
        elif stripped.startswith("perspectiveHierarchy "):
            members.append(
                {
                    "kind": "perspectiveHierarchy",
                    "table": current_table,
                    "name": _parse_tmdl_name(stripped[len("perspectiveHierarchy "):]),
                    "line": line_no,
                    "lineText": stripped,
                }
            )

    if perspective_name is None:
        return None, []

    _finalize_file_blocks(members, lines)
    perspective_end = members[0]["line"] - 1 if members else len(lines)
    perspective = {
        "name": perspective_name,
        "path": path,
        "line": perspective_line,
        "endLine": perspective_end,
        "lineText": lines[perspective_line - 1].strip() if lines else "",
        "snippet": _snippet(lines, perspective_line, perspective_end),
    }
    return perspective, members


def build_tmdl_trace(project_root: Path) -> dict[str, Any]:
    project_root = project_root.resolve()
    model = SemanticModel.load(project_root)
    sm_folder = model.folder.resolve()
    definition_dir = sm_folder / "definition"

    refs: dict[str, dict[str, Any]] = {}
    table_summaries: dict[str, dict[str, Any]] = {}

    table_files = sorted((definition_dir / "tables").glob("*.tmdl")) if (definition_dir / "tables").exists() else []
    scanned_tables = {record["name"]: record for record in (_scan_table_file(path) for path in table_files)}

    for table in model.tables:
        scanned = scanned_tables.get(table.name)
        if scanned is None:
            continue
        table_ref = f"table:{table.name}"
        refs[table_ref] = _entity_record(
            ref=table_ref,
            kind="table",
            path=scanned["path"],
            start_line=scanned["line"],
            end_line=scanned["endLine"],
            line_text=scanned["lineText"],
            snippet=scanned["snippet"],
            name=table.name,
            dataCategory=table.data_category,
            isParameterType=table.is_parameter_type,
            counts={
                "columns": len(table.columns),
                "measures": len(table.measures),
                "hierarchies": len(table.hierarchies),
                "partitions": len(table.partitions),
            },
        )

        for member in scanned["members"]:
            member_kind = member["kind"]
            if member_kind == "column":
                ref = f'column:{table.name}.{member["name"]}'
            elif member_kind == "calculatedColumn":
                ref = f'calculatedColumn:{table.name}.{member["name"]}'
            elif member_kind == "measure":
                ref = f'measure:{table.name}.{member["name"]}'
            elif member_kind == "hierarchy":
                ref = f'hierarchy:{table.name}.{member["name"]}'
            elif member_kind == "partition":
                ref = f'partition:{table.name}.{member["name"]}'
            else:
                continue
            refs[ref] = _entity_record(
                ref=ref,
                kind=member_kind,
                path=scanned["path"],
                start_line=member["line"],
                end_line=member["endLine"],
                line_text=member["lineText"],
                snippet=member["snippet"],
                table=table.name,
                name=member["name"],
            )

        for level in scanned["levels"]:
            ref = f'level:{table.name}.{level["hierarchy"]}.{level["name"]}'
            refs[ref] = _entity_record(
                ref=ref,
                kind="level",
                path=scanned["path"],
                start_line=level["line"],
                end_line=level["endLine"],
                line_text=level["lineText"],
                snippet=level["snippet"],
                table=table.name,
                hierarchy=level["hierarchy"],
                name=level["name"],
            )

        table_summaries[table.name] = {
            "path": str(scanned["path"]),
            "line": scanned["line"],
            "counts": refs[table_ref]["counts"],
        }

    model_path = definition_dir / "model.tmdl"
    annotations: list[str] = []
    if model_path.exists():
        for annotation in _scan_model_file(model_path):
            refs[annotation["ref"]] = annotation
            annotations.append(annotation["name"])

    rel_path = definition_dir / "relationships.tmdl"
    if rel_path.exists():
        for relationship in _scan_relationships_file(rel_path):
            refs[relationship["ref"]] = relationship

    roles_dir = definition_dir / "roles"
    if roles_dir.exists():
        for role_path in sorted(roles_dir.glob("*.tmdl")):
            role, members = _scan_role_file(role_path)
            if role is None:
                continue
            role_ref = f'role:{role["name"]}'
            refs[role_ref] = _entity_record(
                ref=role_ref,
                kind="role",
                path=role["path"],
                start_line=role["line"],
                end_line=role["endLine"],
                line_text=role["lineText"],
                snippet=role["snippet"],
                name=role["name"],
            )
            for member in members:
                if member["kind"] == "roleTablePermission":
                    ref = f'roleTablePermission:{role["name"]}.{member["name"]}'
                else:
                    ref = f'roleMember:{role["name"]}.{member["name"]}'
                refs[ref] = _entity_record(
                    ref=ref,
                    kind=member["kind"],
                    path=role_path,
                    start_line=member["line"],
                    end_line=member["endLine"],
                    line_text=member["lineText"],
                    snippet=member["snippet"],
                    role=role["name"],
                    name=member["name"],
                    memberType=member.get("memberType"),
                )

    perspectives_dir = definition_dir / "perspectives"
    if perspectives_dir.exists():
        for perspective_path in sorted(perspectives_dir.glob("*.tmdl")):
            perspective, members = _scan_perspective_file(perspective_path)
            if perspective is None:
                continue
            perspective_ref = f'perspective:{perspective["name"]}'
            refs[perspective_ref] = _entity_record(
                ref=perspective_ref,
                kind="perspective",
                path=perspective["path"],
                start_line=perspective["line"],
                end_line=perspective["endLine"],
                line_text=perspective["lineText"],
                snippet=perspective["snippet"],
                name=perspective["name"],
            )
            for member in members:
                if member["kind"] == "perspectiveTable":
                    ref = f'perspectiveTable:{perspective["name"]}.{member["name"]}'
                else:
                    ref = f'{member["kind"]}:{perspective["name"]}.{member["table"]}.{member["name"]}'
                refs[ref] = _entity_record(
                    ref=ref,
                    kind=member["kind"],
                    path=perspective_path,
                    start_line=member["line"],
                    end_line=member["endLine"],
                    line_text=member["lineText"],
                    snippet=member["snippet"],
                    perspective=perspective["name"],
                    table=member.get("table"),
                    name=member["name"],
                )

    return {
        "meta": {
            "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "projectRoot": str(project_root),
            "semanticModelFolder": str(sm_folder),
            "modelPath": str(model.model_path) if model.model_path else None,
            "tableCount": len(model.tables),
            "relationshipCount": len(model.relationships),
            "roleCount": len(model.roles),
            "perspectiveCount": len(model.perspectives),
            "annotationCount": len(model.annotations),
            "refCount": len(refs),
        },
        "tables": table_summaries,
        "refs": refs,
    }


def resolve_tmdl_trace_ref(trace_manifest: dict[str, Any], ref: str) -> dict[str, Any]:
    refs = trace_manifest.get("refs", {})
    if ref in refs:
        return refs[ref]

    candidates = sorted(refs)
    close = difflib.get_close_matches(ref, candidates, n=5, cutoff=0.4)
    if close:
        suggestion = ", ".join(close)
        raise ValueError(f'Reference "{ref}" not found. Did you mean: {suggestion}?')
    sample = ", ".join(candidates[:10])
    raise ValueError(f'Reference "{ref}" not found. Available: {sample}')


def format_tmdl_trace_report(trace_manifest: dict[str, Any], ref: str) -> str:
    record = resolve_tmdl_trace_ref(trace_manifest, ref)
    lines = [
        f"Ref: {record['ref']}",
        f"Kind: {record['kind']}",
        f"Path: {record['path']}",
        f"Line: {record['line']}",
        f"End line: {record['endLine']}",
    ]

    for key in ("table", "hierarchy", "role", "perspective", "name"):
        value = record.get(key)
        if value:
            lines.append(f"{key[0].upper() + key[1:]}: {value}")

    if record["kind"] == "relationship":
        lines.append(
            "Relationship: "
            f"{record.get('fromTable', '?')}.{record.get('fromColumn', '?')} -> "
            f"{record.get('toTable', '?')}.{record.get('toColumn', '?')}"
        )

    lines.extend([
        "",
        "Snippet:",
        record["snippet"],
    ])
    return "\n".join(lines)


def trace_to_json(trace_manifest: dict[str, Any]) -> str:
    return json.dumps(trace_manifest, indent=2) + "\n"
