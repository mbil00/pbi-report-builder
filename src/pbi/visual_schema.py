"""Schema-powered validation for Power BI visual objects and properties.

Uses extracted capability data from PBI Desktop to validate that object names
and property names written to PBIR files are correct for each visual type.

Data source: schema-analysis/generated/visual-capabilities.full.json
Compact data: src/pbi/data/visual_capabilities.json
"""

from __future__ import annotations

import difflib
import json
from functools import lru_cache
from importlib import resources
from typing import Any


# ── Schema loading ──────────────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_schema() -> dict:
    """Load the compact visual capabilities schema (cached)."""
    ref = resources.files("pbi.data").joinpath("visual_capabilities.json")
    return json.loads(ref.read_text(encoding="utf-8"))


def get_visual_types() -> list[str]:
    """Return all known visual type names."""
    return list(_load_schema()["visuals"].keys())


def get_visual_schema(visual_type: str) -> dict | None:
    """Return schema for a visual type, or None if unknown."""
    return _load_schema()["visuals"].get(visual_type)


def get_object_names(visual_type: str) -> list[str] | None:
    """Return valid object names for a visual type, or None if type unknown."""
    schema = get_visual_schema(visual_type)
    if schema is None:
        return None
    return list(schema["objects"].keys())


def get_property_names(visual_type: str, object_name: str) -> list[str] | None:
    """Return valid property names for an object on a visual type.

    Returns None if visual type or object name is unknown.
    """
    schema = get_visual_schema(visual_type)
    if schema is None:
        return None
    obj = schema["objects"].get(object_name)
    if obj is None:
        return None
    return list(obj.keys())


def get_property_type(
    visual_type: str, object_name: str, property_name: str,
) -> str | list[str] | None:
    """Return the type descriptor for a property.

    Returns:
        - A string like "bool", "num", "int", "color", "text", "fmt", "any"
        - A list of strings for enum types (the allowed values)
        - None if the property is not found
    """
    schema = get_visual_schema(visual_type)
    if schema is None:
        return None
    obj = schema["objects"].get(object_name)
    if obj is None:
        return None
    return obj.get(property_name)


def get_data_roles(visual_type: str) -> dict | None:
    """Return data role definitions for a visual type.

    Returns dict of {roleName: {"displayName": str, "kind": int}} or None.
    """
    schema = get_visual_schema(visual_type)
    if schema is None:
        return None
    return schema.get("dataRoles", {})


# ── Validation ──────────────────────────────────────────────────────


class SchemaWarning:
    """A validation warning (non-fatal, for reporting)."""

    def __init__(self, message: str, suggestion: str | None = None):
        self.message = message
        self.suggestion = suggestion

    def __str__(self) -> str:
        if self.suggestion:
            return f"{self.message} {self.suggestion}"
        return self.message


def _fuzzy_suggest(name: str, candidates: list[str], n: int = 3) -> str | None:
    """Fuzzy-match a name against candidates, return suggestion string or None."""
    matches = difflib.get_close_matches(name, candidates, n=n, cutoff=0.5)
    if not matches:
        return None
    quoted = ", ".join(f'"{m}"' for m in matches)
    return f'Did you mean: {quoted}?'


def validate_object(
    visual_type: str, object_name: str,
) -> SchemaWarning | None:
    """Validate that an object name is valid for a visual type.

    Returns a SchemaWarning if invalid, None if valid or type is unknown.
    """
    valid_objects = get_object_names(visual_type)
    if valid_objects is None:
        return None  # Unknown visual type — can't validate
    if object_name in valid_objects:
        return None  # Valid

    suggestion = _fuzzy_suggest(object_name, valid_objects)
    return SchemaWarning(
        f'Object "{object_name}" is not valid for visual type "{visual_type}".',
        suggestion,
    )


def validate_property(
    visual_type: str, object_name: str, property_name: str,
) -> SchemaWarning | None:
    """Validate that a property name is valid for an object on a visual type.

    Returns a SchemaWarning if invalid, None if valid or type/object is unknown.
    """
    valid_props = get_property_names(visual_type, object_name)
    if valid_props is None:
        return None  # Unknown type or object — can't validate (object error caught elsewhere)
    if property_name in valid_props:
        return None  # Valid

    suggestion = _fuzzy_suggest(property_name, valid_props)
    return SchemaWarning(
        f'Property "{property_name}" is not valid for '
        f'"{visual_type}.{object_name}".',
        suggestion,
    )


def validate_value(
    visual_type: str,
    object_name: str,
    property_name: str,
    value: Any,
) -> SchemaWarning | None:
    """Validate a property value against its schema type.

    Returns a SchemaWarning if the value doesn't match, None if valid.
    Only validates when the type is specific enough (bool, enum).
    """
    ptype = get_property_type(visual_type, object_name, property_name)
    if ptype is None:
        return None

    # Enum validation: ptype is a list of allowed values
    if isinstance(ptype, list):
        str_value = str(value)
        # Case-insensitive match
        lower_map = {v.lower(): v for v in ptype}
        if str_value.lower() not in lower_map:
            allowed = ", ".join(f'"{v}"' for v in ptype[:10])
            suffix = f" (+{len(ptype) - 10} more)" if len(ptype) > 10 else ""
            return SchemaWarning(
                f'Value "{str_value}" is not valid for '
                f'"{object_name}.{property_name}".',
                f"Allowed: {allowed}{suffix}",
            )
        return None

    # Bool validation
    if ptype == "bool":
        if isinstance(value, bool):
            return None
        str_value = str(value).lower()
        if str_value not in ("true", "false", "yes", "no", "1", "0"):
            return SchemaWarning(
                f'Value "{value}" is not valid for bool property '
                f'"{object_name}.{property_name}".',
                'Expected: true or false.',
            )
        return None

    # Color validation
    if ptype == "color":
        str_value = str(value)
        if not str_value.startswith("#") and str_value.lower() not in ("transparent",):
            return SchemaWarning(
                f'Value "{value}" may not be a valid color for '
                f'"{object_name}.{property_name}".',
                "Expected: #RRGGBB hex color.",
            )
        return None

    return None


def validate_visual_objects(
    visual_type: str,
    objects: dict[str, list[dict]],
) -> list[SchemaWarning]:
    """Validate all objects and properties on a visual.

    Args:
        visual_type: The visual type name (e.g., "clusteredBarChart").
        objects: The visual.objects dict from a PBIR visual.json.

    Returns:
        List of SchemaWarning instances for all validation issues found.
    """
    warnings: list[SchemaWarning] = []

    for obj_name, entries in objects.items():
        # Validate object name
        obj_warning = validate_object(visual_type, obj_name)
        if obj_warning is not None:
            warnings.append(obj_warning)
            continue  # Skip property validation for unknown objects

        # Validate properties in each entry
        if not isinstance(entries, list):
            continue
        for entry in entries:
            props = entry.get("properties", {})
            for prop_name in props:
                prop_warning = validate_property(
                    visual_type, obj_name, prop_name,
                )
                if prop_warning is not None:
                    warnings.append(prop_warning)

    return warnings


def validate_chart_property(
    visual_type: str | None,
    object_name: str,
    property_name: str,
    value: Any = None,
) -> list[SchemaWarning]:
    """Validate a chart:<object>.<property> assignment.

    Called from the chart: prefix code path in properties.py.
    Returns a list of warnings (may be empty).
    """
    if visual_type is None:
        return []

    warnings: list[SchemaWarning] = []

    obj_w = validate_object(visual_type, object_name)
    if obj_w is not None:
        warnings.append(obj_w)
        return warnings  # Don't validate property if object is invalid

    prop_w = validate_property(visual_type, object_name, property_name)
    if prop_w is not None:
        warnings.append(prop_w)

    if value is not None:
        val_w = validate_value(visual_type, object_name, property_name, value)
        if val_w is not None:
            warnings.append(val_w)

    return warnings
