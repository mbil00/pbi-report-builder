"""Helpers for report-level resource package editing."""

from __future__ import annotations

import difflib
import shutil
from dataclasses import dataclass
from pathlib import Path

from pbi.project import Project
from pbi.report_io import read_report_json, write_report_json
from pbi.resources import (
    REGISTERED_RESOURCES_PACKAGE,
    get_or_create_resource_package,
    normalize_resource_item,
    normalize_resource_packages,
)
from pbi.schema_refs import REPORT_SCHEMA

RESOURCE_PACKAGE_TYPES = (
    "CustomVisual",
    "RegisteredResources",
    "SharedResources",
    "OrganizationalStoreCustomVisual",
)

RESOURCE_ITEM_TYPES = (
    "CustomVisualJavascript",
    "CustomVisualsCss",
    "CustomVisualScreenshot",
    "CustomVisualIcon",
    "CustomVisualWatermark",
    "CustomVisualMetadata",
    "Image",
    "ShapeMap",
    "CustomTheme",
    "BaseTheme",
    "DashboardTheme",
    "DashboardBaseTheme",
    "HighContrastTheme",
    "AppNavigation",
    "AppTheme",
    "AppBaseTheme",
)


@dataclass(frozen=True)
class ResourcePackageInfo:
    name: str
    package_type: str
    item_count: int
    disabled: bool


@dataclass(frozen=True)
class ResourceItemInfo:
    package_name: str
    package_type: str
    name: str
    path: str
    item_type: str


def list_resource_packages(project: Project) -> list[ResourcePackageInfo]:
    report = _read_report(project)
    rows: list[ResourcePackageInfo] = []
    for pkg in _resource_packages(report):
        rows.append(
            ResourcePackageInfo(
                name=str(pkg.get("name", "")),
                package_type=str(pkg.get("type", "")),
                item_count=len(_package_items(pkg)),
                disabled=bool(pkg.get("disabled", False)),
            )
        )
    return rows


def get_resource_package(project: Project, identifier: str) -> dict:
    report = _read_report(project)
    return _find_package(_resource_packages(report), identifier)


def create_resource_package(
    project: Project,
    name: str,
    *,
    package_type: str = REGISTERED_RESOURCES_PACKAGE,
    disabled: bool = False,
) -> dict:
    if package_type not in RESOURCE_PACKAGE_TYPES:
        raise ValueError(
            f'Unsupported package type "{package_type}". Available: {", ".join(RESOURCE_PACKAGE_TYPES)}'
        )

    report = _read_report(project)
    packages = _resource_packages(report)
    for pkg in packages:
        if str(pkg.get("name", "")).lower() == name.lower():
            raise ValueError(f'Resource package "{name}" already exists.')

    created = {
        "name": name,
        "type": package_type,
        "items": [],
    }
    if disabled:
        created["disabled"] = True
    packages.append(created)
    _write_report(project, report)
    return created


def delete_resource_package(
    project: Project,
    identifier: str,
    *,
    drop_files: bool = False,
) -> dict:
    report = _read_report(project)
    packages = _resource_packages(report)
    pkg = _find_package(packages, identifier)
    normalized_pkg = _normalize_package(pkg)

    if drop_files:
        if normalized_pkg.get("name") != REGISTERED_RESOURCES_PACKAGE:
            raise ValueError("--drop-files is only supported for RegisteredResources.")
        for item in _package_items(pkg):
            _delete_registered_resource_file(project, item)

    packages.remove(pkg)
    if not packages:
        report.pop("resourcePackages", None)
    _write_report(project, report)
    return normalized_pkg


def list_resource_items(project: Project, package_identifier: str) -> list[ResourceItemInfo]:
    report = _read_report(project)
    pkg = _find_package(_resource_packages(report), package_identifier)
    normalized_pkg = _normalize_package(pkg)
    rows: list[ResourceItemInfo] = []
    for item in _package_items(pkg):
        rows.append(
            ResourceItemInfo(
                package_name=str(normalized_pkg.get("name", "")),
                package_type=str(normalized_pkg.get("type", "")),
                name=str(item.get("name", "")),
                path=str(item.get("path", "")),
                item_type=str(item.get("type", "")),
            )
        )
    return rows


def get_resource_item(project: Project, package_identifier: str, identifier: str) -> dict:
    report = _read_report(project)
    pkg = _find_package(_resource_packages(report), package_identifier)
    return _find_item(_package_items(pkg), identifier)


def set_resource_item(
    project: Project,
    package_identifier: str,
    stored_path: str,
    *,
    item_type: str,
    name: str | None = None,
    source_path: Path | None = None,
) -> tuple[dict, bool]:
    if item_type not in RESOURCE_ITEM_TYPES:
        raise ValueError(
            f'Unsupported resource item type "{item_type}". Available: {", ".join(RESOURCE_ITEM_TYPES)}'
        )

    report = _read_report(project)
    packages = _resource_packages(report)
    if package_identifier == REGISTERED_RESOURCES_PACKAGE:
        pkg = get_or_create_resource_package(report, package_name=REGISTERED_RESOURCES_PACKAGE)
    else:
        pkg = _find_package(packages, package_identifier)

    normalized = normalize_resource_item(
        {
            "type": item_type,
            "name": name or Path(stored_path).name,
            "path": stored_path,
        }
    )

    if source_path is not None:
        if str(pkg.get("name", "")) != REGISTERED_RESOURCES_PACKAGE:
            raise ValueError("--from-file is only supported for RegisteredResources items.")
        _copy_registered_resource_file(project, source_path, normalized["path"])

    items = pkg.setdefault("items", [])
    for existing in items:
        normalized_existing = normalize_resource_item(existing)
        if str(normalized_existing.get("path", "")).lower() == str(normalized["path"]).lower():
            existing_id = existing.get("id")
            existing.clear()
            existing.update(normalized)
            if existing_id is not None:
                existing["id"] = existing_id
            _write_report(project, report)
            return normalize_resource_item(existing), False

    items.append(normalized)
    _write_report(project, report)
    return normalize_resource_item(items[-1]), True


def delete_resource_item(
    project: Project,
    package_identifier: str,
    identifier: str,
    *,
    drop_file: bool = False,
) -> dict:
    report = _read_report(project)
    pkg = _find_package(_resource_packages(report), package_identifier)
    item = _find_item(_package_items(pkg), identifier)

    if drop_file:
        if str(pkg.get("name", "")) != REGISTERED_RESOURCES_PACKAGE:
            raise ValueError("--drop-file is only supported for RegisteredResources items.")
        _delete_registered_resource_file(project, item)

    pkg["items"] = [
        existing
        for existing in pkg.get("items", [])
        if normalize_resource_item(existing) != item
    ]
    _write_report(project, report)
    return item


def _read_report(project: Project) -> dict:
    return read_report_json(project, ensure_schema=True, normalize_resources_flag=True)


def _write_report(project: Project, report: dict) -> None:
    write_report_json(project, report)


def _resource_packages(report: dict) -> list[dict]:
    normalize_resource_packages(report)
    packages = report.setdefault("resourcePackages", [])
    filtered = [pkg for pkg in packages if isinstance(pkg, dict)]
    if filtered != packages:
        report["resourcePackages"] = filtered
    return report["resourcePackages"]


def _normalize_package(pkg: dict) -> dict:
    normalized = {
        "name": str(pkg.get("name", "")),
        "type": str(pkg.get("type", "")),
        "items": _package_items(pkg),
    }
    if "disabled" in pkg:
        normalized["disabled"] = bool(pkg["disabled"])
    if "id" in pkg:
        normalized["id"] = pkg["id"]
    return normalized


def _package_items(pkg: dict) -> list[dict]:
    return [
        normalize_resource_item(item)
        for item in pkg.get("items", [])
        if isinstance(item, dict)
    ]


def _find_package(packages: list[dict], identifier: str) -> dict:
    return _find_by_identifier(
        packages,
        identifier,
        value_getter=lambda pkg: str(pkg.get("name", "")),
        kind="Resource package",
    )


def _find_item(items: list[dict], identifier: str) -> dict:
    return _find_by_identifier(
        items,
        identifier,
        value_getter=lambda item: str(item.get("name") or item.get("path", "")),
        alt_values=lambda item: [str(item.get("path", ""))],
        kind="Resource item",
    )


def _find_by_identifier(
    rows: list[dict],
    identifier: str,
    *,
    value_getter,
    kind: str,
    alt_values=None,
) -> dict:
    lowered = identifier.lower()

    for row in rows:
        values = [value_getter(row)]
        if alt_values:
            values.extend(alt_values(row))
        for value in values:
            if value.lower() == lowered:
                return row

    partial_matches = []
    for row in rows:
        values = [value_getter(row)]
        if alt_values:
            values.extend(alt_values(row))
        if any(lowered in value.lower() for value in values if value):
            partial_matches.append(row)
    if len(partial_matches) == 1:
        return partial_matches[0]

    names = [value_getter(row) for row in rows if value_getter(row)]
    matches = difflib.get_close_matches(identifier, names, n=3, cutoff=0.5)
    if matches:
        raise ValueError(f'{kind} "{identifier}" not found. Did you mean: {", ".join(matches)}?')
    if names:
        raise ValueError(f'{kind} "{identifier}" not found. Available: {", ".join(names)}')
    raise ValueError(f"No {kind.lower()}s configured.")


def _registered_resources_dir(project: Project) -> Path:
    return project.report_folder / "StaticResources" / REGISTERED_RESOURCES_PACKAGE


def _copy_registered_resource_file(project: Project, source_path: Path, stored_path: str) -> Path:
    source = source_path.resolve()
    if not source.exists():
        raise FileNotFoundError(f"Resource file not found: {source}")

    dest_dir = _registered_resources_dir(project)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / Path(stored_path).name
    shutil.copy2(source, dest)
    return dest


def _delete_registered_resource_file(project: Project, item: dict) -> None:
    path = _registered_resources_dir(project) / str(item.get("path", ""))
    if path.exists():
        path.unlink()
