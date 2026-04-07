"""Unified reusable asset catalog over existing stored asset kinds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pbi.project import Project


CATALOG_KINDS = ("visual", "style", "component", "page")
CATALOG_SCOPES = ("project", "global", "bundled")


@dataclass(frozen=True)
class CatalogItem:
    """One reusable asset exposed through the shared catalog."""

    kind: str
    name: str
    scope: str
    path: Path
    description: str | None = None
    category: str | None = None
    tags: tuple[str, ...] = ()
    summary: dict[str, Any] | None = None

    def to_row(self) -> dict[str, Any]:
        """Return a stable CLI/JSON row."""
        row = {
            "kind": self.kind,
            "name": self.name,
            "scope": self.scope,
            "description": self.description or "",
            "category": self.category or "",
            "tags": list(self.tags),
            "path": str(self.path),
        }
        if self.summary:
            row.update(self.summary)
        return row


@dataclass(frozen=True)
class CatalogValidationIssue:
    """One validation issue discovered while scanning the catalog."""

    kind: str
    scope: str
    path: Path
    message: str

    def to_row(self) -> dict[str, str]:
        """Return a stable CLI/JSON row."""
        return {
            "kind": self.kind,
            "scope": self.scope,
            "path": str(self.path),
            "message": self.message,
        }


class CatalogHandler(Protocol):
    """Per-kind catalog adapter."""

    kind: str

    def list_items(self, project: Project | None, *, scope: str | None = None) -> list[CatalogItem]:
        """List items of this kind."""

    def get_item(self, project: Project | None, name: str, *, scope: str | None = None) -> CatalogItem:
        """Resolve one item by name."""

    def dump_item(self, project: Project | None, name: str, *, scope: str | None = None) -> str:
        """Return the YAML payload for one item."""

    def validate_items(
        self,
        project: Project | None,
        *,
        scope: str | None = None,
    ) -> list[CatalogValidationIssue]:
        """Validate stored items of this kind."""


class _BaseHandler:
    """Shared scope resolution for catalog kinds."""

    kind = ""

    def list_items(self, project: Project | None, *, scope: str | None = None) -> list[CatalogItem]:
        if scope is not None:
            self._validate_scope(scope)
            return list(self._list_scope(project, scope))

        items: list[CatalogItem] = []
        seen: set[str] = set()
        for candidate_scope in CATALOG_SCOPES:
            for item in self._list_scope(project, candidate_scope):
                if item.name in seen:
                    continue
                items.append(item)
                seen.add(item.name)
        return items

    def get_item(self, project: Project | None, name: str, *, scope: str | None = None) -> CatalogItem:
        if scope is not None:
            self._validate_scope(scope)
            for item in self._list_scope(project, scope):
                if item.name == name:
                    return item
            raise FileNotFoundError(f'{self.kind} "{name}" not found in {scope} scope.')

        for candidate_scope in CATALOG_SCOPES:
            for item in self._list_scope(project, candidate_scope):
                if item.name == name:
                    return item
        raise FileNotFoundError(f'{self.kind} "{name}" not found.')

    def dump_item(self, project: Project | None, name: str, *, scope: str | None = None) -> str:
        item = self.get_item(project, name, scope=scope)
        return item.path.read_text(encoding="utf-8-sig")

    def validate_items(
        self,
        project: Project | None,
        *,
        scope: str | None = None,
    ) -> list[CatalogValidationIssue]:
        issues: list[CatalogValidationIssue] = []
        scopes = (scope,) if scope is not None else CATALOG_SCOPES
        for candidate_scope in scopes:
            self._validate_scope(candidate_scope)
            for path in self._iter_paths(project, candidate_scope):
                try:
                    self._load_path(path, scope=candidate_scope)
                except (FileNotFoundError, ValueError) as e:
                    issues.append(
                        CatalogValidationIssue(
                            kind=self.kind,
                            scope=candidate_scope,
                            path=path,
                            message=str(e),
                        )
                    )
        return issues

    def _validate_scope(self, scope: str) -> None:
        if scope not in CATALOG_SCOPES:
            raise ValueError(f'Unknown scope "{scope}". Use: {", ".join(CATALOG_SCOPES)}.')

    def _list_scope(self, project: Project | None, scope: str) -> list[CatalogItem]:
        items: list[CatalogItem] = []
        for path in self._iter_paths(project, scope):
            try:
                items.append(self._load_path(path, scope=scope))
            except (FileNotFoundError, ValueError):
                continue
        return items

    def _iter_paths(self, project: Project | None, scope: str) -> list[Path]:
        raise NotImplementedError

    def _load_path(self, path: Path, *, scope: str) -> CatalogItem:
        raise NotImplementedError


class _StyleHandler(_BaseHandler):
    kind = "style"

    def _iter_paths(self, project: Project | None, scope: str) -> list[Path]:
        from pbi.styles import _bundled_styles_dir, _global_styles_dir, _styles_dir

        if scope == "project":
            if project is None:
                return []
            target = _styles_dir(project)
        elif scope == "global":
            target = _global_styles_dir()
        else:
            target = _bundled_styles_dir()
        if not target.exists():
            return []
        return sorted(target.glob("*.yaml"))

    def _load_path(self, path: Path, *, scope: str) -> CatalogItem:
        from pbi.styles import _load_style_file

        style = _load_style_file(path, path.stem, scope=scope)
        return CatalogItem(
            kind=self.kind,
            name=style.name,
            scope=style.scope,
            path=style.path,
            description=style.description,
            summary={"properties": len(style.properties)},
        )


class _ComponentHandler(_BaseHandler):
    kind = "component"

    def _iter_paths(self, project: Project | None, scope: str) -> list[Path]:
        from pbi.components import (
            _bundled_components_dir,
            _components_dir,
            _global_components_dir,
        )

        if scope == "project":
            if project is None:
                return []
            target = _components_dir(project)
        elif scope == "global":
            target = _global_components_dir()
        else:
            target = _bundled_components_dir()
        if not target.exists():
            return []
        return sorted(target.glob("*.yaml"))

    def _load_path(self, path: Path, *, scope: str) -> CatalogItem:
        from pbi.components import _load_component_file

        component = _load_component_file(path, path.stem, scope=scope)
        return CatalogItem(
            kind=self.kind,
            name=component.name,
            scope=component.scope,
            path=component.path,
            description=component.description,
            summary={
                "visuals": len(component.visuals),
                "parameters": len(component.parameters),
                "size": f"{component.size[0]} x {component.size[1]}",
            },
        )


class _PageTemplateHandler(_BaseHandler):
    kind = "page"

    def _iter_paths(self, project: Project | None, scope: str) -> list[Path]:
        from pbi.templates import _global_templates_dir, _templates_dir

        if scope == "project":
            if project is None:
                return []
            target = _templates_dir(project)
        elif scope == "global":
            target = _global_templates_dir()
        else:
            return []
        if not target.exists():
            return []
        return sorted(target.glob("*.yaml"))

    def _load_path(self, path: Path, *, scope: str) -> CatalogItem:
        from pbi.templates import _load_template_file, template_summary

        template = _load_template_file(path, path.stem, scope=scope)
        summary = template_summary(template)
        return CatalogItem(
            kind=self.kind,
            name=template.name,
            scope=template.scope,
            path=template.path,
            description=template.description,
            summary={
                "page": summary["page"],
                "visuals": summary["visuals"],
                "bookmarks": summary["bookmarks"],
                "size": summary["size"],
            },
        )


class _VisualTemplateHandler(_BaseHandler):
    kind = "visual"

    def _iter_paths(self, project: Project | None, scope: str) -> list[Path]:
        from pbi.visual_templates import (
            _bundled_visual_templates_dir,
            _global_visual_templates_dir,
            _project_visual_templates_dir,
        )

        if scope == "project":
            if project is None:
                return []
            target = _project_visual_templates_dir(project)
        elif scope == "global":
            target = _global_visual_templates_dir()
        else:
            target = _bundled_visual_templates_dir()
        if not target.exists():
            return []
        return sorted(target.glob("*.yaml"))

    def _load_path(self, path: Path, *, scope: str) -> CatalogItem:
        from pbi.visual_templates import _load_visual_template_file

        template = _load_visual_template_file(path, path.stem, scope=scope)
        return CatalogItem(
            kind=self.kind,
            name=template.name,
            scope=template.scope,
            path=template.path,
            description=template.description,
            category=template.category,
            tags=template.tags,
            summary={
                "visualType": template.payload.get("type", ""),
                "parameters": len(template.parameters),
            },
        )


_HANDLERS: dict[str, CatalogHandler] = {
    "visual": _VisualTemplateHandler(),
    "style": _StyleHandler(),
    "component": _ComponentHandler(),
    "page": _PageTemplateHandler(),
}


def normalize_catalog_kind(kind: str | None) -> str | None:
    """Normalize a catalog kind identifier."""
    if kind is None:
        return None
    normalized = kind.strip().lower()
    aliases = {
        "styles": "style",
        "components": "component",
        "visual-template": "visual",
        "visual_template": "visual",
        "visual-templates": "visual",
        "visual_templates": "visual",
        "visual": "visual",
        "visuals": "visual",
        "template": "page",
        "templates": "page",
        "page-template": "page",
        "page_template": "page",
        "page": "page",
        "pages": "page",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in _HANDLERS:
        raise ValueError(
            f'Unknown kind "{kind}". Use: {", ".join(sorted(_HANDLERS))}.'
        )
    return normalized


def parse_catalog_ref(ref: str, *, kind: str | None = None) -> tuple[str | None, str]:
    """Parse `kind/name` refs while preserving plain names."""
    if "/" in ref:
        raw_kind, raw_name = ref.split("/", 1)
        return normalize_catalog_kind(raw_kind), raw_name
    return normalize_catalog_kind(kind), ref


def list_catalog_items(
    project: Project | None,
    *,
    kind: str | None = None,
    scope: str | None = None,
) -> list[CatalogItem]:
    """List catalog items across kinds."""
    resolved_kind = normalize_catalog_kind(kind)
    if scope is not None and scope not in CATALOG_SCOPES:
        raise ValueError(f'Unknown scope "{scope}". Use: {", ".join(CATALOG_SCOPES)}.')

    handlers = (
        [_HANDLERS[resolved_kind]]
        if resolved_kind is not None
        else [_HANDLERS[name] for name in ("visual", "style", "component", "page")]
    )
    items: list[CatalogItem] = []
    for handler in handlers:
        items.extend(handler.list_items(project, scope=scope))
    return sorted(items, key=lambda item: (item.kind, item.name, item.scope))


def get_catalog_item(
    project: Project | None,
    ref: str,
    *,
    kind: str | None = None,
    scope: str | None = None,
) -> CatalogItem:
    """Resolve a catalog item by `kind/name` or plain name."""
    ref_kind, name = parse_catalog_ref(ref, kind=kind)
    if ref_kind is not None:
        return _HANDLERS[ref_kind].get_item(project, name, scope=scope)

    matches: list[CatalogItem] = []
    for handler in _HANDLERS.values():
        try:
            matches.append(handler.get_item(project, name, scope=scope))
        except FileNotFoundError:
            continue
    if not matches:
        raise FileNotFoundError(f'Catalog item "{name}" not found.')
    if len(matches) > 1:
        available = ", ".join(f"{item.kind}/{item.name}" for item in matches)
        raise ValueError(f'Catalog item "{name}" is ambiguous. Use one of: {available}')
    return matches[0]


def dump_catalog_item(
    project: Project | None,
    ref: str,
    *,
    kind: str | None = None,
    scope: str | None = None,
) -> str:
    """Return the YAML for one catalog item."""
    item = get_catalog_item(project, ref, kind=kind, scope=scope)
    return _HANDLERS[item.kind].dump_item(project, item.name, scope=item.scope)


def validate_catalog(
    project: Project | None,
    *,
    kind: str | None = None,
    scope: str | None = None,
) -> list[CatalogValidationIssue]:
    """Validate catalog items and return issues."""
    resolved_kind = normalize_catalog_kind(kind)
    handlers = (
        [_HANDLERS[resolved_kind]]
        if resolved_kind is not None
        else [_HANDLERS[name] for name in ("visual", "style", "component", "page")]
    )
    issues: list[CatalogValidationIssue] = []
    for handler in handlers:
        issues.extend(handler.validate_items(project, scope=scope))
    return sorted(issues, key=lambda issue: (issue.kind, issue.scope, str(issue.path)))
