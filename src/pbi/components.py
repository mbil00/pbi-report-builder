"""Reusable visual component storage and stamping."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from pbi.apply.visual_support import apply_raw_visual_payload
from pbi.export import export_visual_spec
from pbi.project import Page, Project, Visual, sanitize_visual_name
from pbi.textbox import set_textbox_content
from pbi.visual_groups import create_group


@dataclass(frozen=True)
class Component:
    """A saved reusable visual component."""

    name: str
    path: Path
    description: str | None = None
    scope: str = "project"
    size: tuple[int, int] = (0, 0)
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    visuals: list[dict[str, Any]] = field(default_factory=list)


def _global_components_dir() -> Path:
    return Path.home() / ".config" / "pbi" / "components"


def _components_dir(project: Project) -> Path:
    return project.root / ".pbi-components"


def _validate_component_name(name: str) -> str:
    if not name or name in {".", ".."}:
        raise ValueError("Component name must be a non-empty file-safe name.")
    if "/" in name or "\\" in name:
        raise ValueError("Component name may not contain path separators.")
    if Path(name).is_absolute():
        raise ValueError("Component name may not be an absolute path.")
    return name


def _component_path(project: Project, name: str) -> Path:
    safe = _validate_component_name(name)
    return _components_dir(project) / f"{safe}.yaml"


def _global_component_path(name: str) -> Path:
    safe = _validate_component_name(name)
    return _global_components_dir() / f"{safe}.yaml"


def save_component(
    project: Project,
    page: Page,
    group_visual: Visual,
    component_name: str,
    *,
    description: str | None = None,
    overwrite: bool = False,
    global_scope: bool = False,
) -> Path:
    """Save a visual group as a reusable component.

    Captures all child visuals with relative positions, formatting,
    bindings, filters, and auto-detected parameters.
    """
    if "visualGroup" not in group_visual.data:
        raise ValueError(f'"{group_visual.name}" is not a group.')

    path = _global_component_path(component_name) if global_scope else _component_path(project, component_name)
    if path.exists() and not overwrite:
        raise FileExistsError(
            f'Component "{component_name}" already exists. Use --force to replace it.'
        )

    # Find children
    all_visuals = project.get_visuals(page)
    group_name = group_visual.name
    children = [v for v in all_visuals if v.data.get("parentGroupName") == group_name]

    if not children:
        raise ValueError(f'Group "{group_name}" has no children.')

    # Group origin for relative positioning
    group_pos = group_visual.position
    origin_x = group_pos.get("x", 0)
    origin_y = group_pos.get("y", 0)
    group_w = group_pos.get("width", 0)
    group_h = group_pos.get("height", 0)

    # Export each child with relative positions
    visual_specs = []
    for child in children:
        spec = export_visual_spec(project, child)
        # Convert position to relative
        child_pos = child.position
        rel_x = child_pos.get("x", 0) - origin_x
        rel_y = child_pos.get("y", 0) - origin_y
        spec["position"] = f"{rel_x}, {rel_y}"
        # Remove id (will be regenerated on stamp)
        spec.pop("id", None)
        visual_specs.append(spec)

    # Auto-detect parameters
    parameters = _detect_parameters(visual_specs)

    # Replace detected parameter values with {{ }} placeholders
    for param_name, param_def in parameters.items():
        default = param_def.get("default")
        if default is not None:
            for spec in visual_specs:
                _deep_replace(spec, default, f"{{{{ {param_name} }}}}")

    payload: dict[str, Any] = {
        "name": _validate_component_name(component_name),
        "size": f"{group_w} x {group_h}",
    }
    if description:
        payload["description"] = description
    if parameters:
        payload["parameters"] = parameters
    payload["visuals"] = visual_specs

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    return path


def save_component_from_yaml(
    project: Project | None,
    yaml_path: Path,
    component_name: str,
    *,
    description: str | None = None,
    overwrite: bool = False,
    global_scope: bool = False,
) -> Path:
    """Create a component directly from a YAML spec file."""
    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML: {e}") from e

    if not isinstance(data, dict):
        raise ValueError("YAML must be a mapping with a 'visuals' key.")

    visuals = data.get("visuals", [])
    if not isinstance(visuals, list) or not visuals:
        raise ValueError("YAML must contain a non-empty 'visuals' list.")

    # Calculate bounding box from visual positions/sizes
    max_w, max_h = 0, 0
    for spec in visuals:
        if not isinstance(spec, dict):
            continue
        rx, ry = _parse_position(spec.get("position", "0, 0"))
        sw, sh = _parse_size(spec.get("size", "0 x 0"))
        max_w = max(max_w, rx + sw)
        max_h = max(max_h, ry + sh)

    parameters = data.get("parameters", {})
    if not isinstance(parameters, dict):
        parameters = {}

    if global_scope:
        path = _global_component_path(component_name)
    else:
        if project is None:
            raise ValueError("Project is required for project-scoped components.")
        path = _component_path(project, component_name)

    if path.exists() and not overwrite:
        raise FileExistsError(
            f'Component "{component_name}" already exists. Use --force to replace it.'
        )

    payload: dict[str, Any] = {
        "name": _validate_component_name(component_name),
        "size": f"{max_w} x {max_h}",
    }
    if description:
        payload["description"] = description
    if parameters:
        payload["parameters"] = parameters
    payload["visuals"] = visuals

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    return path


def _detect_parameters(visual_specs: list[dict]) -> dict[str, dict[str, Any]]:
    """Auto-detect parameterizable fields from visual specs."""
    parameters: dict[str, dict[str, Any]] = {}

    for i, spec in enumerate(visual_specs):
        vis_name = spec.get("name", f"visual_{i}")

        # Title text
        title = spec.get("title", {})
        if isinstance(title, dict) and title.get("text"):
            parameters["title"] = {
                "source": f"{vis_name}.title.text",
                "default": title["text"],
            }

        text = spec.get("text")
        if isinstance(text, str) and text:
            param_name = _textbox_param_name(vis_name, parameters)
            parameters[param_name] = {
                "source": f"{vis_name}.text",
                "default": text,
            }

        # Categorical filter values
        for filt in spec.get("filters", []):
            if not isinstance(filt, dict):
                continue
            field_ref = filt.get("field", "")
            values = filt.get("values", [])
            if values and isinstance(field_ref, str) and "." in field_ref:
                # Create param name from field
                param_name = f"filter[{field_ref}]"
                parameters[param_name] = {
                    "source": f"{vis_name}.filters[{field_ref}]",
                    "default": values[0] if len(values) == 1 else values,
                }

        # Binding field references
        bindings = spec.get("bindings", {})
        if isinstance(bindings, dict):
            for role, fields in bindings.items():
                field_list = [fields] if isinstance(fields, str) else fields
                if not isinstance(field_list, list):
                    continue
                for field_ref in field_list:
                    if not isinstance(field_ref, str) or "." not in field_ref:
                        continue
                    param_name = _binding_param_name(role, parameters)
                    parameters[param_name] = {
                        "source": f"{vis_name}.bindings.{role}",
                        "default": field_ref,
                    }

    return parameters


def _deep_replace(obj: Any, old_value: Any, new_value: str) -> Any:
    """Recursively replace old_value with new_value in a nested structure."""
    if isinstance(obj, dict):
        for key in obj:
            if obj[key] == old_value:
                obj[key] = new_value
            elif isinstance(obj[key], (dict, list)):
                _deep_replace(obj[key], old_value, new_value)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if item == old_value:
                obj[i] = new_value
            elif isinstance(item, (dict, list)):
                _deep_replace(item, old_value, new_value)


def _textbox_param_name(vis_name: str, parameters: dict[str, dict[str, Any]]) -> str:
    lowered = vis_name.lower()
    for candidate in ("title", "subtitle", "note", "label"):
        if candidate in lowered and candidate not in parameters:
            return candidate
    candidate = f"text[{vis_name}]"
    suffix = 2
    while candidate in parameters:
        candidate = f"text[{vis_name}]#{suffix}"
        suffix += 1
    return candidate


def _binding_param_name(role: str, parameters: dict[str, dict[str, Any]]) -> str:
    """Generate a parameter name for a binding role."""
    candidate = role.lower()
    if candidate not in parameters:
        return candidate
    suffix = 2
    while f"{candidate}{suffix}" in parameters:
        suffix += 1
    return f"{candidate}{suffix}"


def get_component(
    project: Project | None,
    name: str,
    *,
    global_scope: bool = False,
) -> Component:
    """Load a saved component."""
    if global_scope:
        path = _global_component_path(name)
        if not path.exists():
            raise FileNotFoundError(f'Global component "{name}" not found')
        return _load_component_file(path, name, scope="global")

    if project is not None:
        path = _component_path(project, name)
        if path.exists():
            return _load_component_file(path, name, scope="project")

    global_path = _global_component_path(name)
    if global_path.exists():
        return _load_component_file(global_path, name, scope="global")

    raise FileNotFoundError(f'Component "{name}" not found')


def _load_component_file(path: Path, name: str, *, scope: str) -> Component:
    """Load and validate a component YAML file."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except yaml.YAMLError as e:
        raise ValueError(f'Component "{name}" is not valid YAML: {e}') from e

    if not isinstance(data, dict):
        raise ValueError(f'Component "{name}" must be a YAML mapping.')

    raw_name = data.get("name", name)
    description = data.get("description")
    parameters = data.get("parameters", {})
    visuals = data.get("visuals", [])

    # Parse size
    size_str = data.get("size", "0 x 0")
    size = _parse_size(size_str) if isinstance(size_str, str) else (0, 0)

    return Component(
        name=_validate_component_name(raw_name),
        path=path,
        description=description,
        scope=scope,
        size=size,
        parameters=parameters if isinstance(parameters, dict) else {},
        visuals=visuals if isinstance(visuals, list) else [],
    )


def _parse_size(s: str) -> tuple[int, int]:
    """Parse '229 x 184' or '214.5 x 93.0' into (229, 184)."""
    parts = s.lower().split("x")
    if len(parts) == 2:
        try:
            return round(float(parts[0].strip())), round(float(parts[1].strip()))
        except ValueError:
            pass
    return 0, 0


def list_components(
    project: Project | None,
    *,
    global_scope: bool = False,
) -> list[Component]:
    """List saved components with project-first resolution."""
    result: list[Component] = []
    seen: set[str] = set()

    if not global_scope and project is not None:
        comp_dir = _components_dir(project)
        if comp_dir.exists():
            for path in sorted(comp_dir.glob("*.yaml")):
                try:
                    comp = _load_component_file(path, path.stem, scope="project")
                    result.append(comp)
                    seen.add(comp.name)
                except (FileNotFoundError, ValueError):
                    continue

    global_dir = _global_components_dir()
    if global_dir.exists():
        for path in sorted(global_dir.glob("*.yaml")):
            try:
                comp = _load_component_file(path, path.stem, scope="global")
                if comp.name not in seen:
                    result.append(comp)
                    seen.add(comp.name)
            except (FileNotFoundError, ValueError):
                continue

    return result


def delete_component(
    project: Project | None,
    name: str,
    *,
    global_scope: bool = False,
) -> bool:
    """Delete a saved component."""
    if global_scope:
        path = _global_component_path(name)
    else:
        if project is None:
            raise ValueError("Project is required for project-scoped components.")
        path = _component_path(project, name)
    if not path.exists():
        return False
    path.unlink()
    return True


def clone_component(
    project: Project,
    name: str,
    *,
    to_global: bool = False,
    new_name: str | None = None,
    overwrite: bool = False,
) -> Path:
    """Clone a component between project and global scope."""
    target_name = new_name or name

    if to_global:
        source = get_component(project, name, global_scope=False)
        if source.scope != "project":
            path = _component_path(project, name)
            if not path.exists():
                raise FileNotFoundError(f'Project component "{name}" not found')
            source = _load_component_file(path, name, scope="project")
        target_path = _global_component_path(target_name)
    else:
        source = get_component(project, name, global_scope=True)
        target_path = _component_path(project, target_name)

    if target_path.exists() and not overwrite:
        raise FileExistsError(
            f'Component "{target_name}" already exists. Use --force to replace it.'
        )

    payload = yaml.safe_load(source.path.read_text(encoding="utf-8-sig"))
    payload["name"] = _validate_component_name(target_name)

    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(
        yaml.safe_dump(payload, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    return target_path


def apply_component(
    project: Project,
    page: Page,
    component_name: str,
    x: int = 0,
    y: int = 0,
    *,
    instance_name: str | None = None,
    params: dict[str, str] | None = None,
    global_scope: bool = False,
    dry_run: bool = False,
) -> list[Visual]:
    """Stamp a component onto a page at the given position.

    Returns the list of created visuals (including the group container).
    """
    comp = get_component(project, component_name, global_scope=global_scope)

    if not comp.visuals:
        raise ValueError(f'Component "{component_name}" has no visuals.')

    # Deep copy and apply parameter substitutions
    visual_specs = copy.deepcopy(comp.visuals)
    if params:
        for param_key, param_value in params.items():
            placeholder = f"{{{{ {param_key} }}}}"
            _deep_replace_str(visual_specs, placeholder, param_value)

    # Also substitute unset parameters with their defaults
    for param_name, param_def in comp.parameters.items():
        placeholder = f"{{{{ {param_name} }}}}"
        default = param_def.get("default")
        if default is not None and params and param_name not in params:
            _deep_replace_str(visual_specs, placeholder, str(default))
        elif default is not None and not params:
            _deep_replace_str(visual_specs, placeholder, str(default))

    if dry_run:
        return []

    _remove_existing_component_instance(project, page, instance_name or component_name)

    # Create visuals with absolute positions
    created: list[Visual] = []
    for spec in visual_specs:
        if isinstance(spec, dict):
            spec.pop("group", None)
            raw_pbir = spec.get("pbir")
            if isinstance(raw_pbir, dict):
                raw_pbir.pop("parentGroupName", None)
        vis_type = spec.get("type", "shape")
        pos_str = spec.get("position", "0, 0")
        size_str = spec.get("size", "300 x 200")

        # Parse relative position and offset by target (x, y)
        rel_x, rel_y = _parse_position(pos_str)
        abs_x = x + rel_x
        abs_y = y + rel_y
        w, h = _parse_size(size_str)

        vis = project.create_visual(page, vis_type, x=abs_x, y=abs_y, width=w, height=h)

        # Apply name
        vis_name = spec.get("name")
        if vis_name:
            vis.data["name"] = sanitize_visual_name(vis_name)

        # Apply properties via the YAML apply engine approach
        _apply_spec_to_visual(project, vis, spec)
        vis.save()
        created.append(vis)

    # Group the created visuals if more than one
    if len(created) >= 2:
        group = create_group(project, page, created, display_name=instance_name or component_name)
        created.append(group)

    return created


def _remove_existing_component_instance(project: Project, page: Page, component_name: str) -> None:
    """Delete an existing grouped component stamp with the same logical name."""
    safe_name = sanitize_visual_name(component_name)
    visuals = project.get_visuals(page)
    matching_groups = [
        visual
        for visual in visuals
        if "visualGroup" in visual.data
        and (
            visual.name == safe_name
            or visual.data.get("visualGroup", {}).get("displayName") == component_name
        )
    ]
    if not matching_groups:
        return

    for group in matching_groups:
        children = [
            visual for visual in project.get_visuals(page)
            if visual.data.get("parentGroupName") == group.name
        ]
        for child in children:
            project.delete_visual(child)
        project.delete_visual(group)


def apply_component_row(
    project: Project,
    page: Page,
    component_name: str,
    count: int,
    x: int = 0,
    y: int = 0,
    gap: int = 12,
    *,
    set_each: dict[str, list[str]] | None = None,
    global_scope: bool = False,
    dry_run: bool = False,
) -> list[list[Visual]]:
    """Stamp multiple component instances in a horizontal row.

    Returns a list of created visual groups (one per instance).
    """
    comp = get_component(project, component_name, global_scope=global_scope)
    comp_width = comp.size[0]

    if not dry_run:
        _remove_existing_component_instance(project, page, component_name)
        for i in range(1, count + 20):  # generous range to clean up old stamps
            _remove_existing_component_instance(project, page, f"{component_name}-{i}")

    all_created: list[list[Visual]] = []
    for i in range(count):
        offset_x = x + i * (comp_width + gap)
        instance_name = f"{component_name}-{i + 1}"

        # Build per-instance params
        instance_params: dict[str, str] = {}
        if set_each:
            for key, values in set_each.items():
                if i < len(values):
                    instance_params[key] = values[i]

        created = apply_component(
            project, page, component_name,
            x=offset_x, y=y,
            instance_name=instance_name,
            params=instance_params if instance_params else None,
            global_scope=global_scope,
            dry_run=dry_run,
        )
        all_created.append(created)

    return all_created


def _parse_position(s: str) -> tuple[int, int]:
    """Parse '16, 200' or '7.47, 6.96' into (16, 200) or (7, 7)."""
    parts = s.split(",")
    if len(parts) == 2:
        try:
            return round(float(parts[0].strip())), round(float(parts[1].strip()))
        except ValueError:
            pass
    return 0, 0


def _deep_replace_str(obj: Any, old: str, new: str) -> None:
    """Replace string occurrences in nested structure."""
    if isinstance(obj, dict):
        for key in obj:
            if isinstance(obj[key], str) and old in obj[key]:
                obj[key] = obj[key].replace(old, new)
            elif isinstance(obj[key], (dict, list)):
                _deep_replace_str(obj[key], old, new)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            if isinstance(item, str) and old in item:
                obj[i] = item.replace(old, new)
            elif isinstance(item, (dict, list)):
                _deep_replace_str(item, old, new)


def _apply_spec_to_visual(project: Project, visual: Visual, spec: dict) -> None:
    """Apply component spec properties/bindings/filters to a created visual."""
    from pbi.properties import VISUAL_PROPERTIES, set_property

    # Apply formatting properties
    skip_keys = {
        "id",
        "name",
        "type",
        "position",
        "size",
        "bindings",
        "sort",
        "filters",
        "pbir",
        "style",
        "isHidden",
        "text",
        "textStyle",
        "group",
    }

    for key, value in spec.items():
        if key in skip_keys:
            continue
        if isinstance(value, dict):
            # Nested properties like title: {show: true, text: "Hello"}
            for subkey, subval in value.items():
                prop_name = f"{key}.{subkey}"
                try:
                    set_property(visual.data, prop_name, str(subval), VISUAL_PROPERTIES)
                except (ValueError, KeyError):
                    pass
        elif isinstance(value, (str, int, float, bool)):
            try:
                set_property(visual.data, key, str(value), VISUAL_PROPERTIES)
            except (ValueError, KeyError):
                pass

    # Apply bindings
    bindings = spec.get("bindings", {})
    if isinstance(bindings, dict):
        for role, fields in bindings.items():
            if isinstance(fields, str):
                fields = [fields]
            if isinstance(fields, list):
                for field_ref in fields:
                    if not isinstance(field_ref, str) or "." not in field_ref:
                        continue
                    is_measure = "(measure)" in field_ref
                    clean_ref = field_ref.replace("(measure)", "").strip()
                    dot = clean_ref.find(".")
                    entity = clean_ref[:dot]
                    prop = clean_ref[dot + 1:]
                    ftype = "measure" if is_measure else "column"
                    project.add_binding(visual, role, entity, prop, field_type=ftype)

    # Apply isHidden
    if spec.get("isHidden"):
        visual.data["isHidden"] = True

    # Apply filters
    filters = spec.get("filters", [])
    if isinstance(filters, list):
        from pbi.filters import add_categorical_filter, add_exclude_filter
        for filt in filters:
            if not isinstance(filt, dict):
                continue
            field_ref = filt.get("field", "")
            values = filt.get("values", [])
            mode = filt.get("mode", "include")
            if field_ref and "." in field_ref and values:
                dot = field_ref.find(".")
                entity = field_ref[:dot]
                prop = field_ref[dot + 1:]
                try:
                    if mode == "exclude":
                        add_exclude_filter(visual.data, entity, prop, values=values)
                    else:
                        add_categorical_filter(visual.data, entity, prop, values=values)
                except (ValueError, KeyError):
                    pass

    # Apply raw PBIR payload if present (for round-trip fidelity)
    pbir = spec.get("pbir")
    if isinstance(pbir, dict):
        apply_raw_visual_payload(visual, pbir)

    if visual.visual_type == "textbox" and isinstance(spec.get("text"), str):
        style = spec.get("textStyle", {})
        set_textbox_content(
            visual.data,
            text=spec["text"],
            style_updates=style if isinstance(style, dict) else None,
        )
