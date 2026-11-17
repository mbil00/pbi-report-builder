"""An unedited export -> apply leaves files alone (#79).

- ``_write_json`` skips a file whose parsed content (values, types, key order)
  already equals what it would write, keeping Desktop's float text, CRLF and
  missing trailing newline.
- Bookmark group reconcile keeps ``bookmarks.json`` items where they are.
- Query-metadata pruning doesn't add ``"objects": {}``.
- A textbox whose text and style already match the YAML keeps its paragraphs
  and runs, including report-04's second paragraph and report-03's old quoted
  runs; changed text is still written.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from pbi.apply.visual_queries import _prune_unbound_query_metadata
from pbi.bookmarks import reconciled_bookmark_items
from pbi.project import Visual, _write_json
from tests.support import cli, report_definition

# --- _write_json -----------------------------------------------------------------

DESKTOP_BYTES = (
    b'{\r\n  "name": "a",\r\n  "position": {\r\n    "x": 926.93393562958784,\r\n'
    b'    "z": 4.0\r\n  }\r\n}'
)


def test_write_json_keeps_bytes_when_content_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "visual.json"
    path.write_bytes(DESKTOP_BYTES)

    _write_json(path, json.loads(DESKTOP_BYTES))

    assert path.read_bytes() == DESKTOP_BYTES


def test_write_json_writes_when_key_order_changes(tmp_path: Path) -> None:
    path = tmp_path / "visual.json"
    path.write_bytes(DESKTOP_BYTES)
    data = json.loads(DESKTOP_BYTES)

    _write_json(path, {"position": data["position"], "name": "a"})

    assert list(json.loads(path.read_bytes())) == ["position", "name"]


def test_write_json_writes_when_a_number_type_changes(tmp_path: Path) -> None:
    path = tmp_path / "visual.json"
    path.write_bytes(DESKTOP_BYTES)
    data = json.loads(DESKTOP_BYTES)
    data["position"]["z"] = 4

    _write_json(path, data)

    assert json.loads(path.read_bytes())["position"]["z"] == 4
    assert b'"z": 4\r\n' in path.read_bytes()


def test_write_json_creates_a_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "new.json"

    _write_json(path, {"a": 1})

    assert json.loads(path.read_bytes()) == {"a": 1}


# --- bookmarks.json items --------------------------------------------------------

# report-03's bookmarks.json: groups between standalone bookmarks.
REPORT_03_ITEMS = [
    {"name": "e9bf"},
    {"name": "c49b", "displayName": "Department Views", "children": ["17ae", "d15d", "ea2f"]},
    {"name": "e53f", "displayName": "Variance Views", "children": ["649d", "bc9d"]},
    {"name": "a178"},
    {"name": "9530"},
]
REPORT_03_PLACEMENTS = [
    ("e9bf", None),
    ("17ae", "Department Views"),
    ("d15d", "Department Views"),
    ("ea2f", "Department Views"),
    ("649d", "Variance Views"),
    ("bc9d", "Variance Views"),
    ("a178", None),
    ("9530", None),
]


def test_bookmark_items_unchanged_when_every_bookmark_stays() -> None:
    assert reconciled_bookmark_items(REPORT_03_ITEMS, REPORT_03_PLACEMENTS) == REPORT_03_ITEMS


def test_bookmark_items_keep_unplaced_items_in_place() -> None:
    items = reconciled_bookmark_items(REPORT_03_ITEMS, [("a178", None), ("new1", None)])

    assert items == [*REPORT_03_ITEMS, {"name": "new1"}]


def test_bookmark_moving_into_new_group_puts_group_in_its_slot() -> None:
    items = reconciled_bookmark_items(
        REPORT_03_ITEMS, [("a178", "Extras"), ("9530", "Extras")]
    )

    assert [item.get("displayName", item["name"]) for item in items] == [
        "e9bf", "Department Views", "Variance Views", "Extras",
    ]
    assert items[3]["children"] == ["a178", "9530"]


def test_bookmark_leaving_a_group_goes_right_after_it() -> None:
    items = reconciled_bookmark_items(REPORT_03_ITEMS, [("d15d", None)])

    assert items[1] == {"name": "c49b", "displayName": "Department Views", "children": ["17ae", "ea2f"]}
    assert items[2] == {"name": "d15d"}
    assert items[3]["displayName"] == "Variance Views"


def test_bookmark_joining_an_existing_group_keeps_one_group() -> None:
    items = reconciled_bookmark_items(REPORT_03_ITEMS, [("a178", "variance views")])

    groups = [item for item in items if item.get("displayName") == "Variance Views"]
    assert len(groups) == 1
    assert groups[0] == {"name": "e53f", "displayName": "Variance Views", "children": ["649d", "bc9d", "a178"]}
    assert {"name": "a178"} not in items


def test_bookmark_group_emptied_by_placements_is_dropped() -> None:
    items = reconciled_bookmark_items(REPORT_03_ITEMS, [("649d", None), ("bc9d", None)])

    assert all(item.get("displayName") != "Variance Views" for item in items)
    assert [item["name"] for item in items] == ["e9bf", "c49b", "649d", "bc9d", "a178", "9530"]


def test_group_of_one_placed_bookmark_is_written_as_that_bookmark() -> None:
    items = reconciled_bookmark_items(REPORT_03_ITEMS, [("649d", "Variance Views"), ("bc9d", None)])

    assert [item["name"] for item in items] == ["e9bf", "c49b", "649d", "bc9d", "a178", "9530"]
    assert items[2] == {"name": "649d"}


# --- query metadata ----------------------------------------------------------------


def test_prune_unbound_query_metadata_adds_no_objects(tmp_path: Path) -> None:
    data = {"visual": {"visualType": "card", "query": {"queryState": {}}}}
    _prune_unbound_query_metadata(Visual(tmp_path, data))

    assert "objects" not in data["visual"]


# --- textboxes ---------------------------------------------------------------------


def _visual_file(root: Path, page_id: str, visual_id: str) -> Path:
    return report_definition(root) / "pages" / page_id / "visuals" / visual_id / "visual.json"


def _export_page(root: Path, page: str) -> Path:
    out = root.parent / "page.yaml"
    result = cli("export", "--page", page, "-o", out, project=root)
    assert result.exit_code == 0, result.output
    return out


def _set_text(spec_path: Path, visual_id: str, text: str) -> None:
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    visuals = [v for page in spec["pages"] for v in page.get("visuals", []) if v.get("id") == visual_id]
    assert len(visuals) == 1
    visuals[0]["text"] = text
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")


def test_unedited_textbox_keeps_desktop_paragraphs(fixture_copy) -> None:
    root = fixture_copy("report-04-desktop-shapes")
    header = _visual_file(root, "930a249948047432b8ba", "7d88e913cd74e62b0c83")
    link = _visual_file(root, "930a249948047432b8ba", "0edca500e000b9be8bca")
    before = {header: header.read_bytes(), link: link.read_bytes()}
    spec = _export_page(root, "Overview")

    result = cli("apply", spec, project=root)

    assert result.exit_code == 0, result.output
    assert {path: path.read_bytes() for path in before} == before


def test_changed_textbox_text_is_written(fixture_copy) -> None:
    root = fixture_copy("report-04-desktop-shapes")
    header = _visual_file(root, "930a249948047432b8ba", "7d88e913cd74e62b0c83")
    spec = _export_page(root, "Overview")
    _set_text(spec, "7d88e913cd74e62b0c83", "Delivery Review")

    result = cli("apply", spec, project=root)

    assert result.exit_code == 0, result.output
    paragraphs = json.loads(header.read_bytes())["visual"]["objects"]["general"][0]["properties"]["paragraphs"]
    assert paragraphs[0]["textRuns"][0]["value"] == "Delivery Review"


def test_unedited_legacy_quoted_textbox_is_left_alone(fixture_copy) -> None:
    """report-03's pbi-written runs hold quoted literals; an unedited apply doesn't touch them."""
    root = fixture_copy("report-03-authoring-parity-lab")
    title = _visual_file(root, "27fe4d5736a37e897ff8", "9ca99fe3c514a525e66c")
    before = title.read_bytes()
    spec = _export_page(root, "Executive Overview")

    result = cli("apply", spec, project=root)

    assert result.exit_code == 0, result.output
    assert title.read_bytes() == before

    _set_text(spec, "9ca99fe3c514a525e66c", "Finance Dashboard")
    result = cli("apply", spec, project=root)

    assert result.exit_code == 0, result.output
    run = json.loads(title.read_bytes())["visual"]["objects"]["general"][0]["properties"]["paragraphs"][0]["textRuns"][0]
    assert run["value"] == "Finance Dashboard"
