"""Runtime property helpers for PBI JSON access and mutation."""

from __future__ import annotations

import difflib
import logging
from typing import Any

from .property_catalog import PropertyDef

logger = logging.getLogger(__name__)

_PROPERTY_ALIAS_CACHE: dict[int, tuple[int, dict[str, str]]] = {}

# ── Value encoding/decoding ────────────────────────────────────────

def encode_pbi_value(value: str, value_type: str) -> Any:
    """Encode a CLI string value into PBI JSON format."""
    if value_type in ("color", "page_color"):
        color = value if value.startswith("#") else f"#{value}"
        return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{color}'"}}}}}
    elif value_type == "number":
        num = float(value)
        return {"expr": {"Literal": {"Value": f"{num}D"}}}
    elif value_type == "long":
        num = int(float(value))
        return {"expr": {"Literal": {"Value": f"{num}L"}}}
    elif value_type == "boolean":
        b = value.lower() in ("true", "1", "yes", "on")
        return {"expr": {"Literal": {"Value": str(b).lower()}}}
    elif value_type == "string":
        return {"expr": {"Literal": {"Value": f"'{value}'"}}}
    elif value_type == "enum":
        return {"expr": {"Literal": {"Value": f"'{value}'"}}}
    return value


def decode_pbi_value(raw: Any) -> Any:
    """Decode a PBI JSON value into a human-readable form."""
    if isinstance(raw, dict):
        # Color: {"solid": {"color": "#hex"}} or {"solid": {"color": {expr...}}}
        if "solid" in raw:
            color = raw["solid"].get("color", raw)
            # Recurse for page-level colors where color is an expr dict
            return decode_pbi_value(color) if isinstance(color, dict) else color
        # Expr literal: {"expr": {"Literal": {"Value": "..."}}}
        if "expr" in raw:
            literal = raw.get("expr", {}).get("Literal", {}).get("Value")
            if literal is not None:
                return _decode_literal(literal)
        return raw
    return raw


def _decode_literal(value: str) -> Any:
    """Decode a PBI literal string like '42D', 'true', or \"'text'\"."""
    if value.endswith(("D", "d", "M", "m")):
        try:
            return float(value[:-1])
        except ValueError:
            pass
    if value.endswith(("L", "l")):
        try:
            return int(value[:-1])
        except ValueError:
            pass
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    # Quoted string
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    return value


# ── Property get/set operations ────────────────────────────────────

def get_property(
    data: dict, prop_name: str, registry: dict[str, PropertyDef],
    *, measure_ref: str | None = None,
) -> Any:
    """Get a property value from a JSON structure.

    If measure_ref is given, reads from the selector-bearing entry for that
    measure instead of the default (index 0) entry.

    Supports 'chart:<object>.<prop>' prefix for reading unregistered
    visual.objects properties dynamically.
    """
    prop_name = normalize_property_name(prop_name, registry)

    # Dynamic chart property: chart:<objectKey>.<propName>
    if prop_name.startswith("chart:"):
        return _get_dynamic_chart_prop(data, prop_name)

    prop_def = registry.get(prop_name)

    if prop_def and prop_def.container_key:
        return _get_container_prop(data, prop_def, measure_ref=measure_ref)
    elif prop_def and prop_def.json_path:
        return _get_by_path(data, prop_def.json_path)
    else:
        # Raw path fallback
        return _get_by_path(data, prop_name)


def set_property(
    data: dict, prop_name: str, value: str, registry: dict[str, PropertyDef],
    *, measure_ref: str | None = None,
) -> list[str]:
    """Set a property value in a JSON structure.

    If measure_ref is given, writes to a per-measure selector entry instead
    of the default (index 0) entry. This enables per-measure formatting in
    multi-measure visuals (e.g. cardVisual accent bars).

    Supports 'chart:<object>.<prop>' prefix for writing unregistered
    visual.objects properties dynamically with auto-inferred value types.
    """
    original_name = prop_name

    # Extract bracket selector if present (e.g. "value.fontSize [Measures.X]"
    # or "value.fontSize[Measures.X]" without the space)
    # This enables per-measure formatting from YAML round-trip
    bracket_measure = measure_ref
    if bracket_measure is None and prop_name.endswith("]"):
        # Try space-separated first, then no-space
        if " [" in prop_name:
            base, selector_part = prop_name.rsplit(" [", 1)
            bracket_measure = selector_part[:-1]
            prop_name = base
        elif "[" in prop_name:
            base, selector_part = prop_name.rsplit("[", 1)
            bracket_measure = selector_part[:-1]
            prop_name = base

    prop_name = normalize_property_name(prop_name, registry)

    # Dynamic chart property: chart:<objectKey>.<propName>
    if prop_name.startswith("chart:"):
        # Re-attach bracket selector for chart: properties (they handle it internally)
        if bracket_measure is not None and measure_ref is None:
            prop_name = f"{prop_name} [{bracket_measure}]"
        return _set_dynamic_chart_prop(data, prop_name, value)

    prop_def = registry.get(prop_name)

    if prop_def and prop_def.enum_values:
        # Validate enum value
        if value not in prop_def.enum_values:
            raise ValueError(
                f'Invalid value "{value}" for {prop_name}. '
                f"Valid: {', '.join(prop_def.enum_values)}"
            )

    if prop_def and prop_def.container_key:
        _set_container_prop(data, prop_def, value, measure_ref=bracket_measure)
    elif prop_def and prop_def.json_path:
        coerced = _coerce_simple(value, prop_def.value_type)
        _set_by_path(data, prop_def.json_path, coerced)
    elif prop_def is None:
        # Auto-resolve: if it looks like object.prop and schema confirms it's valid
        # for this visual type, treat it as a chart: property transparently.
        # Use prop_name (bracket-stripped) — selector re-attachment is below.
        auto_chart = _try_auto_resolve_chart_property(data, prop_name)
        if auto_chart:
            if bracket_measure is not None and measure_ref is None:
                auto_chart = f"{auto_chart} [{bracket_measure}]"
            return _set_dynamic_chart_prop(data, auto_chart, value)

        suggestions = suggest_property_names(original_name, registry)
        hint_parts = []
        if suggestions:
            hint_parts.append(
                f'Did you mean {", ".join(f"""\"{name}\"""" for name in suggestions)}?'
            )
        chart_hint = chart_property_hint(original_name)
        if chart_hint:
            hint_parts.append(f'For a raw chart object property, try "{chart_hint}".')
        hint = f" {' '.join(hint_parts)}" if hint_parts else ""
        raise ValueError(
            f'Unknown property "{original_name}".{hint} '
            f"Use 'pbi visual props' or 'pbi page props' to see available properties, "
            f"or use 'chart:<object>.<prop>' for unregistered chart properties."
        )
    return []


def normalize_property_name(
    prop_name: str,
    registry: dict[str, PropertyDef],
) -> str:
    """Normalize aliases and raw PBIR object paths to canonical property names."""
    if prop_name.startswith("chart:") or prop_name in registry:
        return prop_name
    alias_map = _property_alias_map(registry)
    return alias_map.get(prop_name, prop_name)


def suggest_property_names(
    prop_name: str,
    registry: dict[str, PropertyDef],
    *,
    limit: int = 3,
) -> list[str]:
    """Suggest nearby canonical property names for an invalid property token."""
    alias_map = _property_alias_map(registry)
    choices = sorted(set(registry) | set(alias_map))
    suggestions: list[str] = []
    for match in difflib.get_close_matches(prop_name, choices, n=limit, cutoff=0.55):
        if match not in suggestions:
            suggestions.append(match)
    chart_prop = chart_property_hint(prop_name)
    if chart_prop:
        if chart_prop not in suggestions:
            suggestions.append(chart_prop)
        if len(suggestions) > limit:
            suggestions = suggestions[: limit - 1] + [chart_prop]
    return suggestions[:limit]


def chart_property_hint(prop_name: str) -> str | None:
    """Return the raw chart-property form for a dotted token when applicable."""
    if "." not in prop_name or prop_name.startswith("chart:"):
        return None
    return f"chart:{prop_name}"


def property_aliases_for(
    prop_name: str,
    registry: dict[str, PropertyDef],
) -> list[str]:
    """Return accepted non-canonical aliases for a property."""
    alias_map = _property_alias_map(registry)
    aliases = sorted(alias for alias, canonical in alias_map.items() if canonical == prop_name)
    return [alias for alias in aliases if alias != prop_name]


def canonical_object_property_name(
    container_key: str,
    prop_name: str,
    registry: dict[str, PropertyDef],
    *,
    objects_path: str = "visualContainerObjects",
    selector: str | None = None,
) -> str:
    """Return the canonical CLI property name for a raw object property."""
    reverse_map = _object_property_reverse_map(registry)
    key = (objects_path, container_key, prop_name, selector)
    canonical = reverse_map.get(key)
    if canonical:
        return canonical
    fallback = reverse_map.get((objects_path, container_key, prop_name, None))
    if fallback:
        return fallback
    if objects_path == "objects":
        return f"chart:{container_key}.{prop_name}"
    return f"{container_key}.{prop_name}"


def _property_alias_map(registry: dict[str, PropertyDef]) -> dict[str, str]:
    """Build a map of accepted aliases to canonical registry keys."""
    cache_key = id(registry)
    registry_size = len(registry)
    cached = _PROPERTY_ALIAS_CACHE.get(cache_key)
    if cached is not None and cached[0] == registry_size:
        return cached[1]

    aliases: dict[str, str] = {}
    for canonical, prop_def in registry.items():
        if prop_def.container_key and prop_def.container_prop:
            raw_name = f"{prop_def.container_key}.{prop_def.container_prop}"
            aliases.setdefault(raw_name, canonical)
    for source_prefix, target_prefix in (
        ("dataLabels.", "labels."),
        ("dropShadow.", "shadow."),
    ):
        for canonical in registry:
            if canonical.startswith(target_prefix):
                aliases.setdefault(source_prefix + canonical[len(target_prefix):], canonical)
    # Shorthand aliases for position properties
    for short, full in (
        ("x", "position.x"), ("y", "position.y"),
        ("width", "position.width"), ("height", "position.height"),
    ):
        if full in registry:
            aliases.setdefault(short, full)
    _PROPERTY_ALIAS_CACHE[cache_key] = (registry_size, aliases)
    return aliases


def _object_property_reverse_map(
    registry: dict[str, PropertyDef],
) -> dict[tuple[str, str, str, str | None], str]:
    """Map raw object properties back to canonical CLI property names."""
    reverse: dict[tuple[str, str, str, str | None], str] = {}
    for canonical, prop_def in registry.items():
        if not (prop_def.container_key and prop_def.container_prop):
            continue
        key = (
            prop_def.objects_path,
            prop_def.container_key,
            prop_def.container_prop,
            prop_def.selector,
        )
        reverse.setdefault(key, canonical)
    return reverse


def _find_entry(entries: list[dict], selector: str | None) -> dict | None:
    """Find an entry matching a selector in an object array.

    selector=None → entry with no selector (first selectorless entry)
    selector="default" → entry with {"id": "default"}
    """
    if selector == "default":
        for entry in entries:
            if entry.get("selector", {}).get("id") == "default":
                return entry
        return None
    # No selector → first entry without a selector key
    for entry in entries:
        if "selector" not in entry:
            return entry
    # Fallback to first entry
    return entries[0] if entries else None


def _get_container_prop(
    data: dict, prop_def: PropertyDef,
    *, measure_ref: str | None = None,
) -> Any:
    """Read from object collections (visual-level or page-level)."""
    root = data if prop_def.top_level else data.get("visual", {})
    objects = root.get(prop_def.objects_path, {})
    entries = objects.get(prop_def.container_key, [])
    if not entries:
        return None

    if measure_ref:
        for entry in entries:
            if entry.get("selector", {}).get("metadata") == measure_ref:
                raw = entry.get("properties", {}).get(prop_def.container_prop)
                return decode_pbi_value(raw) if raw is not None else None
        return None

    target = _find_entry(entries, prop_def.selector)
    if target is None:
        return None
    raw = target.get("properties", {}).get(prop_def.container_prop)
    if raw is None:
        return None
    return decode_pbi_value(raw)


def _set_container_prop(
    data: dict, prop_def: PropertyDef, value: str,
    *, measure_ref: str | None = None,
) -> None:
    """Write to object collections, creating structure as needed.

    Selector routing:
      measure_ref → entry with {"metadata": "<measure_ref>"}
      prop_def.selector="default" → entry with {"id": "default"}
      prop_def.selector=None → first selectorless entry (index 0)
    """
    root = data if prop_def.top_level else data.setdefault("visual", {})
    objects = root.setdefault(prop_def.objects_path, {})
    entries = objects.setdefault(prop_def.container_key, [])

    encoded = encode_pbi_value(value, prop_def.value_type)

    if measure_ref:
        target = None
        for entry in entries:
            if entry.get("selector", {}).get("metadata") == measure_ref:
                target = entry
                break
        if target is None:
            target = {
                "properties": {},
                "selector": {"metadata": measure_ref},
            }
            entries.append(target)
        target.setdefault("properties", {})[prop_def.container_prop] = encoded
        return

    # Use prop_def.selector to find the right entry
    target = _find_entry(entries, prop_def.selector)
    if target is None:
        # Create new entry with appropriate selector
        target = {"properties": {}}
        if prop_def.selector == "default":
            target["selector"] = {"id": "default"}
        entries.append(target)
    target.setdefault("properties", {})[prop_def.container_prop] = encoded


def _resolve_value_type(
    data: dict, obj_key: str, prop_key: str, value: str,
) -> str:
    """Determine the PBI value type using schema, falling back to inference.

    Schema type mapping:
      "bool"  → "boolean"  (encoded as true/false literal)
      "num"   → "number"   (encoded as 42D float literal)
      "int"   → "long"     (encoded as 42L integer literal)
      "color" → "color"    (encoded as solid/color/expr structure)
      "text"  → "enum"     (encoded as quoted string)
      "fmt"   → "enum"     (encoded as quoted string)
      list    → "enum"     (enum values, encoded as quoted string)
    """
    visual_type = data.get("visual", {}).get("visualType")
    if visual_type:
        try:
            from pbi.visual_schema import get_property_type

            schema_type = get_property_type(visual_type, obj_key, prop_key)
            if schema_type is not None:
                if isinstance(schema_type, list):
                    return "enum"
                mapping = {
                    "bool": "boolean",
                    "num": "number",
                    "int": "long",
                    "color": "color",
                    "text": "enum",
                    "fmt": "enum",
                    "expr": "enum",
                    "filter": "enum",
                }
                mapped = mapping.get(schema_type)
                if mapped:
                    return mapped
        except Exception:
            pass

    return _infer_value_type(value)


def _infer_value_type(value: str) -> str:
    """Infer PBI value type from a CLI string value.

    Fallback when schema type is not available.
    """
    if value.startswith("#"):
        return "color"
    if value.lower() in ("true", "false"):
        return "boolean"
    try:
        int(value)
        return "number"
    except ValueError:
        pass
    try:
        float(value)
        return "number"
    except ValueError:
        pass
    return "enum"  # Default: treat as quoted string


def _parse_chart_prefix(prop_name: str) -> tuple[str, str, str | None]:
    """Parse 'chart:<objectKey>.<propName> [selector]' or 'chart:<objectKey>.<propName>[selector]' into parts."""
    rest = prop_name[len("chart:"):]
    selector = None
    if rest.endswith("]"):
        if " [" in rest:
            rest, selector_part = rest.rsplit(" [", 1)
            selector = selector_part[:-1]
        elif "[" in rest:
            rest, selector_part = rest.rsplit("[", 1)
            selector = selector_part[:-1]
    dot = rest.find(".")
    if dot == -1:
        raise ValueError(
            f'Invalid chart property "{prop_name}". '
            f"Use chart:<object>.<prop> format (e.g. chart:legend.show)."
        )
    return rest[:dot], rest[dot + 1:], selector


def _match_chart_selector(entry: dict, selector: str | None) -> bool:
    """Return True when a chart object entry matches the selector token."""
    entry_selector = entry.get("selector", {})
    if selector is None:
        return "selector" not in entry
    if selector == "default":
        return entry_selector.get("id") == "default"
    return (
        entry_selector.get("metadata") == selector
        or entry_selector.get("id") == selector
    )


def _get_dynamic_chart_prop(data: dict, prop_name: str) -> Any:
    """Read a dynamic chart property from visual.objects."""
    obj_key, prop_key, selector = _parse_chart_prefix(prop_name)
    objects = data.get("visual", {}).get("objects", {})
    entries = objects.get(obj_key, [])
    if not entries or not isinstance(entries, list):
        return None
    target = None
    for entry in entries:
        if _match_chart_selector(entry, selector):
            target = entry
            break
    if target is None and selector is None:
        target = entries[0]
    if target is None:
        return None
    raw = target.get("properties", {}).get(prop_key)
    if raw is None:
        return None
    return decode_pbi_value(raw)


def _set_dynamic_chart_prop(data: dict, prop_name: str, value: str) -> list[str]:
    """Write a dynamic chart property to visual.objects with schema-aware encoding.

    Uses the schema to determine the correct PBI value type for encoding.
    Falls back to heuristic inference when the schema type isn't available.

    Returns a list of schema validation warning strings (may be empty).
    """
    obj_key, prop_key, selector = _parse_chart_prefix(prop_name)

    # Schema validation — warn on invalid objects/properties for this visual type
    schema_warnings = _schema_validate_chart_prop(data, obj_key, prop_key, value)

    value_type = _resolve_value_type(data, obj_key, prop_key, value)
    encoded = encode_pbi_value(value, value_type)

    objects = data.setdefault("visual", {}).setdefault("objects", {})
    entries = objects.setdefault(obj_key, [])
    target = None
    for entry in entries:
        if _match_chart_selector(entry, selector):
            target = entry
            break
    # Fallback: when no selector specified, reuse the first entry (like _find_entry)
    if target is None and selector is None and entries:
        target = entries[0]
    if target is None:
        target = {"properties": {}}
        if selector == "default":
            target["selector"] = {"id": "default"}
        elif selector is not None:
            target["selector"] = {"metadata": selector}
        entries.append(target)
    target.setdefault("properties", {})[prop_key] = encoded
    return schema_warnings


def _try_auto_resolve_chart_property(data: dict, prop_name: str) -> str | None:
    """Try to auto-resolve a dotted property name as a chart object property.

    If prop_name is "legend.show" and the visual type's schema confirms
    that "legend" is a valid object with a "show" property, returns
    "chart:legend.show" so it can be handled by the chart property path.

    Expects prop_name without bracket selectors (caller handles those).
    Returns None if the property can't be resolved from the schema.
    """
    if "." not in prop_name or prop_name.startswith("chart:"):
        return None

    dot = prop_name.find(".")
    obj_key = prop_name[:dot]
    prop_key = prop_name[dot + 1:]

    visual_type = data.get("visual", {}).get("visualType")
    if not visual_type:
        return None

    from pbi.visual_schema import get_object_names, get_property_names

    valid_objects = get_object_names(visual_type)
    if valid_objects is None or obj_key not in valid_objects:
        return None

    valid_props = get_property_names(visual_type, obj_key)
    if valid_props is None or prop_key not in valid_props:
        return None

    return f"chart:{obj_key}.{prop_key}"


def _schema_validate_chart_prop(
    data: dict, obj_key: str, prop_key: str, value: Any,
) -> list[str]:
    """Run schema validation for a chart object property write.

    Returns warning strings. Non-blocking — the write still happens.
    """
    from pbi.visual_schema import validate_chart_property

    visual_type = data.get("visual", {}).get("visualType")
    if not visual_type:
        return []
    warnings = validate_chart_property(visual_type, obj_key, prop_key, value)
    result = [
        str(w)
        for w in warnings
        if not _is_known_chart_schema_gap(visual_type, obj_key, prop_key)
    ]
    for msg in result:
        logger.warning("Schema: %s", msg)
    return result


def _is_known_chart_schema_gap(visual_type: str, obj_key: str, prop_key: str) -> bool:
    """Suppress known extractor gaps for Desktop-exported property paths."""
    if visual_type == "image" and obj_key == "image":
        return prop_key == "sourceFile.image" or prop_key.startswith("sourceFile.image.")
    if visual_type == "textbox" and obj_key in {"paragraph", "general"}:
        return prop_key == "paragraphs" or prop_key.startswith("paragraphs.")
    if visual_type == "tableEx" and ".expr.FillRule." in prop_key:
        return True
    if visual_type == "pivotTable" and ".expr.Conditional." in prop_key:
        return True
    return False


def get_visual_objects(data: dict) -> dict[str, dict[str, Any]]:
    """Introspect all current visual.objects on a visual.

    Returns {objectKey: {propName: decodedValue, ...}, ...}.
    """
    objects = data.get("visual", {}).get("objects", {})
    result: dict[str, dict[str, Any]] = {}
    for obj_key, entries in objects.items():
        if not isinstance(entries, list) or not entries:
            continue
        props: dict[str, Any] = {}
        for entry in entries:
            selector = entry.get("selector")
            entry_props = entry.get("properties", {})
            for prop_name, raw_val in entry_props.items():
                decoded = decode_pbi_value(raw_val)
                if selector:
                    # Show selector-qualified props
                    sel_id = selector.get("id", selector.get("metadata", "?"))
                    key = f"{prop_name} [{sel_id}]"
                else:
                    key = prop_name
                props[key] = decoded
        if props:
            result[obj_key] = props
    return result


def _get_by_path(data: dict, path: str) -> Any:
    """Navigate a dot-separated path into a dict."""
    current = data
    for key in path.split("."):
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return None
    return current


def _set_by_path(data: dict, path: str, value: Any) -> None:
    """Set a value at a dot-separated path, creating dicts as needed."""
    keys = path.split(".")
    current = data
    for key in keys[:-1]:
        current = current.setdefault(key, {})
    current[keys[-1]] = value


def _coerce_simple(value: str, value_type: str) -> Any:
    """Coerce a string to the appropriate Python type for direct JSON properties."""
    if value_type == "number":
        try:
            return int(value)
        except ValueError:
            return float(value)
    elif value_type == "boolean":
        return value.lower() in ("true", "1", "yes", "on")
    return value


def list_properties(
    registry: dict[str, PropertyDef],
    *,
    group: str | None = None,
    visual_type: str | None = None,
) -> list[tuple[str, str, str, str | None, tuple[str, ...] | None]]:
    """Return (name, type, description, group, enum_values) for properties.

    Filters:
      group — only properties in this group
      visual_type — only properties applicable to this visual type

    When visual_type is set, also appends schema-derived chart object
    properties that are valid for that type but not in the registry,
    so users can discover all available properties.
    """
    display_type = lambda t: "color" if t == "page_color" else t
    result = []
    registered_chart_keys: set[str] = set()
    for name, p in sorted(registry.items()):
        prop_group = _derive_group(name, p)
        if group and prop_group != group:
            continue
        if visual_type and p.visual_types and visual_type not in p.visual_types:
            continue
        result.append((
            name,
            display_type(p.value_type),
            p.description,
            prop_group,
            p.enum_values,
        ))
        # Track registered chart properties by their object.prop key
        if p.container_key and p.objects_path == "objects":
            registered_chart_keys.add(f"{p.container_key}.{p.container_prop}")

    # Append schema-derived properties not already registered
    if visual_type and (group is None or group == "chart"):
        result.extend(
            _schema_chart_properties(visual_type, registered_chart_keys)
        )

    return result


# Map compact schema types to display types
_SCHEMA_TYPE_MAP = {
    "bool": "boolean",
    "num": "number",
    "int": "number",
    "color": "color",
    "text": "string",
    "fmt": "string",
    "expr": "string",
    "any": "string",
}


def _schema_chart_properties(
    visual_type: str,
    registered_keys: set[str],
) -> list[tuple[str, str, str, str | None, tuple[str, ...] | None]]:
    """Return schema-derived chart properties not already in the registry.

    These are properties the user can set via auto-resolve (object.property
    syntax) or chart: prefix, but aren't individually registered.
    """
    try:
        from pbi.visual_schema import get_visual_schema
    except Exception:
        return []

    schema = get_visual_schema(visual_type)
    if schema is None:
        return []

    result = []
    for obj_name, props in sorted(schema["objects"].items()):
        for prop_name, ptype in sorted(props.items()):
            key = f"{obj_name}.{prop_name}"
            if key in registered_keys:
                continue  # Already registered with a friendly name

            # Determine display type and enum values
            if isinstance(ptype, list):
                display_type = "enum"
                enum_values = tuple(ptype)
            else:
                display_type = _SCHEMA_TYPE_MAP.get(ptype, "string")
                enum_values = None

            result.append((
                key,
                display_type,
                f"(schema) {obj_name}",
                "chart",
                enum_values,
            ))

    return result


def get_known_default(
    prop_name: str,
    registry: dict[str, PropertyDef],
    *,
    visual_type: str | None = None,
) -> Any:
    """Return a known default value for a property when one is registered."""
    prop_name = normalize_property_name(prop_name, registry)
    prop_def = registry.get(prop_name)
    if prop_def is None:
        return None
    if visual_type and prop_def.visual_types and visual_type not in prop_def.visual_types:
        return None
    return prop_def.default


def _derive_group(name: str, prop: PropertyDef) -> str:
    """Derive the display group for a property."""
    if prop.group:
        return prop.group
    if name.startswith("position."):
        return "position"
    if prop.objects_path == "objects" or (prop.container_key and prop.objects_path == "objects"):
        return "chart"
    if prop.container_key:
        return "container"
    return "core"
