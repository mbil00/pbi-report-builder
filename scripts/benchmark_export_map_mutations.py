#!/usr/bin/env python3
"""Reusable performance smoke benchmark for export/map scans and batch visual mutations.

The script builds a synthetic PBIP project from the checked-in sample fixture,
then measures the hot paths agents use before/after edits:

  * YAML export (`pbi.export.export_yaml`)
  * Project map generation (`pbi.mapper.generate_map`)
  * Batch visual mutation write path (`pbi visual set-all ... --all-pages`)
  * Batch visual mutation no-op path (same command after values are already set)

It reports elapsed time plus coarse instrumentation counters for project scans
and JSON I/O. Timings are intentionally lightweight smoke numbers: compare them
across runs on the same machine/branch rather than as absolute benchmarks.

Usage:

    uv run python scripts/benchmark_export_map_mutations.py
    uv run python scripts/benchmark_export_map_mutations.py --pages 20 --visuals-per-page 30 --repeat 5
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from unittest import mock

from typer.testing import CliRunner

from pbi.cli import app
from pbi.export import export_yaml
from pbi.mapper import generate_map
from pbi.project import Project

# Reuse the synthetic PBIP builder from the existing apply benchmark script.
from benchmark_buffered_apply import DEFAULT_FIXTURE, synthesize_fixture_project


@dataclass(frozen=True)
class RunMetrics:
    elapsed: float
    page_scans: int
    visual_scans: int
    json_reads: int
    json_writes: int
    output_size: int = 0


@dataclass(frozen=True)
class Scenario:
    name: str
    metrics: RunMetrics


class Counters:
    def __init__(self) -> None:
        self.page_scans = 0
        self.visual_scans = 0
        self.json_reads = 0
        self.json_writes = 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--pages", type=int, default=12)
    parser.add_argument("--visuals-per-page", type=int, default=25)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a table.",
    )
    parser.add_argument(
        "--keep-workdir",
        action="store_true",
        help="Keep the generated project directory and print its path.",
    )
    args = parser.parse_args()

    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")
    if args.pages < 1:
        raise SystemExit("--pages must be >= 1")
    if args.visuals_per_page < 1:
        raise SystemExit("--visuals-per-page must be >= 1")
    if not args.fixture.exists():
        raise SystemExit(f"Fixture not found: {args.fixture}")

    with tempfile.TemporaryDirectory(prefix="pbi-perf-smoke-") as tmp:
        workdir = Path(tmp)
        if args.keep_workdir:
            # Use a second temp root that survives the context cleanup.
            workdir = Path(tempfile.mkdtemp(prefix="pbi-perf-smoke-keep-"))
            print(f"Keeping workdir: {workdir}")

        results = run_benchmarks(
            workdir,
            fixture=args.fixture,
            pages=args.pages,
            visuals_per_page=args.visuals_per_page,
            repeat=args.repeat,
        )

        if args.json:
            print(json.dumps(_as_json(results), indent=2))
        else:
            print_table(results, pages=args.pages, visuals_per_page=args.visuals_per_page, repeat=args.repeat)


def run_benchmarks(
    workdir: Path,
    *,
    fixture: Path,
    pages: int,
    visuals_per_page: int,
    repeat: int,
) -> list[Scenario]:
    scenarios: list[tuple[str, Callable[[Path], None], Callable[[Path], int]]] = [
        ("export-all", _no_prepare, lambda pbip_path: len(export_yaml(Project.find(pbip_path)))),
        ("map-all", _no_prepare, lambda pbip_path: len(generate_map(Project.find(pbip_path)))),
        ("visual-set-all-write", _no_prepare, _run_visual_set_all),
        ("visual-set-all-noop", _prime_visual_set_all, _run_visual_set_all),
    ]

    results: list[Scenario] = []
    for name, prepare, func in scenarios:
        runs: list[RunMetrics] = []
        for run_index in range(repeat):
            # Build a fresh synthetic project for every measured run. This is
            # especially important for mutating scenarios: otherwise the first
            # visual-set-all repeat measures writes and subsequent repeats
            # measure the no-op path, making medians depend on repeat count.
            project_root = workdir / f"{name}-{run_index}"
            project = synthesize_fixture_project(
                fixture,
                project_root,
                page_count=pages,
                visuals_per_page=visuals_per_page,
            )
            prepare(project.pbip_file)
            runs.append(_measure(lambda pbip=project.pbip_file: func(pbip)))
        results.append(Scenario(name=name, metrics=_median(runs)))
    return results


def _no_prepare(_pbip_path: Path) -> None:
    return None


def _prime_visual_set_all(pbip_path: Path) -> None:
    _run_visual_set_all(pbip_path)


def _run_visual_set_all(pbip_path: Path) -> int:
    result = CliRunner().invoke(
        app,
        [
            "visual",
            "set-all",
            "background.show=true",
            "--all-pages",
            "--project",
            str(pbip_path),
        ],
    )
    if result.exit_code != 0:
        raise RuntimeError(result.stdout or str(result.exception))
    return len(result.stdout)


def _measure(func: Callable[[], int]) -> RunMetrics:
    counters = Counters()
    real_get_pages = Project.get_pages
    real_get_visuals = Project.get_visuals
    project_module = __import__("pbi.project", fromlist=["_read_json", "_write_json"])
    real_read_json = project_module._read_json
    real_write_json = project_module._write_json

    def counted_get_pages(self: Project) -> list[Any]:
        counters.page_scans += 1
        return real_get_pages(self)

    def counted_get_visuals(self: Project, page: Any) -> list[Any]:
        counters.visual_scans += 1
        return real_get_visuals(self, page)

    def counted_read_json(path: Path) -> dict[str, Any]:
        counters.json_reads += 1
        return real_read_json(path)

    def counted_write_json(path: Path, data: dict[str, Any], **kwargs: Any) -> None:
        counters.json_writes += 1
        return real_write_json(path, data, **kwargs)

    with mock.patch.object(Project, "get_pages", counted_get_pages), \
        mock.patch.object(Project, "get_visuals", counted_get_visuals), \
        mock.patch("pbi.project._read_json", side_effect=counted_read_json), \
        mock.patch("pbi.project._write_json", side_effect=counted_write_json):
        start = time.perf_counter()
        output_size = func()
        elapsed = time.perf_counter() - start

    return RunMetrics(
        elapsed=elapsed,
        page_scans=counters.page_scans,
        visual_scans=counters.visual_scans,
        json_reads=counters.json_reads,
        json_writes=counters.json_writes,
        output_size=output_size,
    )


def _median(runs: list[RunMetrics]) -> RunMetrics:
    def med(attr: str) -> float:
        return statistics.median(getattr(run, attr) for run in runs)

    return RunMetrics(
        elapsed=med("elapsed"),
        page_scans=int(med("page_scans")),
        visual_scans=int(med("visual_scans")),
        json_reads=int(med("json_reads")),
        json_writes=int(med("json_writes")),
        output_size=int(med("output_size")),
    )


def print_table(results: list[Scenario], *, pages: int, visuals_per_page: int, repeat: int) -> None:
    print(f"Synthetic project: {pages} page(s) x {visuals_per_page} visual(s); repeat={repeat}")
    print("")
    print(f"{'scenario':<18} {'elapsed':>9} {'pages':>7} {'visuals':>8} {'reads':>7} {'writes':>7} {'out':>9}")
    print("-" * 78)
    for result in results:
        m = result.metrics
        print(
            f"{result.name:<18} "
            f"{m.elapsed:>8.3f}s "
            f"{m.page_scans:>7} "
            f"{m.visual_scans:>8} "
            f"{m.json_reads:>7} "
            f"{m.json_writes:>7} "
            f"{m.output_size:>9}"
        )


def _as_json(results: list[Scenario]) -> list[dict[str, Any]]:
    return [
        {
            "scenario": result.name,
            "elapsed": result.metrics.elapsed,
            "page_scans": result.metrics.page_scans,
            "visual_scans": result.metrics.visual_scans,
            "json_reads": result.metrics.json_reads,
            "json_writes": result.metrics.json_writes,
            "output_size": result.metrics.output_size,
        }
        for result in results
    ]


if __name__ == "__main__":
    main()
