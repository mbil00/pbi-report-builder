#!/usr/bin/env bash
# Reusable smoke test runner for the current performance work.
# Runs focused regression tests plus the export/map/batch mutation benchmark.

set -euo pipefail

uv run --with pytest python -m pytest \
  tests/test_yaml_roundtrip.py::YamlRoundTripTests::test_round_trip_preserves_visual_groups \
  tests/test_cli_formatting_regressions.py \
  tests/test_cli_visual_regressions.py::VisualSetRegressionTests::test_visual_arrange_row_positions_visuals_left_to_right \
  tests/test_cli_visual_regressions.py::VisualSetRegressionTests::test_visual_arrange_grid_wraps_rows_using_visual_sizes \
  tests/test_cli_visual_regressions.py::VisualSetRegressionTests::test_visual_arrange_column_positions_visuals_top_to_bottom \
  tests/test_cli_visual_regressions.py::VisualSetRegressionTests::test_visual_set_all_prevalidates_and_does_not_partially_write \
  tests/test_cli_visual_regressions.py::VisualSetRegressionTests::test_visual_set_all_supports_dry_run \
  tests/test_cli_theme_regressions.py \
  tests/test_themes.py \
  -q

uv run python scripts/benchmark_export_map_mutations.py --pages "${PBI_PERF_PAGES:-8}" --visuals-per-page "${PBI_PERF_VISUALS:-16}" --repeat "${PBI_PERF_REPEAT:-2}"
