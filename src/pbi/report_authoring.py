"""PBIR Report authoring adapter.

This module is the explicit seam for mutating Pages and Visuals in a PBIR
Report. ``Project`` remains the PBIP Project access root; report authoring
behavior lives here.
"""

from __future__ import annotations

from dataclasses import dataclass

from pbi.project import Page, Project, Visual


@dataclass(frozen=True)
class ReportAuthoring:
    """Author Pages and Visuals in a PBIR Report."""

    project: Project

    # ── Page authoring ──────────────────────────────────────────

    def create_page(
        self,
        display_name: str,
        width: int = 1280,
        height: int = 720,
        display_option: str = "FitToPage",
    ) -> Page:
        """Create a new Page."""
        from pbi.page_authoring import create_page

        return create_page(
            self.project,
            display_name,
            width=width,
            height=height,
            display_option=display_option,
        )

    def copy_page(self, source: Page, new_name: str) -> Page:
        """Deep-copy a Page and all of its Visuals."""
        from pbi.page_authoring import copy_page

        return copy_page(self.project, source, new_name)

    def delete_page(self, page: Page) -> None:
        """Delete a Page and all of its Visuals."""
        from pbi.page_authoring import delete_page

        delete_page(self.project, page)

    def set_page_order(self, page_ids: list[str]) -> None:
        """Overwrite the Page order with a new sequence of Page folder IDs."""
        from pbi.page_authoring import set_page_order

        set_page_order(self.project, page_ids)

    def set_active_page(self, page_id: str) -> None:
        """Set the active Page by folder ID."""
        from pbi.page_authoring import set_active_page

        set_active_page(self.project, page_id)

    # ── Visual authoring ────────────────────────────────────────

    def create_visual(
        self,
        page: Page,
        visual_type: str,
        x: int = 0,
        y: int = 0,
        width: int = 300,
        height: int = 200,
        *,
        behind: bool = False,
    ) -> Visual:
        """Create a new Visual on a Page with type-aware scaffolding."""
        from pbi.visual_authoring import create_visual

        return create_visual(
            self.project,
            page,
            visual_type,
            x=x,
            y=y,
            width=width,
            height=height,
            behind=behind,
        )

    def copy_visual(
        self,
        source: Visual,
        target_page: Page,
        new_name: str | None = None,
    ) -> Visual:
        """Copy a Visual, optionally to a different Page."""
        from pbi.visual_authoring import copy_visual

        return copy_visual(self.project, source, target_page, new_name=new_name)

    def delete_visual(self, visual: Visual) -> None:
        """Delete a Visual."""
        from pbi.visual_authoring import delete_visual

        delete_visual(self.project, visual)

    # ── Visual grouping ─────────────────────────────────────────

    def create_group(
        self,
        page: Page,
        visuals: list[Visual],
        display_name: str | None = None,
    ) -> Visual:
        """Group Visuals together and return the group container Visual."""
        from pbi.visual_groups import create_group

        return create_group(self.project, page, visuals, display_name=display_name)

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
        """Create an empty Visual group container."""
        from pbi.visual_groups import create_group_container

        return create_group_container(
            self.project,
            page,
            name=name,
            display_name=display_name,
            x=x,
            y=y,
            width=width,
            height=height,
        )

    def ungroup(self, page: Page, group: Visual) -> list[Visual]:
        """Ungroup a Visual group and return the freed child Visuals."""
        from pbi.visual_groups import ungroup

        return ungroup(self.project, page, group)

    # ── Visual query authoring ──────────────────────────────────

    def add_binding(
        self,
        visual: Visual,
        role: str,
        entity: str,
        prop: str,
        field_type: str = "column",
        display_name: str | None = None,
    ) -> None:
        """Add a data binding to a Visual's query."""
        from pbi.visual_queries import add_binding

        add_binding(visual, role, entity, prop, field_type=field_type, display_name=display_name)

    def remove_binding(
        self,
        visual: Visual,
        role: str,
        field_ref: str | None = None,
    ) -> int:
        """Remove bindings from a Visual and return the number removed."""
        from pbi.visual_queries import remove_binding

        return remove_binding(visual, role, field_ref=field_ref)

    def get_bindings(self, visual: Visual) -> list[tuple[str, str, str, str]]:
        """Get Visual bindings as (role, entity, property, field_type) tuples."""
        from pbi.visual_queries import get_bindings

        return get_bindings(visual)

    def set_sort(
        self,
        visual: Visual,
        entity: str,
        prop: str,
        field_type: str = "column",
        descending: bool = True,
    ) -> None:
        """Set the sort definition on a Visual."""
        from pbi.visual_queries import set_sort

        set_sort(visual, entity, prop, field_type=field_type, descending=descending)

    def clear_sort(self, visual: Visual) -> bool:
        """Remove a Visual sort definition and return whether one was removed."""
        from pbi.visual_queries import clear_sort

        return clear_sort(visual)

    def get_sort(self, visual: Visual) -> list[tuple[str, str, str, str]]:
        """Get Visual sort definitions as (entity, property, field_type, direction)."""
        from pbi.visual_queries import get_sort

        return get_sort(visual)
