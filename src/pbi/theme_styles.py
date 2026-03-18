"""Theme visual-style helpers and value codecs."""

from __future__ import annotations

import re
from typing import Any


THEME_PALETTE_KEYS: tuple[str, ...] = (
    "foreground",
    "foregroundDark",
    "foregroundNeutralDark",
    "foregroundNeutralSecondary",
    "foregroundNeutralSecondaryAlt",
    "foregroundNeutralSecondaryAlt2",
    "foregroundNeutralTertiary",
    "foregroundNeutralTertiaryAlt",
    "foregroundNeutralLight",
    "foregroundButton",
    "foregroundSelected",
    "background",
    "backgroundLight",
    "backgroundNeutral",
    "backgroundDark",
    "tableAccent",
    "hyperlink",
    "visitedHyperlink",
    "good",
    "neutral",
    "bad",
    "maximum",
    "center",
    "minimum",
    "null",
    "disabledText",
    "shapeFill",
    "shapeStroke",
    "sentiment.negative",
    "sentiment.neutral",
    "sentiment.positive",
    "kpiGood",
    "kpiBad",
    "kpiNeutral",
)

_STYLE_PROP_RE = re.compile(r"^([^.]+)\.([^\[]+)(?:\[([^\]]+)\])?$")
_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def parse_style_assignment(raw: str) -> tuple[str, str, str | None, str]:
    """Parse 'object.prop[selector]=value' into (object, prop, selector, value)."""
    eq = raw.find("=")
    if eq == -1:
        raise ValueError(f"Invalid assignment '{raw}'. Use object.property=value format.")
    key, value = raw[:eq], raw[eq + 1 :]

    match = _STYLE_PROP_RE.match(key)
    if not match:
        raise ValueError(f"Invalid property path '{key}'. Use object.property format.")
    return match.group(1), match.group(2), match.group(3), value


def _is_theme_color(value: str) -> bool:
    """Check if value is a hex color or a known theme palette token."""
    if value.startswith("#"):
        return True
    return value in THEME_PALETTE_KEYS


def _validate_hex_color(value: str) -> str:
    """Validate and normalize a hex color string. Returns uppercase #RRGGBB."""
    normalized = value.strip()
    if not _HEX_RE.match(normalized):
        raise ValueError(f"Invalid hex color: '{value}'. Use #RGB, #RRGGBB, or #RRGGBBAA.")
    if len(normalized) == 4:
        normalized = "#" + normalized[1] * 2 + normalized[2] * 2 + normalized[3] * 2
    return normalized.upper()


def encode_theme_style_value(value: str, schema_type: str | list[str] | None = None) -> Any:
    """Encode a CLI string into theme visualStyles JSON format."""
    if schema_type == "color" or _is_theme_color(value):
        color = _validate_hex_color(value) if value.startswith("#") else value
        return {"solid": {"color": color}}

    if schema_type == "bool":
        return value.lower() in ("true", "1", "yes", "on")
    if schema_type in ("int", "num", "fmt"):
        try:
            return float(value) if "." in value else int(value)
        except ValueError:
            return value
    if isinstance(schema_type, list):
        lower_map = {item.lower(): item for item in schema_type}
        return lower_map.get(value.lower(), value)

    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def decode_theme_style_value(raw: Any) -> Any:
    """Decode a theme visualStyles value to a human-readable form."""
    if isinstance(raw, dict) and "solid" in raw:
        return raw["solid"].get("color", raw)
    return raw


def get_visual_style_entries(data: dict, visual_type: str) -> dict[str, list[dict]] | None:
    """Return the objects dict for a visual type (unwrapping the '*' data role level)."""
    visual_styles = data.get("visualStyles", {})
    visual_type_entry = visual_styles.get(visual_type)
    if visual_type_entry is None:
        return None
    return visual_type_entry.get("*")


def list_visual_style_types(data: dict) -> list[str]:
    """Return sorted list of visual type keys in visualStyles."""
    return sorted(data.get("visualStyles", {}).keys())


def _cascade_visual_styles_colors(data: dict, color_map: dict[str, str]) -> int:
    """Replace old colors with new colors in visualStyles."""
    visual_styles = data.get("visualStyles")
    if not visual_styles or not color_map:
        return 0

    count = 0
    for roles in visual_styles.values():
        if not isinstance(roles, dict):
            continue
        for objects in roles.values():
            if not isinstance(objects, dict):
                continue
            for entries in objects.values():
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    for prop_name, value in entry.items():
                        if prop_name == "$id":
                            continue
                        if isinstance(value, dict) and "solid" in value:
                            current = value["solid"].get("color", "")
                            if isinstance(current, str):
                                replacement = color_map.get(current.upper())
                                if replacement is not None:
                                    value["solid"]["color"] = replacement
                                    count += 1
    return count


def set_visual_style_property(
    data: dict,
    visual_type: str,
    object_name: str,
    property_name: str,
    value: str,
    *,
    selector: str | None = None,
) -> None:
    """Set a property in visualStyles[visual_type]['*'][object_name]."""
    from pbi.visual_schema import get_property_type, validate_object, validate_property

    schema_type: str | list[str] | None = None
    if visual_type != "*":
        warning = validate_object(visual_type, object_name)
        if warning:
            from pbi.commands.common import console

            console.print(f"[yellow]Warning:[/yellow] {warning}")
        else:
            warning = validate_property(visual_type, object_name, property_name)
            if warning:
                from pbi.commands.common import console

                console.print(f"[yellow]Warning:[/yellow] {warning}")
        schema_type = get_property_type(visual_type, object_name, property_name)

    encoded = encode_theme_style_value(value, schema_type)

    visual_styles = data.setdefault("visualStyles", {})
    visual_type_entry = visual_styles.setdefault(visual_type, {})
    data_role = visual_type_entry.setdefault("*", {})
    entries: list[dict] = data_role.setdefault(object_name, [{}])

    target: dict | None = None
    if selector:
        for entry in entries:
            if entry.get("$id") == selector:
                target = entry
                break
        if target is None:
            target = {"$id": selector}
            entries.append(target)
    else:
        for entry in entries:
            if "$id" not in entry:
                target = entry
                break
        if target is None:
            target = entries[0]

    target[property_name] = encoded


def delete_visual_style(
    data: dict,
    visual_type: str,
    object_name: str | None = None,
) -> bool:
    """Remove a visual type entry or specific object from visualStyles."""
    visual_styles = data.get("visualStyles")
    if not visual_styles:
        return False

    if object_name is None:
        if visual_type in visual_styles:
            del visual_styles[visual_type]
            return True
        return False

    visual_type_entry = visual_styles.get(visual_type)
    if not visual_type_entry:
        return False
    data_role = visual_type_entry.get("*")
    if not data_role:
        return False
    if object_name in data_role:
        del data_role[object_name]
        if not data_role:
            del visual_type_entry["*"]
        if not visual_type_entry:
            del visual_styles[visual_type]
        return True
    return False
