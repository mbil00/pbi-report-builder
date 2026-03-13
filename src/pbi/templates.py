"""Page template management — save and apply reusable page layouts.

Templates capture a page's visual layout (positions, types, formatting)
without data bindings. Stored as JSON files in <project>/.pbi-templates/.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

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
    dest = _templates_dir(project) / f"{template_name}.json"
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

    # Track group name mapping (old name -> new name) for parent references
    group_map: dict[str, str] = {}
    created: list[Visual] = []

    # Create groups first, then regular visuals
    group_entries = [e for e in template.get("visuals", []) if "visualGroup" in e]
    visual_entries = [e for e in template.get("visuals", []) if "visualGroup" not in e]

    for entry in group_entries:
        vis = _create_from_entry(page, entry, group_map)
        old_name = entry.get("name", "")
        group_map[old_name] = vis.name
        created.append(vis)

    for entry in visual_entries:
        vis = _create_from_entry(page, entry, group_map)
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
    path = _templates_dir(project) / f"{template_name}.json"
    if path.exists():
        path.unlink()
        return True
    return False


# ── Helpers ──────────────────────────────────────────────────

def _templates_dir(project: Project) -> Path:
    return project.root / ".pbi-templates"


def _load_template(project: Project, template_name: str) -> dict:
    path = _templates_dir(project) / f"{template_name}.json"
    if not path.exists():
        raise FileNotFoundError(f'Template "{template_name}" not found')
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _create_from_entry(
    page: Page,
    entry: dict,
    group_map: dict[str, str],
) -> Visual:
    """Create a single visual from a template entry."""
    import secrets
    from pbi.project import _write_json

    pos = entry.get("position", {})
    visual_id = secrets.token_hex(10)
    visual_dir = page.folder / "visuals" / visual_id
    visual_dir.mkdir(parents=True, exist_ok=True)

    if "visualGroup" in entry:
        # Group container
        vg = entry["visualGroup"]
        name = entry.get("name", visual_id)
        data = {
            "$schema": VISUAL_CONTAINER_SCHEMA,
            "name": name,
            "position": copy.deepcopy(pos),
            "visualGroup": {
                "displayName": vg.get("displayName", name),
                "groupMode": vg.get("groupMode", "ScaleMode"),
                "objects": copy.deepcopy(vg.get("objects", {})),
            },
        }
    else:
        # Regular visual
        name = entry.get("name", visual_id)
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
            "position": copy.deepcopy(pos),
            "visual": visual_block,
        }

        # Resolve group membership
        parent = entry.get("parentGroupName")
        if parent and parent in group_map:
            data["parentGroupName"] = group_map[parent]

        if entry.get("isHidden"):
            data["isHidden"] = True

    _write_json(visual_dir / "visual.json", data)
    return Visual(folder=visual_dir, data=data)
