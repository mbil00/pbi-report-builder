"""Helpers for PBIR resourcePackages entries."""

from __future__ import annotations

from pathlib import Path


REGISTERED_RESOURCES_PACKAGE = "RegisteredResources"
_IMAGE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".bmp",
    ".svg",
    ".webp",
    ".ico",
    ".tif",
    ".tiff",
}


def normalize_resource_packages(report: dict) -> None:
    """Normalize legacy resourcePackages entries to the published PBIR schema."""
    packages = report.get("resourcePackages", [])
    normalized: list[dict] = []

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
                normalize_resource_item(item)
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


def get_or_create_resource_package(
    report: dict,
    *,
    package_name: str = REGISTERED_RESOURCES_PACKAGE,
) -> dict:
    """Return a normalized resource package, creating it when missing."""
    normalize_resource_packages(report)
    packages = report.setdefault("resourcePackages", [])
    for pkg in packages:
        if pkg.get("name") == package_name:
            pkg.setdefault("items", [])
            return pkg

    pkg = {
        "name": package_name,
        "type": package_name,
        "items": [],
    }
    packages.append(pkg)
    return pkg


def normalize_resource_item(item: dict) -> dict:
    """Normalize a resource item entry."""
    entry = dict(item)
    raw_name = str(entry.get("name", "") or "")
    raw_path = str(entry.get("path", raw_name) or raw_name)
    path = _normalize_relative_resource_path(raw_path)
    item_type = _coerce_item_type(entry.get("type"), path=path)

    entry["type"] = item_type
    entry["path"] = path

    if item_type == "CustomTheme":
        filename = raw_name if raw_name.endswith(".json") else Path(path).name
        if not filename.endswith(".json"):
            filename = f"{filename}.json"
        entry["name"] = filename
        entry["path"] = filename
    else:
        entry["name"] = raw_name or Path(path).name

    return entry


def add_or_update_resource_item(
    report: dict,
    *,
    item_type: str,
    name: str,
    path: str,
) -> dict:
    """Insert or update a single RegisteredResources item."""
    package = get_or_create_resource_package(report)
    normalized = normalize_resource_item(
        {
            "type": item_type,
            "name": name,
            "path": path,
        }
    )

    items = package.setdefault("items", [])
    for item in items:
        normalized_item = normalize_resource_item(item)
        if (
            normalized_item.get("type") == normalized["type"]
            and normalized_item.get("path") == normalized["path"]
        ):
            item.clear()
            item.update(normalized)
            return item

    items.append(normalized)
    return items[-1]


def choose_registered_image_name(
    existing_items: list[dict],
    *,
    preferred_name: str,
    fallback_name: str,
) -> str:
    """Choose a stable user-facing image name without colliding on path lookup."""
    preferred_lower = preferred_name.lower()
    for item in existing_items:
        normalized = normalize_resource_item(item)
        if normalized.get("type") != "Image":
            continue
        if normalized.get("name", "").lower() == preferred_lower:
            return fallback_name
    return preferred_name


def find_registered_image_item(report: dict, ref: str) -> dict | None:
    """Resolve an image by logical name or stored path."""
    package = get_or_create_resource_package(report)
    items = [
        normalize_resource_item(item)
        for item in package.get("items", [])
        if isinstance(item, dict)
    ]
    if not items:
        return None

    ref_lower = ref.lower()
    for key in ("name", "path"):
        for item in items:
            value = str(item.get(key, ""))
            if value.lower() == ref_lower:
                return item

    for item in items:
        path_name = Path(str(item.get("path", ""))).name
        if path_name.lower() == ref_lower:
            return item

    ref_path = Path(ref)
    ref_stem = ref_path.stem.lower()
    ref_suffix = ref_path.suffix.lower()
    if ref_stem and ref_suffix:
        candidates = []
        for item in items:
            path_name = Path(str(item.get("path", ""))).name
            path = Path(path_name)
            if path.suffix.lower() != ref_suffix:
                continue
            if path.stem.lower().startswith(ref_stem):
                candidates.append(item)
        if len(candidates) == 1:
            return candidates[0]

    return None


def _normalize_relative_resource_path(raw_path: str) -> str:
    prefix = f"{REGISTERED_RESOURCES_PACKAGE}/"
    if raw_path.startswith(prefix):
        return raw_path[len(prefix) :]
    return Path(raw_path).name if raw_path else raw_path


def _coerce_package_type(raw_type: object, name: str) -> str:
    if isinstance(raw_type, str):
        return raw_type
    if raw_type == 1 or name == REGISTERED_RESOURCES_PACKAGE:
        return REGISTERED_RESOURCES_PACKAGE
    if name == "SharedResources":
        return "SharedResources"
    return REGISTERED_RESOURCES_PACKAGE


def _coerce_item_type(raw_type: object, *, path: str) -> str:
    if isinstance(raw_type, str):
        return raw_type
    suffix = Path(path).suffix.lower()
    if raw_type == 202 and suffix in _IMAGE_EXTENSIONS:
        return "Image"
    if suffix in _IMAGE_EXTENSIONS:
        return "Image"
    return "CustomTheme"
