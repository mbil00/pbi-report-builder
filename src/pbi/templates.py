"""Page template management — save and apply reusable page layouts.

Templates capture a page's visual layout (positions, types, formatting)
without data bindings. Stored as JSON files in <project>/.pbi-templates/.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from json import JSONDecodeError

from pbi.project import Project, Page, Visual
from pbi.schema_refs import VISUAL_CONTAINER_SCHEMA


def save_template(
    project: Project,
    page: Page,
    template_name: str,
    visuals: list[Visual],
) -> Path:
    """Save a page's layout as a reusable template.

    Captures page dimensions, visual positions, types, and formatting.
    Strips data bindings, filters, and sort definitions.
    """
    template = {
        "name": template_name,
        "page": {
            "width": page.width,
            "height": page.height,
            "displayOption": page.display_option,
        },
        "visuals": [],
    }

    # Capture page-level objects (background, outspace)
    page_objects = page.data.get("objects")
    if page_objects:
        template["page"]["objects"] = copy.deepcopy(page_objects)

    for vis in visuals:
        entry: dict = {
            "position": copy.deepcopy(vis.position),
        }

        if "visualGroup" in vis.data:
            # Group container
            vg = vis.data["visualGroup"]
            entry["visualGroup"] = {
                "displayName": vg.get("displayName", ""),
                "groupMode": vg.get("groupMode", "ScaleMode"),
            }
            vg_objects = vg.get("objects")
            if vg_objects:
                entry["visualGroup"]["objects"] = copy.deepcopy(vg_objects)
            entry["name"] = vis.name
        else:
            # Regular visual
            visual_data = vis.data.get("visual", {})
            entry["visualType"] = visual_data.get("visualType", "unknown")

            # Preserve friendly name
            is_hex = all(c in "0123456789abcdef" for c in vis.name) and len(vis.name) >= 16
            if not is_hex:
                entry["name"] = vis.name

            # Capture formatting only (not data)
            objects = visual_data.get("objects")
            if objects:
                entry["objects"] = copy.deepcopy(objects)

            container_objects = visual_data.get("visualContainerObjects")
            if container_objects:
                entry["visualContainerObjects"] = copy.deepcopy(container_objects)

            # Capture group membership
            parent = vis.data.get("parentGroupName")
            if parent:
                entry["parentGroupName"] = parent

            # Hidden flag
            if vis.data.get("isHidden"):
                entry["isHidden"] = True

        template["visuals"].append(entry)

    # Write template
    dest = _template_path(project, template_name)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)
        f.write("\n")

    return dest


def apply_template(
    project: Project,
    page: Page,
    template_name: str,
) -> list[Visual]:
    """Apply a template to an existing page.

    Creates visuals matching the template's layout and formatting.
    Does not modify existing visuals on the page.
    Returns the created visuals.
    """
    template = _load_template(project, template_name)

    # Apply page properties
    page_tmpl = template.get("page", {})
    if "width" in page_tmpl:
        page.data["width"] = page_tmpl["width"]
    if "height" in page_tmpl:
        page.data["height"] = page_tmpl["height"]
    if "displayOption" in page_tmpl:
        page.data["displayOption"] = page_tmpl["displayOption"]
    if "objects" in page_tmpl:
        page.data["objects"] = copy.deepcopy(page_tmpl["objects"])
    page.save()

    existing_visuals = project.get_visuals(page)
    used_names = {vis.name for vis in existing_visuals}
    next_z = max((vis.position.get("z", 0) for vis in existing_visuals), default=0) + 1
    next_tab_order = max((vis.position.get("tabOrder", -1) for vis in existing_visuals), default=-1) + 1

    # Track group name mapping (old name -> new name) for parent references
    group_map: dict[str, str] = {}
    created: list[Visual] = []

    # Create groups first, then regular visuals
    group_entries = [e for e in template.get("visuals", []) if "visualGroup" in e]
    visual_entries = [e for e in template.get("visuals", []) if "visualGroup" not in e]

    for entry in group_entries:
        vis, next_z, next_tab_order = _create_from_entry(
            page,
            entry,
            group_map,
            used_names,
            next_z,
            next_tab_order,
        )
        old_name = entry.get("name", "")
        group_map[old_name] = vis.name
        created.append(vis)

    for entry in visual_entries:
        vis, next_z, next_tab_order = _create_from_entry(
            page,
            entry,
            group_map,
            used_names,
            next_z,
            next_tab_order,
        )
        created.append(vis)

    return created


def list_templates(project: Project) -> list[dict]:
    """List available templates with name and visual count."""
    templates_dir = _templates_dir(project)
    if not templates_dir.exists():
        return []

    result = []
    for f in sorted(templates_dir.glob("*.json")):
        try:
            with open(f, encoding="utf-8-sig") as fh:
                data = json.load(fh)
            result.append({
                "name": data.get("name", f.stem),
                "file": f.name,
                "visuals": len(data.get("visuals", [])),
                "size": f"{data.get('page', {}).get('width', '?')} x {data.get('page', {}).get('height', '?')}",
            })
        except (json.JSONDecodeError, KeyError):
            continue

    return result


def delete_template(project: Project, template_name: str) -> bool:
    """Delete a template. Returns True if deleted."""
    path = _template_path(project, template_name)
    if path.exists():
        path.unlink()
        return True
    return False


# ── Helpers ──────────────────────────────────────────────────

def _templates_dir(project: Project) -> Path:
    return project.root / ".pbi-templates"


def _validate_template_name(template_name: str) -> str:
    """Reject template names that would escape the templates directory."""
    if not template_name or template_name in {".", ".."}:
        raise ValueError("Template name must be a non-empty file-safe name.")
    if "/" in template_name or "\\" in template_name:
        raise ValueError("Template name may not contain path separators.")
    if Path(template_name).is_absolute():
        raise ValueError("Template name may not be an absolute path.")
    return template_name


def _template_path(project: Project, template_name: str) -> Path:
    """Resolve a validated template path inside .pbi-templates."""
    safe_name = _validate_template_name(template_name)
    return _templates_dir(project) / f"{safe_name}.json"


def _load_template(project: Project, template_name: str) -> dict:
    path = _template_path(project, template_name)
    if not path.exists():
        raise FileNotFoundError(f'Template "{template_name}" not found')
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except JSONDecodeError as e:
        raise ValueError(f'Template "{template_name}" is not valid JSON: {e.msg}') from e


def _create_from_entry(
    page: Page,
    entry: dict,
    group_map: dict[str, str],
    used_names: set[str],
    next_z: int,
    next_tab_order: int,
) -> tuple[Visual, int, int]:
    """Create a single visual from a template entry."""
    import secrets
    from pbi.project import _write_json

    pos = entry.get("position", {})
    position = copy.deepcopy(pos)
    position["z"] = next_z
    position["tabOrder"] = next_tab_order
    visual_id = secrets.token_hex(10)
    visual_dir = page.folder / "visuals" / visual_id
    visual_dir.mkdir(parents=True, exist_ok=True)

    if "visualGroup" in entry:
        # Group container
        vg = entry["visualGroup"]
        requested_name = entry.get("name", visual_id)
        name = _unique_name(requested_name, used_names)
        data = {
            "$schema": VISUAL_CONTAINER_SCHEMA,
            "name": name,
            "position": position,
            "visualGroup": {
                "displayName": vg.get("displayName", name),
                "groupMode": vg.get("groupMode", "ScaleMode"),
                "objects": copy.deepcopy(vg.get("objects", {})),
            },
        }
    else:
        # Regular visual
        requested_name = entry.get("name", visual_id)
        name = _unique_name(requested_name, used_names)
        visual_type = entry.get("visualType", "shape")

        visual_block: dict = {
            "visualType": visual_type,
            "query": {"queryState": {}},
            "objects": copy.deepcopy(entry.get("objects", {})),
        }
        container_objects = entry.get("visualContainerObjects")
        if container_objects:
            visual_block["visualContainerObjects"] = copy.deepcopy(container_objects)

        data = {
            "$schema": VISUAL_CONTAINER_SCHEMA,
            "name": name,
            "position": position,
            "visual": visual_block,
        }

        # Resolve group membership
        parent = entry.get("parentGroupName")
        if parent and parent in group_map:
            data["parentGroupName"] = group_map[parent]

        if entry.get("isHidden"):
            data["isHidden"] = True

    _write_json(visual_dir / "visual.json", data)
    used_names.add(name)
    return Visual(folder=visual_dir, data=data), next_z + 1, next_tab_order + 1


def _unique_name(requested_name: str, used_names: set[str]) -> str:
    """Generate a unique visual or group name for a page."""
    if requested_name not in used_names:
        return requested_name
    index = 2
    while f"{requested_name}_{index}" in used_names:
        index += 1
    return f"{requested_name}_{index}"
