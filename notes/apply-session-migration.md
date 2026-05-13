# Apply Session Migration Discussion

## Context

GitHub issue #17 proposes using the YAML apply engine as the first testbed for a proper session/write-buffer architecture. The long-term goal is batched PBIR writes and eventually cross-command sessions, but the immediate migration target is `apply`.

## Current apply shape

- `src/pbi/apply/session.py` defines the lifecycle seam:
  - `ApplySession`: `begin`, `commit`, `rollback`, `cleanup`.
  - `PbirWriteSession`: PBIR-specific write operations used by apply leaf code.
  - `run_apply(...)`: owns commit vs rollback behavior.
- `src/pbi/apply/state.py` implements `PbirApplySession`.
  - It currently snapshots `definition/` lazily.
  - It still writes eagerly from `save_page`, `save_visual`, `write_report`, `write_theme`, `write_bookmark`, and structural operations.
  - `commit()` is currently a no-op.
  - `rollback()` restores the snapshot and clears project caches.
- `tests/test_apply_session.py` already pins the seam and rollback behavior.

## Migration intent

Move `PbirApplySession` from “eager writes with snapshot rollback” to a real buffered unit of work:

- apply mutates in-memory `Page`, `Visual`, and document payloads;
- the session records dirty documents/operations;
- no normal JSON document writes happen before `commit()`;
- `commit()` flushes each dirty document once;
- rollback can discard buffered changes, with the existing filesystem snapshot retained initially as a safety net.

## Direction from discussion

We want the apply migration to move deliberately toward the future daemon/session architecture, not merely optimize a few writes.

The preferred development mode is a **secondary apply path** that can run beside the current eager apply implementation. The new path should apply the same YAML to the same starting fixture and produce exactly the same final PBIR files, but by staging all changes and committing them in one go.

This gives us two immediate validation loops:

1. **Correctness parity:** eager apply output and session apply output are byte/content-equivalent for the report definition/resources we expect to touch.
2. **Performance comparison:** run the same changes through both approaches and measure elapsed time and write behavior.

## Candidate secondary path

Decision: start with a separate Python entry point first, not CLI UX.

Introduce a buffered/session-backed variant without replacing the default path at first:

- add a direct Python entry point: `apply_yaml_buffered(...)`;
- keep the current eager `apply_yaml(...)` as the baseline/default;
- defer `pbi apply --buffered` or `--session-mode buffered` until parity and performance tests are useful;
- concrete adapter: keep existing `PbirApplySession` as eager, add a new `BufferedPbirApplySession` or `PbirBufferedApplySession`.

The adapter should still satisfy the existing `PbirWriteSession` protocol so most apply leaf code remains unchanged. The Python entry point exists primarily for tests and benchmarking at first. If the path stabilizes, we can later unify the API behind a mode parameter or expose it through the CLI.

## Architecture target for the buffered path

The buffered path should model a future daemon-owned in-memory project state:

- all apply mutations happen against in-memory `Page`, `Visual`, and document payloads;
- filesystem changes are staged as operations/documents;
- `commit()` executes the staged unit of work in a deterministic order;
- before `commit()`, the on-disk project should remain unchanged except for any explicitly accepted temporary/session bookkeeping;
- after `commit()`, the output should match the current eager apply output for the same fixture/spec.

This implies structural operations should probably be included in the buffered path early, because page/visual creation and deletion are core to both apply and future daemon sessions. A JSON-only buffer would improve writes but would not adequately prove the future session model.

## Validation harness idea

Build tests/utilities that:

1. create or copy the same starting PBIP fixture twice;
2. run current eager `apply_yaml` on copy A;
3. run buffered/session apply on copy B via `apply_yaml_buffered`;
4. compare the resulting report tree contents;
5. assert equal `ApplyResult` shape where practical;
6. optionally record write counts and elapsed time for performance tests/benchmarks.

Parity comparison decision:

- compare `.json` files by parsed JSON equality, not byte-for-byte formatting;
- compare non-JSON files byte-for-byte;
- normalize only known irrelevant/generated differences if they appear in real fixtures.

Existing test support already has `tests/cli_regressions_support.py::make_project` and many apply specs in `tests/test_cli_apply_regressions.py`. These can seed parity fixtures before adding larger fixture-based comparisons.

## Implementation implications

The buffered implementation likely needs a richer unit-of-work than simple dirty JSON maps:

- dirty document writes: visual/page/report/bookmark metadata JSON;
- staged mkdir/write-folder operations for created pages and visuals;
- staged deletes for overwrite/type conversion;
- staged resource writes for first-time themes;
- cache/index updates so later apply phases see staged pages/visuals before commit;
- deterministic commit ordering, probably create directories → write documents/resources → delete obsolete paths, or another order proven equivalent/safe.

The existing snapshot rollback can remain initially as a safety net, but the design objective is that rollback before commit mostly discards staged operations rather than restoring many eager writes.

## Vertical slice plan

Decision: break the migration into testable vertical slices, each adding one class of staged operation and proving parity against the eager apply path.

Each slice should include:

- at least one parity test that runs eager apply and buffered apply from identical starting projects;
- comparison of resulting project trees (`.json` parsed equality, other files byte equality);
- equivalent `ApplyResult` assertions where practical;
- enough buffered-session implementation to make that scenario pass without replacing the eager path.

### Slice 0 — harness and entry point skeleton

Goal: establish the secondary path and comparison machinery before implementing real buffering.

Scope:

- add `apply_yaml_buffered(...)` as a Python entry point;
- add `BufferedPbirApplySession` skeleton satisfying `PbirWriteSession`;
- add parity comparison helper(s);
- add an initial skipped/xfail or minimal no-op parity case if useful.

Verification:

- tests can call both `apply_yaml(...)` and `apply_yaml_buffered(...)` against twin fixtures;
- no CLI behavior changes.

Status: implemented as the initial harness.

- `src/pbi/apply/engine.py` now has `apply_yaml_buffered(...)` through shared apply orchestration.
- `src/pbi/apply/buffered.py` contains the fail-fast `BufferedPbirApplySession` skeleton.
- `tests/apply_parity_support.py` provides result/tree parity helpers.
- `tests/test_apply_buffered_parity.py` has no-op parity and fail-fast coverage for unimplemented writes.

### Slice 1 — simple page + visual creation

Goal: prove staged creation/write for the most basic apply workflow.

Scope:

- stage `create_page` and `create_visual`;
- maintain in-memory project/page/visual state so later apply phases can see staged entities;
- stage final page/visual JSON writes;
- commit creates folders and writes the staged documents.

Verification:

- parity case: empty report + YAML with one page and one visual;
- on-disk project remains unchanged before commit, if practical to assert at session level.

### Slice 2 — update existing page/visual

Goal: prove dirty-document buffering for existing entities.

Scope:

- stage `save_page` and `save_visual` for existing folders;
- flush each dirty page/visual JSON once at commit;
- keep rollback-before-commit as discard-only for this path, with snapshot retained as safety net.

Verification:

- parity case: existing page/visual with changed position/size/title/page metadata;
- optional instrumentation: save/write count is lower than eager path.

### Slice 3 — overwrite and type conversion/delete

Goal: prove structural delete/replace operations.

Scope:

- stage `delete_visual`;
- support type conversion path (`delete_visual` then `create_visual`);
- decide and codify commit ordering for delete/create collisions.

Verification:

- parity case: existing visual converted to a different type;
- parity case: `overwrite=True` removes visuals absent from YAML.

### Slice 4 — bookmarks

Goal: prove non-page/visual document staging.

Scope:

- stage individual bookmark JSON writes;
- stage bookmark metadata/group reconciliation;
- commit bookmark files/meta in deterministic order.

Verification:

- parity case: create/update bookmarks referencing staged/existing visuals and groups.

### Slice 5 — theme/resource writes

Goal: prove report-level resource staging, including writes outside `definition/`.

Scope:

- stage `write_report`;
- stage first-time theme resource copy/write;
- stage existing theme updates;
- clarify rollback behavior for resource writes and close or explicitly preserve the current orphan-resource gap.

Verification:

- parity case: first-time theme apply;
- parity case: update existing theme;
- compare `definition/` and relevant `StaticResources/RegisteredResources/` files.

### Slice 6 — performance/write-count benchmark

Goal: quantify why the buffered path exists.

Scope:

- add benchmark or test utility that applies the same larger spec through eager and buffered paths;
- collect elapsed time and write counts where practical;
- keep this out of brittle unit assertions unless stable enough.

Verification:

- documented comparison output or optional benchmark command/test.

## Open questions

- For commit ordering, should deletes happen before creates to avoid name/folder collisions, or should new paths be allocated to avoid collisions until finalization?
