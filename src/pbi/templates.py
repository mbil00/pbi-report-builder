"""Reusable page template storage backed by apply-compatible YAML."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from pbi.apply import ApplyResult, apply_yaml
from pbi.bookmarks import export_bookmarks
from pbi.export import export_pages
from pbi.project import Page, Project, Visual


@dataclass(frozen=True)
class PageTemplate:
    """A saved reusable page template."""

    name: str
    path: Path
    spec: dict[str, Any]
    description: str | None = None
    scope: str = "project"


def _global_templates_dir() -> Path:
    """Return the global templates directory (~/.config/pbi/templates/)."""
    return Path.home() / ".config" / "pbi" / "templates"


def save_template(
    project: Project,
    page: Page,
    template_name: str,
    visuals: list[Visual] | None = None,
    *,
    description: str | None = None,
    overwrite: bool = False,
    global_scope: bool = False,
) -> Path:
    """Save a page as a reusable YAML template."""
    _ = visuals  # Retained for call-site compatibility.

    path = _global_template_path(template_name) if global_scope else _template_path(project, template_name)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f'Template "{template_name}" already exists. Use --force to replace it.'
        )

    payload = export_pages(project, page_filter=page.display_name)
    bookmarks = export_bookmarks(project, page=page)
    if bookmarks:
        payload["bookmarks"] = bookmarks
    payload["name"] = _validate_template_name(template_name)
    if description:
        payload["description"] = description

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )
    return path


def register_template(
    project: Project | None,
    yaml_path: Path,
    *,
    name: str | None = None,
    description: str | None = None,
    overwrite: bool = False,
    global_scope: bool = False,
) -> Path:
    """Register a page asset from an existing template YAML file."""
    template = _load_template_file(yaml_path, name or yaml_path.stem, scope="source")
    payload = copy.deepcopy(template.spec)
    payload["name"] = _validate_template_name(name or template.name)
    if description is not None:
        payload["description"] = description
    elif payload.get("description") is None:
        payload.pop("description", None)
    if global_scope:
        path = _global_template_path(payload["name"])
    else:
        if project is None:
            raise ValueError("Project is required for project-scoped page assets.")
        path = _template_path(project, payload["name"])
    return _write_template(path, payload, overwrite=overwrite)


def apply_template(
    project: Project,
    page: Page,
    template_name: str,
    *,
    global_scope: bool = False,
    overwrite: bool = False,
    dry_run: bool = False,
) -> ApplyResult:
    """Apply a saved template to a target page."""
    template = get_template(project, template_name, global_scope=global_scope)
    spec = copy.deepcopy(template.spec)

    pages = spec.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError(f'Template "{template_name}" must define a non-empty pages list.')
    if len(pages) != 1:
        raise ValueError(f'Template "{template_name}" must contain exactly one page.')

    page_spec = pages[0]
    if not isinstance(page_spec, dict):
        raise ValueError(f'Template "{template_name}" page entry must be a mapping.')

    source_page_name = page_spec.get("name")
    page_spec["name"] = page.display_name

    for bookmark in spec.get("bookmarks", []):
        if not isinstance(bookmark, dict):
            continue
        if bookmark.get("page") == source_page_name:
            bookmark["page"] = page.display_name

    yaml_content = yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=120)
    return apply_yaml(
        project,
        yaml_content,
        page_filter=page.display_name,
        dry_run=dry_run,
        overwrite=overwrite,
    )


def get_template(
    project: Project | None,
    template_name: str,
    *,
    global_scope: bool = False,
) -> PageTemplate:
    """Load and validate one saved page template."""
    if global_scope:
        path = _global_template_path(template_name)
        if not path.exists():
            raise FileNotFoundError(f'Global template "{template_name}" not found')
        return _load_template_file(path, template_name, scope="global")

    if project is not None:
        path = _template_path(project, template_name)
        if path.exists():
            return _load_template_file(path, template_name, scope="project")

    global_path = _global_template_path(template_name)
    if global_path.exists():
        return _load_template_file(global_path, template_name, scope="global")

    raise FileNotFoundError(f'Template "{template_name}" not found')


def list_templates(
    project: Project | None,
    *,
    global_scope: bool = False,
) -> list[PageTemplate]:
    """List saved page templates with project-first resolution."""
    presets: list[PageTemplate] = []
    seen_names: set[str] = set()

    if not global_scope and project is not None:
        templates_dir = _templates_dir(project)
        if templates_dir.exists():
            for path in sorted(templates_dir.glob("*.yaml")):
                try:
                    preset = _load_template_file(path, path.stem, scope="project")
                    presets.append(preset)
                    seen_names.add(preset.name)
                except (FileNotFoundError, ValueError):
                    continue

    global_dir = _global_templates_dir()
    if global_dir.exists():
        for path in sorted(global_dir.glob("*.yaml")):
            try:
                preset = _load_template_file(path, path.stem, scope="global")
                if preset.name not in seen_names:
                    presets.append(preset)
                    seen_names.add(preset.name)
            except (FileNotFoundError, ValueError):
                continue

    return presets


def delete_template(
    project: Project | None,
    template_name: str,
    *,
    global_scope: bool = False,
) -> bool:
    """Delete a saved page template."""
    if global_scope:
        path = _global_template_path(template_name)
    else:
        if project is None:
            raise ValueError("Project is required for project-scoped templates.")
        path = _template_path(project, template_name)
    if not path.exists():
        return False
    path.unlink()
    return True


def clone_template(
    project: Project,
    template_name: str,
    *,
    to_global: bool = False,
    new_name: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Clone a template between project and global scope."""
    target_name = new_name or template_name

    if to_global:
        source = get_template(project, template_name, global_scope=False)
        if source.scope != "project":
            path = _template_path(project, template_name)
            if not path.exists():
                raise FileNotFoundError(f'Project template "{template_name}" not found')
            source = _load_template_file(path, template_name, scope="project")
        target = dict(source.spec)
        target["name"] = _validate_template_name(target_name)
        return _write_template(_global_template_path(target_name), target, overwrite=overwrite)

    source = get_template(project, template_name, global_scope=True)
    target = dict(source.spec)
    target["name"] = _validate_template_name(target_name)
    return _write_template(_template_path(project, target_name), target, overwrite=overwrite)


def dump_template(template: PageTemplate) -> str:
    """Serialize a page template as YAML for CLI display."""
    return yaml.safe_dump(
        template.spec,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )


def template_summary(template: PageTemplate) -> dict[str, Any]:
    """Return summary rows for template listing output."""
    pages = template.spec.get("pages", [])
    page_spec = pages[0] if isinstance(pages, list) and pages else {}
    visuals = page_spec.get("visuals", []) if isinstance(page_spec, dict) else []
    bookmarks = template.spec.get("bookmarks", [])
    return {
        "name": template.name,
        "scope": template.scope,
        "file": template.path.name,
        "page": page_spec.get("name", "") if isinstance(page_spec, dict) else "",
        "visuals": len(visuals) if isinstance(visuals, list) else 0,
        "bookmarks": len(bookmarks) if isinstance(bookmarks, list) else 0,
        "size": (
            f"{page_spec.get('width', '?')} x {page_spec.get('height', '?')}"
            if isinstance(page_spec, dict)
            else "? x ?"
        ),
        "description": template.description or "",
    }


def _templates_dir(project: Project) -> Path:
    return project.root / ".pbi-templates"


def _validate_template_name(template_name: str) -> str:
    if not template_name or template_name in {".", ".."}:
        raise ValueError("Template name must be a non-empty file-safe name.")
    if "/" in template_name or "\\" in template_name:
        raise ValueError("Template name may not contain path separators.")
    if Path(template_name).is_absolute():
        raise ValueError("Template name may not be an absolute path.")
    return template_name


def _template_path(project: Project, template_name: str) -> Path:
    safe_name = _validate_template_name(template_name)
    return _templates_dir(project) / f"{safe_name}.yaml"


def _global_template_path(template_name: str) -> Path:
    safe_name = _validate_template_name(template_name)
    return _global_templates_dir() / f"{safe_name}.yaml"


def _load_template_file(path: Path, template_name: str, *, scope: str) -> PageTemplate:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as e:
        raise ValueError(f'Template "{template_name}" is not valid YAML: {e}') from e

    if not isinstance(data, dict):
        raise ValueError(f'Template "{template_name}" must be a YAML mapping.')

    raw_name = data.get("name", template_name)
    if not isinstance(raw_name, str) or not raw_name.strip():
        raise ValueError(f'Template "{template_name}" must have a non-empty string name.')
    description = data.get("description")
    if description is not None and not isinstance(description, str):
        raise ValueError(f'Template "{template_name}" description must be a string.')

    pages = data.get("pages")
    if not isinstance(pages, list) or not pages:
        raise ValueError(f'Template "{template_name}" must define a non-empty pages list.')

    normalized = dict(data)
    normalized["name"] = _validate_template_name(raw_name)
    return PageTemplate(
        name=normalized["name"],
        path=path,
        spec=normalized,
        description=description,
        scope=scope,
    )


def _write_template(path: Path, payload: dict[str, Any], *, overwrite: bool) -> Path:
    if path.exists() and not overwrite:
        name = payload.get("name", path.stem)
        raise FileExistsError(f'Template "{name}" already exists. Use --force to replace it.')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            width=120,
        ),
        encoding="utf-8",
    )
    return path
