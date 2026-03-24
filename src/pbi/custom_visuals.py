"""Custom visual discovery, schema extraction and registration.

Supports:
- Scanning a PBIP project for visuals whose type is not in the built-in schema
- Extracting capabilities from .pbiviz packages (zip archives)
- Converting capabilities to the compact schema format used by visual_schema.py
- Registering extracted schemas in .pbi-custom-schemas/ for project-local use
"""

from __future__ import annotations

import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pbi.project import Project
from pbi.visual_schema import get_visual_types


# ── Data types ────────────────────────────────────────────────────


@dataclass(frozen=True)
class CustomVisualInfo:
    """A custom visual type discovered in the report."""

    visual_type: str
    visual_count: int
    pbiviz_path: Path | None
    schema_installed: bool


@dataclass(frozen=True)
class InstalledCustomVisual:
    """A custom visual whose schema has been registered."""

    visual_type: str
    display_name: str
    role_count: int
    object_count: int
    property_count: int


# ── Scan ──────────────────────────────────────────────────────────


def scan_custom_visuals(project: Project) -> list[CustomVisualInfo]:
    """Scan the report for visual types not in the built-in schema.

    Returns a list of CustomVisualInfo for each unknown type found.
    """
    builtin_types = set(get_visual_types())
    installed_types = set(_list_installed_types(project))

    # Collect all visual types in use across all pages
    type_counts: dict[str, int] = {}
    for page in project.get_pages():
        for visual in project.get_visuals(page):
            vtype = visual.visual_type
            if vtype and vtype not in builtin_types:
                type_counts[vtype] = type_counts.get(vtype, 0) + 1

    # Find .pbiviz files in the project
    pbiviz_map = _find_pbiviz_files(project)

    results = []
    for vtype, count in sorted(type_counts.items()):
        results.append(CustomVisualInfo(
            visual_type=vtype,
            visual_count=count,
            pbiviz_path=pbiviz_map.get(vtype),
            schema_installed=vtype in installed_types,
        ))
    return results


# ── Install ───────────────────────────────────────────────────────


def install_custom_visual(
    project: Project,
    pbiviz_path: Path,
) -> InstalledCustomVisual:
    """Extract capabilities from a .pbiviz and register the schema.

    The .pbiviz is a zip containing resources/{guid}.pbiviz.json with
    the visual's capabilities (dataRoles, objects, etc.) embedded.
    """
    caps = extract_capabilities(pbiviz_path)
    visual_type = caps["visual_type"]
    display_name = caps.get("display_name", visual_type)
    compact = _capabilities_to_compact_schema(caps)

    schema_dir = _schema_dir(project)
    schema_dir.mkdir(parents=True, exist_ok=True)

    out_path = schema_dir / f"{visual_type}.json"
    out_path.write_text(json.dumps(compact, indent=2, sort_keys=True), encoding="utf-8")

    objects = compact.get("objects", {})
    prop_count = sum(len(v) for v in objects.values())
    return InstalledCustomVisual(
        visual_type=visual_type,
        display_name=display_name,
        role_count=len(compact.get("dataRoles", {})),
        object_count=len(objects),
        property_count=prop_count,
    )


def install_all_from_project(project: Project) -> list[InstalledCustomVisual]:
    """Find all .pbiviz files in the project and install their schemas."""
    pbiviz_files = _find_all_pbiviz_files(project)
    results = []
    for path in pbiviz_files:
        try:
            result = install_custom_visual(project, path)
            results.append(result)
        except (ValueError, KeyError, zipfile.BadZipFile):
            continue
    return results


def auto_install(project: Project) -> list[InstalledCustomVisual]:
    """Install schemas for .pbiviz files not yet registered.

    Called automatically on project load. Only writes to disk when new
    .pbiviz files are found that don't have a corresponding schema file.
    Returns the list of newly installed visuals (empty if nothing new).
    """
    installed = set(_list_installed_types(project))
    pbiviz_files = _find_all_pbiviz_files(project)
    if not pbiviz_files:
        return []

    results = []
    for path in pbiviz_files:
        try:
            caps = extract_capabilities(path)
            vtype = caps["visual_type"]
            if vtype in installed:
                continue
            result = install_custom_visual(project, path)
            results.append(result)
            installed.add(vtype)
        except (ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
            continue
    return results


# ── Schema loading (used by visual_schema.py) ─────────────────────


def load_custom_schemas(project_root: Path) -> dict[str, dict]:
    """Load all registered custom visual schemas from .pbi-custom-schemas/.

    Returns a dict of {visual_type: schema_dict} in the same compact format
    as visual_capabilities.json entries.
    """
    schema_dir = project_root / ".pbi-custom-schemas"
    if not schema_dir.is_dir():
        return {}

    schemas: dict[str, dict] = {}
    for f in schema_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            vtype = f.stem
            if "objects" in data or "dataRoles" in data:
                schemas[vtype] = data
        except (json.JSONDecodeError, OSError):
            continue
    return schemas


# ── Pbiviz extraction ─────────────────────────────────────────────


def extract_capabilities(pbiviz_path: Path) -> dict:
    """Extract capabilities from a .pbiviz zip archive.

    Returns a dict with keys: visual_type, display_name, dataRoles, objects,
    dataViewMappings (if present).
    """
    if not pbiviz_path.exists():
        raise FileNotFoundError(f"File not found: {pbiviz_path}")

    if not zipfile.is_zipfile(pbiviz_path):
        raise ValueError(f"Not a valid zip/pbiviz file: {pbiviz_path}")

    with zipfile.ZipFile(pbiviz_path, "r") as zf:
        pbiviz_json = _find_pbiviz_json(zf)
        if pbiviz_json is None:
            raise ValueError(
                f"No .pbiviz.json found in {pbiviz_path}. "
                "Expected resources/{{guid}}.pbiviz.json inside the archive."
            )

        raw = json.loads(zf.read(pbiviz_json))

    # The pbiviz.json nests capabilities under "visual" or at top level
    capabilities = (
        raw.get("capabilities")
        or raw.get("visual", {}).get("capabilities")
        or {}
    )

    visual_meta = raw.get("visual", {})
    visual_type = (
        visual_meta.get("visualClassName")
        or visual_meta.get("name")
        or pbiviz_path.stem
    )
    display_name = visual_meta.get("displayName", visual_type)

    return {
        "visual_type": visual_type,
        "display_name": display_name,
        "dataRoles": capabilities.get("dataRoles", []),
        "objects": capabilities.get("objects", {}),
        "dataViewMappings": capabilities.get("dataViewMappings", []),
    }


# ── Compact schema conversion ─────────────────────────────────────


def _capabilities_to_compact_schema(caps: dict) -> dict:
    """Convert raw capabilities to the compact schema format.

    Input dataRoles format (from capabilities.json):
        [{"name": "Category", "displayName": "Category", "kind": 0}, ...]

    Input objects format (from capabilities.json):
        {"legend": {"displayName": "Legend", "properties": {
            "show": {"type": {"bool": true}},
            "position": {"type": {"enumeration": [{"value": "Top"}, ...]}}
        }}}

    Output format (compact, matching visual_capabilities.json):
        {"objects": {"legend": {"show": "bool", "position": ["Top", ...]}},
         "dataRoles": {"Category": {"displayName": "Category", "kind": 0}}}
    """
    compact: dict = {}

    # Convert dataRoles: list of dicts → dict keyed by name
    data_roles = caps.get("dataRoles", [])
    if data_roles:
        roles_dict: dict[str, dict] = {}
        for role in data_roles:
            name = role.get("name", "")
            if not name:
                continue
            roles_dict[name] = {
                "displayName": role.get("displayName", name),
                "kind": role.get("kind", 0),
            }
        compact["dataRoles"] = roles_dict

    # Convert objects: nested property types → flat compact types
    raw_objects = caps.get("objects", {})
    if raw_objects:
        objects_dict: dict[str, dict] = {}
        for obj_name, obj_def in raw_objects.items():
            if not isinstance(obj_def, dict):
                continue
            properties = obj_def.get("properties", {})
            if not properties:
                continue
            prop_dict: dict[str, str | list[str]] = {}
            for prop_name, prop_def in properties.items():
                prop_dict[prop_name] = _convert_property_type(prop_def)
            objects_dict[obj_name] = prop_dict
        compact["objects"] = objects_dict

    return compact


def _convert_property_type(prop_def: dict) -> str | list[str]:
    """Convert a capabilities property type definition to compact form.

    Capabilities format:
        {"type": {"bool": true}}           → "bool"
        {"type": {"numeric": true}}        → "num"
        {"type": {"integer": true}}        → "int"
        {"type": {"text": true}}           → "text"
        {"type": {"fill": {"solid": ...}}} → "color"
        {"type": {"enumeration": [...]}}   → ["val1", "val2"]
        {"type": {"formatting": ...}}      → "fmt"
    """
    type_def = prop_def.get("type", {})
    if not isinstance(type_def, dict):
        return "any"

    if type_def.get("bool") is not None:
        return "bool"
    if type_def.get("numeric") is not None:
        return "num"
    if type_def.get("integer") is not None:
        return "int"
    if type_def.get("text") is not None:
        return "text"

    fill = type_def.get("fill")
    if isinstance(fill, dict):
        solid = fill.get("solid")
        if isinstance(solid, dict) and "color" in solid:
            return "color"
        return "color"

    enum = type_def.get("enumeration")
    if isinstance(enum, list):
        values = []
        for item in enum:
            if isinstance(item, dict) and "value" in item:
                values.append(str(item["value"]))
        return values if values else "any"

    if type_def.get("formatting") is not None:
        return "fmt"

    if type_def.get("scripting") is not None:
        return "text"

    return "any"


# ── Internal helpers ──────────────────────────────────────────────


def _schema_dir(project: Project) -> Path:
    """Return the custom schema storage directory for the project."""
    return project.root / ".pbi-custom-schemas"


def _list_installed_types(project: Project) -> list[str]:
    """List visual types that have a registered custom schema."""
    schema_dir = _schema_dir(project)
    if not schema_dir.is_dir():
        return []
    return [f.stem for f in schema_dir.glob("*.json")]


def _find_pbiviz_files(project: Project) -> dict[str, Path]:
    """Find .pbiviz files in the project and try to map them to visual types.

    Searches CustomVisuals/ and RegisteredResources/ directories.
    Returns a dict of {visual_type_guess: path}.
    """
    result: dict[str, Path] = {}
    for pbiviz_path in _find_all_pbiviz_files(project):
        try:
            caps = extract_capabilities(pbiviz_path)
            result[caps["visual_type"]] = pbiviz_path
        except (ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
            continue
    return result


def _find_all_pbiviz_files(project: Project) -> list[Path]:
    """Find all .pbiviz files in standard project locations."""
    paths: list[Path] = []

    # CustomVisuals/ folder
    cv_dir = project.report_folder / "CustomVisuals"
    if cv_dir.is_dir():
        paths.extend(cv_dir.rglob("*.pbiviz"))

    # RegisteredResources/ folder
    rr_dir = project.report_folder / "StaticResources" / "RegisteredResources"
    if rr_dir.is_dir():
        paths.extend(rr_dir.rglob("*.pbiviz"))

    return sorted(set(paths))


def _find_pbiviz_json(zf: zipfile.ZipFile) -> str | None:
    """Find the main .pbiviz.json file inside a zip archive.

    Looks for resources/{guid}.pbiviz.json or any *.pbiviz.json.
    Also checks for a top-level package.json that references the resource.
    """
    # Direct match: resources/*.pbiviz.json
    for name in zf.namelist():
        if name.endswith(".pbiviz.json"):
            return name

    # Fallback: look for package.json referencing a resource
    if "package.json" in zf.namelist():
        try:
            pkg = json.loads(zf.read("package.json"))
            resources = pkg.get("resources", [])
            if isinstance(resources, list):
                for res in resources:
                    if isinstance(res, dict) and "file" in res:
                        candidate = res["file"]
                        if candidate in zf.namelist():
                            return candidate
        except (json.JSONDecodeError, KeyError):
            pass

    return None
