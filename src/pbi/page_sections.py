"""Helpers for authoring page sections."""

from __future__ import annotations

from dataclasses import dataclass

from pbi.project import Page, Project
from pbi.properties import VISUAL_PROPERTIES, set_property as set_visual_property
from pbi.visual_groups import create_group


@dataclass(frozen=True)
class PageSectionResult:
    page_name: str
    title: str
    background_visual: str
    title_visual: str
    group_visual: str
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class PageSectionInfo:
    name: str
    x: int
    y: int
    width: int
    height: int


def create_page_section(
    project: Project,
    page: Page,
    title: str,
    *,
    x: int = 0,
    y: int = 0,
    width: int = 512,
    height: int = 220,
    background: str = "#F5F5F5",
    radius: int = 10,
    title_color: str = "#002C77",
    title_font: str = "Segoe UI Semibold",
    title_size: int = 14,
) -> PageSectionResult:
    background_visual = project.create_visual(page, "shape", x=x, y=y, width=width, height=height)
    background_visual.data["name"] = f"section-bg-{title.lower().replace(' ', '-')[:20]}"
    set_visual_property(background_visual.data, "border.show", "true", VISUAL_PROPERTIES)
    set_visual_property(background_visual.data, "border.radius", str(radius), VISUAL_PROPERTIES)
    set_visual_property(background_visual.data, "border.color", "#EDEBE9", VISUAL_PROPERTIES)
    set_visual_property(background_visual.data, "background.show", "false", VISUAL_PROPERTIES)
    _set_chart_prop(background_visual.data, "fill", "show", True)
    _set_chart_prop(background_visual.data, "fill", "fillColor", background)
    _set_chart_prop(background_visual.data, "outline", "show", False)
    background_visual.save()

    title_height = title_size + 16
    title_visual = project.create_visual(
        page,
        "textbox",
        x=x + 8,
        y=y + 4,
        width=width - 16,
        height=title_height,
    )
    title_visual.data["name"] = f"section-title-{title.lower().replace(' ', '-')[:20]}"
    title_visual.data.setdefault("visual", {})["objects"] = {
        "general": [
            {
                "properties": {
                    "paragraphs": [
                        {
                            "textRuns": [
                                {
                                    "value": f"'{title}'",
                                    "textStyle": {
                                        "fontFamily": f"'{title_font}'",
                                        "fontSize": f"'{title_size}pt'",
                                        "color": {"expr": {"Literal": {"Value": f"'{title_color}'"}}},
                                    },
                                }
                            ],
                        }
                    ],
                },
            }
        ],
    }
    set_visual_property(title_visual.data, "background.show", "false", VISUAL_PROPERTIES)
    set_visual_property(title_visual.data, "border.show", "false", VISUAL_PROPERTIES)
    title_visual.save()

    group = create_group(project, page, [background_visual, title_visual], display_name=f"Section: {title}")
    return PageSectionResult(
        page_name=page.display_name,
        title=title,
        background_visual=background_visual.name,
        title_visual=title_visual.name,
        group_visual=group.name,
        x=x,
        y=y,
        width=width,
        height=height,
    )


def list_page_sections(project: Project, page: Page) -> list[PageSectionInfo]:
    sections: list[PageSectionInfo] = []
    for visual in project.get_visuals(page):
        if "visualGroup" not in visual.data:
            continue
        display = visual.data.get("visualGroup", {}).get("displayName", "")
        if display.startswith("Section:") or visual.name.startswith("section-bg"):
            position = visual.position
            sections.append(
                PageSectionInfo(
                    name=display.replace("Section: ", "") if display.startswith("Section:") else visual.name,
                    x=position.get("x", 0),
                    y=position.get("y", 0),
                    width=position.get("width", 0),
                    height=position.get("height", 0),
                )
            )
    return sections


def _set_chart_prop(data: dict, obj_name: str, prop_name: str, value: object) -> None:
    objects = data.setdefault("visual", {}).setdefault("objects", {})
    entries = objects.setdefault(obj_name, [])
    entry = None
    for existing in entries:
        selector = existing.get("selector", {})
        if selector.get("id") == "default":
            entry = existing
            break
    if entry is None:
        entry = {"selector": {"id": "default"}, "properties": {}}
        entries.append(entry)

    if isinstance(value, bool):
        encoded = {"expr": {"Literal": {"Value": f"{'true' if value else 'false'}L"}}}
    elif isinstance(value, (int, float)):
        encoded = {"expr": {"Literal": {"Value": f"{value}D"}}}
    else:
        encoded = {"expr": {"Literal": {"Value": f"'{value}'"}}}
    entry["properties"][prop_name] = [encoded]
