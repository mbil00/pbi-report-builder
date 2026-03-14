"""PBIP project discovery, navigation, and I/O."""

from __future__ import annotations

import json
import secrets
import shutil
from dataclasses import dataclass
from pathlib import Path

from pbi.schema_refs import (
    PAGE_SCHEMA,
    PAGES_METADATA_SCHEMA,
    VISUAL_CONTAINER_SCHEMA,
)


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
        raw_identifier = identifier
        if identifier.startswith(("#", "@")):
            identifier = identifier[1:]

        # Exact folder name
        for v in visuals:
            if v.folder.name == identifier:
                return v

        # Exact internal name
        for v in visuals:
            if v.name == identifier:
                return v

        # Index-based (1-based). Prefer explicit numeric references before
        # partial matching so the indices shown by `visual list` are usable.
        try:
            idx = int(identifier) - 1
            if 0 <= idx < len(visuals):
                return visuals[idx]
        except ValueError:
            pass

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

        available = ", ".join(
            f'{i+1}: {v.name} ({v.visual_type})'
            for i, v in enumerate(visuals)
        )
        raise ValueError(
            f'Visual "{raw_identifier}" not found on "{page.display_name}". '
            f"Available: {available}"
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
        return Page(folder=page_dir, data=data)

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

        # Give each visual a new unique name
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
                    vdata["name"] = new_visual_id
                    _write_json(visual_json, vdata)

        self._add_to_page_order(new_id)
        return Page(folder=new_dir, data=_read_json(new_dir / "page.json"))

    def delete_page(self, page: Page) -> None:
        """Delete a page and all its visuals."""
        shutil.rmtree(page.folder)
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
        """Create a new visual on a page."""
        visual_id = secrets.token_hex(10)
        visual_dir = page.folder / "visuals" / visual_id
        visual_dir.mkdir(parents=True, exist_ok=True)

        # Determine z-order (above existing visuals)
        existing = self.get_visuals(page)
        max_z = max((v.position.get("z", 0) for v in existing), default=0)

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
                "query": {"queryState": {}},
                "objects": _card_scaffold() if visual_type == "cardVisual" else {},
            },
        }
        _write_json(visual_dir / "visual.json", data)
        return Visual(folder=visual_dir, data=data)

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
        new_data["name"] = new_name or new_id
        _write_json(new_dir / "visual.json", new_data)
        return Visual(folder=new_dir, data=new_data)

    def delete_visual(self, visual: Visual) -> None:
        """Delete a visual."""
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

        group_data = {
            "$schema": VISUAL_CONTAINER_SCHEMA,
            "name": display_name or group_id,
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
            "nativeQueryRef": display_name or prop,
        }

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
        query_state[role]["projections"] = [
            p for p in projections
            if p.get("queryRef", "").lower() != field_ref.lower()
        ]
        removed = original_count - len(query_state[role]["projections"])
        if not query_state[role]["projections"]:
            del query_state[role]
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


def _card_scaffold() -> dict:
    """Generate a complete cardVisual objects scaffold.

    Produces the full multi-entry structure needed for card visuals to render
    correctly: layout (global + per-card), value (show + defaults), label,
    divider, shapeCustomRectangle, overflow, border, shadow, and padding.
    """
    _lit = lambda v: {"expr": {"Literal": {"Value": v}}}
    _sel_default = {"id": "default"}

    return {
        "layout": [
            {
                "properties": {
                    "style": _lit("'Cards'"),
                    "autoGrid": _lit("true"),
                    "alignment": _lit("'middle'"),
                    "orientation": _lit("2D"),
                },
            },
            {
                "properties": {
                    "paddingUniform": _lit("6L"),
                    "backgroundShow": _lit("false"),
                },
                "selector": _sel_default,
            },
        ],
        "value": [
            {
                "properties": {
                    "show": _lit("true"),
                },
            },
            {
                "properties": {
                    "horizontalAlignment": _lit("'center'"),
                },
                "selector": _sel_default,
            },
        ],
        "label": [
            {
                "properties": {
                    "show": _lit("true"),
                    "fontSize": _lit("10D"),
                },
                "selector": _sel_default,
            },
        ],
        "divider": [
            {
                "properties": {
                    "show": _lit("true"),
                },
                "selector": _sel_default,
            },
        ],
        "shapeCustomRectangle": [
            {
                "properties": {
                    "rectangleRoundedCurve": _lit("5L"),
                    "tileShape": _lit("true"),
                },
                "selector": _sel_default,
            },
        ],
        "padding": [
            {
                "properties": {
                    "paddingUniform": _lit("7L"),
                },
                "selector": _sel_default,
            },
        ],
        "overFlow": [
            {
                "properties": {
                    "overFlowStyle": _lit("1D"),
                    "overFlowDirection": _lit("0D"),
                },
            },
        ],
        "border": [
            {
                "properties": {
                    "show": _lit("false"),
                },
                "selector": _sel_default,
            },
        ],
        "shadowCustom": [
            {
                "properties": {
                    "show": _lit("false"),
                },
                "selector": _sel_default,
            },
        ],
    }


def _read_json(path: Path) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def _write_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="\r\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
