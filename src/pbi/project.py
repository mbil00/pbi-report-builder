"""PBIP project discovery, navigation, and I/O."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


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
                report_path = root / artifact["report"].get("path", "")
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
        pages_dir = self.definition_folder / "pages"
        if not pages_dir.exists():
            return []

        pages = []
        for page_dir in pages_dir.iterdir():
            if not page_dir.is_dir():
                continue
            page_json = page_dir / "page.json"
            if page_json.exists():
                pages.append(Page(folder=page_dir, data=_read_json(page_json)))

        # Sort by page order from pages.json
        meta = self.get_pages_meta()
        order = meta.get("pageOrder", [])
        if order:
            order_map = {name: i for i, name in enumerate(order)}
            pages.sort(key=lambda p: order_map.get(p.name, 999))
        else:
            pages.sort(key=lambda p: p.name)

        return pages

    def find_page(self, identifier: str) -> Page:
        """Find a page by display name, folder name, or partial match."""
        pages = self.get_pages()

        # Exact folder name
        for page in pages:
            if page.name == identifier:
                return page

        # Exact display name (case-insensitive)
        id_lower = identifier.lower()
        for page in pages:
            if page.display_name.lower() == id_lower:
                return page

        # Partial display name match
        matches = [p for p in pages if id_lower in p.display_name.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(f'"{p.display_name}"' for p in matches)
            raise ValueError(
                f'Ambiguous page "{identifier}". Matches: {names}'
            )

        # Index-based access (1-based)
        try:
            idx = int(identifier) - 1
            if 0 <= idx < len(pages):
                return pages[idx]
        except ValueError:
            pass

        available = ", ".join(f'"{p.display_name}"' for p in pages)
        raise ValueError(f'Page "{identifier}" not found. Available: {available}')

    def get_visuals(self, page: Page) -> list[Visual]:
        """Get all visuals on a page."""
        visuals_dir = page.folder / "visuals"
        if not visuals_dir.exists():
            return []

        visuals = []
        for visual_dir in visuals_dir.iterdir():
            if not visual_dir.is_dir():
                continue
            visual_json = visual_dir / "visual.json"
            if visual_json.exists():
                visuals.append(
                    Visual(folder=visual_dir, data=_read_json(visual_json))
                )

        # Sort by z-order, then by position
        visuals.sort(
            key=lambda v: (
                v.position.get("y", 0),
                v.position.get("x", 0),
            )
        )
        return visuals

    def find_visual(self, page: Page, identifier: str) -> Visual:
        """Find a visual by name, type, folder name, or index."""
        visuals = self.get_visuals(page)

        # Exact folder name
        for v in visuals:
            if v.folder.name == identifier:
                return v

        # Exact internal name
        for v in visuals:
            if v.name == identifier:
                return v

        id_lower = identifier.lower()

        # By visual type (if unique on page)
        type_matches = [v for v in visuals if v.visual_type.lower() == id_lower]
        if len(type_matches) == 1:
            return type_matches[0]

        # Partial name match
        matches = [v for v in visuals if id_lower in v.name.lower()]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            names = ", ".join(f'"{v.name}" ({v.visual_type})' for v in matches)
            raise ValueError(
                f'Ambiguous visual "{identifier}". Matches: {names}'
            )

        # Index-based (1-based)
        try:
            idx = int(identifier) - 1
            if 0 <= idx < len(visuals):
                return visuals[idx]
        except ValueError:
            pass

        available = ", ".join(
            f'{i+1}: {v.name} ({v.visual_type})'
            for i, v in enumerate(visuals)
        )
        raise ValueError(
            f'Visual "{identifier}" not found on "{page.display_name}". '
            f"Available: {available}"
        )


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
