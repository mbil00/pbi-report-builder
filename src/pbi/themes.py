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
    Returns the theme name.
    """
    # Read and validate theme JSON
    with open(theme_path, encoding="utf-8-sig") as f:
        theme_data = json.load(f)

    theme_name = theme_data.get("name", theme_path.stem)

    # Copy theme to RegisteredResources
    resources_dir = (
        project.report_folder / "StaticResources"
        / "RegisteredResources" / "BaseThemes"
    )
    resources_dir.mkdir(parents=True, exist_ok=True)
    dest = resources_dir / f"{theme_name}.json"
    shutil.copy2(theme_path, dest)

    # Update report.json
    report = _read_report(project)
    _normalize_resource_packages(report)
    report.setdefault("$schema", REPORT_SCHEMA)
    report.setdefault("layoutOptimization", "None")
    report.setdefault("themeCollection", {})

    # Set custom theme reference
    report["themeCollection"]["customTheme"] = {
        "name": theme_name,
        "reportVersionAtImport": "5.55",
        "type": "RegisteredResources",
    }

    # Ensure resourcePackages has the registered resources entry
    _ensure_resource_entry(report, theme_name)

    _write_report(project, report)
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
    # Look in RegisteredResources
    theme_file = (
        project.report_folder / "StaticResources"
        / "RegisteredResources" / "BaseThemes" / f"{theme_name}.json"
    )
    if not theme_file.exists():
        # Also try without BaseThemes/
        theme_file = (
            project.report_folder / "StaticResources"
            / "RegisteredResources" / f"{theme_name}.json"
        )
    if not theme_file.exists():
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
    report.setdefault("layoutOptimization", "None")
    report.setdefault("themeCollection", {})
    custom = report.get("themeCollection", {}).pop("customTheme", None)
    if not custom:
        return None

    theme_name = custom.get("name", "")

    # Remove from resourcePackages
    for pkg in report.get("resourcePackages", []):
        if pkg.get("name") == "RegisteredResources":
            items = pkg.get("items", [])
            pkg["items"] = [
                i for i in items if i.get("name") != theme_name
            ]

    # Remove file if it exists
    theme_file = (
        project.report_folder / "StaticResources"
        / "RegisteredResources" / "BaseThemes" / f"{theme_name}.json"
    )
    if theme_file.exists():
        theme_file.unlink()

    _write_report(project, report)
    return theme_name


# ── Helpers ──────────────────────────────────────────────────

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
        "path": f"BaseThemes/{theme_name}.json",
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
