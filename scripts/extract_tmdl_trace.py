#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from pbi.model import build_tmdl_trace, trace_to_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract a TMDL provenance manifest from a PBIP project.")
    parser.add_argument(
        "--project-root",
        default=".",
        help="PBIP project root containing a .SemanticModel folder.",
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "schema-analysis" / "generated" / "tmdl.trace.json"),
        help="Output JSON file path.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    output_path = Path(args.out).resolve()
    manifest = build_tmdl_trace(project_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(trace_to_json(manifest), encoding="utf-8")
    meta = manifest["meta"]
    print(
        "Extracted "
        f"{meta['tableCount']} tables, "
        f"{meta['relationshipCount']} relationships, "
        f"{meta['roleCount']} roles, "
        f"{meta['perspectiveCount']} perspectives, "
        f"{meta['annotationCount']} annotations."
    )
    print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
