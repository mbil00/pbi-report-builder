"""Image resource management for PBIP projects."""

from __future__ import annotations

import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pbi.project import Project


@dataclass
class RegisteredImage:
    """A registered image resource."""
    name: str
    path: Path
    size: int
    referenced_by: list[str]  # visual names that reference it


def _resources_dir(project: Project) -> Path:
    """Return the RegisteredResources directory."""
    return project.report_folder / "StaticResources" / "RegisteredResources"


def _get_resource_package(project: Project) -> tuple[dict, list[dict]]:
    """Get or create the RegisteredResources package from report.json.
    Returns (report_data, items_list)."""
    report_path = project.definition_folder / "report.json"
    import json
    if report_path.exists():
        with open(report_path, encoding="utf-8-sig") as f:
            report_data = json.load(f)
    else:
        report_data = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.0.0/report.json"}

    packages = report_data.setdefault("resourcePackages", [])
    for pkg in packages:
        rp = pkg.get("resourcePackage", {})
        if rp.get("name") == "RegisteredResources":
            return report_data, rp.setdefault("items", [])

    # Create the package
    new_pkg = {
        "resourcePackage": {
            "name": "RegisteredResources",
            "type": 1,
            "items": [],
            "disabled": False,
        }
    }
    packages.append(new_pkg)
    return report_data, new_pkg["resourcePackage"]["items"]


def _save_report_json(project: Project, report_data: dict) -> None:
    """Write report.json back."""
    import json
    report_path = project.definition_folder / "report.json"
    with open(report_path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _find_image_references(project: Project) -> dict[str, list[str]]:
    """Scan all visuals for ResourcePackageItem references. Returns {image_name: [visual_names]}."""
    refs: dict[str, list[str]] = {}
    import json

    for page in project.get_pages():
        visuals_dir = page.folder / "visuals"
        if not visuals_dir.exists():
            continue
        for vdir in visuals_dir.iterdir():
            if not vdir.is_dir():
                continue
            vjson = vdir / "visual.json"
            if not vjson.exists():
                continue
            content = vjson.read_text(encoding="utf-8-sig")
            # Search for ResourcePackageItem references in the raw JSON text
            if "ResourcePackageItem" not in content:
                continue
            data = json.loads(content)
            vis_name = data.get("name", vdir.name)
            _scan_for_resource_refs(data, vis_name, refs)
    return refs


def _scan_for_resource_refs(obj: Any, vis_name: str, refs: dict[str, list[str]]) -> None:
    """Recursively scan a dict/list for ResourcePackageItem references."""
    if isinstance(obj, dict):
        if "ResourcePackageItem" in obj:
            item_name = obj["ResourcePackageItem"].get("ItemName", "")
            if item_name:
                refs.setdefault(item_name, []).append(vis_name)
        for v in obj.values():
            _scan_for_resource_refs(v, vis_name, refs)
    elif isinstance(obj, list):
        for item in obj:
            _scan_for_resource_refs(item, vis_name, refs)


def add_image(project: Project, source_path: Path) -> str:
    """Register an image file in the project. Returns the registered name."""
    if not source_path.exists():
        raise FileNotFoundError(f"Image file not found: {source_path}")

    # Generate unique name: original_stem + random suffix + extension
    stem = source_path.stem
    suffix = secrets.token_hex(5)
    ext = source_path.suffix
    registered_name = f"{stem}{suffix}{ext}"

    # Copy file to RegisteredResources
    res_dir = _resources_dir(project)
    res_dir.mkdir(parents=True, exist_ok=True)
    dest = res_dir / registered_name
    shutil.copy2(source_path, dest)

    # Add to report.json
    report_data, items = _get_resource_package(project)
    items.append({
        "type": 202,
        "name": registered_name,
        "path": f"RegisteredResources/{registered_name}",
    })
    _save_report_json(project, report_data)

    return registered_name


def list_images(project: Project) -> list[RegisteredImage]:
    """List all registered image resources with reference counts."""
    _report_data, items = _get_resource_package(project)
    refs = _find_image_references(project)
    res_dir = _resources_dir(project)

    result = []
    for item in items:
        name = item.get("name", "")
        file_path = res_dir / name
        size = file_path.stat().st_size if file_path.exists() else 0
        referenced_by = refs.get(name, [])
        result.append(RegisteredImage(
            name=name,
            path=file_path,
            size=size,
            referenced_by=referenced_by,
        ))
    return result


def prune_images(project: Project) -> list[str]:
    """Remove unreferenced images. Returns list of removed image names."""
    refs = _find_image_references(project)
    report_data, items = _get_resource_package(project)
    res_dir = _resources_dir(project)

    removed = []
    remaining = []
    for item in items:
        name = item.get("name", "")
        if name not in refs:
            # Remove file
            file_path = res_dir / name
            if file_path.exists():
                file_path.unlink()
            removed.append(name)
        else:
            remaining.append(item)

    if removed:
        items.clear()
        items.extend(remaining)
        _save_report_json(project, report_data)

    return removed
