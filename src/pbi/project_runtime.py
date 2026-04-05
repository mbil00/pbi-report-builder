"""Operational project bootstrap helpers used by explicit project initialization."""

from __future__ import annotations

from dataclasses import dataclass, field

from pbi.project import Project


@dataclass(frozen=True)
class ProjectRuntimeState:
    """Result of preparing a project for operational CLI use."""

    newly_installed_visuals: list[object] = field(default_factory=list)
    registered_schema_count: int = 0


def register_project_schemas(project: Project) -> int:
    """Load already-installed project-local schemas into the current process."""
    try:
        from pbi.visual_schema import register_custom_schemas

        return register_custom_schemas(project.root)
    except Exception:
        return 0


def prepare_project_runtime(project: Project) -> ProjectRuntimeState:
    """Prepare project-local runtime state needed after explicit initialization.

    This performs the custom-visual bootstrap work behind `pbi init`:
    - install schemas from any discovered `.pbiviz` files that are not yet registered
    - register project-local custom schemas into the in-memory schema catalog

    Failures are intentionally non-fatal so ordinary commands can still proceed
    against built-in visuals and schemas.
    """
    newly_installed_visuals: list[object] = []
    try:
        from pbi.custom_visuals import auto_install

        newly_installed_visuals = auto_install(project)
    except Exception:
        newly_installed_visuals = []

    return ProjectRuntimeState(
        newly_installed_visuals=newly_installed_visuals,
        registered_schema_count=register_project_schemas(project),
    )
