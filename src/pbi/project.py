"""PBIP project discovery, navigation, and I/O."""

from __future__ import annotations

import json
import re
import secrets
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from pbi.lookup import find_page_by_identifier, find_visual_by_identifier
from pbi.schema_refs import (
    PAGE_SCHEMA,
    PAGES_METADATA_SCHEMA,
    VISUAL_CONTAINER_SCHEMA,
)


_UNSAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")


def sanitize_visual_name(name: str) -> str:
    """Sanitize a visual name to be identifier-safe for Power BI.

    Replaces spaces, colons, and other non-alphanumeric characters with hyphens.
    Returns kebab-case string safe for the ``name`` field in visual.json.
    """
    safe = _UNSAFE_NAME_RE.sub("-", name).strip("-")
    # Collapse runs of hyphens
    safe = re.sub(r"-{2,}", "-", safe)
    return safe or name


@dataclass
class Visual:
    """A visual on a report page."""

    folder: Path
    data: dict

    @property
    def name(self) -> str:
        return self.data.get("name", self.folder.name)

    @property
    def visual_type(self) -> str:
        return self.data.get("visual", {}).get("visualType", "unknown")

    @property
    def position(self) -> dict:
        return self.data.get("position", {})

    def save(self) -> None:
        path = self.folder / "visual.json"
        _write_json(path, self.data)


@dataclass
class Page:
    """A report page."""

    folder: Path
    data: dict

    @property
    def name(self) -> str:
        return self.folder.name

    @property
    def display_name(self) -> str:
        return self.data.get("displayName", self.name)

    @property
    def width(self) -> int:
        return self.data.get("width", 0)

    @property
    def height(self) -> int:
        return self.data.get("height", 0)

    @property
    def display_option(self) -> str:
        return self.data.get("displayOption", "FitToPage")

    @property
    def visibility(self) -> str:
        return self.data.get("visibility", "AlwaysVisible")

    def save(self) -> None:
        path = self.folder / "page.json"
        _write_json(path, self.data)


@dataclass
class Project:
    """A PBIP project."""

    root: Path
    pbip_file: Path
    report_folder: Path
    definition_folder: Path
    _pages_cache: list[Page] | None = field(default=None, init=False, repr=False)
    _visuals_cache: dict[Path, list[Visual]] = field(default_factory=dict, init=False, repr=False)

    @classmethod
    def find(cls, path: str | Path | None = None) -> Project:
        """Find a PBIP project by searching the given path and its parents."""
        if path is None:
            path = Path.cwd()
        path = Path(path).resolve()

        if path.is_file() and path.suffix == ".pbip":
            return cls._from_pbip(path)

        search_dir = path if path.is_dir() else path.parent
        while True:
            pbip_files = list(search_dir.glob("*.pbip"))
            if pbip_files:
                return cls._from_pbip(pbip_files[0])
            parent = search_dir.parent
            if parent == search_dir:
                break
            search_dir = parent

        raise FileNotFoundError(f"No .pbip file found in or above {path}")

    @classmethod
    def _from_pbip(cls, pbip_file: Path) -> Project:
        root = pbip_file.parent

        # Parse .pbip to find report path
        pbip_data = _read_json(pbip_file)
        report_path = None
        for artifact in pbip_data.get("artifacts", []):
            if "report" in artifact:
                raw_report_path = artifact["report"].get("path", "")
                if raw_report_path:
                    report_path = _resolve_within_root(
                        root,
                        raw_report_path,
                        label="Report artifact path",
                    )
                break

        # Fallback: search for .Report folder
        if report_path is None or not report_path.exists():
            report_folders = list(root.glob("*.Report"))
            if not report_folders:
                raise FileNotFoundError(f"No .Report folder found in {root}")
            report_path = report_folders[0]

        definition_folder = report_path / "definition"
        if not definition_folder.exists():
            raise FileNotFoundError(
                f"PBIR definition/ not found in {report_path}. "
                "Only PBIR format is supported."
            )

        return cls(
            root=root,
            pbip_file=pbip_file,
            report_folder=report_path,
            definition_folder=definition_folder,
        )

    @property
    def project_name(self) -> str:
        return self.pbip_file.stem

    def _invalidate_pages_cache(self) -> None:
        self._pages_cache = None

    def clear_caches(self) -> None:
        """Drop any loaded page/visual state so subsequent reads hit disk."""
        self._pages_cache = None
        self._visuals_cache.clear()

    def _visual_cache_key(self, page: Page | Path) -> Path:
        return page.folder if isinstance(page, Page) else page

    def _invalidate_visuals_cache(self, page: Page | Path) -> None:
        self._visuals_cache.pop(self._visual_cache_key(page), None)

    def _get_pages_cached(self) -> list[Page]:
        if self._pages_cache is not None:
            return self._pages_cache

        pages_dir = self.definition_folder / "pages"
        if not pages_dir.exists():
            self._pages_cache = []
            return self._pages_cache

        pages = []
        for page_dir in pages_dir.iterdir():
            if not page_dir.is_dir():
                continue
            page_json = page_dir / "page.json"
            if page_json.exists():
                pages.append(Page(folder=page_dir, data=_read_json(page_json)))

        meta = self.get_pages_meta()
        order = meta.get("pageOrder", [])
        if order:
            order_map = {name: i for i, name in enumerate(order)}
            pages.sort(key=lambda p: order_map.get(p.name, 999))
        else:
            pages.sort(key=lambda p: p.name)

        self._pages_cache = pages
        return self._pages_cache

    def _get_visuals_cached(self, page: Page) -> list[Visual]:
        key = self._visual_cache_key(page)
        cached = self._visuals_cache.get(key)
        if cached is not None:
            return cached

        visuals_dir = page.folder / "visuals"
        if not visuals_dir.exists():
            self._visuals_cache[key] = []
            return self._visuals_cache[key]

        visuals = []
        for visual_dir in visuals_dir.iterdir():
            if not visual_dir.is_dir():
                continue
            visual_json = visual_dir / "visual.json"
            if visual_json.exists():
                visuals.append(
                    Visual(folder=visual_dir, data=_read_json(visual_json))
                )

        visuals.sort(
            key=lambda v: (
                v.position.get("y", 0),
                v.position.get("x", 0),
            )
        )
        self._visuals_cache[key] = visuals
        return self._visuals_cache[key]

    def get_report_meta(self) -> dict:
        """Read the report-level metadata (definition/report.json)."""
        path = self.definition_folder / "report.json"
        if path.exists():
            return _read_json(path)
        return {}

    def get_pages_meta(self) -> dict:
        """Read the pages metadata (page order, active page)."""
        path = self.definition_folder / "pages" / "pages.json"
        if path.exists():
            return _read_json(path)
        return {}

    def get_pages(self) -> list[Page]:
        """Get all pages, ordered by page order if available."""
        return list(self._get_pages_cached())

    def find_page(self, identifier: str) -> Page:
        """Find a page by display name, folder name, or partial match."""
        return find_page_by_identifier(
            self._get_pages_cached(),
            identifier,
            folder_name=lambda page: page.name,
            display_name=lambda page: page.display_name,
        )

    def get_visuals(self, page: Page) -> list[Visual]:
        """Get all visuals on a page."""
        return list(self._get_visuals_cached(page))

    def find_visual(self, page: Page, identifier: str) -> Visual:
        """Find a visual by name, type, folder name, or index."""
        return find_visual_by_identifier(
            self._get_visuals_cached(page),
            identifier,
            page_display_name=page.display_name,
            folder_name=lambda visual: visual.folder.name,
            visual_name=lambda visual: visual.name,
            visual_type=lambda visual: visual.visual_type,
        )


    # ── Page CRUD ──────────────────────────────────────────────

    def create_page(
        self,
        display_name: str,
        width: int = 1280,
        height: int = 720,
        display_option: str = "FitToPage",
    ) -> Page:
        """Create a new page."""
        page_id = secrets.token_hex(10)
        page_dir = self.definition_folder / "pages" / page_id
        page_dir.mkdir(parents=True)
        (page_dir / "visuals").mkdir()

        data = {
            "$schema": PAGE_SCHEMA,
            "name": page_id,
            "displayName": display_name,
            "displayOption": display_option,
            "width": width,
            "height": height,
            "visibility": "AlwaysVisible",
        }
        _write_json(page_dir / "page.json", data)
        self._add_to_page_order(page_id)
        page = Page(folder=page_dir, data=data)
        self._visuals_cache[page_dir] = []
        return page

    def copy_page(self, source: Page, new_name: str) -> Page:
        """Deep-copy a page and all its visuals."""
        new_id = secrets.token_hex(10)
        new_dir = self.definition_folder / "pages" / new_id
        shutil.copytree(source.folder, new_dir)

        # Update page identity
        new_data = _read_json(new_dir / "page.json")
        new_data["name"] = new_id
        new_data["displayName"] = new_name
        _write_json(new_dir / "page.json", new_data)

        # Give each visual a new unique folder but preserve friendly names
        visuals_dir = new_dir / "visuals"
        if visuals_dir.exists():
            for visual_dir in list(visuals_dir.iterdir()):
                if not visual_dir.is_dir():
                    continue
                new_visual_id = secrets.token_hex(10)
                new_visual_dir = visuals_dir / new_visual_id
                visual_dir.rename(new_visual_dir)
                visual_json = new_visual_dir / "visual.json"
                if visual_json.exists():
                    vdata = _read_json(visual_json)
                    # Preserve the original friendly name if it differs
                    # from the old folder name (i.e. user set a custom name)
                    old_name = vdata.get("name", "")
                    old_folder = visual_dir.name
                    if old_name == old_folder:
                        # No custom name — use new ID
                        vdata["name"] = new_visual_id
                    # else: keep the existing friendly name
                    _write_json(visual_json, vdata)

        self._add_to_page_order(new_id)
        self._invalidate_visuals_cache(new_dir)
        return Page(folder=new_dir, data=new_data)

    def delete_page(self, page: Page) -> None:
        """Delete a page and all its visuals."""
        shutil.rmtree(page.folder)
        self._invalidate_visuals_cache(page)
        self._remove_from_page_order(page.name)

    def _add_to_page_order(self, page_id: str) -> None:
        meta_path = self.definition_folder / "pages" / "pages.json"
        if meta_path.exists():
            meta = _read_json(meta_path)
        else:
            meta = {
                "$schema": PAGES_METADATA_SCHEMA,
            }
        meta.setdefault("pageOrder", []).append(page_id)
        _write_json(meta_path, meta)
        self._invalidate_pages_cache()

    def _remove_from_page_order(self, page_id: str) -> None:
        meta_path = self.definition_folder / "pages" / "pages.json"
        if not meta_path.exists():
            return
        meta = _read_json(meta_path)
        order = meta.get("pageOrder", [])
        if page_id in order:
            order.remove(page_id)
            meta["pageOrder"] = order
        # If deleted page was active, set first remaining page as active
        if meta.get("activePageName") == page_id and order:
            meta["activePageName"] = order[0]
        _write_json(meta_path, meta)
        self._invalidate_pages_cache()

    def set_page_order(self, page_ids: list[str]) -> None:
        """Overwrite the page order with a new sequence of page folder IDs."""
        meta_path = self.definition_folder / "pages" / "pages.json"
        meta = _read_json(meta_path) if meta_path.exists() else {"$schema": PAGES_METADATA_SCHEMA}
        meta["pageOrder"] = page_ids
        _write_json(meta_path, meta)
        self._invalidate_pages_cache()

    def set_active_page(self, page_id: str) -> None:
        """Set the active (default-open) page by folder ID."""
        meta_path = self.definition_folder / "pages" / "pages.json"
        meta = _read_json(meta_path) if meta_path.exists() else {"$schema": PAGES_METADATA_SCHEMA}
        meta["activePageName"] = page_id
        _write_json(meta_path, meta)

    # ── Visual CRUD ────────────────────────────────────────────

    def create_visual(
        self,
        page: Page,
        visual_type: str,
        x: int = 0,
        y: int = 0,
        width: int = 300,
        height: int = 200,
    ) -> Visual:
        """Create a new visual on a page with type-aware scaffolding."""
        from pbi.roles import get_visual_roles

        visual_id = secrets.token_hex(10)
        visual_dir = page.folder / "visuals" / visual_id
        visual_dir.mkdir(parents=True, exist_ok=True)

        # Determine z-order (above existing visuals)
        existing = self._get_visuals_cached(page)
        max_z = max((v.position.get("z", 0) for v in existing), default=0)

        # Scaffold queryState with empty role projections for the visual type
        roles = get_visual_roles(visual_type)
        query_state: dict = {}
        for role in roles:
            query_state[role["name"]] = {"projections": []}

        data = {
            "$schema": VISUAL_CONTAINER_SCHEMA,
            "name": visual_id,
            "position": {
                "x": x,
                "y": y,
                "width": width,
                "height": height,
                "z": max_z + 1000,
                "tabOrder": len(existing),
            },
            "visual": {
                "visualType": visual_type,
                "query": {"queryState": query_state},
                "objects": {},
            },
        }
        _write_json(visual_dir / "visual.json", data)
        visual = Visual(folder=visual_dir, data=data)
        existing.append(visual)
        existing.sort(
            key=lambda v: (
                v.position.get("y", 0),
                v.position.get("x", 0),
            )
        )
        return visual

    def copy_visual(
        self,
        source: Visual,
        target_page: Page,
        new_name: str | None = None,
    ) -> Visual:
        """Copy a visual, optionally to a different page."""
        new_id = secrets.token_hex(10)
        new_dir = target_page.folder / "visuals" / new_id
        shutil.copytree(source.folder, new_dir)

        new_data = _read_json(new_dir / "visual.json")
        new_data["name"] = sanitize_visual_name(new_name) if new_name else new_id
        _write_json(new_dir / "visual.json", new_data)
        self._invalidate_visuals_cache(target_page)
        return Visual(folder=new_dir, data=new_data)

    def delete_visual(self, visual: Visual) -> None:
        """Delete a visual."""
        self._invalidate_visuals_cache(visual.folder.parent.parent)
        shutil.rmtree(visual.folder)

    # ── Visual grouping ─────────────────────────────────────────

    def create_group(
        self,
        page: Page,
        visuals: list[Visual],
        display_name: str | None = None,
    ) -> Visual:
        """Group visuals together. Returns the group container visual.

        Creates a group container that encompasses all provided visuals
        and sets parentGroupName on each child.
        """
        if len(visuals) < 2:
            raise ValueError("Need at least 2 visuals to group")

        # Check none are already in a group
        for v in visuals:
            if v.data.get("parentGroupName"):
                raise ValueError(
                    f'Visual "{v.name}" is already in group '
                    f'"{v.data["parentGroupName"]}"'
                )
            if "visualGroup" in v.data:
                raise ValueError(f'"{v.name}" is a group container, not a visual')

        # Calculate bounding box from children
        min_x = min(v.position.get("x", 0) for v in visuals)
        min_y = min(v.position.get("y", 0) for v in visuals)
        max_x = max(
            v.position.get("x", 0) + v.position.get("width", 0)
            for v in visuals
        )
        max_y = max(
            v.position.get("y", 0) + v.position.get("height", 0)
            for v in visuals
        )
        max_z = max(v.position.get("z", 0) for v in visuals)

        # Create group container
        group_id = secrets.token_hex(10)
        group_dir = page.folder / "visuals" / group_id
        group_dir.mkdir(parents=True, exist_ok=True)

        safe_name = sanitize_visual_name(display_name) if display_name else group_id

        group_data = {
            "$schema": VISUAL_CONTAINER_SCHEMA,
            "name": safe_name,
            "position": {
                "x": min_x,
                "y": min_y,
                "width": max_x - min_x,
                "height": max_y - min_y,
                "z": max_z + 1,
                "tabOrder": 0,
            },
            "visualGroup": {
                "displayName": display_name or group_id,
                "groupMode": "ScaleMode",
                "objects": {},
            },
        }
        _write_json(group_dir / "visual.json", group_data)

        # Update children to reference the group
        group_name = group_data["name"]
        for v in visuals:
            v.data["parentGroupName"] = group_name
            v.save()

        self._invalidate_visuals_cache(page)
        return Visual(folder=group_dir, data=group_data)

    def ungroup(self, page: Page, group: Visual) -> list[Visual]:
        """Ungroup a visual group. Returns the freed child visuals."""
        if "visualGroup" not in group.data:
            raise ValueError(f'"{group.name}" is not a group')

        group_name = group.name
        children = []
        for v in self.get_visuals(page):
            if v.data.get("parentGroupName") == group_name:
                v.data.pop("parentGroupName", None)
                v.save()
                children.append(v)

        # Delete the group container
        self.delete_visual(group)
        self._invalidate_visuals_cache(page)
        return children

    # ── Data bindings ──────────────────────────────────────────

    @staticmethod
    def add_binding(
        visual: Visual,
        role: str,
        entity: str,
        prop: str,
        field_type: str = "column",
        display_name: str | None = None,
    ) -> None:
        """Add a data binding (column or measure) to a visual's query."""
        field_key = "Column" if field_type == "column" else "Measure"
        projection = {
            "field": {
                field_key: {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop,
                }
            },
            "queryRef": f"{entity}.{prop}",
            "nativeQueryRef": prop,
        }
        if display_name:
            projection["displayName"] = display_name

        query_state = (
            visual.data
            .setdefault("visual", {})
            .setdefault("query", {})
            .setdefault("queryState", {})
        )
        role_config = query_state.setdefault(role, {"projections": []})
        role_config["projections"].append(projection)
        visual.save()

    @staticmethod
    def remove_binding(
        visual: Visual,
        role: str,
        field_ref: str | None = None,
    ) -> int:
        """Remove bindings from a visual. Returns count of removed bindings.

        If field_ref is given (e.g. 'Product.Category'), removes that specific
        binding. Otherwise removes the entire role.
        """
        query_state = (
            visual.data
            .get("visual", {})
            .get("query", {})
            .get("queryState", {})
        )
        if role not in query_state:
            return 0

        if field_ref is None:
            removed = len(query_state[role].get("projections", []))
            del query_state[role]
            visual.save()
            return removed

        projections = query_state[role].get("projections", [])
        original_count = len(projections)
        # Collect queryRefs being removed for metadata cleanup
        removed_refs = [
            p.get("queryRef", "")
            for p in projections
            if p.get("queryRef", "").lower() == field_ref.lower()
        ]
        query_state[role]["projections"] = [
            p for p in projections
            if p.get("queryRef", "").lower() != field_ref.lower()
        ]
        removed = original_count - len(query_state[role]["projections"])
        if not query_state[role]["projections"]:
            del query_state[role]
        # Clean up orphaned column metadata (widths, formatting)
        if removed_refs:
            from pbi.columns import clear_column_width, clear_column_format
            for ref in removed_refs:
                clear_column_width(visual, ref)
                clear_column_format(visual, ref)
        visual.save()
        return removed

    @staticmethod
    def get_bindings(visual: Visual) -> list[tuple[str, str, str, str]]:
        """Get all bindings as (role, entity, property, field_type) tuples."""
        query_state = (
            visual.data
            .get("visual", {})
            .get("query", {})
            .get("queryState", {})
        )
        bindings = []
        for role, config in query_state.items():
            for proj in config.get("projections", []):
                field_data = proj.get("field", {})
                entity, prop, field_type = _resolve_projection_field(field_data)
                if entity != "?":
                    bindings.append((role, entity, prop, field_type))
        return bindings

    # ── Sort definitions ──────────────────────────────────────────

    @staticmethod
    def set_sort(
        visual: Visual,
        entity: str,
        prop: str,
        field_type: str = "column",
        descending: bool = True,
    ) -> None:
        """Set the sort definition on a visual."""
        field_key = "Column" if field_type == "column" else "Measure"
        sort_entry = {
            "field": {
                field_key: {
                    "Expression": {"SourceRef": {"Entity": entity}},
                    "Property": prop,
                }
            },
            "direction": "Descending" if descending else "Ascending",
        }

        query = (
            visual.data
            .setdefault("visual", {})
            .setdefault("query", {})
        )
        query["sortDefinition"] = {
            "sort": [sort_entry],
            "isDefaultSort": False,
        }
        visual.save()

    @staticmethod
    def clear_sort(visual: Visual) -> bool:
        """Remove sort definition from a visual. Returns True if one was removed."""
        query = visual.data.get("visual", {}).get("query", {})
        if "sortDefinition" in query:
            del query["sortDefinition"]
            visual.save()
            return True
        return False

    @staticmethod
    def get_sort(visual: Visual) -> list[tuple[str, str, str, str]]:
        """Get sort definitions as (entity, property, field_type, direction) tuples."""
        sort_def = (
            visual.data
            .get("visual", {})
            .get("query", {})
            .get("sortDefinition", {})
        )
        result = []
        for entry in sort_def.get("sort", []):
            field_data = entry.get("field", {})
            direction = entry.get("direction", "Ascending")
            entity, prop, ftype = _resolve_projection_field(field_data)
            if entity != "?":
                result.append((entity, prop, ftype, direction))
        return result


def _resolve_projection_field(field_data: dict) -> tuple[str, str, str]:
    """Extract (entity, property, field_type) from a query projection field.

    Handles Column, Measure, and Aggregation (Sum, Min, Count, etc.) field types.
    Returns ("?", "?", "column") if the field type is unrecognized.
    """
    for key, ftype in [("Column", "column"), ("Measure", "measure")]:
        if key in field_data:
            entity = field_data[key]["Expression"]["SourceRef"]["Entity"]
            prop = field_data[key]["Property"]
            return entity, prop, ftype

    if "Aggregation" in field_data:
        inner = field_data["Aggregation"].get("Expression", {})
        for key in ("Column", "Measure"):
            if key in inner:
                entity = inner[key]["Expression"]["SourceRef"]["Entity"]
                prop = inner[key]["Property"]
                return entity, prop, "aggregation"

    return "?", "?", "column"

def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _resolve_within_root(root: Path, raw_path: str, *, label: str) -> Path:
    """Resolve a project-relative path and reject escapes outside the root."""
    base = root.resolve()
    candidate = Path(raw_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"{label} must stay within the project root: {raw_path}")
    return resolved
