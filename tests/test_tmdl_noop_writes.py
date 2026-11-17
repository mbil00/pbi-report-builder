"""Model setters leave unchanged TMDL alone, and keep Desktop's layout when they write (#76).

The table below follows what Desktop saves: a blank line between members, an
unquoted partition name with hyphens, lowercase ``uncategorized``, and a
calculated column with a ``variation`` block.
"""

from __future__ import annotations

from pathlib import Path

from pbi.model import SemanticModel
from pbi.modeling.writes import set_member_property
from pbi.modeling.writes_partitions import set_partition
from tests.support import make_project, write_model_table

TABLE = "\n".join(
    [
        "table Events",
        "\tlineageTag: 00000000-0000-0000-0000-000000000001",
        "",
        "\tcolumn Kind",
        "\t\tdataType: string",
        "\t\tlineageTag: 00000000-0000-0000-0000-000000000002",
        "\t\tdataCategory: uncategorized",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: Kind",
        "",
        "\tcolumn When = NOW() + Events[Offset]",
        "\t\tformatString: General Date",
        "\t\tlineageTag: 00000000-0000-0000-0000-000000000003",
        "\t\tsummarizeBy: none",
        "",
        "\t\tvariation Variation",
        "\t\t\tisDefault",
        "\t\t\trelationship: 735b3dda-86ff-4275-87cd-73638f54e97b",
        "\t\t\tdefaultHierarchy: LocalDateTable_7c936782.'Date Hierarchy'",
        "",
        "\t\tannotation SummarizationSetBy = Automatic",
        "",
        "\tmeasure Count =",
        "\t\t\t/*",
        "\t\t\tannotation notes",
        "\t\t\tvariation notes",
        "\t\t\t*/",
        "\t\t\tCOUNTROWS(Events)",
        "\t\tlineageTag: 00000000-0000-0000-0000-000000000004",
        "",
        "\t\tannotation PBI_FormatHint = {\"isGeneralNumber\":true}",
        "",
        "\tpartition Events-2024 = m",
        "\t\tmode: import",
        "\t\tqueryGroup: Facts",
        "\t\tsource =",
        "\t\t\t\tlet",
        "\t\t\t\t    Source = Csv.Document(File.Contents(\"events.csv\"))",
        "",
        "\t\t\t\tin",
        "\t\t\t\t    Source",
        "",
        "\tannotation PBI_ResultType = Table",
        "",
    ]
)

SOURCE = 'let\n    Source = Csv.Document(File.Contents("events.csv"))\nin\n    Source'


def _project(tmp_path: Path) -> Path:
    make_project(tmp_path)
    return write_model_table(tmp_path, "Events.tmdl", TABLE)


def test_variation_block_is_not_part_of_the_expression(tmp_path: Path) -> None:
    _project(tmp_path)
    column = SemanticModel.load(tmp_path).find_table("Events").find_column("When")
    assert column.expression == "NOW() + Events[Offset]"


def test_annotation_text_inside_a_dax_body_stays_dax(tmp_path: Path) -> None:
    _project(tmp_path)
    measure = SemanticModel.load(tmp_path).find_table("Events").find_measure("Count")
    assert measure.expression == "/*\nannotation notes\nvariation notes\n*/\nCOUNTROWS(Events)"


def test_unchanged_partition_is_not_rewritten(tmp_path: Path) -> None:
    path = _project(tmp_path)
    before = path.read_bytes()
    assert set_partition(tmp_path, "Events", "Events-2024", source_expression=SOURCE, source_type="m", mode="import") == (
        "Events",
        "Events-2024",
        False,
    )
    assert path.read_bytes() == before


def test_partition_write_changes_only_what_differs(tmp_path: Path) -> None:
    path = _project(tmp_path)
    *_, changed = set_partition(tmp_path, "Events", "Events-2024", mode="directQuery")
    assert changed
    expected = TABLE.replace("\t\tmode: import", "\t\tmode: directQuery")
    assert path.read_text(encoding="utf-8").replace("\r\n", "\n") == expected

    *_, changed = set_partition(tmp_path, "Events", "Events-2024", source_expression="Events2024", source_type="calculated")
    assert changed
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    start = lines.index("\tpartition Events-2024 = calculated")
    assert lines[start : start + 6] == [
        "\tpartition Events-2024 = calculated",
        "\t\tmode: directQuery",
        "\t\tqueryGroup: Facts",
        "\t\tsource = Events2024",
        "",
        "\tannotation PBI_ResultType = Table",
    ]
    partition = SemanticModel.load(tmp_path).find_table("Events").find_partition("Events-2024")
    assert (partition.source_type, partition.mode, partition.source_expression) == ("calculated", "directQuery", "Events2024")


def test_same_data_category_in_other_casing_is_kept(tmp_path: Path) -> None:
    path = _project(tmp_path)
    before = path.read_bytes()
    assert set_member_property(tmp_path, "Events.Kind", "dataCategory", "Uncategorized")[3] is False
    assert path.read_bytes() == before

    assert set_member_property(tmp_path, "Events.Kind", "dataCategory", "Country")[3] is True
    assert "\t\tdataCategory: Country" in path.read_text(encoding="utf-8").splitlines()
