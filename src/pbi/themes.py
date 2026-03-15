"""Theme management for PBI PBIP projects.

Handles listing, applying, and exporting Power BI report themes.
Themes are JSON files stored in StaticResources/RegisteredResources/
and referenced from report.json's themeCollection and resourcePackages.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from pbi.project import Project
from pbi.schema_refs import REPORT_SCHEMA


@dataclass
class ThemeInfo:
    """Summary of an active theme."""
    name: str
    source: str  # "SharedResources" or "RegisteredResources" or path
    is_custom: bool


def _registered_resources_dir(project: Project) -> Path:
    return project.report_folder / "StaticResources" / "RegisteredResources"


def _validate_theme_name(theme_name: str) -> str:
    """Reject theme names that would escape the resources directory."""
    if not isinstance(theme_name, str) or not theme_name.strip():
        raise ValueError("Theme name must be a non-empty file-safe name.")
    normalized = theme_name.strip()
    if normalized in {".", ".."}:
        raise ValueError("Theme name must be a non-empty file-safe name.")
    if "/" in normalized or "\\" in normalized:
        raise ValueError("Theme name may not contain path separators.")
    if Path(normalized).is_absolute():
        raise ValueError("Theme name may not be an absolute path.")
    return normalized


def _resolve_registered_resource_path(project: Project, raw_path: str) -> Path:
    """Resolve a resource path and reject escapes outside RegisteredResources."""
    resources_dir = _registered_resources_dir(project)
    candidate = Path(raw_path)
    if candidate.is_absolute():
        raise ValueError(f"Theme resource path may not be absolute: {raw_path}")
    resolved = (resources_dir.resolve() / candidate).resolve()
    base = resources_dir.resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"Theme resource path must stay within RegisteredResources: {raw_path}")
    return resolved


def _custom_theme_paths(project: Project, report: dict, theme_name: str | None = None) -> list[Path]:
    """Return confined filesystem paths for custom theme files referenced by the report."""
    paths: list[Path] = []
    resources_dir = _registered_resources_dir(project)

    if theme_name:
        try:
            safe_name = _validate_theme_name(theme_name)
        except ValueError:
            safe_name = ""
        if safe_name:
            paths.extend(
                [
                    resources_dir / f"{safe_name}.json",
                    resources_dir / "BaseThemes" / f"{safe_name}.json",
                ]
            )

    for pkg in report.get("resourcePackages", []):
        if pkg.get("name") != "RegisteredResources":
            continue
        for item in pkg.get("items", []):
            if item.get("type") != "CustomTheme":
                continue
            raw_path = item.get("path", "")
            if not isinstance(raw_path, str) or not raw_path:
                continue
            try:
                paths.append(_resolve_registered_resource_path(project, raw_path))
            except ValueError:
                continue

    deduped: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        if path not in seen:
            deduped.append(path)
            seen.add(path)
    return deduped


def get_themes(project: Project) -> list[ThemeInfo]:
    """List active themes (base + custom) from report.json."""
    report = _read_report(project)
    themes = []

    collection = report.get("themeCollection", {})

    base = collection.get("baseTheme")
    if base:
        themes.append(ThemeInfo(
            name=base.get("name", "unknown"),
            source=base.get("type", "SharedResources"),
            is_custom=False,
        ))

    custom = collection.get("customTheme")
    if custom:
        themes.append(ThemeInfo(
            name=custom.get("name", "unknown"),
            source=custom.get("type", "RegisteredResources"),
            is_custom=True,
        ))

    return themes


def apply_theme(project: Project, theme_path: Path) -> str:
    """Apply a custom theme JSON file to the project.

    Copies the theme file to RegisteredResources/ and updates report.json.
    Removes any previously applied custom theme first.
    Returns the theme name.
    """
    # Read and validate theme JSON
    with open(theme_path, encoding="utf-8-sig") as f:
        theme_data = json.load(f)

    theme_name = _validate_theme_name(theme_data.get("name", theme_path.stem))

    report = _read_report(project)
    _normalize_resource_packages(report)
    old_paths = _custom_theme_paths(
        project,
        report,
        report.get("themeCollection", {}).get("customTheme", {}).get("name"),
    )

    # Copy theme to RegisteredResources (flat, not in BaseThemes/ subdirectory)
    resources_dir = _registered_resources_dir(project)
    resources_dir.mkdir(parents=True, exist_ok=True)
    dest = resources_dir / f"{theme_name}.json"
    temp_dest = resources_dir / f".{theme_name}.json.tmp"
    shutil.copy2(theme_path, temp_dest)
    temp_dest.replace(dest)

    report.setdefault("$schema", REPORT_SCHEMA)
    report.setdefault("themeCollection", {})

    # Get reportVersionAtImport from baseTheme (must be an object, not a string)
    base_theme = report.get("themeCollection", {}).get("baseTheme", {})
    version_at_import = base_theme.get("reportVersionAtImport", {})
    if not isinstance(version_at_import, dict):
        version_at_import = {}

    # Set custom theme reference
    report["themeCollection"]["customTheme"] = {
        "name": theme_name,
        "reportVersionAtImport": version_at_import,
        "type": "RegisteredResources",
    }

    # Remove layoutOptimization if present (not in PBIR schema)
    report.pop("layoutOptimization", None)

    _remove_resource_items_by_type(report, "CustomTheme")

    # Ensure resourcePackages has the registered resources entry
    _ensure_resource_entry(report, theme_name)

    _write_report(project, report)

    for path in old_paths:
        if path == dest:
            continue
        if path.exists():
            path.unlink()

    return theme_name


def export_theme(project: Project, output_path: Path) -> str:
    """Export the active custom theme to a standalone file.

    Returns the theme name. Raises FileNotFoundError if no custom theme.
    """
    report = _read_report(project)
    custom = report.get("themeCollection", {}).get("customTheme")
    if not custom:
        raise FileNotFoundError("No custom theme applied to this project")

    theme_name = custom.get("name", "")
    theme_file = None
    for candidate in _custom_theme_paths(project, report, theme_name):
        if candidate.exists():
            theme_file = candidate
            break
    if theme_file is None or not theme_file.exists():
        raise FileNotFoundError(
            f'Theme file for "{theme_name}" not found in RegisteredResources'
        )

    shutil.copy2(theme_file, output_path)
    return theme_name


def remove_theme(project: Project) -> str | None:
    """Remove the custom theme from the project. Returns removed theme name."""
    report = _read_report(project)
    _normalize_resource_packages(report)
    report.setdefault("$schema", REPORT_SCHEMA)
    report.setdefault("themeCollection", {})
    custom = report.get("themeCollection", {}).pop("customTheme", None)
    if not custom:
        return None

    theme_name = custom.get("name", "")
    paths_to_remove = _custom_theme_paths(project, report, theme_name)

    # Remove from resourcePackages
    _remove_resource_items_by_type(report, "CustomTheme")

    # Clean up layoutOptimization if present
    report.pop("layoutOptimization", None)

    _write_report(project, report)
    for path in paths_to_remove:
        if path.exists():
            path.unlink()
    return theme_name


@dataclass
class ColorReplacement:
    """A color mapping from old theme to new theme."""
    old_color: str
    new_color: str
    property_path: str  # e.g. "visualStyles.tableEx.*.columnHeaders.backColor"
    count: int = 0  # number of visuals affected


@dataclass
class MigrateResult:
    """Summary of what a theme migration would change."""
    replacements: list[ColorReplacement]
    page_background_changes: int = 0

    @property
    def total_changes(self) -> int:
        return sum(r.count for r in self.replacements) + self.page_background_changes


def migrate_theme(
    project: Project,
    old_theme_path: Path,
    new_theme_path: Path,
    *,
    dry_run: bool = False,
) -> MigrateResult:
    """Migrate visual property overrides from old theme colors to new theme colors.

    Compares the two theme JSONs to build a color mapping, then scans all visuals
    for properties matching old colors and replaces them with new colors.
    """
    from pbi.properties import (
        PAGE_PROPERTIES,
        get_property,
        set_property,
    )

    with open(old_theme_path, encoding="utf-8-sig") as f:
        old_theme = json.load(f)
    with open(new_theme_path, encoding="utf-8-sig") as f:
        new_theme = json.load(f)

    # Build color mapping by comparing theme properties at the same paths
    color_map = _build_color_map(old_theme, new_theme)
    if not color_map:
        return MigrateResult(replacements=[])

    result = MigrateResult(replacements=[
        ColorReplacement(old_color=old, new_color=new, property_path=path)
        for (old, new), path in zip(color_map.items(), color_map.keys())
    ])
    # Rebuild as simple old→new (deduplicated)
    result.replacements = []
    seen_pairs: set[tuple[str, str]] = set()
    for old_c, new_c in color_map.items():
        pair = (old_c.lower(), new_c.lower())
        if pair not in seen_pairs and pair[0] != pair[1]:
            seen_pairs.add(pair)
            result.replacements.append(ColorReplacement(
                old_color=old_c, new_color=new_c, property_path="",
            ))

    # Scan all visuals and pages for color properties matching old values
    for page in project.get_pages():
        # Check page background color
        page_bg = get_property(page.data, "background.color", PAGE_PROPERTIES)
        if isinstance(page_bg, str):
            mapped = _match_color(page_bg, color_map)
            if mapped:
                if not dry_run:
                    set_property(page.data, "background.color", mapped, PAGE_PROPERTIES)
                    page.save()
                result.page_background_changes += 1

        # Check all visuals
        for visual in project.get_visuals(page):
            if "visualGroup" in visual.data:
                continue
            changed = _migrate_visual_colors(visual.data, color_map, dry_run=dry_run)
            if changed and not dry_run:
                visual.save()
            # Update counts on replacements
            for repl in result.replacements:
                repl.count += _count_visual_color_matches(visual.data, repl.old_color)

    return result


def _build_color_map(old_theme: dict, new_theme: dict) -> dict[str, str]:
    """Extract color mappings by comparing same-path values in two themes."""
    old_colors: dict[str, str] = {}
    new_colors: dict[str, str] = {}
    _extract_colors(old_theme, "", old_colors)
    _extract_colors(new_theme, "", new_colors)

    mapping: dict[str, str] = {}
    for path, old_val in old_colors.items():
        new_val = new_colors.get(path)
        if new_val and old_val.lower() != new_val.lower():
            mapping[old_val] = new_val

    return mapping


def _extract_colors(obj: object, path: str, out: dict[str, str]) -> None:
    """Recursively extract color values (hex strings) from a theme dict."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            _extract_colors(value, f"{path}.{key}" if path else key, out)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            _extract_colors(item, f"{path}[{i}]", out)
    elif isinstance(obj, str) and obj.startswith("#") and len(obj) in (4, 7, 9):
        out[path] = obj


def _match_color(value: str, color_map: dict[str, str]) -> str | None:
    """Find a matching old color in the map (case-insensitive)."""
    for old, new in color_map.items():
        if old.lower() == value.lower():
            return new
    return None


def _migrate_visual_colors(
    data: dict, color_map: dict[str, str], *, dry_run: bool,
) -> bool:
    """Scan and replace colors in visual objects. Returns True if changes were made."""
    changed = False
    for objects_key in ("objects", "visualContainerObjects"):
        objects = data.get("visual", {}).get(objects_key, {})
        for _obj_key, entries in objects.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                props = entry.get("properties", {})
                for prop_name, raw_value in list(props.items()):
                    color_str = _extract_color_from_value(raw_value)
                    if color_str:
                        replacement = _match_color(color_str, color_map)
                        if replacement and not dry_run:
                            _replace_color_in_value(props, prop_name, replacement)
                            changed = True
                        elif replacement:
                            changed = True
    return changed


def _extract_color_from_value(raw: object) -> str | None:
    """Extract hex color string from a PBI encoded value."""
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


def _replace_color_in_value(props: dict, prop_name: str, new_color: str) -> None:
    """Replace color in a PBI encoded value structure."""
    from pbi.properties import encode_pbi_value
    props[prop_name] = encode_pbi_value(new_color, "color")


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
                    color_str = _extract_color_from_value(raw_value)
                    if color_str and color_str.lower() == color.lower():
                        count += 1
    return count


# ── Helpers ──────────────────────────────────────────────────

def _remove_existing_custom_theme(project: Project) -> None:
    """Remove any existing custom theme file and resource entry."""
    report = _read_report(project)
    custom = report.get("themeCollection", {}).get("customTheme")
    if not custom:
        return

    theme_name = custom.get("name", "")
    paths_to_remove = _custom_theme_paths(project, report, theme_name)

    # Remove old resource entries with type CustomTheme
    _remove_resource_items_by_type(report, "CustomTheme")

    # Remove the customTheme reference
    report.get("themeCollection", {}).pop("customTheme", None)

    _write_report(project, report)
    for path in paths_to_remove:
        if path.exists():
            path.unlink()


def _delete_theme_file(project: Project, theme_name: str) -> None:
    """Delete a theme file from RegisteredResources (flat or BaseThemes/)."""
    report = _read_report(project)
    for path in _custom_theme_paths(project, report, theme_name):
        if path.exists():
            path.unlink()


def _remove_resource_items_by_type(report: dict, item_type: str) -> None:
    """Remove all resource items of the given type from RegisteredResources."""
    for pkg in report.get("resourcePackages", []):
        if pkg.get("name") == "RegisteredResources":
            items = pkg.get("items", [])
            pkg["items"] = [i for i in items if i.get("type") != item_type]


def _read_report(project: Project) -> dict:
    path = project.definition_folder / "report.json"
    if path.exists():
        return project.get_report_meta()
    return {}


def _write_report(project: Project, data: dict) -> None:
    path = project.definition_folder / "report.json"
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _ensure_resource_entry(report: dict, theme_name: str) -> None:
    """Ensure resourcePackages contains the theme file reference."""
    packages = report.setdefault("resourcePackages", [])

    # Find or create RegisteredResources package
    reg_pkg = None
    for pkg in packages:
        if pkg.get("name") == "RegisteredResources":
            reg_pkg = pkg
            break

    if reg_pkg is None:
        reg_pkg = {
            "name": "RegisteredResources",
            "type": "RegisteredResources",
            "items": [],
        }
        packages.append(reg_pkg)

    items = reg_pkg.setdefault("items", [])

    # Check if theme already registered
    for item in items:
        if item.get("name") == theme_name:
            return

    items.append({
        "type": "CustomTheme",
        "name": theme_name,
        "path": f"{theme_name}.json",
    })


def _normalize_resource_packages(report: dict) -> None:
    """Normalize legacy resourcePackages entries to the published schema shape."""
    packages = report.get("resourcePackages", [])
    normalized = []

    for pkg in packages:
        if not isinstance(pkg, dict):
            continue
        inner = pkg.get("resourcePackage", pkg)
        if not isinstance(inner, dict):
            continue

        entry = {
            "name": inner.get("name", ""),
            "type": _coerce_package_type(inner.get("type"), inner.get("name", "")),
            "items": [
                _normalize_resource_item(item)
                for item in inner.get("items", [])
                if isinstance(item, dict)
            ],
        }
        if "id" in inner:
            entry["id"] = inner["id"]
        if "disabled" in inner:
            entry["disabled"] = inner["disabled"]
        normalized.append(entry)

    if normalized != packages:
        report["resourcePackages"] = normalized


def _normalize_resource_item(item: dict) -> dict:
    entry = dict(item)
    entry["type"] = _coerce_item_type(
        item.get("type"),
        path=item.get("path", ""),
    )
    return entry


def _coerce_package_type(raw_type: object, name: str) -> str:
    if isinstance(raw_type, str):
        return raw_type
    if raw_type == 1 or name == "RegisteredResources":
        return "RegisteredResources"
    if name == "SharedResources":
        return "SharedResources"
    return "RegisteredResources"


def _coerce_item_type(raw_type: object, *, path: str) -> str:
    if isinstance(raw_type, str):
        return raw_type
    if raw_type == 202:
        return "CustomTheme"
    if path.endswith(".json"):
        return "CustomTheme"
    return "CustomTheme"
