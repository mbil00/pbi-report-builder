"""Cross-project page import services."""

from __future__ import annotations

import json
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from pbi.page_authoring import add_page_to_order
from pbi.project import Project, _read_json, _write_json
from pbi.report_io import write_report_json


@dataclass(frozen=True)
class PageImportResult:
    """Summary of an imported page."""

    source_project_name: str
    source_page_name: str
    target_page_name: str
    visual_count: int
    resource_count: int = 0


def import_page(
    target_project: Project,
    *,
    from_project: str | Path | Project,
    page: str,
    name: str | None = None,
    include_resources: bool = False,
) -> PageImportResult:
    """Import a page from another project into the target project."""
    source_project = (
        from_project
        if isinstance(from_project, Project)
        else Project.find(from_project)
    )
    source_page = source_project.find_page(page)
    target_name = name or source_page.display_name

    new_id, new_dir = _copy_page_directory(target_project, source_page)
    _rewrite_page_identity(new_dir, new_id, target_name)
    _rewrite_visual_identities(new_dir)
    add_page_to_order(target_project, new_id)

    resource_count = 0
    if include_resources:
        resource_count = _copy_page_resources(
            target_project,
            source_project=source_project,
            source_page=source_page,
        )

    visuals_dir = new_dir / "visuals"
    visual_count = len(list(visuals_dir.iterdir())) if visuals_dir.exists() else 0
    return PageImportResult(
        source_project_name=source_project.project_name,
        source_page_name=source_page.display_name,
        target_page_name=target_name,
        visual_count=visual_count,
        resource_count=resource_count,
    )


def _copy_page_directory(target_project: Project, source_page) -> tuple[str, Path]:
    new_id = secrets.token_hex(10)
    new_dir = target_project.definition_folder / "pages" / new_id
    shutil.copytree(source_page.folder, new_dir)
    return new_id, new_dir


def _rewrite_page_identity(new_dir: Path, page_id: str, display_name: str) -> None:
    page_json_path = new_dir / "page.json"
    page_data = _read_json(page_json_path)
    page_data["name"] = page_id
    page_data["displayName"] = display_name
    _write_json(page_json_path, page_data)


def _rewrite_visual_identities(new_dir: Path) -> None:
    visuals_dir = new_dir / "visuals"
    old_to_new: dict[str, str] = {}
    if not visuals_dir.exists():
        return

    for visual_dir in list(visuals_dir.iterdir()):
        if not visual_dir.is_dir():
            continue
        new_visual_id = secrets.token_hex(10)
        new_visual_dir = visuals_dir / new_visual_id
        visual_dir.rename(new_visual_dir)
        old_name = visual_dir.name

        visual_json = new_visual_dir / "visual.json"
        if not visual_json.exists():
            continue
        visual_data = _read_json(visual_json)
        old_to_new[visual_data.get("name", old_name)] = new_visual_id
        visual_data["name"] = new_visual_id
        _write_json(visual_json, visual_data)

    for visual_dir in visuals_dir.iterdir():
        if not visual_dir.is_dir():
            continue
        visual_json = visual_dir / "visual.json"
        if not visual_json.exists():
            continue
        visual_data = _read_json(visual_json)
        parent = visual_data.get("parentGroupName")
        if parent and parent in old_to_new:
            visual_data["parentGroupName"] = old_to_new[parent]
            _write_json(visual_json, visual_data)


def _copy_page_resources(
    target_project: Project,
    *,
    source_project: Project,
    source_page,
) -> int:
    source_res_dir = source_project.report_folder / "StaticResources" / "RegisteredResources"
    if not source_res_dir.exists():
        return 0

    target_res_dir = target_project.report_folder / "StaticResources" / "RegisteredResources"
    target_res_dir.mkdir(parents=True, exist_ok=True)

    from pbi.images import _get_resource_package, _scan_for_resource_refs
    from pbi.resources import add_or_update_resource_item, find_registered_image_item

    refs: dict[str, list[str]] = {}
    for visual in source_project.get_visuals(source_page):
        content = (visual.folder / "visual.json").read_text(encoding="utf-8-sig")
        if "ResourcePackageItem" not in content:
            continue
        data = json.loads(content)
        _scan_for_resource_refs(data, visual.name, refs)

    copied = 0
    for image_name in refs:
        source_file = source_res_dir / image_name
        target_file = target_res_dir / image_name
        if not source_file.exists() or target_file.exists():
            continue

        shutil.copy2(source_file, target_file)
        report_data, items = _get_resource_package(target_project)
        source_report_data, _ = _get_resource_package(source_project)
        source_item = find_registered_image_item(source_report_data, image_name)
        display_name = image_name
        if source_item is not None:
            display_name = str(source_item.get("name") or image_name)
        existing = {str(item.get("path") or item.get("name", "")) for item in items}
        if image_name not in existing:
            add_or_update_resource_item(
                report_data,
                item_type="Image",
                name=display_name,
                path=image_name,
            )
            write_report_json(target_project, report_data)
        copied += 1

    return copied
