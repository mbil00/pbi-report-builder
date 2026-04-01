#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pbi.model import build_tmdl_trace, format_tmdl_trace_report, resolve_tmdl_trace_ref  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect one TMDL trace reference.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="PBIP project root containing a .SemanticModel folder.",
    )
    parser.add_argument(
        "--ref",
        required=True,
        help=(
            "Reference to inspect, for example "
            "'table:Sales', 'measure:Sales.Revenue', "
            "'column:Sales.Region', 'annotation:__PBI_TimeIntelligenceEnabled', "
            "'relationship:Sales.CustomerID->Customers.CustomerID'."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print the resolved trace record as JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = build_tmdl_trace(Path(args.project_root).resolve())
    if args.as_json:
        record = resolve_tmdl_trace_ref(manifest, args.ref)
        print(json.dumps({"meta": manifest["meta"], "record": record}, indent=2))
        return 0
    print(format_tmdl_trace_report(manifest, args.ref))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
