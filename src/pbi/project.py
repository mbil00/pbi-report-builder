"""PBIP project discovery, navigation, and I/O."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pbi.lookup import find_page_by_identifier, find_visual_by_identifier


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
        from pbi.page_authoring import create_page as _create_page

        return _create_page(
            self,
            display_name,
            width=width,
            height=height,
            display_option=display_option,
        )

    def copy_page(self, source: Page, new_name: str) -> Page:
        """Deep-copy a page and all its visuals."""
        from pbi.page_authoring import copy_page as _copy_page

        return _copy_page(self, source, new_name)

    def delete_page(self, page: Page) -> None:
        """Delete a page and all its visuals."""
        from pbi.page_authoring import delete_page as _delete_page

        _delete_page(self, page)

    def _add_to_page_order(self, page_id: str) -> None:
        from pbi.page_authoring import add_page_to_order

        add_page_to_order(self, page_id)

    def _remove_from_page_order(self, page_id: str) -> None:
        from pbi.page_authoring import remove_page_from_order

        remove_page_from_order(self, page_id)

    def set_page_order(self, page_ids: list[str]) -> None:
        """Overwrite the page order with a new sequence of page folder IDs."""
        from pbi.page_authoring import set_page_order as _set_page_order

        _set_page_order(self, page_ids)

    def set_active_page(self, page_id: str) -> None:
        """Set the active (default-open) page by folder ID."""
        from pbi.page_authoring import set_active_page as _set_active_page

        _set_active_page(self, page_id)

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
        from pbi.visual_authoring import create_visual as _create_visual

        return _create_visual(
            self,
            page,
            visual_type,
            x=x,
            y=y,
            width=width,
            height=height,
        )

    def copy_visual(
        self,
        source: Visual,
        target_page: Page,
        new_name: str | None = None,
    ) -> Visual:
        """Copy a visual, optionally to a different page."""
        from pbi.visual_authoring import copy_visual as _copy_visual

        return _copy_visual(self, source, target_page, new_name=new_name)

    def delete_visual(self, visual: Visual) -> None:
        """Delete a visual."""
        from pbi.visual_authoring import delete_visual as _delete_visual

        _delete_visual(self, visual)

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
        from pbi.visual_groups import create_group as _create_group

        return _create_group(self, page, visuals, display_name=display_name)

    def create_group_container(
        self,
        page: Page,
        *,
        name: str | None = None,
        display_name: str | None = None,
        x: int = 0,
        y: int = 0,
        width: int = 0,
        height: int = 0,
    ) -> Visual:
        """Create an empty visual group container."""
        from pbi.visual_groups import create_group_container as _create_group_container

        return _create_group_container(
            self,
            page,
            name=name,
            display_name=display_name,
            x=x,
            y=y,
            width=width,
            height=height,
        )

    def ungroup(self, page: Page, group: Visual) -> list[Visual]:
        """Ungroup a visual group. Returns the freed child visuals."""
        from pbi.visual_groups import ungroup as _ungroup

        return _ungroup(self, page, group)

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
        from pbi.visual_queries import add_binding as _add_binding

        _add_binding(visual, role, entity, prop, field_type=field_type, display_name=display_name)

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
        from pbi.visual_queries import remove_binding as _remove_binding

        return _remove_binding(visual, role, field_ref=field_ref)

    @staticmethod
    def get_bindings(visual: Visual) -> list[tuple[str, str, str, str]]:
        """Get all bindings as (role, entity, property, field_type) tuples."""
        from pbi.visual_queries import get_bindings as _get_bindings

        return _get_bindings(visual)

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
        from pbi.visual_queries import set_sort as _set_sort

        _set_sort(visual, entity, prop, field_type=field_type, descending=descending)

    @staticmethod
    def clear_sort(visual: Visual) -> bool:
        """Remove sort definition from a visual. Returns True if one was removed."""
        from pbi.visual_queries import clear_sort as _clear_sort

        return _clear_sort(visual)

    @staticmethod
    def get_sort(visual: Visual) -> list[tuple[str, str, str, str]]:
        """Get sort definitions as (entity, property, field_type, direction) tuples."""
        from pbi.visual_queries import get_sort as _get_sort

        return _get_sort(visual)

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
