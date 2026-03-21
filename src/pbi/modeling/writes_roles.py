"""TMDL write helpers for semantic-model roles and RLS filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .schema import ModelRole, RoleMember, RoleTablePermission, SemanticModel
from .writes import TmdlEditSession, _commit_tmdl_lines, validate_model_object_name

_MODEL_PERMISSION_VALUES = frozenset({"none", "read", "readRefresh", "refresh", "administrator"})
_ROLE_MEMBER_TYPES = frozenset({"user", "group", "auto", "activeDirectory"})


@dataclass
class RoleSpec:
    """Requested role contents."""

    model_permission: str = "read"
    table_permissions: list[RoleTablePermission] = field(default_factory=list)
    members: list[RoleMember] = field(default_factory=list)


def create_role(
    project_root: Path,
    role_name: str,
    spec: RoleSpec,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Create one role definition file."""
    loaded_model = model or SemanticModel.load(project_root)
    validate_model_object_name(role_name, "role")
    try:
        loaded_model.find_role(role_name)
    except ValueError:
        pass
    else:
        raise ValueError(f'Role "{role_name}" already exists.')

    role = _build_role(loaded_model, role_name, spec)
    _commit_tmdl_lines(
        _role_path(loaded_model, role.name),
        _render_role_lines(role),
        dry_run=dry_run,
        session=edit_session,
    )
    return role.name, True


def set_role(
    project_root: Path,
    role_name: str,
    spec: RoleSpec,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Replace one role definition file."""
    loaded_model = model or SemanticModel.load(project_root)
    existing = loaded_model.find_role(role_name)
    role = _build_role(loaded_model, existing.name, spec)
    path = existing.definition_path or _role_path(loaded_model, existing.name)
    current = path.read_text(encoding="utf-8-sig").splitlines() if path.exists() else []
    rendered = _render_role_lines(role)
    if current == rendered:
        return role.name, False
    _commit_tmdl_lines(path, rendered, dry_run=dry_run, session=edit_session)
    return role.name, True


def delete_role(
    project_root: Path,
    role_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Delete one role definition file."""
    loaded_model = model or SemanticModel.load(project_root)
    role = loaded_model.find_role(role_name)
    path = role.definition_path or _role_path(loaded_model, role.name)
    if not path.exists():
        return role.name, False
    if dry_run:
        return role.name, True
    if edit_session is not None:
        edit_session._lines_by_path.pop(path, None)
        edit_session._dirty_paths.discard(path)
    path.unlink()
    return role.name, True


def set_role_permission(
    project_root: Path,
    role_name: str,
    model_permission: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, bool]:
    """Set one role's model permission."""
    loaded_model = model or SemanticModel.load(project_root)
    role = loaded_model.find_role(role_name)
    spec = RoleSpec(
        model_permission=model_permission,
        table_permissions=list(role.table_permissions),
        members=list(role.members),
    )
    return set_role(
        project_root,
        role.name,
        spec,
        dry_run=dry_run,
        model=loaded_model,
        edit_session=edit_session,
    )


def set_role_table_filter(
    project_root: Path,
    role_name: str,
    table_name: str,
    expression: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Set or replace one role table filter."""
    loaded_model = model or SemanticModel.load(project_root)
    role = loaded_model.find_role(role_name)
    table = loaded_model.find_table(table_name)

    permissions = [RoleTablePermission(item.table, item.filter_expression) for item in role.table_permissions]
    replaced = False
    for item in permissions:
        if item.table.lower() == table.name.lower():
            item.filter_expression = expression.strip()
            replaced = True
            break
    if not replaced:
        permissions.append(RoleTablePermission(table=table.name, filter_expression=expression.strip()))

    _, changed = set_role(
        project_root,
        role.name,
        RoleSpec(
            model_permission=role.model_permission,
            table_permissions=permissions,
            members=list(role.members),
        ),
        dry_run=dry_run,
        model=loaded_model,
        edit_session=edit_session,
    )
    return role.name, table.name, changed


def clear_role_table_filter(
    project_root: Path,
    role_name: str,
    table_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Remove one table filter from a role."""
    loaded_model = model or SemanticModel.load(project_root)
    role = loaded_model.find_role(role_name)
    permission = role.find_table_permission(table_name)
    permissions = [
        RoleTablePermission(item.table, item.filter_expression)
        for item in role.table_permissions
        if item.table.lower() != permission.table.lower()
    ]
    _, changed = set_role(
        project_root,
        role.name,
        RoleSpec(
            model_permission=role.model_permission,
            table_permissions=permissions,
            members=list(role.members),
        ),
        dry_run=dry_run,
        model=loaded_model,
        edit_session=edit_session,
    )
    return role.name, permission.table, changed


def add_role_member(
    project_root: Path,
    role_name: str,
    member: RoleMember,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Add one member to a role."""
    loaded_model = model or SemanticModel.load(project_root)
    role = loaded_model.find_role(role_name)
    _validate_role_member(member)
    for existing in role.members:
        if existing.name.lower() == member.name.lower():
            raise ValueError(f'Role member "{member.name}" already exists in role "{role.name}".')
    members = list(role.members) + [member]
    _, changed = set_role(
        project_root,
        role.name,
        RoleSpec(
            model_permission=role.model_permission,
            table_permissions=list(role.table_permissions),
            members=members,
        ),
        dry_run=dry_run,
        model=loaded_model,
        edit_session=edit_session,
    )
    return role.name, member.name, changed


def delete_role_member(
    project_root: Path,
    role_name: str,
    member_name: str,
    *,
    dry_run: bool = False,
    model: SemanticModel | None = None,
    edit_session: TmdlEditSession | None = None,
) -> tuple[str, str, bool]:
    """Delete one member from a role."""
    loaded_model = model or SemanticModel.load(project_root)
    role = loaded_model.find_role(role_name)
    member = role.find_member(member_name)
    members = [item for item in role.members if item.name.lower() != member.name.lower()]
    _, changed = set_role(
        project_root,
        role.name,
        RoleSpec(
            model_permission=role.model_permission,
            table_permissions=list(role.table_permissions),
            members=members,
        ),
        dry_run=dry_run,
        model=loaded_model,
        edit_session=edit_session,
    )
    return role.name, member.name, changed


def _build_role(model: SemanticModel, role_name: str, spec: RoleSpec) -> ModelRole:
    permission = _normalize_model_permission(spec.model_permission)
    permissions: list[RoleTablePermission] = []
    seen_tables: set[str] = set()
    for item in spec.table_permissions:
        table = model.find_table(item.table)
        key = table.name.lower()
        if key in seen_tables:
            raise ValueError(f'Role "{role_name}" cannot define multiple filters for table "{table.name}".')
        seen_tables.add(key)
        expression = item.filter_expression.strip()
        if not expression:
            raise ValueError(f'Role "{role_name}" filter for table "{table.name}" cannot be empty.')
        permissions.append(RoleTablePermission(table=table.name, filter_expression=expression))

    members: list[RoleMember] = []
    seen_members: set[str] = set()
    for item in spec.members:
        _validate_role_member(item)
        key = item.name.lower()
        if key in seen_members:
            raise ValueError(f'Role "{role_name}" cannot define duplicate member "{item.name}".')
        seen_members.add(key)
        members.append(RoleMember(item.name, item.member_type, item.identity_provider))

    return ModelRole(
        name=role_name,
        model_permission=permission,
        table_permissions=sorted(permissions, key=lambda item: item.table.lower()),
        members=sorted(members, key=lambda item: item.name.lower()),
        definition_path=_role_path(model, role_name),
    )


def _normalize_model_permission(value: str) -> str:
    normalized = value.strip()
    if normalized not in _MODEL_PERMISSION_VALUES:
        allowed = ", ".join(sorted(_MODEL_PERMISSION_VALUES))
        raise ValueError(f'Invalid role permission "{value}". Allowed: {allowed}')
    return normalized


def _validate_role_member(member: RoleMember) -> None:
    if not member.name.strip():
        raise ValueError("Role member name cannot be empty.")
    if member.member_type not in _ROLE_MEMBER_TYPES:
        allowed = ", ".join(sorted(_ROLE_MEMBER_TYPES))
        raise ValueError(f'Invalid role member type "{member.member_type}". Allowed: {allowed}')
    if member.identity_provider is not None and not member.identity_provider.strip():
        raise ValueError("Role member identityProvider cannot be empty.")
    if member.identity_provider and member.member_type != "user":
        raise ValueError(
            "Custom identityProvider members currently support only the default user member type."
        )


def _render_role_lines(role: ModelRole) -> list[str]:
    lines = [f"role {_format_tmdl_name(role.name)}", f"\tmodelPermission: {role.model_permission}"]
    for permission in role.table_permissions:
        lines.append(
            f"\ttablePermission {_format_tmdl_name(permission.table)} = {permission.filter_expression}"
        )
    if role.members:
        lines.append("")
    for member in role.members:
        if member.identity_provider:
            lines.append(f"\tmember {_format_tmdl_name(member.name)}")
            lines.append(f"\t\tidentityProvider = {member.identity_provider}")
            continue
        if member.member_type == "user":
            lines.append(f"\tmember {_format_tmdl_name(member.name)}")
        else:
            lines.append(f"\tmember {_format_tmdl_name(member.name)} = {member.member_type}")
    return lines


def _role_path(model: SemanticModel, role_name: str) -> Path:
    return model.folder / "definition" / "roles" / f"{role_name}.tmdl"


def _format_tmdl_name(name: str) -> str:
    if name and all(ch.isalnum() or ch == "_" for ch in name):
        return name
    escaped = name.replace("'", "''")
    return f"'{escaped}'"
