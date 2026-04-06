"""Catalog-native reusable single-visual assets."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pbi.export import export_visual_spec
from pbi.project import Page, Project, sanitize_visual_name
from pbi.visual_stamping import create_visual_from_spec


_VISUAL_TEMPLATE_DIRNAME = "visual"
_PLACEHOLDER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")


@dataclass(frozen=True)
class VisualTemplate:
    """A saved reusable single-visual template."""

    name: str
    path: Path
    payload: dict[str, Any]
    description: str | None = None
    scope: str = "project"
    category: str | None = None
    tags: tuple[str, ...] = ()
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)


def _project_visual_templates_dir(project: Project) -> Path:
    return project.root / ".pbi-catalog" / _VISUAL_TEMPLATE_DIRNAME


def _global_visual_templates_dir() -> Path:
    return Path.home() / ".config" / "pbi" / "catalog" / _VISUAL_TEMPLATE_DIRNAME


def _bundled_visual_templates_dir() -> Path:
    return Path(__file__).parent / "catalog_assets" / "visual"


def _validate_visual_template_name(name: str) -> str:
    if not name or name in {".", ".."}:
        raise ValueError("Visual template name must be a non-empty file-safe name.")
    if "/" in name or "\\" in name:
        raise ValueError("Visual template name may not contain path separators.")
    if Path(name).is_absolute():
        raise ValueError("Visual template name may not be an absolute path.")
    return name


def _visual_template_path(
    project: Project | None,
    name: str,
    *,
    global_scope: bool = False,
) -> Path:
    safe = _validate_visual_template_name(name)
    if global_scope:
        return _global_visual_templates_dir() / f"{safe}.yaml"
    if project is None:
        raise ValueError("Project is required for project-scoped visual templates.")
    return _project_visual_templates_dir(project) / f"{safe}.yaml"


def register_visual_template(
    project: Project | None,
    yaml_path: Path,
    *,
    name: str | None = None,
    description: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    overwrite: bool = False,
    global_scope: bool = False,
) -> Path:
    """Register a visual template from YAML."""
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("Visual template YAML must be a mapping.")

    normalized = normalize_visual_template_data(
        data,
        default_name=yaml_path.stem,
        name=name,
        description=description,
        category=category,
        tags=tags,
    )
    path = _visual_template_path(project, normalized["name"], global_scope=global_scope)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f'Visual template "{normalized["name"]}" already exists. Use --force to replace it.'
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(normalized, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    return path


def save_visual_template(
    project: Project | None,
    page: Page,
    visual,
    template_name: str,
    *,
    description: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
    overwrite: bool = False,
    global_scope: bool = False,
) -> Path:
    """Create a visual template directly from an existing report visual."""
    spec = export_visual_spec(project, visual)
    spec.pop("id", None)
    spec.pop("name", None)
    spec.pop("group", None)
    spec.pop("position", None)
    path = _visual_template_path(project if not global_scope else None, template_name, global_scope=global_scope)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f'Visual template "{template_name}" already exists. Use --force to replace it.'
        )
    payload = normalize_visual_template_data(
        spec,
        default_name=template_name,
        name=template_name,
        description=description,
        category=category,
        tags=tags,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    return path


def normalize_visual_template_data(
    data: dict[str, Any],
    *,
    default_name: str | None = None,
    name: str | None = None,
    description: str | None = None,
    category: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Normalize either envelope YAML or raw visual spec into a catalog-native envelope."""
    if "payload" in data or data.get("kind") in {"visual", "visual-template"}:
        raw_kind = str(data.get("kind", "visual")).strip().lower()
        if raw_kind not in {"visual", "visual-template"}:
            raise ValueError('Catalog item kind must be "visual".')
        payload = data.get("payload")
        if not isinstance(payload, dict):
            raise ValueError('Visual item must define a mapping "payload".')
        resolved_name = _validate_visual_template_name(
            str(name or data.get("name") or default_name or "").strip()
        )
        parameters = data.get("parameters", {})
        if parameters and not isinstance(parameters, dict):
            raise ValueError('Visual item "parameters" must be a mapping.')
        resolved_tags = tags if tags is not None else data.get("tags", [])
        if not isinstance(resolved_tags, list) or not all(isinstance(tag, str) for tag in resolved_tags):
            raise ValueError('Visual item "tags" must be a list of strings.')
        normalized = {
            "kind": "visual",
            "name": resolved_name,
            "payload": _normalize_visual_payload(payload),
        }
        final_description = description if description is not None else data.get("description")
        if final_description is not None:
            if not isinstance(final_description, str):
                raise ValueError("Visual description must be a string.")
            normalized["description"] = final_description
        final_category = category if category is not None else data.get("category")
        if final_category is not None:
            if not isinstance(final_category, str):
                raise ValueError("Visual category must be a string.")
            normalized["category"] = final_category
        if resolved_tags:
            normalized["tags"] = resolved_tags
        if parameters:
            normalized["parameters"] = parameters
        return normalized

    resolved_name = _validate_visual_template_name(
        str(name or data.get("name") or default_name or Path("template").stem).strip()
    )
    normalized: dict[str, Any] = {
        "kind": "visual",
        "name": resolved_name,
        "payload": _normalize_visual_payload(data),
    }
    if description is not None:
        normalized["description"] = description
    if category is not None:
        normalized["category"] = category
    if tags:
        normalized["tags"] = tags
    return normalized


def _normalize_visual_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Visual payload must be a mapping.")
    if "pages" in payload or "visuals" in payload:
        raise ValueError("Visual payload must be a single visual spec, not page YAML.")
    vis_type = payload.get("type")
    if not isinstance(vis_type, str) or not vis_type.strip():
        raise ValueError('Visual payload must include a non-empty "type".')
    return copy.deepcopy(payload)


def get_visual_template(
    project: Project | None,
    name: str,
    *,
    scope: str | None = None,
    global_scope: bool = False,
) -> VisualTemplate:
    """Load a visual template with project -> global -> bundled resolution."""
    if scope is not None:
        if scope == "project":
            if project is None:
                raise FileNotFoundError(f'Project visual template "{name}" not found')
            path = _visual_template_path(project, name, global_scope=False)
            if not path.exists():
                raise FileNotFoundError(f'Project visual template "{name}" not found')
            return _load_visual_template_file(path, name, scope="project")
        if scope == "global":
            path = _visual_template_path(None, name, global_scope=True)
            if not path.exists():
                raise FileNotFoundError(f'Global visual template "{name}" not found')
            return _load_visual_template_file(path, name, scope="global")
        if scope == "bundled":
            path = _bundled_visual_templates_dir() / f"{_validate_visual_template_name(name)}.yaml"
            if not path.exists():
                raise FileNotFoundError(f'Bundled visual template "{name}" not found')
            return _load_visual_template_file(path, name, scope="bundled")
        raise ValueError(f'Unknown visual template scope "{scope}".')

    if global_scope:
        path = _visual_template_path(None, name, global_scope=True)
        if not path.exists():
            raise FileNotFoundError(f'Global visual template "{name}" not found')
        return _load_visual_template_file(path, name, scope="global")

    if project is not None:
        project_path = _visual_template_path(project, name, global_scope=False)
        if project_path.exists():
            return _load_visual_template_file(project_path, name, scope="project")

    global_path = _visual_template_path(None, name, global_scope=True)
    if global_path.exists():
        return _load_visual_template_file(global_path, name, scope="global")

    bundled_path = _bundled_visual_templates_dir() / f"{_validate_visual_template_name(name)}.yaml"
    if bundled_path.exists():
        return _load_visual_template_file(bundled_path, name, scope="bundled")

    raise FileNotFoundError(f'Visual template "{name}" not found')


def list_visual_templates(
    project: Project | None,
    *,
    global_scope: bool = False,
) -> list[VisualTemplate]:
    """List visual templates with project-first resolution."""
    result: list[VisualTemplate] = []
    seen: set[str] = set()

    if not global_scope and project is not None:
        directory = _project_visual_templates_dir(project)
        if directory.exists():
            for path in sorted(directory.glob("*.yaml")):
                try:
                    item = _load_visual_template_file(path, path.stem, scope="project")
                    result.append(item)
                    seen.add(item.name)
                except (FileNotFoundError, ValueError):
                    continue

    global_dir = _global_visual_templates_dir()
    if global_dir.exists():
        for path in sorted(global_dir.glob("*.yaml")):
            try:
                item = _load_visual_template_file(path, path.stem, scope="global")
                if item.name not in seen:
                    result.append(item)
                    seen.add(item.name)
            except (FileNotFoundError, ValueError):
                continue

    bundled_dir = _bundled_visual_templates_dir()
    if bundled_dir.exists():
        for path in sorted(bundled_dir.glob("*.yaml")):
            try:
                item = _load_visual_template_file(path, path.stem, scope="bundled")
                if item.name not in seen:
                    result.append(item)
                    seen.add(item.name)
            except (FileNotFoundError, ValueError):
                continue

    return result


def delete_visual_template(
    project: Project | None,
    name: str,
    *,
    global_scope: bool = False,
) -> bool:
    """Delete a saved visual template."""
    path = _visual_template_path(None if global_scope else project, name, global_scope=global_scope)
    if not path.exists():
        return False
    path.unlink()
    return True


def clone_visual_template(
    project: Project | None,
    name: str,
    *,
    from_scope: str | None = None,
    to_global: bool = False,
    new_name: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Clone a visual template between scopes."""
    target_name = new_name or name
    source = get_visual_template(project, name, scope=from_scope, global_scope=(from_scope == "global"))
    if source.scope == "bundled" and to_global is False and project is None:
        raise ValueError("Project is required to clone a bundled visual template to project scope.")

    target_path = _visual_template_path(
        None if to_global else project,
        target_name,
        global_scope=to_global,
    )
    if target_path.exists() and not overwrite:
        raise FileExistsError(
            f'Visual template "{target_name}" already exists. Use --force to replace it.'
        )

    payload = yaml.safe_load(source.path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f'Visual template "{name}" must be a YAML mapping.')
    payload["name"] = _validate_visual_template_name(target_name)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    return target_path


def _load_visual_template_file(path: Path, template_name: str, *, scope: str) -> VisualTemplate:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as e:
        raise ValueError(f'Visual template "{template_name}" is not valid YAML: {e}') from e

    if not isinstance(data, dict):
        raise ValueError(f'Visual template "{template_name}" must be a YAML mapping.')

    normalized = normalize_visual_template_data(data, default_name=template_name)
    parameters = normalized.get("parameters", {})
    return VisualTemplate(
        name=normalized["name"],
        path=path,
        payload=normalized["payload"],
        description=normalized.get("description"),
        scope=scope,
        category=normalized.get("category"),
        tags=tuple(normalized.get("tags", [])),
        parameters=parameters if isinstance(parameters, dict) else {},
    )


def dump_visual_template(template: VisualTemplate) -> str:
    """Serialize a visual template as YAML."""
    payload: dict[str, Any] = {
        "kind": "visual",
        "name": template.name,
        "payload": template.payload,
    }
    if template.category:
        payload["category"] = template.category
    if template.description:
        payload["description"] = template.description
    if template.tags:
        payload["tags"] = list(template.tags)
    if template.parameters:
        payload["parameters"] = template.parameters
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120)


def apply_visual_template(
    project: Project,
    page: Page,
    template_name: str,
    *,
    x: int | float = 0,
    y: int | float = 0,
    name: str | None = None,
    params: dict[str, str] | None = None,
    scope: str | None = None,
    global_scope: bool = False,
) -> tuple[Any, VisualTemplate]:
    """Create one visual from a visual template on a page."""
    template = get_visual_template(project, template_name, scope=scope, global_scope=global_scope)
    spec = copy.deepcopy(template.payload)
    _apply_template_parameters(spec, template.parameters, params or {})
    auto_name = name or spec.get("name") or template.name
    final_name = _resolve_visual_name(project, page, auto_name, explicit=name is not None)
    visual = create_visual_from_spec(project, page, spec, x=x, y=y, name=final_name)
    return visual, template


def _apply_template_parameters(
    obj: Any,
    parameter_defs: dict[str, dict[str, Any]],
    params: dict[str, str],
) -> None:
    defaults = {
        key: str(value.get("default"))
        for key, value in parameter_defs.items()
        if isinstance(value, dict) and value.get("default") is not None
    }
    replacements = {**defaults, **params}

    def replace_text(text: str) -> str:
        def repl(match: re.Match[str]) -> str:
            key = match.group(1).strip()
            return replacements.get(key, match.group(0))

        return _PLACEHOLDER_RE.sub(repl, text)

    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str):
                obj[key] = replace_text(value)
            elif isinstance(value, (dict, list)):
                _apply_template_parameters(value, parameter_defs, params)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            if isinstance(value, str):
                obj[index] = replace_text(value)
            elif isinstance(value, (dict, list)):
                _apply_template_parameters(value, parameter_defs, params)


def _resolve_visual_name(project: Project, page: Page, name: str, *, explicit: bool) -> str:
    safe = sanitize_visual_name(name)
    existing = {visual.name for visual in project.get_visuals(page)}
    if safe not in existing:
        return safe
    if explicit:
        raise ValueError(f'Visual "{safe}" already exists on page "{page.display_name}".')
    suffix = 2
    candidate = f"{safe}-{suffix}"
    while candidate in existing:
        suffix += 1
        candidate = f"{safe}-{suffix}"
    return candidate
