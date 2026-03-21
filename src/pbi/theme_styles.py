"""Theme visual-style helpers and value codecs."""

from __future__ import annotations

import json
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
    if isinstance(raw, dict):
        return {key: decode_theme_style_value(value) for key, value in raw.items()}
    if isinstance(raw, list):
        return [decode_theme_style_value(value) for value in raw]
    return raw


def get_visual_style_entries(
    data: dict,
    visual_type: str,
    *,
    role: str = "*",
) -> dict[str, list[dict]] | None:
    """Return the objects dict for one visual type and role branch."""
    visual_styles = data.get("visualStyles", {})
    visual_type_entry = visual_styles.get(visual_type)
    if visual_type_entry is None:
        return None
    role_entry = visual_type_entry.get(role)
    if not isinstance(role_entry, dict):
        return None
    return role_entry


def list_visual_style_roles(data: dict, visual_type: str) -> list[str]:
    """Return sorted role branches for one visual type."""
    visual_styles = data.get("visualStyles", {})
    visual_type_entry = visual_styles.get(visual_type)
    if not isinstance(visual_type_entry, dict):
        return []
    return sorted(key for key, value in visual_type_entry.items() if isinstance(value, dict))


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


def parse_theme_style_value(value: str, schema_type: str | list[str] | None = None) -> Any:
    """Parse a CLI value into visualStyles JSON, allowing inline JSON for complex shapes."""
    raw = value.strip()
    if raw and raw[0] in "{[\"":
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            pass
        else:
            return _normalize_theme_style_value(parsed)
    return encode_theme_style_value(raw, schema_type)


def _normalize_theme_style_value(value: Any) -> Any:
    """Normalize inline JSON theme values for consistent storage."""
    if isinstance(value, dict):
        normalized = {key: _normalize_theme_style_value(raw) for key, raw in value.items()}
        solid = normalized.get("solid")
        if (
            isinstance(solid, dict)
            and isinstance(solid.get("color"), str)
            and solid["color"].startswith("#")
        ):
            solid["color"] = _validate_hex_color(solid["color"])
        return normalized
    if isinstance(value, list):
        return [_normalize_theme_style_value(item) for item in value]
    return value


def set_visual_style_property(
    data: dict,
    visual_type: str,
    object_name: str,
    property_name: str,
    value: str,
    *,
    selector: str | None = None,
    role: str = "*",
) -> None:
    """Set a property in visualStyles[visual_type][role][object_name]."""
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

    encoded = parse_theme_style_value(value, schema_type)

    set_visual_style_value(
        data,
        visual_type,
        object_name,
        property_name,
        encoded,
        selector=selector,
        role=role,
    )


def set_visual_style_value(
    data: dict,
    visual_type: str,
    object_name: str,
    property_name: str,
    value: Any,
    *,
    selector: str | None = None,
    role: str = "*",
) -> None:
    """Set an already-encoded value in visualStyles[visual_type][role][object_name]."""
    target = _get_or_create_visual_style_entry(
        data,
        visual_type,
        object_name,
        selector=selector,
        role=role,
    )
    target[property_name] = value


def clear_visual_style_property(
    data: dict,
    visual_type: str,
    object_name: str,
    property_name: str,
    *,
    selector: str | None = None,
    role: str = "*",
) -> bool:
    """Remove one property from visualStyles and clean up empty containers."""
    visual_styles = data.get("visualStyles")
    if not isinstance(visual_styles, dict):
        return False
    visual_type_entry = visual_styles.get(visual_type)
    if not isinstance(visual_type_entry, dict):
        return False
    role_entry = visual_type_entry.get(role)
    if not isinstance(role_entry, dict):
        return False
    entries = role_entry.get(object_name)
    if not isinstance(entries, list):
        return False

    removed = False
    to_remove: list[int] = []
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if selector is not None:
            if entry.get("$id") != selector:
                continue
        elif "$id" in entry:
            continue
        if property_name in entry:
            del entry[property_name]
            removed = True
        if not entry or tuple(entry.keys()) == ("$id",):
            to_remove.append(index)

    for index in reversed(to_remove):
        entries.pop(index)

    if not entries:
        role_entry.pop(object_name, None)
    if not role_entry:
        visual_type_entry.pop(role, None)
    if not visual_type_entry:
        visual_styles.pop(visual_type, None)
    return removed


def delete_visual_style(
    data: dict,
    visual_type: str,
    object_name: str | None = None,
    *,
    role: str | None = "*",
) -> bool:
    """Remove a visual type entry or specific object from visualStyles."""
    visual_styles = data.get("visualStyles")
    if not visual_styles:
        return False

    if object_name is None and role is None:
        if visual_type in visual_styles:
            del visual_styles[visual_type]
            return True
        return False

    visual_type_entry = visual_styles.get(visual_type)
    if not visual_type_entry:
        return False
    if object_name is None:
        data_role = visual_type_entry.get(role or "*")
        if not data_role:
            return False
        del visual_type_entry[role or "*"]
        if not visual_type_entry:
            del visual_styles[visual_type]
        return True

    data_role = visual_type_entry.get(role or "*")
    if not data_role:
        return False
    if object_name in data_role:
        del data_role[object_name]
        if not data_role:
            del visual_type_entry[role or "*"]
        if not visual_type_entry:
            del visual_styles[visual_type]
        return True
    return False


def _get_or_create_visual_style_entry(
    data: dict,
    visual_type: str,
    object_name: str,
    *,
    selector: str | None = None,
    role: str = "*",
) -> dict:
    """Return a writable entry for one visualStyles object branch."""
    visual_styles = data.setdefault("visualStyles", {})
    visual_type_entry = visual_styles.setdefault(visual_type, {})
    data_role = visual_type_entry.setdefault(role, {})
    entries: list[dict] = data_role.setdefault(object_name, [{}])

    if selector:
        for entry in entries:
            if entry.get("$id") == selector:
                return entry
        target = {"$id": selector}
        entries.append(target)
        return target

    for entry in entries:
        if "$id" not in entry:
            return entry
    return entries[0]
