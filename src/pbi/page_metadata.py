"""Helpers for page metadata and page-level binding workflows."""

from __future__ import annotations

import copy
from dataclasses import dataclass

from pbi.drillthrough import (
    clear_drillthrough,
    clear_tooltip_page,
    configure_drillthrough,
    configure_tooltip_page,
    get_drillthrough_fields,
    get_tooltip_fields,
    is_cross_report_drillthrough,
    is_drillthrough,
    is_tooltip_page,
)
from pbi.fields import resolve_field_type
from pbi.project import Page, Project
from pbi.properties import PAGE_PROPERTIES, get_property, set_property


@dataclass(frozen=True)
class PageListRow:
    index: int
    display_name: str
    folder: str
    width: int
    height: int
    display_option: str
    visibility: str
    active: bool
    visual_count: int


@dataclass(frozen=True)
class PagePropertyChange:
    prop: str
    old: object
    new: object
    changed: bool


@dataclass(frozen=True)
class PageBindingInfo:
    binding_type: str
    fields: list[tuple[str, str, str]]
    cross_report: bool = False


def list_pages(project: Project) -> list[PageListRow]:
    pages = project.get_pages()
    meta = project.get_pages_meta()
    rows: list[PageListRow] = []
    for index, page in enumerate(pages, 1):
        rows.append(
            PageListRow(
                index=index,
                display_name=page.display_name,
                folder=page.name,
                width=page.width,
                height=page.height,
                display_option=page.display_option,
                visibility=page.visibility,
                active=meta.get("activePageName") == page.name,
                visual_count=len(project.get_visuals(page)),
            )
        )
    return rows


def reorder_pages(project: Project, identifiers: list[str]) -> list[Page]:
    all_pages = project.get_pages()
    all_ids = [page.name for page in all_pages]

    resolved_ids: list[str] = []
    for identifier in identifiers:
        page = project.find_page(identifier)
        if page.name in resolved_ids:
            raise ValueError(f'Page "{page.display_name}" listed more than once.')
        resolved_ids.append(page.name)

    if len(resolved_ids) < len(all_ids):
        for page_id in all_ids:
            if page_id not in resolved_ids:
                resolved_ids.append(page_id)

    project.set_page_order(resolved_ids)
    page_map = {page.name: page for page in all_pages}
    return [page_map[page_id] for page_id in resolved_ids]


def set_active_page(project: Project, identifier: str) -> tuple[Page, str | None, bool]:
    page = project.find_page(identifier)
    meta = project.get_pages_meta()
    old_active = meta.get("activePageName")
    if old_active == page.name:
        return page, page.display_name, False

    project.set_active_page(page.name)

    old_name = None
    if old_active:
        for candidate in project.get_pages():
            if candidate.name == old_active:
                old_name = candidate.display_name
                break
    return page, old_name, True


def set_page_properties(page: Page, assignments: list[tuple[str, str]]) -> list[PagePropertyChange]:
    changes: list[PagePropertyChange] = []
    for prop, value in assignments:
        old = get_property(page.data, prop, PAGE_PROPERTIES)
        try:
            set_property(page.data, prop, value, PAGE_PROPERTIES)
        except ValueError as e:
            raise ValueError(f"{prop}: {e}") from e
        new = get_property(page.data, prop, PAGE_PROPERTIES)
        changes.append(
            PagePropertyChange(
                prop=prop,
                old=old,
                new=new,
                changed=str(old) != str(new),
            )
        )

    if any(change.changed for change in changes):
        page.save()
    return changes


def set_all_page_properties(
    project: Project,
    assignments: list[tuple[str, str]],
    *,
    exclude: str | None = None,
    dry_run: bool = False,
) -> int:
    pages = project.get_pages()
    if exclude:
        pages = [page for page in pages if exclude not in page.display_name]

    for page in pages:
        for prop, value in assignments:
            try:
                set_property(page.data, prop, value, PAGE_PROPERTIES)
            except ValueError as e:
                raise ValueError(f"{page.display_name}: {prop}: {e}") from e
        if not dry_run:
            page.save()

    return len(pages)


def rename_page(project: Project, page: Page, new_name: str) -> bool:
    if page.display_name == new_name:
        return False
    page.data["displayName"] = new_name
    page.save()
    project.clear_caches()
    return True


def resolve_page_fields(project: Project, fields: list[str]) -> list[tuple[str, str, str]]:
    parsed: list[tuple[str, str, str]] = []
    for field in fields:
        parsed.append(resolve_field_type(project, field, "auto", strict=True))
    return parsed


def get_page_binding_info(page: Page) -> PageBindingInfo | None:
    if is_drillthrough(page):
        return PageBindingInfo(
            binding_type="Drillthrough",
            fields=get_drillthrough_fields(page),
            cross_report=is_cross_report_drillthrough(page),
        )
    if is_tooltip_page(page):
        return PageBindingInfo(
            binding_type="Tooltip",
            fields=get_tooltip_fields(page),
        )
    return None


def configure_page_drillthrough(
    page: Page,
    fields: list[tuple[str, str, str]],
    *,
    cross_report: bool = False,
    hide: bool = True,
) -> None:
    configure_drillthrough(page, fields, cross_report=cross_report, hide=hide)
    page.save()


def clear_page_drillthrough(page: Page) -> bool:
    preview = Page(folder=page.folder, data=copy.deepcopy(page.data))
    if not clear_drillthrough(preview):
        return False
    clear_drillthrough(page)
    page.save()
    return True


def configure_page_tooltip(
    page: Page,
    fields: list[tuple[str, str, str]] | None,
    *,
    width: int = 320,
    height: int = 240,
) -> None:
    configure_tooltip_page(page, fields or None, width=width, height=height)
    page.save()


def clear_page_tooltip(page: Page) -> bool:
    preview = Page(folder=page.folder, data=copy.deepcopy(page.data))
    if not clear_tooltip_page(preview):
        return False
    clear_tooltip_page(page)
    page.save()
    return True
