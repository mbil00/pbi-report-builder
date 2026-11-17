"""Field parameters: written in Desktop's shape, read in Desktop's and the old pbi shape.

Ground truth is Desktop's ``Metric Selector`` table in ``report-04-desktop-shapes``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest
import yaml

from pbi.model_apply import apply_model_yaml
from pbi.model_export import export_model_yaml
from pbi.modeling.schema import SemanticModel
from pbi.modeling.writes_field_parameters import (
    FieldParameterField,
    create_field_parameter,
    field_parameter_fields,
    field_parameter_source,
    parse_field_parameter_source,
)
from tests.support import SHAPES_DIR, cli, make_project, write_model_table

SHAPES = "report-04-desktop-shapes"
MODEL = "04-desktop-shapes.SemanticModel/definition"
DESKTOP_TABLE = SHAPES_DIR / MODEL / "tables" / "Metric Selector.tmdl"
DESKTOP_ROWS = [
    FieldParameterField("Total Hours", "Measures Table", "Total Hours"),
    FieldParameterField("Task Count", "Measures Table", "Task Count"),
    FieldParameterField("Expense Amount", "Measures Table", "Expense Amount"),
]
DESKTOP_FIELDS = [row.ref for row in DESKTOP_ROWS]
DESKTOP_LABELS = [row.label for row in DESKTOP_ROWS]

# What ``pbi`` wrote before it followed Desktop: an ``isParameterType`` flag and
# ``[Name]/[Value]/[Ordinal]`` source columns. Projects made with it must still read.
OLD_SHAPE = """\
table 'Metric Picker'
\tisParameterType
\tlineageTag: 11111111-1111-1111-1111-111111111111

\tcolumn 'Metric Picker'
\t\tdataType: string
\t\tisHidden
\t\tisNameInferred
\t\tlineageTag: 22222222-2222-2222-2222-222222222222
\t\tsourceColumn: [Name]
\t\tsortByColumn: 'Metric Picker Order'

\t\tannotation SummarizationType = None

\tcolumn 'Metric Picker Fields'
\t\tdataType: string
\t\tisHidden
\t\tlineageTag: 33333333-3333-3333-3333-333333333333
\t\tsourceColumn: [Value]

\t\tannotation SummarizationType = None

\t\tannotation PBI_ChangedProperties = ["IsHidden"]

\tcolumn 'Metric Picker Order'
\t\tdataType: int64
\t\tisHidden
\t\tlineageTag: 44444444-4444-4444-4444-444444444444
\t\tsourceColumn: [Ordinal]

\t\tannotation SummarizationType = None

\t\tannotation PBI_ChangedProperties = ["IsHidden"]

\tpartition 'Metric Picker' = calculated
\t\tmode: import
\t\tsource =
\t\t\t{
\t\t\t("Hours", NAMEOF('Measures Table'[Total Hours]), 0),
\t\t\t("Tasks", NAMEOF('Measures Table'[Task Count]), 1)
\t\t\t}
"""

_IDS = re.compile(rb"(lineageTag: |PBI_Id = )[0-9a-f-]+")


def _shape(data: bytes, name: str) -> bytes:
    """A table file with its IDs and its own name masked, to compare shapes."""
    return _IDS.sub(rb"\1<id>", data).replace(name.encode(), b"<name>")


@pytest.fixture
def shapes(fixture_copy: Callable[[str], Path]) -> Path:
    return fixture_copy(SHAPES)


def _tables(project: Path) -> Path:
    """The tables folder of a report-04 copy or a ``make_project`` project."""
    model = project / MODEL
    return (model if model.exists() else project / "Sample.SemanticModel" / "definition") / "tables"


def _apply(project: Path, spec: dict) -> None:
    result = apply_model_yaml(project, yaml.safe_dump(spec, sort_keys=False))
    assert result.errors == []


# --- Writing: Desktop's shape ------------------------------------------------


def test_create_writes_desktops_metric_selector_shape(shapes: Path) -> None:
    result = cli(
        "model", "field-parameter", "create", "Copy Selector", *DESKTOP_FIELDS,
        *(arg for label in DESKTOP_LABELS for arg in ("--labels", label)),
        project=shapes,
    )
    assert result.exit_code == 0, result.output

    created = (_tables(shapes) / "Copy Selector.tmdl").read_bytes()
    assert _shape(created, "Copy Selector") == _shape(DESKTOP_TABLE.read_bytes(), "Metric Selector")
    model_lines = (shapes / MODEL / "model.tmdl").read_text(encoding="utf-8").splitlines()
    assert "ref table 'Copy Selector'" in model_lines


def test_model_apply_writes_desktops_shape(shapes: Path) -> None:
    rows = [{"field": row.ref, "label": row.label} for row in DESKTOP_ROWS]
    _apply(shapes, {"fieldParameters": {"Copy Selector": {"fields": rows}}})

    created = (_tables(shapes) / "Copy Selector.tmdl").read_bytes()
    assert _shape(created, "Copy Selector") == _shape(DESKTOP_TABLE.read_bytes(), "Metric Selector")


def test_created_ids_are_fresh(shapes: Path) -> None:
    create_field_parameter(shapes, "A", DESKTOP_FIELDS, None)
    create_field_parameter(shapes, "B", DESKTOP_FIELDS, None)
    tags = [
        set(re.findall(rb"(?:lineageTag: |PBI_Id = )([0-9a-f-]+)", (_tables(shapes) / f"{n}.tmdl").read_bytes()))
        for n in ("A", "B")
    ]
    assert len(tags[0]) == 5 and not tags[0] & tags[1]


def test_labels_default_to_field_names(shapes: Path) -> None:
    create_field_parameter(shapes, "Picker", ["measures table.task count"], None)
    table = SemanticModel.load(shapes).find_table("Picker")
    assert field_parameter_fields(table) == [DESKTOP_ROWS[1]]


def test_dry_run_writes_nothing(shapes: Path) -> None:
    model_tmdl = (shapes / MODEL / "model.tmdl").read_bytes()
    _, path, _ = create_field_parameter(shapes, "Picker", DESKTOP_FIELDS, None, dry_run=True)
    assert not path.exists()
    assert (shapes / MODEL / "model.tmdl").read_bytes() == model_tmdl


@pytest.mark.parametrize(
    ("name", "fields", "labels", "message"),
    [
        ("Metric Selector", DESKTOP_FIELDS[:1], None, "already exists"),
        ("Picker", [], None, "At least one field"),
        ("Picker", DESKTOP_FIELDS, ["Only one"], "Labels count"),
        ("Picker", ["Measures Table.Nope"], None, "not found"),
        ("Picker", ["NoDot"], None, "Table.Field"),
        ("Picker", DESKTOP_FIELDS[:1], ["two\nlines"], "single line"),
    ],
)
def test_create_rejects(shapes: Path, name: str, fields: list[str], labels: list[str] | None, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        create_field_parameter(shapes, name, fields, labels)
    assert not (_tables(shapes) / "Picker.tmdl").exists()


def test_names_and_labels_needing_escapes_round_trip(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_model_table(tmp_path, "Owner's Info.tmdl", """
table 'Owner''s Info'
\tlineageTag: t1

\tcolumn 'Rev [USD]'
\t\tdataType: double
\t\tlineageTag: c1
\t\tsourceColumn: Rev [USD]
""")
    labels = ['Say "hi"', "", "Owner's"]
    fields = ["Owner's Info.Rev [USD]"] * 3
    create_field_parameter(tmp_path, "Odd 'Names'", fields, labels)

    source = (_tables(tmp_path) / "Odd 'Names'.tmdl").read_text(encoding="utf-8")
    assert "NAMEOF('Owner''s Info'[Rev [USD]]])" in source
    assert '("Say ""hi""", ' in source
    table = SemanticModel.load(tmp_path).find_table("Odd 'Names'")
    assert field_parameter_fields(table) == [
        FieldParameterField(label, "Owner's Info", "Rev [USD]") for label in labels
    ]


# --- Reading: Desktop's shape and the old pbi shape --------------------------


def test_desktop_field_parameter_is_read(shapes: Path) -> None:
    model = SemanticModel.load(shapes)
    table = model.find_table("Metric Selector")
    assert table.is_field_parameter
    assert not table.is_parameter_type  # Desktop writes no isParameterType flag
    assert [c.name for c in table.columns if c.is_field_parameter_fields] == ["Metric Selector Fields"]
    assert field_parameter_fields(table) == DESKTOP_ROWS
    others = [t.name for t in model.tables if t.is_field_parameter and t.name != "Metric Selector"]
    assert others == []


def test_old_pbi_shape_is_read(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_model_table(tmp_path, "Measures Table.tmdl", "table 'Measures Table'\n\tmeasure 'Total Hours' = 1\n")
    write_model_table(tmp_path, "Metric Picker.tmdl", OLD_SHAPE)

    table = SemanticModel.load(tmp_path).find_table("Metric Picker")
    assert table.is_parameter_type and table.is_field_parameter
    assert field_parameter_fields(table) == [
        FieldParameterField("Hours", "Measures Table", "Total Hours"),
        FieldParameterField("Tasks", "Measures Table", "Task Count"),
    ]


def test_what_if_parameter_is_not_a_field_parameter(tmp_path: Path) -> None:
    """A numeric-range parameter carries ParameterMetadata too, without ``kind: 2``."""
    make_project(tmp_path)
    write_model_table(tmp_path, "Discount.tmdl", """
table Discount
\tcolumn Discount
\t\tsummarizeBy: none
\t\tsourceColumn: [Value]

\t\textendedProperty ParameterMetadata =
\t\t\t\t{
\t\t\t\t  "version": 0
\t\t\t\t}

\tpartition Discount = calculated
\t\tmode: import
\t\tsource = GENERATESERIES(0, 1, 0.1)
""")
    table = SemanticModel.load(tmp_path).find_table("Discount")
    assert table.columns[0].extended_properties == {"ParameterMetadata": '{\n"version": 0\n}'}
    assert not table.is_field_parameter


@pytest.mark.parametrize(
    "source",
    [
        '{\n    ("A", NAMEOF(Sales[Revenue]), 1),\n    ("B", NAMEOF(\'Sales\'[Margin]), 0)\n}',
        '{("B", NAMEOF( \'Sales\' [Margin] ), 0), ("A", NAMEOF(Sales[Revenue]), 1)}',
    ],
)
def test_parse_reads_unquoted_tables_and_sorts_by_ordinal(source: str) -> None:
    assert parse_field_parameter_source(source) == [
        FieldParameterField("B", "Sales", "Margin"),
        FieldParameterField("A", "Sales", "Revenue"),
    ]


@pytest.mark.parametrize(
    "source",
    [
        "",
        "{}",
        '{("A", NAMEOF(Sales[Revenue]), 0, "Group")}',  # an extra column
        '{("A", NAMEOF(Sales[Revenue]), 0), ("B", "not a NAMEOF", 1)}',
        '{("A", NAMEOF(Sales[Revenue]), 0)} & "x"',
        'SELECTCOLUMNS(Sales, "A", Sales[Revenue])',
    ],
)
def test_parse_refuses_what_it_cannot_read_in_full(source: str) -> None:
    assert parse_field_parameter_source(source) is None


def test_source_round_trips() -> None:
    rows = [FieldParameterField('a "b"', "O'Neil", "x]y"), FieldParameterField("", "T", "F")]
    assert parse_field_parameter_source(field_parameter_source(rows)) == rows


# --- Export / apply ----------------------------------------------------------


def test_export_lists_desktop_field_parameter(shapes: Path) -> None:
    exported = yaml.safe_load(export_model_yaml(shapes))
    assert exported["fieldParameters"] == {
        "Metric Selector": {"fields": [{"field": r.ref, "label": r.label} for r in DESKTOP_ROWS]},
    }
    assert "Metric Selector" not in exported.get("columns", {})
    assert "Metric Selector" not in exported.get("partitions", {})


def test_export_keeps_an_unreadable_field_parameter_as_a_table(shapes: Path) -> None:
    path = _tables(shapes) / "Metric Selector.tmdl"
    data = path.read_bytes().replace(b"Expense Amount]), 2)", b"Expense Amount]), 2, \"Group\")")
    path.write_bytes(data)

    exported = yaml.safe_load(export_model_yaml(shapes))
    assert "fieldParameters" not in exported
    assert "Group" in exported["partitions"]["Metric Selector"][0]["source"]


def test_apply_updates_only_the_rows_of_an_existing_field_parameter(shapes: Path) -> None:
    path = _tables(shapes) / "Metric Selector.tmdl"
    before = path.read_bytes()
    spec = {"fieldParameters": {"Metric Selector": {"fields": [
        {"field": "Measures Table.Task Count", "label": "Tasks"},
        "Measures Table.Total Hours",
    ]}}}

    result = cli("model", "apply", "-", project=shapes, input=yaml.safe_dump(spec))
    assert result.exit_code == 0, result.output
    assert "Updated field parameter Metric Selector" in result.output

    after = path.read_bytes()
    old_rows = [line for line in before.split(b"\r\n") if b"NAMEOF" in line]
    new_rows = [line for line in after.split(b"\r\n") if b"NAMEOF" in line]
    assert new_rows == [
        b"\t\t\t\t    (\"Tasks\", NAMEOF('Measures Table'[Task Count]), 0),",
        b"\t\t\t\t    (\"Total Hours\", NAMEOF('Measures Table'[Total Hours]), 1)",
    ]
    assert [line for line in before.split(b"\r\n") if line not in old_rows] == [
        line for line in after.split(b"\r\n") if line not in new_rows
    ]

    result = cli("model", "apply", "-", project=shapes, input=yaml.safe_dump(spec))
    assert "No changes applied." in result.output
    assert path.read_bytes() == after


def test_apply_updates_an_old_shape_field_parameter(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_model_table(tmp_path, "Sales.tmdl", "table Sales\n\tmeasure Revenue = 1\n\tmeasure Margin = 2\n")
    write_model_table(tmp_path, "Metric Picker.tmdl", OLD_SHAPE.replace("Measures Table", "Sales"))
    path = _tables(tmp_path) / "Metric Picker.tmdl"

    _apply(tmp_path, {"fieldParameters": {"Metric Picker": {"fields": ["Sales.Revenue", "Sales.Margin"]}}})

    text = path.read_text(encoding="utf-8")
    assert "\tisParameterType\n" in text and "sourceColumn: [Name]" in text  # columns kept
    table = SemanticModel.load(tmp_path).find_table("Metric Picker")
    assert field_parameter_fields(table) == [
        FieldParameterField("Revenue", "Sales", "Revenue"),
        FieldParameterField("Margin", "Sales", "Margin"),
    ]


def test_apply_refuses_to_turn_a_table_into_a_field_parameter(shapes: Path) -> None:
    before = (_tables(shapes) / "Hours Band.tmdl").read_bytes()
    result = apply_model_yaml(shapes, yaml.safe_dump(
        {"fieldParameters": {"Hours Band": {"fields": DESKTOP_FIELDS}}}
    ))
    assert result.errors == ['fieldParameters.Hours Band: Table "Hours Band" already exists and is not a field parameter.']
    assert (_tables(shapes) / "Hours Band.tmdl").read_bytes() == before


@pytest.mark.parametrize("bad_entry", [42, {"label": "no field"}, {"field": 7}])
def test_apply_rejects_a_bad_entry_without_creating_anything(shapes: Path, bad_entry: object) -> None:
    result = apply_model_yaml(shapes, yaml.safe_dump(
        {"fieldParameters": {"Picker": {"fields": [DESKTOP_FIELDS[0], bad_entry]}}}
    ))
    assert len(result.errors) == 1 and "each field must be" in result.errors[0]
    assert not (_tables(shapes) / "Picker.tmdl").exists()


def test_apply_reports_created_field_parameters(shapes: Path) -> None:
    spec = {"fieldParameters": {"Picker": {"fields": DESKTOP_FIELDS}}}
    result = cli("model", "apply", "-", project=shapes, input=yaml.safe_dump(spec))
    assert result.exit_code == 0, result.output
    assert "Created field parameter Picker" in result.output


# --- Editing a field parameter's columns -------------------------------------


def test_column_properties_go_before_desktops_nested_blocks(shapes: Path) -> None:
    for args in (
        ("Metric Selector.Metric Selector Fields", "displayFolder=Pickers"),
        ("Metric Selector.Metric Selector", "formatString=0"),
    ):
        result = cli("model", "column", "set", *args, project=shapes)
        assert result.exit_code == 0, result.output

    lines = (_tables(shapes) / "Metric Selector.tmdl").read_text(encoding="utf-8").splitlines()
    assert lines.index("\t\tformatString: 0") < lines.index("\t\trelatedColumnDetails")
    assert lines.index("\t\tdisplayFolder: Pickers") < lines.index("\t\textendedProperty ParameterMetadata =")

    table = SemanticModel.load(shapes).find_table("Metric Selector")
    assert table.find_column("Metric Selector Fields").display_folder == "Pickers"
    assert field_parameter_fields(table) == DESKTOP_ROWS


# --- Export only what applies back unchanged ---------------------------------


def _model_files(project: Path) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in sorted(_tables(project).parent.rglob("*.tmdl"))}


def _assert_export_applies_unchanged(project: Path) -> dict:
    before = _model_files(project)
    exported = export_model_yaml(project)
    result = apply_model_yaml(project, exported)
    assert result.errors == []
    assert not result.has_changes
    assert _model_files(project) == before
    return yaml.safe_load(exported)


def test_dotted_table_names_resolve_and_round_trip(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_model_table(tmp_path, "Sales.Data.tmdl", "table 'Sales.Data'\n\tmeasure Revenue = 1\n")
    write_model_table(tmp_path, "Sales.tmdl", "table Sales\n\tmeasure Margin = 2\n")

    create_field_parameter(tmp_path, "Picker", ["Sales.Data.Revenue", "sales.margin"], None)

    table = SemanticModel.load(tmp_path).find_table("Picker")
    assert field_parameter_fields(table) == [
        FieldParameterField("Revenue", "Sales.Data", "Revenue"),
        FieldParameterField("Margin", "Sales", "Margin"),
    ]
    exported = _assert_export_applies_unchanged(tmp_path)
    assert exported["fieldParameters"]["Picker"]["fields"][0] == {"field": "Sales.Data.Revenue", "label": "Revenue"}


def test_a_ref_two_tables_could_own_is_refused(tmp_path: Path) -> None:
    make_project(tmp_path)
    write_model_table(tmp_path, "Sales.Data.tmdl", "table 'Sales.Data'\n\tmeasure Revenue = 1\n")
    write_model_table(tmp_path, "Sales.tmdl", "table Sales\n\tmeasure 'Data.Revenue' = 2\n")
    with pytest.raises(ValueError, match="ambiguous"):
        create_field_parameter(tmp_path, "Picker", ["Sales.Data.Revenue"], None)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (b'("Task Count", ', b'("Task\r\n\t\t\t\t    Count", '),  # a multi-line label
        (b"[Task Count]", b"[Gone]"),  # a field the model doesn't have
        (b"'Measures Table'[Task Count]", b"'measures table'[task count]"),  # other casing
    ],
)
def test_rows_that_would_not_apply_back_export_as_a_table(shapes: Path, old: bytes, new: bytes) -> None:
    path = _tables(shapes) / "Metric Selector.tmdl"
    data = path.read_bytes()
    assert data.count(old) == 1
    path.write_bytes(data.replace(old, new))

    exported = _assert_export_applies_unchanged(shapes)
    assert "fieldParameters" not in exported
    assert exported["partitions"]["Metric Selector"][0]["sourceType"] == "calculated"
