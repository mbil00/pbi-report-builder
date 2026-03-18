from __future__ import annotations

from dataclasses import dataclass

import pytest

from pbi.lookup import find_page_by_identifier, find_visual_by_identifier


@dataclass(frozen=True)
class FakePage:
    name: str
    display_name: str


@dataclass(frozen=True)
class FakeVisual:
    folder_name: str
    name: str
    visual_type: str


def test_find_page_by_identifier_supports_standard_precedence() -> None:
    pages = [
        FakePage(name="page-a", display_name="Overview"),
        FakePage(name="page-b", display_name="Detail"),
    ]

    assert find_page_by_identifier(
        pages,
        "page-b",
        folder_name=lambda page: page.name,
        display_name=lambda page: page.display_name,
    ) == pages[1]

    assert find_page_by_identifier(
        pages,
        "overview",
        folder_name=lambda page: page.name,
        display_name=lambda page: page.display_name,
    ) == pages[0]

    assert find_page_by_identifier(
        pages,
        "2",
        folder_name=lambda page: page.name,
        display_name=lambda page: page.display_name,
    ) == pages[1]


def test_find_page_by_identifier_reports_suggestion() -> None:
    pages = [FakePage(name="page-a", display_name="Overview")]

    with pytest.raises(ValueError, match='Did you mean: "Overview"'):
        find_page_by_identifier(
            pages,
            "Overveiw",
            folder_name=lambda page: page.name,
            display_name=lambda page: page.display_name,
        )


def test_find_visual_by_identifier_uses_exact_maps_and_unique_type_match() -> None:
    visuals = [
        FakeVisual(folder_name="v-a", name="salesCard", visual_type="cardVisual"),
        FakeVisual(folder_name="v-b", name="regionChart", visual_type="clusteredColumnChart"),
    ]

    assert find_visual_by_identifier(
        visuals,
        "v-b",
        page_display_name="Overview",
        folder_name=lambda visual: visual.folder_name,
        visual_name=lambda visual: visual.name,
        visual_type=lambda visual: visual.visual_type,
        by_folder={visual.folder_name: visual for visual in visuals},
        by_name={visual.name: visual for visual in visuals},
    ) == visuals[1]

    assert find_visual_by_identifier(
        visuals,
        "cardVisual",
        page_display_name="Overview",
        folder_name=lambda visual: visual.folder_name,
        visual_name=lambda visual: visual.name,
        visual_type=lambda visual: visual.visual_type,
    ) == visuals[0]


def test_find_visual_by_identifier_reports_ambiguous_partial_match() -> None:
    visuals = [
        FakeVisual(folder_name="v-a", name="sales-card", visual_type="cardVisual"),
        FakeVisual(folder_name="v-b", name="sales-chart", visual_type="clusteredColumnChart"),
    ]

    with pytest.raises(ValueError, match='Ambiguous visual "sales"'):
        find_visual_by_identifier(
            visuals,
            "sales",
            page_display_name="Overview",
            folder_name=lambda visual: visual.folder_name,
            visual_name=lambda visual: visual.name,
            visual_type=lambda visual: visual.visual_type,
        )
