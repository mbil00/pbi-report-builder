"""Hierarchy-level field references: PBIR ``HierarchyLevel`` <-> YAML mapping.

Desktop binds a hierarchy level (a matrix row level, a date-hierarchy level)
as a ``HierarchyLevel`` expression rather than a ``Column``. The hierarchy is
either a model hierarchy on a table, or the hierarchy of a column's
``variation`` (the auto date/time table behind a date column):

    HierarchyLevel.Expression.Hierarchy.Expression = SourceRef
        -> Project[Portfolio Tree], level Portfolio
    HierarchyLevel.Expression.Hierarchy.Expression = PropertyVariationSource
        -> Date[Date] variation "Variation", hierarchy "Date Hierarchy", level Year

YAML writes these as a mapping, never as a dotted string, because table,
hierarchy and level names may all contain dots:

    {hierarchy: Project.Portfolio Tree, level: Portfolio}
    {column: Date.Date, variation: Variation, hierarchy: Date Hierarchy, level: Year}
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import Any, Mapping

HIERARCHY_SPEC_KEYS = frozenset({"hierarchy", "level", "column", "variation"})


@dataclass(frozen=True)
class HierarchyLevelRef:
    """One level of a model hierarchy or of a column variation's hierarchy."""

    entity: str
    hierarchy: str
    level: str
    # Set for a variation-sourced hierarchy: the date column and its variation.
    column: str | None = None
    variation: str | None = None

    @classmethod
    def from_field(cls, field: Any) -> HierarchyLevelRef | None:
        """Decode a PBIR field expression; None when it is not a HierarchyLevel."""
        if not isinstance(field, Mapping):
            return None
        node = field.get("HierarchyLevel")
        if not isinstance(node, Mapping):
            return None
        level = node.get("Level")
        hierarchy_node = node.get("Expression", {}).get("Hierarchy")
        if not isinstance(level, str) or not isinstance(hierarchy_node, Mapping):
            return None
        hierarchy = hierarchy_node.get("Hierarchy")
        source = hierarchy_node.get("Expression", {})
        if not isinstance(hierarchy, str) or not isinstance(source, Mapping):
            return None
        if "SourceRef" in source:
            entity = source["SourceRef"].get("Entity")
            if not isinstance(entity, str):
                return None
            return cls(entity, hierarchy, level)
        variation_source = source.get("PropertyVariationSource")
        if isinstance(variation_source, Mapping):
            entity = variation_source.get("Expression", {}).get("SourceRef", {}).get("Entity")
            column = variation_source.get("Property")
            variation = variation_source.get("Name")
            if all(isinstance(value, str) for value in (entity, column, variation)):
                return cls(entity, hierarchy, level, column=column, variation=variation)
        return None

    def to_field(self) -> dict[str, Any]:
        """Encode as the PBIR ``HierarchyLevel`` expression Desktop writes."""
        source: dict[str, Any] = {"SourceRef": {"Entity": self.entity}}
        if self.column is not None:
            source = {
                "PropertyVariationSource": {
                    "Expression": source,
                    "Name": self.variation,
                    "Property": self.column,
                }
            }
        return {
            "HierarchyLevel": {
                "Expression": {
                    "Hierarchy": {
                        "Expression": source,
                        "Hierarchy": self.hierarchy,
                    }
                },
                "Level": self.level,
            }
        }

    @property
    def query_ref(self) -> str:
        """The projection ``queryRef`` Desktop writes for this level."""
        if self.column is not None:
            return f"{self.entity}.{self.column}.{self.variation}.{self.hierarchy}.{self.level}"
        return f"{self.entity}.{self.hierarchy}.{self.level}"

    @property
    def native_query_ref(self) -> str:
        """The projection ``nativeQueryRef`` Desktop writes for this level."""
        owner = self.column if self.column is not None else self.hierarchy
        return f"{owner} {self.level}"

    def to_spec(self) -> dict[str, str]:
        """Encode as the YAML mapping used by export and apply."""
        if self.column is not None:
            return {
                "column": f"{self.entity}.{self.column}",
                "variation": str(self.variation),
                "hierarchy": self.hierarchy,
                "level": self.level,
            }
        return {"hierarchy": f"{self.entity}.{self.hierarchy}", "level": self.level}

    def matches(self, other: HierarchyLevelRef) -> bool:
        """Case-insensitive equality, the way the model resolves names."""
        return _casefold(self) == _casefold(other)


def _casefold(ref: HierarchyLevelRef) -> tuple[str | None, ...]:
    return tuple(
        value.lower() if isinstance(value, str) else value
        for value in (ref.entity, ref.hierarchy, ref.level, ref.column, ref.variation)
    )


def is_hierarchy_spec(value: Any) -> bool:
    """Return True for a YAML hierarchy-level mapping (it has a ``level`` key)."""
    return isinstance(value, Mapping) and "level" in value


def parse_hierarchy_spec(
    spec: Mapping[str, Any],
    model: Any = None,
) -> tuple[HierarchyLevelRef, str | None]:
    """Parse and, given a model, validate a YAML hierarchy-level mapping.

    Returns the reference with the model's canonical names and the data type
    of the level's column (None without a model).
    """
    unknown = sorted(set(spec) - HIERARCHY_SPEC_KEYS)
    if unknown:
        raise ValueError(
            f"unknown hierarchy-level key(s) {', '.join(unknown)}; "
            f"use {', '.join(sorted(HIERARCHY_SPEC_KEYS))}"
        )
    level = _required_text(spec, "level")
    hierarchy = _required_text(spec, "hierarchy")
    column_ref = spec.get("column")
    variation = spec.get("variation")

    if column_ref is None:
        if variation is not None:
            raise ValueError("a hierarchy level with 'variation' also needs 'column' (Table.Column)")
        return _resolve_table_hierarchy(hierarchy, level, model)

    column_ref = _required_text(spec, "column")
    variation = _required_text(spec, "variation")
    return _resolve_variation_hierarchy(column_ref, variation, hierarchy, level, model)


def _required_text(spec: Mapping[str, Any], key: str) -> str:
    value = spec.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"hierarchy level needs a non-empty '{key}'")
    return value.strip()


def _resolve_table_hierarchy(
    ref: str,
    level: str,
    model: Any,
) -> tuple[HierarchyLevelRef, str | None]:
    """Resolve ``Table.Hierarchy`` and a level name against the model."""
    if "." not in ref:
        raise ValueError(f'hierarchy "{ref}" must be Table.Hierarchy')
    if model is None:
        entity, _, hierarchy = ref.partition(".")
        return HierarchyLevelRef(entity, hierarchy, level), None

    table, hierarchy_obj = _split_table_member(
        model, ref, lambda table, name: table.find_hierarchy(name)
    )
    level_obj = _find_level(hierarchy_obj, level)
    return (
        HierarchyLevelRef(table.name, hierarchy_obj.name, level_obj.name),
        _column_data_type(table, level_obj.column),
    )


def _resolve_variation_hierarchy(
    column_ref: str,
    variation: str,
    hierarchy: str,
    level: str,
    model: Any,
) -> tuple[HierarchyLevelRef, str | None]:
    """Resolve a column variation's hierarchy level against the model."""
    if model is None:
        if "." not in column_ref:
            raise ValueError(f'column "{column_ref}" must be Table.Column')
        entity, _, column = column_ref.partition(".")
        return HierarchyLevelRef(entity, hierarchy, level, column=column, variation=variation), None

    if "." not in column_ref:
        raise ValueError(f'column "{column_ref}" must be Table.Column')
    table, column_obj = _split_table_member(
        model, column_ref, lambda table, name: table.find_column(name)
    )
    entity, column = table.name, column_obj.name
    variation_obj = _find_named(
        column_obj.variations,
        variation,
        kind="Variation",
        owner=f'column "{entity}.{column}"',
    )
    if not variation_obj.default_hierarchy_table:
        # Without a default hierarchy the target table is unknown; keep the
        # names as written.
        ref = HierarchyLevelRef(entity, hierarchy, level, column=column, variation=variation_obj.name)
        return ref, None

    target = model.find_table(variation_obj.default_hierarchy_table)
    hierarchy_obj = target.find_hierarchy(hierarchy)
    level_obj = _find_level(hierarchy_obj, level)
    ref = HierarchyLevelRef(
        entity,
        hierarchy_obj.name,
        level_obj.name,
        column=column,
        variation=variation_obj.name,
    )
    return ref, _column_data_type(target, level_obj.column)


def _split_table_member(model: Any, ref: str, find_member: Any) -> tuple[Any, Any]:
    """Resolve ``Table.Member`` where the table name may contain dots.

    Takes the first dot split that names an existing table and member; when
    none does, resolves at the first dot so the error names what is missing.
    """
    for index, char in enumerate(ref):
        if char != ".":
            continue
        try:
            table = model.find_table(ref[:index])
            return table, find_member(table, ref[index + 1 :])
        except ValueError:
            continue
    entity, _, member = ref.partition(".")
    table = model.find_table(entity)
    return table, find_member(table, member)


def _find_level(hierarchy: Any, name: str) -> Any:
    return _find_named(
        hierarchy.levels,
        name,
        kind="Level",
        owner=f'hierarchy "{hierarchy.name}"',
    )


def _find_named(items: list[Any], name: str, *, kind: str, owner: str) -> Any:
    """Find an item by case-insensitive name, with the CLI's suggestion format."""
    for item in items:
        if item.name.lower() == name.lower():
            return item
    names = [item.name for item in items]
    close = difflib.get_close_matches(name, names, n=3, cutoff=0.5)
    if close:
        suggestion = ", ".join(f'"{n}"' for n in close)
        raise ValueError(f'{kind} "{name}" not found in {owner}. Did you mean: {suggestion}?')
    available = ", ".join(f'"{n}"' for n in names) or "(none)"
    raise ValueError(f'{kind} "{name}" not found in {owner}. Available: {available}')


def _column_data_type(table: Any, column_name: str) -> str | None:
    for column in table.columns:
        if column.name.lower() == column_name.lower():
            return column.data_type
    return None
