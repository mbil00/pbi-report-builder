"""PBIP project discovery, navigation, and I/O."""

from __future__ import annotations

import json
import re
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from pathlib import Path

from pbi.lookup import find_page_by_identifier, find_visual_by_identifier


_UNSAFE_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]")
_JSON_PRETTY: ContextVar[bool] = ContextVar("pbi_json_pretty", default=True)


def set_json_pretty(pretty: bool) -> Token[bool]:
    """Set the default PBIR JSON write format for the current context."""
    return _JSON_PRETTY.set(pretty)


def reset_json_pretty(token: Token[bool]) -> None:
    """Restore the previous PBIR JSON write format for the current context."""
    _JSON_PRETTY.reset(token)


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

    def save(self, *, pretty: bool | None = None) -> None:
        path = self.folder / "visual.json"
        _write_json(path, self.data, pretty=pretty)


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

    def save(self, *, pretty: bool | None = None) -> None:
        path = self.folder / "page.json"
        _write_json(path, self.data, pretty=pretty)


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

    def stage_page_in_cache(self, page: Page) -> None:
        """Add an in-memory page before it exists on disk.

        Buffered/session write paths use this so project lookups can see staged
        pages before commit without reaching into cache internals directly.
        """
        self._get_pages_cached().append(page)
        self._visuals_cache[page.folder] = []

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


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(path: Path, data: dict, *, pretty: bool | None = None) -> None:
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        if pretty is None:
            pretty = _JSON_PRETTY.get()
        if pretty:
            json.dump(data, f, indent=2, ensure_ascii=False, check_circular=False)
        else:
            json.dump(
                data,
                f,
                ensure_ascii=False,
                check_circular=False,
                separators=(",", ":"),
            )
        f.write("\n")


def _resolve_within_root(root: Path, raw_path: str, *, label: str) -> Path:
    """Resolve a project-relative path and reject escapes outside the root."""
    base = root.resolve()
    candidate = Path(raw_path)
    resolved = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    if resolved != base and base not in resolved.parents:
        raise ValueError(f"{label} must stay within the project root: {raw_path}")
    return resolved
