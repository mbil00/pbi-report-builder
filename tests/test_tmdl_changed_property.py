"""``changedProperty`` lines are metadata only at property indent (#75).

Desktop writes ``changedProperty = X`` at a member's property indent (two
tabs). A multi-line DAX body sits one level deeper, where the same text is a
comparison against a variable and must stay part of the expression.
"""

from __future__ import annotations

from pathlib import Path

from pbi.model import SemanticModel
from pbi.modeling.writes import edit_calculated_column_expression, edit_measure_expression
from tests.support import make_project, write_model_table

TABLE = "\n".join(
    [
        "table Sales",
        "\tlineageTag: 00000000-0000-0000-0000-000000000001",
        "",
        "\tmeasure Flag =",
        "\t\t\tVAR changedProperty = 1",
        "\t\t\tRETURN",
        "\t\t\tchangedProperty = 1",
        "\t\tlineageTag: 00000000-0000-0000-0000-000000000002",
        "",
        "\t\tchangedProperty = Name",
        "",
        "\tcolumn Check =",
        "\t\t\tVAR changedProperty = 1",
        "\t\t\tRETURN",
        "\t\t\tchangedProperty = 1",
        "\t\tdataType: boolean",
        "\t\tlineageTag: 00000000-0000-0000-0000-000000000003",
        "\t\tsummarizeBy: none",
        "",
        "\t\tchangedProperty = IsHidden",
    ]
)

BODY = "VAR changedProperty = 1\nRETURN\nchangedProperty = 1"


def _project(tmp_path: Path) -> Path:
    make_project(tmp_path)
    return write_model_table(tmp_path, "Sales.tmdl", TABLE)


def test_dax_body_comparison_is_kept(tmp_path: Path) -> None:
    _project(tmp_path)
    table = SemanticModel.load(tmp_path).find_table("Sales")
    assert table.find_measure("Flag").expression == BODY
    assert table.find_column("Check").expression == BODY


def test_expression_edit_replaces_body_and_keeps_metadata(tmp_path: Path) -> None:
    path = _project(tmp_path)
    edit_measure_expression(tmp_path, "Sales", "Flag", "42")
    edit_calculated_column_expression(tmp_path, "Sales", "Check", "TRUE ()")

    lines = path.read_text(encoding="utf-8").splitlines()
    assert "\t\t\tchangedProperty = 1" not in lines
    assert "\tmeasure Flag = 42" in lines
    assert "\tcolumn Check = TRUE ()" in lines
    assert lines.count("\t\tchangedProperty = Name") == 1
    assert lines.count("\t\tchangedProperty = IsHidden") == 1

    table = SemanticModel.load(tmp_path).find_table("Sales")
    assert table.find_measure("Flag").expression == "42"
    assert table.find_column("Check").expression == "TRUE ()"
