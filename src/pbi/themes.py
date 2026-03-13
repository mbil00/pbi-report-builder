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

    # Set custom theme reference
    report.setdefault("themeCollection", {})["customTheme"] = {
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
    custom = report.get("themeCollection", {}).pop("customTheme", None)
    if not custom:
        return None

    theme_name = custom.get("name", "")

    # Remove from resourcePackages
    for pkg in report.get("resourcePackages", []):
        rp = pkg.get("resourcePackage", {})
        if rp.get("name") == "RegisteredResources":
            items = rp.get("items", [])
            rp["items"] = [
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
        if pkg.get("resourcePackage", {}).get("name") == "RegisteredResources":
            reg_pkg = pkg
            break

    if reg_pkg is None:
        reg_pkg = {
            "resourcePackage": {
                "name": "RegisteredResources",
                "type": 1,
                "items": [],
            }
        }
        packages.append(reg_pkg)

    items = reg_pkg["resourcePackage"].setdefault("items", [])

    # Check if theme already registered
    for item in items:
        if item.get("name") == theme_name:
            return

    items.append({
        "type": 202,
        "name": theme_name,
        "path": f"BaseThemes/{theme_name}.json",
    })
