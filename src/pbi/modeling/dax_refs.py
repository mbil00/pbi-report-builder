"""DAX expression reference scanner.

Extracts measure and column references from DAX expressions to support
dependency analysis and cascading renames.

DAX reference patterns:
  [Measure Name]          — unqualified measure reference
  Table[Column]           — qualified column reference
  'Table Name'[Column]    — quoted table + column reference

We must skip references inside string literals ("...") and line comments (// ...).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DaxRef:
    """A single reference found in a DAX expression."""

    table: str  # empty for unqualified [MeasureName]
    name: str  # the measure or column name
    start: int  # character offset in the original expression
    end: int  # character offset (exclusive)

    @property
    def qualified(self) -> bool:
        return bool(self.table)

    def __repr__(self) -> str:
        if self.table:
            return f"{self.table}[{self.name}]"
        return f"[{self.name}]"


# Regex for a quoted TMDL/DAX table name: 'Name''s Table' (doubled single quotes)
_QUOTED_TABLE = r"'(?:[^']|'')+'"
# Regex for an unquoted table name: simple identifier
_UNQUOTED_TABLE = r"[A-Za-z_]\w*"
# Regex for a column/measure name inside brackets (anything except ])
_BRACKET_NAME = r"[^\]]+"

# Combined pattern: optional Table prefix + [Name]
# Group 1: quoted table name (with quotes)
# Group 2: unquoted table name
# Group 3: bracketed name
_REF_PATTERN = re.compile(
    rf"(?:({_QUOTED_TABLE})|({_UNQUOTED_TABLE}))\s*\[({_BRACKET_NAME})\]"
    rf"|\[({_BRACKET_NAME})\]"
)

# Patterns to skip: string literals and line comments
_SKIP_PATTERN = re.compile(
    r'"(?:[^"\\]|\\.)*"'  # double-quoted string literal
    r"|//[^\n]*"  # line comment
)


def _strip_table_quotes(name: str) -> str:
    """Remove surrounding single quotes and unescape doubled quotes."""
    if name.startswith("'") and name.endswith("'"):
        return name[1:-1].replace("''", "'")
    return name


def extract_refs(expression: str) -> list[DaxRef]:
    """Extract all measure/column references from a DAX expression.

    Returns a list of DaxRef objects with table, name, and position info.
    References inside string literals and comments are excluded.
    """
    # Build a set of character ranges to skip (strings and comments)
    skip_ranges: list[tuple[int, int]] = []
    for m in _SKIP_PATTERN.finditer(expression):
        skip_ranges.append((m.start(), m.end()))

    def _in_skip(pos: int) -> bool:
        for s, e in skip_ranges:
            if s <= pos < e:
                return True
        return False

    refs: list[DaxRef] = []
    for m in _REF_PATTERN.finditer(expression):
        if _in_skip(m.start()):
            continue

        quoted_table = m.group(1)
        unquoted_table = m.group(2)
        qualified_name = m.group(3)
        unqualified_name = m.group(4)

        if unqualified_name is not None:
            refs.append(DaxRef(
                table="",
                name=unqualified_name.strip(),
                start=m.start(),
                end=m.end(),
            ))
        else:
            table = _strip_table_quotes(quoted_table) if quoted_table else (unquoted_table or "")
            refs.append(DaxRef(
                table=table,
                name=(qualified_name or "").strip(),
                start=m.start(),
                end=m.end(),
            ))

    return refs


def replace_refs(
    expression: str,
    *,
    old_table: str | None = None,
    old_name: str,
    new_name: str,
    new_table: str | None = None,
    qualified_only: bool = False,
) -> str:
    """Replace references in a DAX expression.

    Args:
        old_table: Match only refs with this table (None = match unqualified).
        old_name: The old measure/column name to find.
        new_name: The replacement name.
        new_table: If set, also rename the table part (for column renames).
        qualified_only: If True, only replace Table[Name] refs, skip [Name].
    """
    skip_ranges: list[tuple[int, int]] = []
    for m in _SKIP_PATTERN.finditer(expression):
        skip_ranges.append((m.start(), m.end()))

    def _in_skip(pos: int) -> bool:
        for s, e in skip_ranges:
            if s <= pos < e:
                return True
        return False

    replacements: list[tuple[int, int, str]] = []
    for m in _REF_PATTERN.finditer(expression):
        if _in_skip(m.start()):
            continue

        quoted_table = m.group(1)
        unquoted_table = m.group(2)
        qualified_name = m.group(3)
        unqualified_name = m.group(4)

        if unqualified_name is not None:
            # Unqualified [Name]
            if qualified_only:
                continue
            if old_table is not None:
                continue
            if unqualified_name.strip().lower() != old_name.lower():
                continue
            replacements.append((m.start(), m.end(), f"[{new_name}]"))
        else:
            # Qualified Table[Name]
            table = _strip_table_quotes(quoted_table) if quoted_table else (unquoted_table or "")
            name = (qualified_name or "").strip()

            if old_table is not None and table.lower() != old_table.lower():
                continue
            if name.lower() != old_name.lower():
                continue

            tbl = new_table if new_table is not None else table
            # Re-quote table if it needs quoting
            if re.fullmatch(r"[A-Za-z_]\w*", tbl):
                tbl_str = tbl
            else:
                tbl_str = "'" + tbl.replace("'", "''") + "'"
            replacements.append((m.start(), m.end(), f"{tbl_str}[{new_name}]"))

    if not replacements:
        return expression

    # Apply replacements from end to start to preserve offsets
    result = expression
    for start, end, replacement in reversed(replacements):
        result = result[:start] + replacement + result[end:]
    return result


def find_dependents(
    expression: str,
    target_table: str,
    target_name: str,
    *,
    is_measure: bool = False,
) -> bool:
    """Check if an expression references a specific field.

    For measures (is_measure=True), matches both [Name] and Table[Name].
    For columns, only matches Table[Name].
    """
    refs = extract_refs(expression)
    target_name_lower = target_name.lower()
    target_table_lower = target_table.lower()

    for ref in refs:
        if ref.name.lower() != target_name_lower:
            continue
        if is_measure and not ref.qualified:
            return True
        if ref.qualified and ref.table.lower() == target_table_lower:
            return True

    return False
