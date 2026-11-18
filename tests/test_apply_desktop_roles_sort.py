"""Desktop-saved roles and sorts the extracted schema does not list (#109).

sample-report (Desktop-saved) holds a cardVisual with a ``Rows`` projection,
an ``Aggregation`` (Min of a column) in its measure-kind ``Tooltips`` role, and
a keyDriversVisual with a default ``sortDefinition``. Apply used to reject all
three. The full-report round trip is still an xfail in ``test_fixture_harness``
(#108); these tests pin the #109 shapes.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from tests.support import cli, read_json, report_definition

FIXTURE = "sample-report"
PAGE = "14 visuals with bindings"
CARD = "4881412909e86c0ae023"  # cardVisual: Data, Rows (Product.Category), Tooltips (Min SaleID)
KEY_DRIVERS = "13ccb523443b4a2550ad"  # keyDriversVisual sorted by Sales.Total Quantity desc


def _visual_path(root: Path, visual: str) -> Path:
    return next(report_definition(root).glob(f"pages/*/visuals/{visual}/visual.json"))


def _query(root: Path, visual: str) -> dict:
    return read_json(_visual_path(root, visual))["visual"]["query"]


def _export_page(root: Path, tmp_path: Path) -> Path:
    spec = tmp_path / "page.yaml"
    result = cli("export", "--page", PAGE, "-o", spec, project=root)
    assert result.exit_code == 0, result.output
    return spec


def test_page_export_apply_keeps_card_rows_and_key_driver_sort(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(FIXTURE)
    card_bytes = _visual_path(root, CARD).read_bytes()
    key_drivers_query = _query(root, KEY_DRIVERS)
    spec = _export_page(root, tmp_path)

    applied = cli("apply", spec, project=root)

    assert applied.exit_code == 0, applied.output
    assert _visual_path(root, CARD).read_bytes() == card_bytes
    assert _query(root, KEY_DRIVERS) == key_drivers_query


def test_apply_rejects_a_new_sort_on_key_drivers(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(FIXTURE)
    before = _query(root, KEY_DRIVERS)
    spec = tmp_path / "page.yaml"
    spec.write_text(
        json.dumps({
            "pages": [{
                "name": PAGE,
                "visuals": [{
                    "id": KEY_DRIVERS,
                    "type": "keyDriversVisual",
                    "sort": "Sales.Total Quantity (measure) Ascending",
                }],
            }],
        }),
        encoding="utf-8",
    )

    applied = cli("apply", spec, project=root)

    assert applied.exit_code == 1
    assert "keyDriversVisual does not support sorting" in applied.output
    assert _query(root, KEY_DRIVERS) == before


def test_sort_set_restating_key_drivers_sort_is_a_no_op(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(FIXTURE)
    before = _visual_path(root, KEY_DRIVERS).read_bytes()

    same = cli("visual", "sort", "set", PAGE, KEY_DRIVERS, "Sales.Total Quantity", project=root)
    flipped = cli(
        "visual", "sort", "set", PAGE, KEY_DRIVERS, "Sales.Total Quantity", "--direction", "asc",
        project=root,
    )

    assert same.exit_code == 0, same.output
    assert flipped.exit_code == 1
    assert "does not support sorting" in flipped.output
    assert _visual_path(root, KEY_DRIVERS).read_bytes() == before


def test_bind_card_rows_writes_desktop_projection(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(FIXTURE)
    desktop_rows = _query(root, CARD)["queryState"]["Rows"]
    unbound = cli("visual", "unbind", PAGE, CARD, "Rows", project=root)
    assert unbound.exit_code == 0, unbound.output
    assert "Rows" not in _query(root, CARD)["queryState"]

    bound = cli("visual", "bind", PAGE, CARD, "Rows", "Product.Category", project=root)

    assert bound.exit_code == 0, bound.output
    assert _query(root, CARD)["queryState"]["Rows"] == desktop_rows


def test_card_rows_takes_a_column(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(FIXTURE)
    before = _visual_path(root, CARD).read_bytes()

    measure = cli("visual", "bind", PAGE, CARD, "Rows", "Sales.Total Revenue", project=root)

    assert measure.exit_code == 1
    assert 'Role "Rows" must use a column' in measure.output
    assert _visual_path(root, CARD).read_bytes() == before


def test_card_rows_role_is_case_insensitive(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(FIXTURE)
    desktop_rows = _query(root, CARD)["queryState"]["Rows"]

    unbound = cli("visual", "unbind", PAGE, CARD, "rows", project=root)
    assert unbound.exit_code == 0, unbound.output
    assert "Rows" not in _query(root, CARD)["queryState"]

    bound = cli("visual", "bind", PAGE, CARD, "rows", "Product.Category", project=root)

    assert bound.exit_code == 0, bound.output
    assert _query(root, CARD)["queryState"]["Rows"] == desktop_rows


def test_create_card_binds_rows_but_does_not_scaffold_it(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(FIXTURE)
    desktop_rows = _query(root, CARD)["queryState"]["Rows"]

    with_rows = cli(
        "visual", "create", PAGE, "cardVisual", "--name", "with-rows",
        "--bind", "Data=Sales.Total Revenue", "--bind", "Rows=Product.Category",
        project=root,
    )
    plain = cli("visual", "create", PAGE, "cardVisual", "--name", "plain", project=root)

    assert with_rows.exit_code == 0, with_rows.output
    assert plain.exit_code == 0, plain.output
    states = {
        data["name"]: data["visual"]["query"]["queryState"]
        for data in (read_json(p) for p in report_definition(root).glob("pages/*/visuals/*/visual.json"))
        if data.get("name") in {"with-rows", "plain"}
    }
    assert states["with-rows"]["Rows"] == desktop_rows
    assert "Rows" not in states["plain"]


def test_apply_keeps_card_aggregation_under_an_abbreviated_table_name(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(FIXTURE)
    card_bytes = _visual_path(root, CARD).read_bytes()
    spec = _export_page(root, tmp_path)
    text = spec.read_text(encoding="utf-8")
    assert "Tooltips: Sales.SaleID" in text
    spec.write_text(text.replace("Tooltips: Sales.SaleID", "Tooltips: Sal.SaleID"), encoding="utf-8")

    applied = cli("apply", spec, project=root)

    assert applied.exit_code == 0, applied.output
    assert _visual_path(root, CARD).read_bytes() == card_bytes


def _column_projection(entity: str, prop: str) -> dict:
    return {
        "field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
        "queryRef": f"{entity}.{prop}",
        "nativeQueryRef": prop,
    }


def test_projection_match_compares_fields_not_display_suffixes() -> None:
    from pbi.roundtrip_primitives import BindingItem, match_existing_projection

    suffixed = _column_projection("Task", "TaskName (measure)")
    plain = _column_projection("Task", "TaskName")
    item = BindingItem(field_ref="Task.TaskName", entity="Task", prop="TaskName", field_type="column")

    assert match_existing_projection([suffixed, plain], item) is plain


def test_projection_match_prefers_a_name_match_over_the_resolved_field() -> None:
    from pbi.roundtrip_primitives import BindingItem, match_existing_projection

    summed = {
        "field": {"Aggregation": {"Expression": _column_projection("Task", "ActualHours")["field"], "Function": 0}},
        "queryRef": "Sum(Task.ActualHours)",
        "nativeQueryRef": "Sum of ActualHours",
    }
    plain = _column_projection("Task", "ActualHours")
    item = BindingItem(field_ref="Tas.ActualHours", entity="Task", prop="ActualHours", field_type="column")

    assert match_existing_projection([summed, plain], item) is plain
    assert match_existing_projection([summed], item) is summed
