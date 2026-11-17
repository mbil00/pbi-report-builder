"""Hierarchy-level bindings and filters round-trip through export and apply (#69).

Desktop binds a hierarchy level as a ``HierarchyLevel`` field, over a model
hierarchy (report-04's ``Project[Portfolio Tree]`` matrix rows) or over a date
column's variation (sample-report's ``Date[Date]`` → ``Date Hierarchy``).
Export writes them as ``{hierarchy, level}`` / ``{column, variation,
hierarchy, level}`` mappings and apply reads them back.

The full-report round-trips of these fixtures still xfail in
``test_fixture_harness`` on other issues (#108, #109), so these tests pin the
pages and visuals #69 broke.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from pbi.hierarchy_fields import HierarchyLevelRef, parse_hierarchy_spec
from pbi.model import SemanticModel
from pbi.project import Project
from tests.support import cli, make_project, read_json, write_model_table

SHAPES = "report-04-desktop-shapes"
SAMPLE = "sample-report"
MATRIX_PAGE = "Task Board"
MATRIX = "a375982550080600757e"  # Portfolio Matrix (pivotTable)
# sample-report visuals binding levels of a date column's variation hierarchy.
VARIATION_VISUALS = {
    "01 Relative Date": "dcf7bcc8185a099d336e",  # tableEx over Date[Date]
    "11 Slicers": "1dfa70a8b011da246684",  # slicer over Sales[OrderDateTime]
}


def _visual_json(root: Path, page: str, visual: str) -> dict:
    project = Project.find(root)
    return read_json(project.find_visual(project.find_page(page), visual).folder / "visual.json")


def _export_page(root: Path, page: str, out: Path) -> dict:
    exported = cli("export", "--page", page, "-o", out, project=root)
    assert exported.exit_code == 0, exported.output
    return yaml.safe_load(out.read_text(encoding="utf-8"))


def _exported_visual(spec: dict, visual: str) -> dict:
    return next(v for v in spec["pages"][0]["visuals"] if v["id"] == visual)


# --- report-04: model hierarchy -------------------------------------------------


def test_matrix_page_export_apply_keeps_hierarchy_query_and_filters(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(SHAPES)
    before = _visual_json(root, MATRIX_PAGE, MATRIX)
    spec_path = tmp_path / "page.yaml"
    spec = _export_page(root, MATRIX_PAGE, spec_path)

    matrix = _exported_visual(spec, MATRIX)
    assert matrix["bindings"]["Rows"] == [
        {"hierarchy": "Project.Portfolio Tree", "level": "Portfolio"},
        {"hierarchy": "Project.Portfolio Tree", "level": "ProjectName"},
    ]
    assert [f["field"] for f in matrix["filters"][:2]] == [
        {"hierarchy": "Project.Portfolio Tree", "level": "Portfolio"},
        {"hierarchy": "Project.Portfolio Tree", "level": "ProjectName"},
    ]

    applied = cli("apply", spec_path, project=root)

    assert applied.exit_code == 0, applied.output
    after = _visual_json(root, MATRIX_PAGE, MATRIX)
    # The existing projections survive untouched, ``active`` flags included.
    assert after["visual"]["query"] == before["visual"]["query"]
    assert after["filterConfig"] == before["filterConfig"]


def test_new_hierarchy_binding_writes_desktop_projection(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(SHAPES)
    desktop = _visual_json(root, MATRIX_PAGE, MATRIX)["visual"]["query"]["queryState"]["Rows"]
    spec_path = tmp_path / "new.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "pages": [
                    {
                        "name": MATRIX_PAGE,
                        "visuals": [
                            {
                                "name": "hierarchyMatrix",
                                "type": "pivotTable",
                                "position": "0, 0",
                                "size": "400 x 300",
                                "bindings": {
                                    "Rows": [
                                        {"hierarchy": "project.portfolio tree", "level": "portfolio"},
                                        {
                                            "field": {"hierarchy": "Project.Portfolio Tree", "level": "ProjectName"},
                                            "displayName": "Project",
                                        },
                                    ],
                                    "Values": "Measures Table.Task Count (measure)",
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    applied = cli("apply", spec_path, project=root)

    assert applied.exit_code == 0, applied.output
    rows = _visual_json(root, MATRIX_PAGE, "hierarchyMatrix")["visual"]["query"]["queryState"]["Rows"]
    expected = []
    for projection in copy.deepcopy(desktop["projections"]):
        projection.pop("active")  # drill state, not part of a new binding
        expected.append(projection)
    expected[1]["displayName"] = "Project"
    # Names are canonicalized to the model's spelling.
    assert rows["projections"] == expected


def test_hierarchy_binding_errors_name_the_missing_part(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(SHAPES)
    spec_path = tmp_path / "bad.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "pages": [
                    {
                        "name": MATRIX_PAGE,
                        "visuals": [
                            {
                                "id": MATRIX,
                                "type": "pivotTable",
                                "bindings": {
                                    "Rows": [{"hierarchy": "Project.Portfolio Tree", "level": "Portfolo"}],
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    applied = cli("apply", spec_path, project=root)

    assert applied.exit_code == 1
    assert 'Level "Portfolo" not found in hierarchy "Portfolio Tree". Did you mean: "Portfolio"?' in applied.output


# --- sample-report: date variation hierarchy -------------------------------------


@pytest.mark.parametrize("page", list(VARIATION_VISUALS))
def test_variation_page_export_apply_keeps_hierarchy_query(
    fixture_copy: Callable[[str], Path], tmp_path: Path, page: str
) -> None:
    root = fixture_copy(SAMPLE)
    visual = VARIATION_VISUALS[page]
    before = _visual_json(root, page, visual)["visual"]["query"]
    spec_path = tmp_path / "page.yaml"
    spec = _export_page(root, page, spec_path)

    values = _exported_visual(spec, visual)["bindings"]["Values"]
    assert [item["level"] for item in values] == ["Year", "Quarter", "Month", "Day"]
    assert values[0] == {
        "column": "Date.Date" if visual == "dcf7bcc8185a099d336e" else "Sales.OrderDateTime",
        "variation": "Variation",
        "hierarchy": "Date Hierarchy",
        "level": "Year",
    }

    applied = cli("apply", spec_path, project=root)

    assert applied.exit_code == 0, applied.output
    assert _visual_json(root, page, visual)["visual"]["query"] == before


def test_variation_level_encodes_as_desktop_wrote_it(fixture_copy: Callable[[str], Path]) -> None:
    root = fixture_copy(SAMPLE)
    model = SemanticModel.load(root)
    projections = _visual_json(root, "01 Relative Date", "dcf7bcc8185a099d336e")["visual"]["query"][
        "queryState"
    ]["Values"]["projections"]

    for projection in projections:
        ref = HierarchyLevelRef.from_field(projection["field"])
        assert ref is not None
        parsed, data_type = parse_hierarchy_spec(ref.to_spec(), model)
        assert parsed == ref
        assert data_type is not None
        assert parsed.to_field() == projection["field"]
        assert parsed.query_ref == projection["queryRef"]
        assert parsed.native_query_ref == projection["nativeQueryRef"]


@pytest.mark.parametrize(
    ("spec", "message"),
    [
        (
            {"column": "Date.Date", "variation": "Variaton", "hierarchy": "Date Hierarchy", "level": "Year"},
            'Variation "Variaton" not found in column "Date.Date". Did you mean: "Variation"?',
        ),
        (
            {"column": "Date.Date", "variation": "Variation", "hierarchy": "Date Hierarchy", "level": "Week"},
            'Level "Week" not found in hierarchy "Date Hierarchy". Available: "Year", "Quarter", "Month", "Day"',
        ),
        (
            {"column": "Date.Year", "variation": "Variation", "hierarchy": "Date Hierarchy", "level": "Year"},
            'Variation "Variation" not found in column "Date.Year". Available: (none)',
        ),
        (
            {"variation": "Variation", "hierarchy": "Date.Date Hierarchy", "level": "Year"},
            "a hierarchy level with 'variation' also needs 'column'",
        ),
        (
            {"hierarchy": "Date.Date Hierarchy", "level": "Year", "levle": "x"},
            "unknown hierarchy-level key(s) levle",
        ),
    ],
)
def test_variation_spec_errors(fixture_copy: Callable[[str], Path], spec: dict, message: str) -> None:
    model = SemanticModel.load(fixture_copy(SAMPLE))

    with pytest.raises(ValueError) as excinfo:
        parse_hierarchy_spec(spec, model)

    assert message in str(excinfo.value)


# --- names with dots and the parser ------------------------------------------------


DOTTED_TABLE = """
table 'Sales.EU'
\tcolumn 'Region.Name'
\t\tdataType: string
\t\tsourceColumn: Region.Name

\tcolumn City
\t\tdataType: string
\t\tsourceColumn: City

\thierarchy 'Geo.Tree'
\t\tlevel 'Region.Name'
\t\t\tcolumn: 'Region.Name'

\t\tlevel City
\t\t\tcolumn: City
"""


def test_dotted_names_round_trip(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    write_model_table(tmp_path, "Sales.EU.tmdl", DOTTED_TABLE)
    model = SemanticModel.load(project.root)

    ref, data_type = parse_hierarchy_spec({"hierarchy": "Sales.EU.Geo.Tree", "level": "Region.Name"}, model)

    assert ref == HierarchyLevelRef("Sales.EU", "Geo.Tree", "Region.Name")
    assert data_type == "string"
    assert ref.to_spec() == {"hierarchy": "Sales.EU.Geo.Tree", "level": "Region.Name"}
    assert HierarchyLevelRef.from_field(ref.to_field()) == ref


VARIATION_TABLES = {
    "Orders.tmdl": """
table Orders
\tcolumn OrderDate
\t\tdataType: dateTime
\t\tsourceColumn: OrderDate

\t\tvariation Variation
\t\t\tisDefault
\t\t\trelationship: 0f0e1d2c
\t\t\tdefaultHierarchy: 'LocalDateTable_1'.'Date Hierarchy'

\t\tannotation SummarizationSetBy = Automatic

\tcolumn ShipDate
\t\tdataType: dateTime
\t\tsourceColumn: ShipDate

\t\tvariation Bare
\t\t\tisDefault

\tcolumn 'Late Flag' =
\t\t\tVAR variation = 1
\t\t\tRETURN variation
\t\tdataType: int64
""",
    "LocalDateTable_1.tmdl": """
table LocalDateTable_1
\tcolumn Year
\t\tdataType: int64

\thierarchy 'Date Hierarchy'
\t\tlevel Year
\t\t\tcolumn: Year
""",
}


def test_parser_reads_column_variations(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    for name, content in VARIATION_TABLES.items():
        write_model_table(tmp_path, name, content)
    orders = SemanticModel.load(project.root).find_table("Orders")

    order_date = orders.find_column("OrderDate")
    assert [(v.name, v.default_hierarchy_table, v.default_hierarchy) for v in order_date.variations] == [
        ("Variation", "LocalDateTable_1", "Date Hierarchy")
    ]
    assert [(v.name, v.default_hierarchy) for v in orders.find_column("ShipDate").variations] == [("Bare", "")]
    late = orders.find_column("Late Flag")
    assert late.variations == []
    assert "VAR variation = 1" in late.expression


def test_variation_without_default_hierarchy_keeps_names(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    for name, content in VARIATION_TABLES.items():
        write_model_table(tmp_path, name, content)
    model = SemanticModel.load(project.root)

    ref, data_type = parse_hierarchy_spec(
        {"column": "orders.shipdate", "variation": "bare", "hierarchy": "Date Hierarchy", "level": "Year"},
        model,
    )

    assert ref == HierarchyLevelRef("Orders", "Date Hierarchy", "Year", column="ShipDate", variation="Bare")
    assert data_type is None


# --- filters -----------------------------------------------------------------------


def _apply_matrix_filters(root: Path, tmp_path: Path, filters: list[dict]) -> object:
    spec_path = tmp_path / "filters.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {"pages": [{"name": MATRIX_PAGE, "visuals": [{"id": MATRIX, "type": "pivotTable", "filters": filters}]}]}
        ),
        encoding="utf-8",
    )
    return cli("apply", spec_path, project=root)


def test_hierarchy_filter_without_raw_writes_desktop_shape(
    fixture_copy: Callable[[str], Path], tmp_path: Path
) -> None:
    root = fixture_copy(SHAPES)
    desktop = _visual_json(root, MATRIX_PAGE, MATRIX)["filterConfig"]["filters"][0]

    applied = _apply_matrix_filters(
        root,
        tmp_path,
        [
            {
                "field": {"hierarchy": "Project.Portfolio Tree", "level": "Portfolio"},
                "type": "Categorical",
                "name": desktop["name"],
            }
        ],
    )

    assert applied.exit_code == 0, applied.output
    assert _visual_json(root, MATRIX_PAGE, MATRIX)["filterConfig"]["filters"] == [desktop]


@pytest.mark.parametrize(
    ("filter_spec", "message"),
    [
        (
            {"field": {"hierarchy": "Project.Portfolio Tree", "level": "Portfolio"}, "values": ["A"]},
            "a hierarchy-level filter supports only an empty Categorical filter",
        ),
        (
            {"field": {"hierarchy": "Project.Portfolio Tre", "level": "Portfolio"}},
            'Hierarchy "Portfolio Tre" not found in table "Project"',
        ),
    ],
)
def test_hierarchy_filter_errors(
    fixture_copy: Callable[[str], Path], tmp_path: Path, filter_spec: dict, message: str
) -> None:
    root = fixture_copy(SHAPES)

    applied = _apply_matrix_filters(root, tmp_path, [filter_spec])

    assert applied.exit_code == 1
    assert message in applied.output
