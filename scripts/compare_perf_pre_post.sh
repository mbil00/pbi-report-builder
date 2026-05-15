#!/usr/bin/env bash
# Compare performance smoke benchmark on git HEAD (pre-change) vs current working tree.
#
# Usage:
#   scripts/compare_perf_pre_post.sh
#   PBI_PERF_PAGES=24 PBI_PERF_VISUALS=40 PBI_PERF_REPEAT=2 scripts/compare_perf_pre_post.sh

set -euo pipefail

PAGES="${PBI_PERF_PAGES:-12}"
VISUALS="${PBI_PERF_VISUALS:-25}"
REPEAT="${PBI_PERF_REPEAT:-3}"
BASE_REF="${PBI_PERF_BASE_REF:-HEAD}"

repo_root="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
cleanup() {
  if [[ -d "${tmp}/baseline" ]]; then
    git worktree remove --force "${tmp}/baseline" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp"
}
trap cleanup EXIT

baseline_json="${tmp}/baseline.json"
current_json="${tmp}/current.json"

printf 'Preparing baseline worktree from %s...\n' "$BASE_REF" >&2
git worktree add --detach "${tmp}/baseline" "$BASE_REF" >/dev/null
cp "${repo_root}/scripts/benchmark_export_map_mutations.py" "${tmp}/baseline/scripts/benchmark_export_map_mutations.py"
chmod +x "${tmp}/baseline/scripts/benchmark_export_map_mutations.py"

printf 'Running baseline benchmark (%s pages x %s visuals, repeat=%s)...\n' "$PAGES" "$VISUALS" "$REPEAT" >&2
(
  cd "${tmp}/baseline"
  uv run python scripts/benchmark_export_map_mutations.py \
    --pages "$PAGES" \
    --visuals-per-page "$VISUALS" \
    --repeat "$REPEAT" \
    --json > "$baseline_json"
)

printf 'Running current benchmark (%s pages x %s visuals, repeat=%s)...\n' "$PAGES" "$VISUALS" "$REPEAT" >&2
(
  cd "$repo_root"
  uv run python scripts/benchmark_export_map_mutations.py \
    --pages "$PAGES" \
    --visuals-per-page "$VISUALS" \
    --repeat "$REPEAT" \
    --json > "$current_json"
)

python - "$baseline_json" "$current_json" "$PAGES" "$VISUALS" "$REPEAT" <<'PY'
from __future__ import annotations

import json
import sys
from pathlib import Path

baseline = {row["scenario"]: row for row in json.loads(Path(sys.argv[1]).read_text())}
current = {row["scenario"]: row for row in json.loads(Path(sys.argv[2]).read_text())}
pages, visuals, repeat = sys.argv[3:6]

print(f"Comparison: git HEAD vs current ({pages} page(s) x {visuals} visual(s), repeat={repeat})")
print("")
print(f"{'scenario':<18} {'base':>9} {'current':>9} {'delta':>9} {'scan delta':>13} {'write delta':>12}")
print("-" * 78)
for name in baseline:
    b = baseline[name]
    c = current[name]
    elapsed_delta = c["elapsed"] - b["elapsed"]
    elapsed_pct = (elapsed_delta / b["elapsed"] * 100) if b["elapsed"] else 0.0
    scan_delta = (c["page_scans"] + c["visual_scans"]) - (b["page_scans"] + b["visual_scans"])
    write_delta = c["json_writes"] - b["json_writes"]
    print(
        f"{name:<18} "
        f"{b['elapsed']:>8.3f}s "
        f"{c['elapsed']:>8.3f}s "
        f"{elapsed_delta:>+7.3f}s/{elapsed_pct:>+5.1f}% "
        f"{scan_delta:>13} "
        f"{write_delta:>12}"
    )

print("")
print("Raw counters:")
for name in baseline:
    b = baseline[name]
    c = current[name]
    print(
        f"- {name}: "
        f"scans {b['page_scans'] + b['visual_scans']} -> {c['page_scans'] + c['visual_scans']}, "
        f"reads {b['json_reads']} -> {c['json_reads']}, "
        f"writes {b['json_writes']} -> {c['json_writes']}"
    )
PY
