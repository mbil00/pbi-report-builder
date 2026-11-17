from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from pbi.model import build_tmdl_trace, format_tmdl_trace_report
from tests.support import FIXTURES

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_tmdl_trace_indexes_and_reports_a_fixture_model(tmp_path: Path) -> None:
    # report-03 is the only fixture with roles and perspectives; the trace only reads it.
    root = FIXTURES["report-03-authoring-parity-lab"]
    trace = build_tmdl_trace(root)

    meta = trace["meta"]
    assert (
        meta["tableCount"],
        meta["relationshipCount"],
        meta["roleCount"],
        meta["perspectiveCount"],
        meta["annotationCount"],
    ) == (10, 14, 3, 3, 4)

    refs = trace["refs"]
    measure = refs["measure:GL_Actuals.Actual Amount"]
    assert measure["path"].endswith("GL_Actuals.tmdl")
    assert measure["table"] == "GL_Actuals"
    assert "measure 'Actual Amount' = SUM ( GL_Actuals[Amount] )" in measure["snippet"]

    relationship = refs["relationship:Forecast.AccountKey->Account.AccountKey"]
    assert (relationship["kind"], relationship["fromTable"], relationship["toTable"]) == (
        "relationship",
        "Forecast",
        "Account",
    )
    assert "fromColumn: Forecast.AccountKey" in relationship["snippet"]
    assert "__PBI_TimeIntelligenceEnabled" in refs["annotation:__PBI_TimeIntelligenceEnabled"]["snippet"]

    report = format_tmdl_trace_report(trace, "measure:GL_Actuals.Actual Amount")
    assert "Ref: measure:GL_Actuals.Actual Amount" in report
    assert "Kind: measure" in report
    assert "Path:" in report
    assert "measure 'Actual Amount' = SUM" in report

    out_path = tmp_path / "tmdl.trace.json"
    subprocess.run(
        [sys.executable, "scripts/extract_tmdl_trace.py", "--project-root", str(root), "--out", str(out_path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "measure:GL_Actuals.Actual Amount" in json.loads(out_path.read_text(encoding="utf-8"))["refs"]

    result = subprocess.run(
        [sys.executable, "scripts/inspect_tmdl_trace.py", "--project-root", str(root), "--ref", "role:Finance Readers"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "Ref: role:Finance Readers" in result.stdout
    assert "role 'Finance Readers'" in result.stdout
