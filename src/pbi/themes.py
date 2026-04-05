"""Theme management for PBI PBIP projects.

Handles listing, applying, exporting, creating, and editing Power BI report themes.
Themes are JSON files stored in StaticResources/RegisteredResources/
and referenced from report.json's themeCollection and resourcePackages.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pbi.project import Project
from pbi.report_io import read_report_json, write_report_json
from pbi.resources import (
    add_or_update_resource_item,
    get_or_create_resource_package,
    normalize_resource_item,
    normalize_resource_packages,
)
from pbi.schema_refs import REPORT_SCHEMA
from pbi.theme_audit import (
    ThemeAuditResult,
    ThemeOverrideEntry,
    _build_theme_defaults,
    _lookup_theme_default,
    audit_theme_overrides_from_data,
    fix_theme_overrides,
)
from pbi.theme_migration import ColorReplacement, MigrateResult, migrate_theme
from pbi.theme_styles import (
    THEME_PALETTE_KEYS,
    _cascade_visual_styles_colors,
    _validate_hex_color,
    clear_visual_style_property,
    decode_theme_style_value,
    delete_visual_style,
    encode_theme_style_value,
    get_visual_style_entries,
    list_visual_style_roles,
    list_visual_style_types,
    parse_style_assignment,
    set_visual_style_property,
    set_visual_style_value,
)


# ── Cascade rules (PBI Desktop JS) ──────────────────────────────────────

THEME_CASCADE: dict[str, list[str]] = {
    "foreground": [
        "foregroundDark",
        "foregroundNeutralDark",
        "foregroundSelected",
        "backgroundDark",
    ],
    "foregroundNeutralSecondary": [
        "foregroundNeutralSecondaryAlt",
        "foregroundNeutralSecondaryAlt2",
        "foregroundButton",
    ],
    "backgroundLight": [
        "foregroundNeutralLight",
    ],
    "foregroundNeutralTertiary": [
        "disabledText",
    ],
    "backgroundNeutral": [
        "foregroundNeutralTertiaryAlt",
    ],
}


# ── Default text classes ─────────────────────────────────────────────────

DEFAULT_TEXT_CLASSES: dict[str, dict[str, Any]] = {
    "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": "#252423"},
    "header": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": "#252423"},
    "callout": {"fontSize": 24, "fontFace": "DIN", "color": "#252423"},
    "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": "#252423"},
}


# ── Writable theme properties (for `theme properties`) ──────────────────

THEME_PROPERTIES: list[tuple[str, str, str]] = [
    # (dot_path, type, description)
    ("foreground", "color", "Primary text color"),
    ("foregroundNeutralSecondary", "color", "Secondary text color"),
    ("foregroundNeutralTertiary", "color", "Tertiary/muted text color"),
    ("background", "color", "Page background color"),
    ("backgroundLight", "color", "Light background (cards, wells)"),
    ("backgroundNeutral", "color", "Neutral background"),
    ("tableAccent", "color", "Accent color (table headers, highlights)"),
    ("hyperlink", "color", "Hyperlink color"),
    ("visitedHyperlink", "color", "Visited hyperlink color"),
    ("good", "color", "Positive/good sentiment color"),
    ("neutral", "color", "Neutral sentiment color"),
    ("bad", "color", "Negative/bad sentiment color"),
    ("maximum", "color", "Maximum value color (conditional formatting)"),
    ("center", "color", "Center value color (conditional formatting)"),
    ("minimum", "color", "Minimum value color (conditional formatting)"),
    ("null", "color", "Null value color"),
    ("dataColors", "color[]", "Comma-separated data series colors"),
    ("textClasses.title.fontSize", "number", "Title font size"),
    ("textClasses.title.fontFace", "string", "Title font face"),
    ("textClasses.title.color", "color", "Title text color"),
    ("textClasses.header.fontSize", "number", "Header font size"),
    ("textClasses.header.fontFace", "string", "Header font face"),
    ("textClasses.header.color", "color", "Header text color"),
    ("textClasses.callout.fontSize", "number", "Callout font size"),
    ("textClasses.callout.fontFace", "string", "Callout font face"),
    ("textClasses.callout.color", "color", "Callout text color"),
    ("textClasses.label.fontSize", "number", "Label font size"),
    ("textClasses.label.fontFace", "string", "Label font face"),
    ("textClasses.label.color", "color", "Label text color"),
]


# ── Theme preset storage (project + global scope) ───────────────────────

@dataclass(frozen=True)
class ThemePreset:
    """A saved theme preset."""

    name: str
    path: Path
    data: dict[str, Any] = field(default_factory=dict)
    description: str | None = None
    scope: str = "project"  # "project" or "global"


@dataclass(frozen=True)
class ThemePropertyChange:
    prop: str
    old: Any
    new: Any
    changed: bool
    cascaded_keys: list[str] = field(default_factory=list)


def _global_themes_dir() -> Path:
    """Return the global themes directory (~/.config/pbi/themes/)."""
    return Path.home() / ".config" / "pbi" / "themes"


def _themes_dir(project: Project) -> Path:
    return project.root / ".pbi-themes"


def _validate_preset_name(name: str) -> str:
    if not name or name in {".", ".."}:
        raise ValueError("Theme preset name must be a non-empty file-safe name.")
    if "/" in name or "\\" in name:
        raise ValueError("Theme preset name may not contain path separators.")
    if Path(name).is_absolute():
        raise ValueError("Theme preset name may not be an absolute path.")
    return name


def _theme_preset_path(project: Project, name: str) -> Path:
    safe = _validate_preset_name(name)
    return _themes_dir(project) / f"{safe}.yaml"


def _load_theme_preset(path: Path, name: str, *, scope: str = "project") -> ThemePreset:
    """Load and validate a theme preset from a YAML file."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as e:
        raise ValueError(f'Theme preset "{name}" is not valid YAML: {e}') from e

    if not isinstance(raw, dict):
        raise ValueError(f'Theme preset "{name}" must be a YAML mapping.')

    preset_name = raw.get("name", name)
    if not isinstance(preset_name, str) or not preset_name.strip():
        raise ValueError(f'Theme preset "{name}" must have a non-empty string name.')

    description = raw.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError(f'Theme preset "{name}" description must be a string.')

    theme_data = raw.get("theme")
    if not isinstance(theme_data, dict) or not theme_data:
        raise ValueError(f'Theme preset "{name}" must define a non-empty theme mapping.')

    return ThemePreset(
        name=_validate_preset_name(preset_name),
        path=path,
        data=theme_data,
        description=description,
        scope=scope,
    )


def save_theme_preset(
    project: Project | None,
    name: str,
    theme_data: dict[str, Any],
    *,
    description: str | None = None,
    overwrite: bool = False,
    global_scope: bool = False,
) -> Path:
    """Save a theme preset to .pbi-themes/ or ~/.config/pbi/themes/."""
    if not theme_data:
        raise ValueError("Theme data must be non-empty.")

    if global_scope:
        path = _global_themes_dir() / f"{_validate_preset_name(name)}.yaml"
    else:
        if project is None:
            raise ValueError("Project is required for project-scoped theme presets.")
        path = _theme_preset_path(project, name)

    if path.exists() and not overwrite:
        raise FileExistsError(
            f'Theme preset "{name}" already exists. Use --force to replace it.'
        )

    payload: dict[str, Any] = {"name": _validate_preset_name(name)}
    if description:
        payload["description"] = description
    payload["theme"] = theme_data

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    return path


def get_theme_preset(
    project: Project | None,
    name: str,
    *,
    global_scope: bool = False,
) -> ThemePreset:
    """Load one saved theme preset. Resolution: project → global fallback."""
    if global_scope:
        path = _global_themes_dir() / f"{_validate_preset_name(name)}.yaml"
        if not path.exists():
            raise FileNotFoundError(f'Global theme preset "{name}" not found')
        return _load_theme_preset(path, name, scope="global")

    # Try project first, then global fallback
    if project is not None:
        path = _theme_preset_path(project, name)
        if path.exists():
            return _load_theme_preset(path, name, scope="project")

    global_path = _global_themes_dir() / f"{_validate_preset_name(name)}.yaml"
    if global_path.exists():
        return _load_theme_preset(global_path, name, scope="global")

    raise FileNotFoundError(f'Theme preset "{name}" not found')


def list_theme_presets(
    project: Project | None,
    *,
    global_scope: bool = False,
) -> list[ThemePreset]:
    """List saved theme presets. Merges project + global unless scoped."""
    presets: list[ThemePreset] = []
    seen_names: set[str] = set()

    if not global_scope and project is not None:
        themes_dir = _themes_dir(project)
        if themes_dir.exists():
            for path in sorted(themes_dir.glob("*.yaml")):
                try:
                    preset = _load_theme_preset(path, path.stem, scope="project")
                    presets.append(preset)
                    seen_names.add(preset.name)
                except (FileNotFoundError, ValueError):
                    continue

    global_dir = _global_themes_dir()
    if global_dir.exists():
        for path in sorted(global_dir.glob("*.yaml")):
            try:
                preset = _load_theme_preset(path, path.stem, scope="global")
                if preset.name not in seen_names:
                    presets.append(preset)
                    seen_names.add(preset.name)
            except (FileNotFoundError, ValueError):
                continue

    return presets


def delete_theme_preset(
    project: Project | None,
    name: str,
    *,
    global_scope: bool = False,
) -> bool:
    """Delete a saved theme preset. Returns True if deleted."""
    if global_scope:
        path = _global_themes_dir() / f"{_validate_preset_name(name)}.yaml"
    else:
        if project is None:
            raise ValueError("Project is required for project-scoped theme presets.")
        path = _theme_preset_path(project, name)
    if not path.exists():
        return False
    path.unlink()
    return True


def clone_theme_preset(
    project: Project,
    name: str,
    *,
    to_global: bool = False,
    new_name: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Clone a theme preset between project and global scope."""
    target_name = new_name or name

    if to_global:
        source = get_theme_preset(project, name, global_scope=False)
        if source.scope != "project":
            path = _theme_preset_path(project, name)
            if not path.exists():
                raise FileNotFoundError(f'Project theme preset "{name}" not found')
            source = _load_theme_preset(path, name, scope="project")
        return save_theme_preset(
            None, target_name, source.data,
            description=source.description, overwrite=overwrite,
            global_scope=True,
        )
    else:
        source = get_theme_preset(project, name, global_scope=True)
        return save_theme_preset(
            project, target_name, source.data,
            description=source.description, overwrite=overwrite,
            global_scope=False,
        )


def dump_theme_preset(preset: ThemePreset) -> str:
    """Serialize a theme preset as YAML for CLI display."""
    payload: dict[str, Any] = {"name": preset.name}
    if preset.description:
        payload["description"] = preset.description
    payload["theme"] = preset.data
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120)


def get_theme_data(project: Project) -> dict:
    """Load the active custom theme JSON. Raises FileNotFoundError if none."""
    report = _read_report(project)
    custom = report.get("themeCollection", {}).get("customTheme")
    if not custom:
        raise FileNotFoundError("No custom theme applied to this project")

    theme_name = custom.get("name", "")
    for candidate in _custom_theme_paths(project, report, theme_name):
        if candidate.exists():
            with open(candidate, encoding="utf-8-sig") as f:
                return json.load(f)

    raise FileNotFoundError(
        f'Theme file for "{theme_name}" not found in RegisteredResources'
    )


def save_theme_data(project: Project, data: dict) -> None:
    """Write modified theme JSON back to the active custom theme file."""
    report = _read_report(project)
    custom = report.get("themeCollection", {}).get("customTheme")
    if not custom:
        raise FileNotFoundError("No custom theme applied to this project")

    theme_name = custom.get("name", "")

    # Repair resource path if .json extension is missing (BUG-031)
    if _fix_theme_resource_path(report, theme_name):
        _write_report(project, report)

    for candidate in _custom_theme_paths(project, report, theme_name):
        if candidate.exists():
            with open(candidate, "w", encoding="utf-8", newline="\r\n") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            return

    raise FileNotFoundError(
        f'Theme file for "{theme_name}" not found in RegisteredResources'
    )


def get_theme_property(data: dict, prop_path: str) -> Any:
    """Read a value from theme JSON using dot-path traversal."""
    parts = prop_path.split(".")
    current: Any = data
    for part in parts:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def set_theme_property(
    data: dict,
    prop_path: str,
    value: str,
    *,
    cascade: bool = True,
) -> list[str]:
    """Set a theme property value with optional cascade. Returns list of all keys set."""
    changed: list[str] = []

    # Special handling for dataColors (comma-separated hex list)
    if prop_path == "dataColors":
        colors = [_validate_hex_color(c.strip()) for c in value.split(",")]
        data["dataColors"] = colors
        changed.append("dataColors")
        return changed

    # Determine type from THEME_PROPERTIES
    prop_type = "string"
    for p_path, p_type, _desc in THEME_PROPERTIES:
        if p_path == prop_path:
            prop_type = p_type
            break

    coerced = _coerce_theme_value(value, prop_type)

    # Build color mapping for visualStyles cascade (old → new)
    color_map: dict[str, str] = {}
    if cascade and prop_type == "color" and isinstance(coerced, str):
        old_val = get_theme_property(data, prop_path)
        if isinstance(old_val, str) and old_val.upper() != coerced.upper():
            color_map[old_val.upper()] = coerced

    # Set the value using dot-path
    _set_nested(data, prop_path, coerced)
    changed.append(prop_path)

    # Apply cascade if the key is a cascade source
    if cascade:
        # Get the top-level key for cascade lookup
        top_key = prop_path.split(".")[0]
        for derived in THEME_CASCADE.get(top_key, []):
            # Only cascade if we're setting the top-level key directly
            if prop_path == top_key:
                # Capture old derived value for visualStyles cascade
                if prop_type == "color" and isinstance(coerced, str):
                    old_derived = data.get(derived)
                    if isinstance(old_derived, str) and old_derived.upper() != coerced.upper():
                        color_map[old_derived.upper()] = coerced
                _set_nested(data, derived, coerced)
                changed.append(derived)

    # Cascade color changes to visualStyles
    if color_map:
        vs_count = _cascade_visual_styles_colors(data, color_map)
        if vs_count:
            changed.append(f"visualStyles ({vs_count} properties)")

    return changed


def create_theme(
    name: str,
    *,
    foreground: str = "#252423",
    background: str = "#FFFFFF",
    accent: str = "#118DFF",
    font: str | None = None,
    data_colors: list[str] | None = None,
    good: str | None = None,
    bad: str | None = None,
    neutral: str | None = None,
) -> dict:
    """Scaffold a complete theme dict from brand colors."""
    fg = _validate_hex_color(foreground)
    bg = _validate_hex_color(background)
    ac = _validate_hex_color(accent)

    theme: dict[str, Any] = {"name": name}

    # Data colors
    if data_colors:
        theme["dataColors"] = [_validate_hex_color(c) for c in data_colors]
    else:
        theme["dataColors"] = [ac]

    # Core palette
    theme["foreground"] = fg
    theme["foregroundNeutralSecondary"] = _blend(fg, bg, 0.6)
    theme["foregroundNeutralTertiary"] = _blend(fg, bg, 0.3)
    theme["background"] = bg
    theme["backgroundLight"] = _blend(bg, fg, 0.95)
    theme["backgroundNeutral"] = _blend(bg, fg, 0.78)
    theme["tableAccent"] = ac

    # Cascade derived colors
    theme["foregroundDark"] = fg
    theme["foregroundNeutralDark"] = fg
    theme["foregroundSelected"] = fg
    theme["backgroundDark"] = fg
    theme["foregroundNeutralSecondaryAlt"] = theme["foregroundNeutralSecondary"]
    theme["foregroundNeutralSecondaryAlt2"] = theme["foregroundNeutralSecondary"]
    theme["foregroundButton"] = theme["foregroundNeutralSecondary"]
    theme["foregroundNeutralLight"] = theme["backgroundLight"]
    theme["disabledText"] = theme["foregroundNeutralTertiary"]
    theme["foregroundNeutralTertiaryAlt"] = theme["backgroundNeutral"]

    # Sentiment & conditional formatting
    theme["good"] = _validate_hex_color(good) if good else "#1AAB40"
    theme["neutral"] = _validate_hex_color(neutral) if neutral else "#D9B300"
    theme["bad"] = _validate_hex_color(bad) if bad else "#D64554"
    theme["maximum"] = ac
    theme["center"] = theme["neutral"]
    theme["minimum"] = _blend(ac, bg, 0.13)
    theme["null"] = "#FF7F48"

    # Hyperlinks
    theme["hyperlink"] = ac
    theme["visitedHyperlink"] = ac

    # Text classes
    base_font = font or "Segoe UI"
    theme["textClasses"] = {
        "title": {"fontSize": 12, "fontFace": f"{base_font} Semibold" if font else "Segoe UI Semibold", "color": fg},
        "header": {"fontSize": 12, "fontFace": f"{base_font} Semibold" if font else "Segoe UI Semibold", "color": fg},
        "callout": {"fontSize": 24, "fontFace": base_font if font else "DIN", "color": fg},
        "label": {"fontSize": 10, "fontFace": base_font, "color": fg},
    }

    return theme


# ── Internal helpers for theme authoring ─────────────────────────────────

def _coerce_theme_value(value: str, prop_type: str) -> Any:
    """Coerce a string value to the appropriate type for theme JSON."""
    if prop_type == "color":
        return _validate_hex_color(value)
    if prop_type == "number":
        try:
            return int(value)
        except ValueError:
            return float(value)
    return value


def _set_nested(data: dict, dot_path: str, value: Any) -> None:
    """Set a value in a nested dict using dot-path notation."""
    parts = dot_path.split(".")
    current = data
    for part in parts[:-1]:
        if part not in current or not isinstance(current[part], dict):
            current[part] = {}
        current = current[part]
    current[parts[-1]] = value


def _blend(color1: str, color2: str, ratio: float) -> str:
    """Blend two hex colors. ratio=1.0 → all color1, ratio=0.0 → all color2."""
    c1 = _hex_to_rgb(color1)
    c2 = _hex_to_rgb(color2)
    r = int(c1[0] * ratio + c2[0] * (1 - ratio))
    g = int(c1[1] * ratio + c2[1] * (1 - ratio))
    b = int(c1[2] * ratio + c2[2] * (1 - ratio))
    return f"#{min(r, 255):02X}{min(g, 255):02X}{min(b, 255):02X}"


def _hex_to_rgb(color: str) -> tuple[int, int, int]:
    """Parse #RRGGBB to (r, g, b)."""
    c = color.lstrip("#")
    if len(c) == 3:
        c = c[0] * 2 + c[1] * 2 + c[2] * 2
    # For #RRGGBBAA, just take the RGB part
    return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))


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


def _theme_filename(theme_name: str) -> str:
    """Return the registered theme filename stored in report metadata."""
    validated = _validate_theme_name(theme_name)
    return validated if validated.endswith(".json") else f"{validated}.json"


def _theme_display_name(theme_name: str) -> str:
    """Return the logical theme name without the registered file suffix."""
    validated = _validate_theme_name(theme_name)
    return validated[:-5] if validated.endswith(".json") else validated


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
            filename = _theme_filename(theme_name)
            stem = _theme_display_name(theme_name)
        except ValueError:
            filename = ""
            stem = ""
        if filename:
            paths.extend(
                [
                    resources_dir / filename,
                    resources_dir / "BaseThemes" / filename,
                ]
            )
        if stem and stem != filename:
            paths.extend(
                [
                    resources_dir / f"{stem}.json",
                    resources_dir / "BaseThemes" / f"{stem}.json",
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
            name=_theme_display_name(custom.get("name", "unknown")),
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
    with open(theme_path, encoding="utf-8-sig") as f:
        theme_data = json.load(f)

    theme_name = _validate_theme_name(theme_data.get("name", theme_path.stem))
    theme_filename = _theme_filename(theme_name)

    report = _read_report(project)
    _normalize_resource_packages(report)
    old_paths = _custom_theme_paths(
        project,
        report,
        report.get("themeCollection", {}).get("customTheme", {}).get("name"),
    )

    resources_dir = _registered_resources_dir(project)
    resources_dir.mkdir(parents=True, exist_ok=True)
    dest = resources_dir / theme_filename
    temp_dest = resources_dir / f".{theme_filename}.tmp"
    shutil.copy2(theme_path, temp_dest)
    temp_dest.replace(dest)

    report.setdefault("$schema", REPORT_SCHEMA)
    report.setdefault("themeCollection", {})

    base_theme = report.get("themeCollection", {}).get("baseTheme", {})
    version_at_import = base_theme.get("reportVersionAtImport", {})
    if not isinstance(version_at_import, dict):
        version_at_import = {}

    report["themeCollection"]["customTheme"] = {
        "name": theme_filename,
        "reportVersionAtImport": version_at_import,
        "type": "RegisteredResources",
    }

    report.pop("layoutOptimization", None)
    _remove_resource_items_by_type(report, "CustomTheme")
    _ensure_resource_entry(report, theme_name)
    _write_report(project, report)

    for path in old_paths:
        if path == dest:
            continue
        if path.exists():
            path.unlink()

    return _theme_display_name(theme_name)


def apply_theme_data(project: Project, theme_data: dict[str, Any]) -> str:
    """Apply theme JSON data directly to the project."""
    theme_name = _validate_theme_name(theme_data.get("name", "Theme"))
    theme_filename = _theme_filename(theme_name)

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
    dest = resources_dir / theme_filename
    temp_dest = resources_dir / f".{theme_filename}.tmp"
    with open(temp_dest, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(theme_data, f, indent=2, ensure_ascii=False)
        f.write("\n")
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
        "name": theme_filename,
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

    return _theme_display_name(theme_name)


def create_and_apply_theme(
    project: Project,
    name: str,
    *,
    foreground: str = "#252423",
    background: str = "#FFFFFF",
    accent: str = "#118DFF",
    font: str | None = None,
    data_colors: list[str] | None = None,
    good: str | None = None,
    bad: str | None = None,
    neutral: str | None = None,
) -> str:
    """Create theme data from brand colors and apply it to the project."""
    theme_data = create_theme(
        name,
        foreground=foreground,
        background=background,
        accent=accent,
        font=font,
        data_colors=data_colors,
        good=good,
        bad=bad,
        neutral=neutral,
    )
    return apply_theme_data(project, theme_data)


def update_theme_properties(
    project: Project,
    assignments: list[tuple[str, str]],
    *,
    no_cascade: bool = False,
) -> list[ThemePropertyChange]:
    """Update theme properties and persist the theme if anything changed."""
    data = get_theme_data(project)
    changes: list[ThemePropertyChange] = []
    for prop, value in assignments:
        old = get_theme_property(data, prop)
        try:
            keys = set_theme_property(data, prop, value, cascade=not no_cascade)
        except ValueError as e:
            raise ValueError(f"{prop}: {e}") from e
        new = get_theme_property(data, prop)
        old_str = str(old) if old is not None else "(none)"
        new_str = str(new) if new is not None else "(none)"
        changes.append(
            ThemePropertyChange(
                prop=prop,
                old=old,
                new=new,
                changed=old_str != new_str,
                cascaded_keys=keys[1:],
            )
        )

    if any(change.changed for change in changes):
        save_theme_data(project, data)
    return changes


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
    return _theme_display_name(theme_name)


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


def audit_theme_overrides(
    project: Project,
    *,
    page_filter: str | None = None,
) -> ThemeAuditResult:
    """Scan all visuals for properties that override theme defaults."""
    data = get_theme_data(project)
    return audit_theme_overrides_from_data(project, data, page_filter=page_filter)


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


def _fix_theme_resource_path(report: dict, theme_name: str) -> bool:
    """Ensure the CustomTheme resource item has the full filename in both name and path.

    PBI Desktop requires both ``name`` and ``path`` to be the full filename
    (e.g. ``IntunePrestige.json``), not just the stem.

    Searches both flat and wrapped (``resourcePackage``) package formats.
    Returns True if report was modified.
    """
    expected = _theme_filename(theme_name)
    stem = _theme_display_name(theme_name)
    fixed = False

    for pkg in report.get("resourcePackages", []):
        # Support both flat format and legacy wrapped format
        inner = pkg.get("resourcePackage", pkg)
        if not isinstance(inner, dict):
            continue
        for item in inner.get("items", []):
            if not isinstance(item, dict):
                continue
            # Match by either old format (stem) or new format (filename)
            item_name = item.get("name", "")
            if item_name != theme_name and item_name != expected and item_name != stem:
                continue
            if item.get("name") != expected:
                item["name"] = expected
                fixed = True
            cur_path = item.get("path", "")
            if cur_path != expected:
                item["path"] = expected
                fixed = True

    return fixed


def _remove_resource_items_by_type(report: dict, item_type: str) -> None:
    """Remove all resource items of the given type from RegisteredResources."""
    for pkg in report.get("resourcePackages", []):
        if pkg.get("name") == "RegisteredResources":
            items = pkg.get("items", [])
            pkg["items"] = [i for i in items if i.get("type") != item_type]


def _read_report(project: Project) -> dict:
    return read_report_json(project)


def _write_report(project: Project, data: dict) -> None:
    write_report_json(project, data)


def _ensure_resource_entry(report: dict, theme_name: str) -> None:
    """Ensure resourcePackages contains the theme file reference."""
    add_or_update_resource_item(
        report,
        item_type="CustomTheme",
        name=f"{theme_name}.json",
        path=f"{theme_name}.json",
    )


def _normalize_resource_packages(report: dict) -> None:
    """Normalize legacy resourcePackages entries to the published schema shape."""
    normalize_resource_packages(report)


def _normalize_resource_item(item: dict) -> dict:
    return normalize_resource_item(item)


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
    if path.endswith(".json"):
        return "CustomTheme"
    return "CustomTheme"
