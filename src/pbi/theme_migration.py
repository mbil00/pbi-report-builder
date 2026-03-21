"""Theme migration helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from pbi.project import Project


@dataclass
class ColorReplacement:
    """A color mapping from old theme to new theme."""

    old_color: str
    new_color: str
    property_path: str
    count: int = 0


@dataclass
class MigrateResult:
    """Summary of what a theme migration would change."""

    replacements: list[ColorReplacement]
    page_background_changes: int = 0

    @property
    def total_changes(self) -> int:
        return sum(replacement.count for replacement in self.replacements) + self.page_background_changes


def migrate_theme(
    project: Project,
    old_theme_path: Path,
    new_theme_path: Path,
    *,
    dry_run: bool = False,
) -> MigrateResult:
    """Migrate visual property overrides from old theme colors to new theme colors."""
    from pbi.properties import PAGE_PROPERTIES, get_property, set_property

    with open(old_theme_path, encoding="utf-8-sig") as handle:
        old_theme = json.load(handle)
    with open(new_theme_path, encoding="utf-8-sig") as handle:
        new_theme = json.load(handle)

    color_map = _build_color_map(old_theme, new_theme)
    if not color_map:
        return MigrateResult(replacements=[])

    result = MigrateResult(replacements=[])
    seen_pairs: set[tuple[str, str]] = set()
    for old_color, new_color in color_map.items():
        pair = (old_color.lower(), new_color.lower())
        if pair in seen_pairs or pair[0] == pair[1]:
            continue
        seen_pairs.add(pair)
        result.replacements.append(
            ColorReplacement(old_color=old_color, new_color=new_color, property_path="")
        )

    for page in project.get_pages():
        page_background = get_property(page.data, "background.color", PAGE_PROPERTIES)
        if isinstance(page_background, str):
            mapped = _match_color(page_background, color_map)
            if mapped:
                if not dry_run:
                    set_property(page.data, "background.color", mapped, PAGE_PROPERTIES)
                    page.save()
                result.page_background_changes += 1

        for visual in project.get_visuals(page):
            if "visualGroup" in visual.data:
                continue
            match_counts = {
                replacement.old_color: _count_visual_color_matches(visual.data, replacement.old_color)
                for replacement in result.replacements
            }
            changed = _migrate_visual_colors(visual.data, color_map, dry_run=dry_run)
            if changed and not dry_run:
                visual.save()
            for replacement in result.replacements:
                replacement.count += match_counts[replacement.old_color]

    return result


def _build_color_map(old_theme: dict, new_theme: dict) -> dict[str, str]:
    """Extract color mappings by comparing same-path values in two themes."""
    old_colors: dict[str, str] = {}
    new_colors: dict[str, str] = {}
    _extract_colors(old_theme, "", old_colors)
    _extract_colors(new_theme, "", new_colors)

    mapping: dict[str, str] = {}
    for path, old_value in old_colors.items():
        new_value = new_colors.get(path)
        if new_value and old_value.lower() != new_value.lower():
            mapping[old_value] = new_value

    return mapping


def _extract_colors(obj: object, path: str, out: dict[str, str]) -> None:
    """Recursively extract color values from a theme dict."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            _extract_colors(value, f"{path}.{key}" if path else key, out)
    elif isinstance(obj, list):
        for index, item in enumerate(obj):
            _extract_colors(item, f"{path}[{index}]", out)
    elif isinstance(obj, str) and obj.startswith("#") and len(obj) in (4, 7, 9):
        out[path] = obj


def _match_color(value: str, color_map: dict[str, str]) -> str | None:
    """Find a matching old color in the map."""
    for old_color, new_color in color_map.items():
        if old_color.lower() == value.lower():
            return new_color
    return None


def _migrate_visual_colors(
    data: dict,
    color_map: dict[str, str],
    *,
    dry_run: bool,
) -> bool:
    """Scan and replace colors in visual objects."""
    changed = False
    for objects_key in ("objects", "visualContainerObjects"):
        objects = data.get("visual", {}).get(objects_key, {})
        for entries in objects.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                properties = entry.get("properties", {})
                for prop_name, raw_value in list(properties.items()):
                    color = _extract_color_from_value(raw_value)
                    if not color:
                        continue
                    replacement = _match_color(color, color_map)
                    if not replacement:
                        continue
                    if not dry_run:
                        _replace_color_in_value(properties, prop_name, replacement)
                    changed = True
    return changed


def _extract_color_from_value(raw: object) -> str | None:
    """Extract a hex color string from a PBI encoded value."""
    if isinstance(raw, dict):
        if "solid" in raw:
            color = raw["solid"].get("color")
            if isinstance(color, str) and color.startswith("#"):
                return color
            if isinstance(color, dict):
                literal = color.get("expr", {}).get("Literal", {}).get("Value")
                if isinstance(literal, str) and literal.startswith("'#"):
                    return literal.strip("'")
    return None


def _replace_color_in_value(properties: dict, prop_name: str, new_color: str) -> None:
    """Replace a color in a PBI encoded value structure."""
    from pbi.properties import encode_pbi_value

    properties[prop_name] = encode_pbi_value(new_color, "color")


def _count_visual_color_matches(data: dict, color: str) -> int:
    """Count how many times a color appears in visual objects."""
    count = 0
    for objects_key in ("objects", "visualContainerObjects"):
        objects = data.get("visual", {}).get(objects_key, {})
        for entries in objects.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                for raw_value in entry.get("properties", {}).values():
                    color_value = _extract_color_from_value(raw_value)
                    if color_value and color_value.lower() == color.lower():
                        count += 1
    return count
