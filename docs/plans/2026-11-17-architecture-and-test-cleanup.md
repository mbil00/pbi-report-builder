# Architecture and test cleanup (2026-11-17)

Source: an architecture review plus a test-suite audit (2026-11-17). The audit found that
YAML round-trip, the main feature, fails on the Desktop-saved fixtures. The tests missed it
because they compare YAML to YAML or run `diff` instead of `apply`. The plan therefore:

1. adds groundwork,
2. makes the fixtures the main validation target with a harness whose known failures are strict xfails,
3. fixes the bugs one PR at a time (each fix removes its xfails),
4. deletes the hand-built tests the harness now covers,
5. does the architecture cleanup.

Each unit is one PR with a Conventional Commit title, squash-merged. State markers:
`[ ]` todo, `[x]` merged (PR number and short SHA).

## Decisions

- **Desktop-saved output is ground truth.** When a fix must choose between the extracted
  schema and what Desktop actually writes, follow Desktop and record the choice under
  `## Design decisions` in the PR body (user, 2026-11-17).
- **report-03 is not ground truth.** It was built with `pbi`. Use it for round-trip and
  idempotency only.
- **Fixtures are copied, never edited in place,** except where a unit says otherwise (B6 may
  repair report-02 shapes that `pbi` wrote, with the provenance shown in the PR).
- **Buffered apply is removed and the daemon/session idea is dropped** (user, 2026-11-17).
  `pbi batch` covers long edit sequences.
- ADR 0001 stands: YAML section dispatch stays hard-coded.

## Relay units (in order; the relay stops after T4)

| # | Unit | Issue | State |
|---|---|---|---|
| 1 | T1 conftest and shared fixture-copy support | #82 | [x] #98 (3f52d10) |
| 2 | T2 delete dead, unfailable and fully duplicated tests | #83 | [x] #100 (f0a1d0d) |
| 3 | T3 fixture harness with strict xfails | #84 | [x] #105 (fa6b3f7) |
| 4 | B1 `changedProperty` pulled into calculated-column DAX | #75 | [x] #106 (30649d0) |
| 5 | B2 model export → apply rewrites unchanged TMDL | #76 | [x] #107 (309c0de) |
| 6 | B3 apply crashes on Aggregation bindings | #73 | [x] #110 (22252c0) |
| 7 | B4 hierarchy-level bindings don't round-trip | #69 | [x] #111 (337a63a) |
| 8 | B5 `legend.position: TopRight` rejected | #77 | [x] #114 (c1d65af) |
| 9 | B6 report-02 card roles and corrupt sort ref | #78 | [x] #116 (8133c0b) |
| 10 | B7 report-03 apply rewrites 14 files | #79 | [x] #117 (9fa7161) |
| 11 | B8 `diff` disagrees with `apply` | #80 | [x] #119 |
| 12 | B9 field parameters in a guessed shape | #81 | [ ] |
| 13 | T4a delete harness-covered tests: apply | #85 | [ ] |
| 14 | T4b … model | #85 | [ ] |
| 15 | T4c … visual/CLI | #85 | [ ] |
| 16 | T4d … themes | #85 | [ ] |
| 17 | T4e … misc | #85 | [ ] |

Each B unit runs the harness, removes the xfails its fix resolves, and leaves any xfails it
doesn't resolve. If a fix turns up a further round-trip bug, file an issue and add it as an
xfail; don't widen the PR. If the B fixes leave an area's harness steps still xfailed, the
matching T4 PR deletes only what the harness actually covers.

## After the relay (not scheduled yet)

| Unit | Issue |
|---|---|
| A1 remove buffered apply path (approved) | #89 |
| A6 domain code stops printing | #94 |
| A2 public JSON I/O, no private cross-imports | #90 |
| A3 split `modeling/writes.py` | #91 |
| A4 model package naming, absorb tiny wrapper modules | #92 |
| T5 parametrize copy-paste tests | #86 |
| T6 regroup grab-bag test files | #87 |
| T7 destructive commands prompt without `--force` | #88 |
| A5 thin `cli.py`, split giant functions | #93 |
| A7 docs drift | #95 |
| A8 subpackages (optional, needs triage) | #96 |
