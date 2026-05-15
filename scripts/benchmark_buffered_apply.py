#!/usr/bin/env python3
"""Benchmark eager vs buffered YAML apply on synthetic PBIR workloads.

The script builds temporary PBIP projects from the checked-in sample fixture and
expands them by copy/pasting existing PBIR page/visual folders. It then applies
identical YAML specs through the eager and buffered Python entry points and
reports elapsed time plus coarse filesystem instrumentation.

Usage:

    uv run python scripts/benchmark_buffered_apply.py
    uv run python scripts/benchmark_buffered_apply.py --pages 20 --visuals-per-page 30

This is intentionally a benchmark utility, not a unit test: timings are noisy
and should be compared across runs on the same machine.
"""

from __future__ import annotations

import argparse
import cProfile
import copy
import json
import shutil
import statistics
import tempfile
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest import mock

import yaml

from pbi.apply import apply_yaml, apply_yaml_buffered
from pbi.project import Project, Visual, _read_json

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE = REPO_ROOT / "fixtures" / "sample-report" / "SampleReport.pbip"


@dataclass
class Metrics:
    elapsed: float
    json_writes: int
    json_reads: int
    copytrees: int
    rmtrees: int
    page_scans: int
    visual_scans: int
    errors: int
    pages_created: int
    pages_updated: int
    visuals_created: int
    visuals_updated: int
    visuals_deleted: int
    properties_set: int
    phase_times: dict[str, float] = field(default_factory=dict)
    write_categories: dict[str, int] = field(default_factory=dict)
    read_categories: dict[str, int] = field(default_factory=dict)
    phase_write_categories: dict[str, dict[str, int]] = field(default_factory=dict)
    phase_read_categories: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass
class Diagnostics:
    phase_times: dict[str, float] = field(default_factory=dict)
    write_categories: dict[str, int] = field(default_factory=dict)
    read_categories: dict[str, int] = field(default_factory=dict)
    phase_write_categories: dict[str, dict[str, int]] = field(default_factory=dict)
    phase_read_categories: dict[str, dict[str, int]] = field(default_factory=dict)
    current_phase: str | None = None
    page_scans: int = 0
    visual_scans: int = 0


@dataclass
class ScenarioResult:
    name: str
    eager: Metrics
    buffered: Metrics


class Counters:
    def __init__(self) -> None:
        self.json_writes = 0
        self.json_reads = 0
        self.copytrees = 0
        self.rmtrees = 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--pages", type=int, default=12)
    parser.add_argument("--visuals-per-page", type=int, default=25)
    parser.add_argument("--create-pages", type=int, default=8)
    parser.add_argument("--create-visuals-per-page", type=int, default=20)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument(
        "--detail",
        action="store_true",
        help="Print phase timings and read/write category counters.",
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        help="Write one cProfile .prof file per scenario/mode/run to this directory.",
    )
    parser.add_argument("--keep-workdir", action="store_true")
    args = parser.parse_args()

    if args.repeat < 1:
        raise SystemExit("--repeat must be >= 1")
    if not args.fixture.exists():
        raise SystemExit(f"Fixture not found: {args.fixture}")
    if args.profile_dir is not None:
        args.profile_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        if args.keep_workdir:
            # Move work under a stable location and intentionally do not clean it.
            workdir = Path(tempfile.mkdtemp(prefix="pbi-buffered-bench-"))
            print(f"Keeping workdir: {workdir}")

        results = [
            benchmark_create_heavy(
                workdir,
                pages=args.create_pages,
                visuals_per_page=args.create_visuals_per_page,
                repeat=args.repeat,
                profile_dir=args.profile_dir,
            ),
            benchmark_fixture_update(
                workdir,
                fixture=args.fixture,
                pages=args.pages,
                visuals_per_page=args.visuals_per_page,
                repeat=args.repeat,
                profile_dir=args.profile_dir,
            ),
            benchmark_fixture_mixed(
                workdir,
                fixture=args.fixture,
                pages=args.pages,
                visuals_per_page=args.visuals_per_page,
                repeat=args.repeat,
                profile_dir=args.profile_dir,
            ),
        ]
        print_results(results, detail=args.detail)

        if args.keep_workdir:
            # Prevent TemporaryDirectory cleanup of an unrelated path only; tmp still cleans.
            pass


def benchmark_create_heavy(
    workdir: Path,
    *,
    pages: int,
    visuals_per_page: int,
    repeat: int,
    profile_dir: Path | None = None,
) -> ScenarioResult:
    spec = yaml.safe_dump(
        {
            "version": 1,
            "pages": [
                {
                    "name": f"Create Page {page_index + 1}",
                    "visuals": [
                        {
                            "name": f"card_{page_index}_{visual_index}",
                            "type": "cardVisual",
                            "position": _position_for(visual_index),
                            "size": "140 x 70",
                            "title": {
                                "show": True,
                                "text": f"Card {page_index}-{visual_index}",
                            },
                        }
                        for visual_index in range(visuals_per_page)
                    ],
                }
                for page_index in range(pages)
            ],
        },
        sort_keys=False,
    )

    return _benchmark_from_project_factory(
        "create-empty",
        lambda root: create_minimal_project(root),
        spec,
        repeat=repeat,
        overwrite=False,
        workdir=workdir,
        profile_dir=profile_dir,
    )


def benchmark_fixture_update(
    workdir: Path,
    *,
    fixture: Path,
    pages: int,
    visuals_per_page: int,
    repeat: int,
    profile_dir: Path | None = None,
) -> ScenarioResult:
    def factory(root: Path) -> Project:
        return synthesize_fixture_project(
            fixture, root, page_count=pages, visuals_per_page=visuals_per_page
        )

    seed_root = workdir / "seed-update"
    if seed_root.exists():
        shutil.rmtree(seed_root)
    project = factory(seed_root)
    spec = build_update_spec(project, offset=9)

    return _benchmark_from_project_factory(
        "fixture-update",
        factory,
        spec,
        repeat=repeat,
        overwrite=False,
        workdir=workdir,
        profile_dir=profile_dir,
    )


def benchmark_fixture_mixed(
    workdir: Path,
    *,
    fixture: Path,
    pages: int,
    visuals_per_page: int,
    repeat: int,
    profile_dir: Path | None = None,
) -> ScenarioResult:
    def factory(root: Path) -> Project:
        return synthesize_fixture_project(
            fixture, root, page_count=pages, visuals_per_page=visuals_per_page
        )

    seed_root = workdir / "seed-mixed"
    if seed_root.exists():
        shutil.rmtree(seed_root)
    project = factory(seed_root)
    spec = build_mixed_overwrite_spec(project)

    return _benchmark_from_project_factory(
        "fixture-mixed-overwrite",
        factory,
        spec,
        repeat=repeat,
        overwrite=True,
        workdir=workdir,
        profile_dir=profile_dir,
    )


def _benchmark_from_project_factory(
    name: str,
    project_factory: Callable[[Path], Project],
    spec: str,
    *,
    repeat: int,
    overwrite: bool,
    workdir: Path,
    profile_dir: Path | None = None,
) -> ScenarioResult:
    eager_runs: list[Metrics] = []
    buffered_runs: list[Metrics] = []
    for run_index in range(repeat):
        eager_root = workdir / f"{name}-{run_index}-eager"
        buffered_root = workdir / f"{name}-{run_index}-buffered"
        for root in (eager_root, buffered_root):
            if root.exists():
                shutil.rmtree(root)
        eager_project = project_factory(eager_root)
        buffered_project = project_factory(buffered_root)

        eager_runs.append(
            run_apply_measured(
                apply_yaml,
                eager_project,
                spec,
                overwrite=overwrite,
                profile_path=_profile_path(profile_dir, name, "eager", run_index),
            )
        )
        buffered_runs.append(
            run_apply_measured(
                apply_yaml_buffered,
                buffered_project,
                spec,
                overwrite=overwrite,
                profile_path=_profile_path(profile_dir, name, "buffered", run_index),
            )
        )

    return ScenarioResult(
        name=name,
        eager=median_metrics(eager_runs),
        buffered=median_metrics(buffered_runs),
    )


def _profile_path(
    profile_dir: Path | None,
    scenario: str,
    mode: str,
    run_index: int,
) -> Path | None:
    if profile_dir is None:
        return None
    return profile_dir / f"{scenario}-{mode}-{run_index}.prof"


def run_apply_measured(
    apply_func: Callable[..., Any],
    project: Project,
    spec: str,
    *,
    overwrite: bool,
    profile_path: Path | None = None,
) -> Metrics:
    counters = Counters()
    diagnostics = Diagnostics()
    real_project_write_json = __import__("pbi.project", fromlist=["_write_json"])._write_json
    real_buffered_write_json = __import__("pbi.apply.buffered", fromlist=["_write_json"])._write_json
    real_project_read_json = __import__("pbi.project", fromlist=["_read_json"])._read_json
    real_copytree = shutil.copytree
    real_rmtree = shutil.rmtree

    engine = __import__("pbi.apply.engine", fromlist=["yaml"])
    real_safe_load = engine.yaml.safe_load
    real_apply_sections = engine._apply_top_level_sections
    real_validate_session_project = engine._validate_session_project
    real_validate_apply_invariants = engine._validate_apply_invariants
    real_record_post_apply_validation = engine._record_post_apply_validation
    real_validate_project = engine.validate_project
    eager_state = __import__("pbi.apply.state", fromlist=["PbirApplySession"])
    buffered_state = __import__("pbi.apply.buffered", fromlist=["BufferedPbirApplySession"])
    real_eager_commit = eager_state.PbirApplySession.commit
    real_buffered_commit = buffered_state.BufferedPbirApplySession.commit
    real_get_pages = Project.get_pages
    real_get_visuals = Project.get_visuals

    def add_phase(name: str, elapsed: float) -> None:
        diagnostics.phase_times[name] = diagnostics.phase_times.get(name, 0.0) + elapsed

    def timed(name: str, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        previous_phase = diagnostics.current_phase
        diagnostics.current_phase = name
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            add_phase(name, time.perf_counter() - start)
            diagnostics.current_phase = previous_phase

    def counted_project_write_json(path: Path, data: dict[str, Any]) -> None:
        counters.json_writes += 1
        category = _json_category(path)
        _increment(diagnostics.write_categories, category)
        _increment_phase_category(
            diagnostics.phase_write_categories,
            diagnostics.current_phase,
            category,
        )
        return real_project_write_json(path, data)

    def counted_buffered_write_json(path: Path, data: dict[str, Any]) -> None:
        counters.json_writes += 1
        category = _json_category(path)
        _increment(diagnostics.write_categories, category)
        _increment_phase_category(
            diagnostics.phase_write_categories,
            diagnostics.current_phase,
            category,
        )
        return real_buffered_write_json(path, data)

    def counted_read_json(path: Path) -> dict[str, Any]:
        counters.json_reads += 1
        category = _json_category(path)
        _increment(diagnostics.read_categories, category)
        _increment_phase_category(
            diagnostics.phase_read_categories,
            diagnostics.current_phase,
            category,
        )
        return real_project_read_json(path)

    def counted_copytree(*args: Any, **kwargs: Any) -> Any:
        counters.copytrees += 1
        return real_copytree(*args, **kwargs)

    def counted_rmtree(*args: Any, **kwargs: Any) -> Any:
        counters.rmtrees += 1
        return real_rmtree(*args, **kwargs)

    def counted_get_pages(self: Project) -> list[Any]:
        diagnostics.page_scans += 1
        return real_get_pages(self)

    def counted_get_visuals(self: Project, page: Any) -> list[Any]:
        diagnostics.visual_scans += 1
        return real_get_visuals(self, page)

    with mock.patch("pbi.project._write_json", side_effect=counted_project_write_json), \
        mock.patch("pbi.apply.buffered._write_json", side_effect=counted_buffered_write_json), \
        mock.patch("pbi.project._read_json", side_effect=counted_read_json), \
        mock.patch("pbi.apply.buffered._read_json", side_effect=counted_read_json), \
        mock.patch("pbi.validate._read_json", side_effect=counted_read_json), \
        mock.patch("pbi.apply.engine.yaml.safe_load", side_effect=lambda content: timed("yaml_parse", real_safe_load, content)), \
        mock.patch("pbi.apply.engine._apply_top_level_sections", side_effect=lambda *args, **kwargs: timed("apply_body", real_apply_sections, *args, **kwargs)), \
        mock.patch("pbi.apply.engine._validate_session_project", side_effect=lambda *args, **kwargs: timed("session_validation", real_validate_session_project, *args, **kwargs)), \
        mock.patch("pbi.apply.engine._validate_apply_invariants", side_effect=lambda *args, **kwargs: timed("apply_invariants", real_validate_apply_invariants, *args, **kwargs)), \
        mock.patch("pbi.apply.engine._record_post_apply_validation", side_effect=lambda *args, **kwargs: timed("post_apply_validation", real_record_post_apply_validation, *args, **kwargs)), \
        mock.patch("pbi.apply.engine.validate_project", side_effect=lambda *args, **kwargs: timed("validate_project", real_validate_project, *args, **kwargs)), \
        mock.patch("pbi.apply.state.PbirApplySession.commit", side_effect=lambda self: timed("commit", real_eager_commit, self), autospec=True), \
        mock.patch("pbi.apply.buffered.BufferedPbirApplySession.commit", side_effect=lambda self: timed("commit", real_buffered_commit, self), autospec=True), \
        mock.patch.object(Project, "get_pages", counted_get_pages), \
        mock.patch.object(Project, "get_visuals", counted_get_visuals), \
        mock.patch("shutil.copytree", side_effect=counted_copytree), \
        mock.patch("shutil.rmtree", side_effect=counted_rmtree):
        start = time.perf_counter()
        if profile_path is None:
            result = apply_func(project, spec, overwrite=overwrite)
        else:
            profiler = cProfile.Profile()
            profiler.enable()
            try:
                result = apply_func(project, spec, overwrite=overwrite)
            finally:
                profiler.disable()
                profiler.dump_stats(profile_path)
        elapsed = time.perf_counter() - start

    return Metrics(
        elapsed=elapsed,
        json_writes=counters.json_writes,
        json_reads=counters.json_reads,
        copytrees=counters.copytrees,
        rmtrees=counters.rmtrees,
        page_scans=diagnostics.page_scans,
        visual_scans=diagnostics.visual_scans,
        errors=len(result.errors),
        pages_created=len(result.pages_created),
        pages_updated=len(result.pages_updated),
        visuals_created=len(result.visuals_created),
        visuals_updated=len(result.visuals_updated),
        visuals_deleted=len(result.visuals_deleted),
        properties_set=result.properties_set,
        phase_times=diagnostics.phase_times,
        write_categories=diagnostics.write_categories,
        read_categories=diagnostics.read_categories,
        phase_write_categories=diagnostics.phase_write_categories,
        phase_read_categories=diagnostics.phase_read_categories,
    )


def median_metrics(runs: list[Metrics]) -> Metrics:
    def median(attr: str) -> float:
        return statistics.median(getattr(run, attr) for run in runs)

    # Counts should be stable; median protects against accidental one-off noise.
    return Metrics(
        elapsed=median("elapsed"),
        json_writes=int(median("json_writes")),
        json_reads=int(median("json_reads")),
        copytrees=int(median("copytrees")),
        rmtrees=int(median("rmtrees")),
        page_scans=int(median("page_scans")),
        visual_scans=int(median("visual_scans")),
        errors=int(median("errors")),
        pages_created=int(median("pages_created")),
        pages_updated=int(median("pages_updated")),
        visuals_created=int(median("visuals_created")),
        visuals_updated=int(median("visuals_updated")),
        visuals_deleted=int(median("visuals_deleted")),
        properties_set=int(median("properties_set")),
        phase_times=_median_float_mapping([run.phase_times for run in runs]),
        write_categories=_median_int_mapping([run.write_categories for run in runs]),
        read_categories=_median_int_mapping([run.read_categories for run in runs]),
        phase_write_categories=_median_nested_int_mapping(
            [run.phase_write_categories for run in runs]
        ),
        phase_read_categories=_median_nested_int_mapping(
            [run.phase_read_categories for run in runs]
        ),
    )


def _increment(mapping: dict[str, int], key: str) -> None:
    mapping[key] = mapping.get(key, 0) + 1


def _increment_phase_category(
    mapping: dict[str, dict[str, int]],
    phase: str | None,
    category: str,
) -> None:
    bucket = mapping.setdefault(phase or "unattributed", {})
    _increment(bucket, category)


def _json_category(path: Path) -> str:
    name = path.name
    if name == "visual.json":
        return "visual"
    if name == "page.json":
        return "page"
    if name == "pages.json":
        return "pages-meta"
    if name == "report.json":
        return "report"
    if name == "bookmarks.json":
        return "bookmarks-meta"
    if name.endswith(".bookmark.json"):
        return "bookmark"
    if "RegisteredResources" in path.parts:
        return "resource"
    if name.endswith(".pbip"):
        return "pbip"
    return "other"


def _median_int_mapping(mappings: list[dict[str, int]]) -> dict[str, int]:
    keys = sorted({key for mapping in mappings for key in mapping})
    result: dict[str, int] = {}
    for key in keys:
        value = int(statistics.median(mapping.get(key, 0) for mapping in mappings))
        if value:
            result[key] = value
    return result


def _median_float_mapping(mappings: list[dict[str, float]]) -> dict[str, float]:
    keys = sorted({key for mapping in mappings for key in mapping})
    return {
        key: statistics.median(mapping.get(key, 0.0) for mapping in mappings)
        for key in keys
    }


def _median_nested_int_mapping(
    mappings: list[dict[str, dict[str, int]]]
) -> dict[str, dict[str, int]]:
    phases = sorted({phase for mapping in mappings for phase in mapping})
    result: dict[str, dict[str, int]] = {}
    for phase in phases:
        values = _median_int_mapping([mapping.get(phase, {}) for mapping in mappings])
        if values:
            result[phase] = values
    return result


@contextmanager
def copied_fixture(fixture_pbip: Path, target_root: Path):
    source_root = fixture_pbip.parent
    if target_root.exists():
        shutil.rmtree(target_root)
    shutil.copytree(source_root, target_root)
    yield target_root / fixture_pbip.name


def synthesize_fixture_project(
    fixture_pbip: Path,
    target_root: Path,
    *,
    page_count: int,
    visuals_per_page: int,
) -> Project:
    with copied_fixture(fixture_pbip, target_root) as pbip:
        project = Project.find(pbip)
        pages_dir = project.definition_folder / "pages"
        source_pages = load_source_pages(pages_dir)
        if not source_pages:
            raise RuntimeError(f"No source pages found in {fixture_pbip}")

        for child in list(pages_dir.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)

        page_order: list[str] = []
        for page_index in range(page_count):
            source_page = source_pages[page_index % len(source_pages)]
            page_id = f"benchpage{page_index:05d}"
            target_page = pages_dir / page_id
            target_page.mkdir(parents=True)
            page_data = copy.deepcopy(source_page["page"])
            page_data["name"] = page_id
            page_data["displayName"] = f"Bench Page {page_index + 1}"
            write_json_direct(target_page / "page.json", page_data)
            write_expanded_visuals(
                target_page, page_index, visuals_per_page, source_page["visuals"]
            )
            page_order.append(page_id)

        pages_meta = _read_json(pages_dir / "pages.json") if (pages_dir / "pages.json").exists() else {}
        pages_meta["pageOrder"] = page_order
        write_json_direct(pages_dir / "pages.json", pages_meta)

    return Project.find(target_root / fixture_pbip.name)


def load_source_pages(pages_dir: Path) -> list[dict[str, Any]]:
    pages: list[dict[str, Any]] = []
    for page_dir in sorted(
        path for path in pages_dir.iterdir() if path.is_dir() and (path / "page.json").exists()
    ):
        visual_payloads = [
            _read_json(visual_dir / "visual.json")
            for visual_dir in sorted((page_dir / "visuals").iterdir())
            if visual_dir.is_dir() and (visual_dir / "visual.json").exists()
        ] if (page_dir / "visuals").exists() else []
        if visual_payloads:
            pages.append({"page": _read_json(page_dir / "page.json"), "visuals": visual_payloads})
    return pages


def write_expanded_visuals(
    page_dir: Path,
    page_index: int,
    visual_count: int,
    source_payloads: list[dict[str, Any]],
) -> None:
    visuals_dir = page_dir / "visuals"
    visuals_dir.mkdir(exist_ok=True)
    if not source_payloads:
        return

    for visual_index in range(visual_count):
        visual_id = f"benchvis{page_index:05d}{visual_index:05d}"
        visual_dir = visuals_dir / visual_id
        visual_dir.mkdir(parents=True)
        payload = copy.deepcopy(source_payloads[visual_index % len(source_payloads)])
        payload["name"] = visual_id
        payload.setdefault("position", {})
        payload["position"].update(_position_dict_for(visual_index))
        write_json_direct(visual_dir / "visual.json", payload)


def create_minimal_project(root: Path) -> Project:
    if root.exists():
        shutil.rmtree(root)
    pbip = root / "Sample.pbip"
    definition = root / "Sample.Report" / "definition"
    definition.mkdir(parents=True)
    write_json_direct(pbip, {"artifacts": [{"report": {"path": "Sample.Report"}}]})
    write_json_direct(
        definition / "report.json",
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/2.0.0/schema.json",
            "themeCollection": {},
            "layoutOptimization": "None",
        },
    )
    return Project.find(pbip)


def build_update_spec(project: Project, *, offset: int) -> str:
    pages = []
    for page in project.get_pages():
        visuals = []
        for index, visual in enumerate(project.get_visuals(page)):
            pos = visual.position
            x = int(pos.get("x", 0)) + offset
            y = int(pos.get("y", 0)) + offset
            width = max(10, int(pos.get("width", 140)))
            height = max(10, int(pos.get("height", 70)))
            visuals.append(
                {
                    "name": visual.name,
                    "position": f"{x}, {y}",
                    "size": f"{width} x {height}",
                    "isHidden": index % 17 == 0,
                }
            )
        pages.append({"name": page.display_name, "visuals": visuals})
    return yaml.safe_dump({"version": 1, "pages": pages}, sort_keys=False)


def build_mixed_overwrite_spec(project: Project) -> str:
    pages = []
    for page_index, page in enumerate(project.get_pages()):
        existing_visuals = project.get_visuals(page)
        visuals: list[dict[str, Any]] = []
        keep_count = max(1, int(len(existing_visuals) * 0.7))
        for index, visual in enumerate(existing_visuals[:keep_count]):
            pos = visual.position
            visuals.append(
                {
                    "name": visual.name,
                    "position": f"{int(pos.get('x', 0)) + 5}, {int(pos.get('y', 0)) + 5}",
                    "size": f"{max(10, int(pos.get('width', 140)))} x {max(10, int(pos.get('height', 70)))}",
                }
            )
        create_count = max(1, len(existing_visuals) // 5)
        for new_index in range(create_count):
            visual_index = keep_count + new_index
            visuals.append(
                {
                    "name": f"new_card_{page_index}_{new_index}",
                    "type": "cardVisual",
                    "position": _position_for(visual_index),
                    "size": "140 x 70",
                }
            )
        pages.append({"name": page.display_name, "visuals": visuals})
    return yaml.safe_dump({"version": 1, "pages": pages}, sort_keys=False)


def _position_for(index: int) -> str:
    pos = _position_dict_for(index)
    return f"{pos['x']}, {pos['y']}"


def _position_dict_for(index: int) -> dict[str, int]:
    return {
        "x": 10 + (index % 5) * 160,
        "y": 20 + (index // 5) * 90,
        "width": 140,
        "height": 70,
    }


def write_json_direct(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def print_results(results: list[ScenarioResult], *, detail: bool = False) -> None:
    header = (
        f"{'Scenario':<24} {'Mode':<9} {'Time':>8} {'Writes':>8} "
        f"{'Reads':>7} {'copytree':>8} {'rmtree':>7} {'Changes':>28} {'Err':>4}"
    )
    print(header)
    print("-" * len(header))
    for result in results:
        for mode, metrics in (("eager", result.eager), ("buffered", result.buffered)):
            changes = (
                f"p+{metrics.pages_created}/p~{metrics.pages_updated} "
                f"v+{metrics.visuals_created}/v~{metrics.visuals_updated}/v-{metrics.visuals_deleted}"
            )
            print(
                f"{result.name:<24} {mode:<9} {metrics.elapsed:>7.3f}s "
                f"{metrics.json_writes:>8} {metrics.json_reads:>7} "
                f"{metrics.copytrees:>8} {metrics.rmtrees:>7} "
                f"{changes:>28} {metrics.errors:>4}"
            )
        delta = result.buffered.elapsed - result.eager.elapsed
        pct = (delta / result.eager.elapsed * 100) if result.eager.elapsed else 0.0
        write_delta = result.buffered.json_writes - result.eager.json_writes
        print(
            f"{'':<24} {'Δ':<9} {delta:>+7.3f}s ({pct:+5.1f}%) "
            f"{write_delta:>+8}"
        )
        if detail:
            print_detail(result)


def print_detail(result: ScenarioResult) -> None:
    for mode, metrics in (("eager", result.eager), ("buffered", result.buffered)):
        print(
            f"  {mode:<8} scans pages={metrics.page_scans} visuals={metrics.visual_scans}"
        )
        print(f"  {mode:<8} phases: {_format_seconds_mapping(metrics.phase_times)}")
        print(f"  {mode:<8} writes: {_format_int_mapping(metrics.write_categories)}")
        print(f"  {mode:<8} reads:  {_format_int_mapping(metrics.read_categories)}")
        print(f"  {mode:<8} phase writes:")
        print(_format_nested_int_mapping(metrics.phase_write_categories, indent="    "))
        print(f"  {mode:<8} phase reads:")
        print(_format_nested_int_mapping(metrics.phase_read_categories, indent="    "))


def _format_seconds_mapping(mapping: dict[str, float]) -> str:
    if not mapping:
        return "(none)"
    return ", ".join(f"{key}={value:.3f}s" for key, value in sorted(mapping.items()))


def _format_int_mapping(mapping: dict[str, int]) -> str:
    if not mapping:
        return "(none)"
    return ", ".join(f"{key}={value}" for key, value in sorted(mapping.items()))


def _format_nested_int_mapping(
    mapping: dict[str, dict[str, int]],
    *,
    indent: str = "",
) -> str:
    if not mapping:
        return f"{indent}(none)"
    return "\n".join(
        f"{indent}{phase}: {_format_int_mapping(categories)}"
        for phase, categories in sorted(mapping.items())
    )


if __name__ == "__main__":
    main()
