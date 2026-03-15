"""TMDL parsing helpers for semantic-model metadata."""

from __future__ import annotations

from pathlib import Path

from .schema import Column, Measure, SemanticTable


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
    columns: list[Column] = []
    measures: list[Measure] = []

    current_type: str | None = None
    current_name = ""
    current_props: dict[str, str] = {}
    current_expr = ""

    def _flush() -> None:
        nonlocal current_type, current_name, current_props, current_expr
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
                )
            )
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
            if stripped.startswith(("partition ", "hierarchy ", "annotation ")):
                _flush()
                current_type = None
                continue

        if current_type and indent >= 2:
            if stripped == "isHidden":
                current_props["isHidden"] = "true"
            elif ":" in stripped and not stripped.startswith("```"):
                key, _, val = stripped.partition(":")
                current_props[key.strip()] = val.strip()
            elif current_type == "measure" or (
                current_type == "column" and current_props.get("__kind") == "calculatedColumn"
            ):
                current_expr += "\n" + stripped

    _flush()

    if table_name is None:
        return None

    return SemanticTable(name=table_name, columns=columns, measures=measures, definition_path=path)
