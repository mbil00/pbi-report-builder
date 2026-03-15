# PBI Report Builder — Usability Review

*Generated 2026-03-15. Agent-first tool; human usability is secondary but still matters for quick edits.*

## Executive Summary

PBI Report Builder is a well-architected CLI tool for programmatic Power BI report editing. It covers an impressive breadth of PBIR authoring operations with a consistent command grammar and thoughtful agent-oriented workflow. There are meaningful usability gaps around naming consistency, discoverability, and structured output that would impact both human and AI agent users.

---

## 1. First Impressions & Onboarding

### The README is thin

The README is 17 lines. It tells the user how to install but nothing about what the tool does beyond one line. No link to `docs/`, no command overview, no quick example.

**Recommendation:** Add a brief pitch, 3-4 example commands, and a link to `docs/`.

### No `--version` flag

Resolved. The CLI now exposes `--version`; keep package metadata and the runtime version string aligned.

---

## 2. Command Structure & Discoverability

### Strengths

- Logical grouping into 9 command groups mapping to Power BI concepts.
- `pbi info` as a quick entry point.
- `pbi capabilities` for transparent feature support status.
- `pbi validate` as a post-mutation safety check.

### Problems

**`pbi info` doesn't show visual names.** It shows types and positions but not the user-assigned names that every other command requires. Forces an immediate follow-up `pbi visual list`.

---

## 3. Naming & Consistency

### Verb inconsistencies — RESOLVED

All verb inconsistencies have been fixed:
- `model measure show` → `model measure get`
- `model column show` (unhide) → `model column unhide`
- `style show` → `style get`
- `filter remove` → `filter delete`
- `theme remove` → `theme delete`

### `apply` is overloaded

`pbi apply`, `theme apply`, `page apply-template`, and `model apply` all use "apply" for different target/format combinations. Defensible but worth noting.

### Filter command grammar is unusual

Variable positional args based on scope (`filter add report <field>` vs `filter add visual <page> <visual> <field>`) is a parsing challenge for agents. Named flags (`--scope`, `--page`, `--visual`) would be more predictable.

---

## 4. Error Handling & Guidance

### Strengths

- Consistent `[red]Error:[/red]` formatting.
- Confirmation prompts on destructive ops with `--force` bypass.
- `--dry-run` widely available.
- Rollback on `--overwrite` failure.
- Empty result guidance suggesting the `create` command.

### Problems

- **No "did you mean?" suggestions.** When a visual/page/property isn't found, no suggestions offered.
- **No validation on property names.** Typos in property paths silently write to JSON.

---

## 5. Feature Completeness

### Well-covered

| Area | Assessment |
|------|-----------|
| Page CRUD | Complete |
| Visual CRUD | Complete |
| Data binding | Strong |
| Visual properties | Good (~60+ named properties) |
| Filters | Good (6 types, 3 scopes) |
| Semantic model | Good |
| Export/Apply | Excellent — star feature |
| Validation | Good |

### Notable gaps

| Missing Feature | Impact |
|----------------|--------|
| Page reordering / active page | Can't set from CLI |
| Visual type-specific scaffolding | `create` makes bare shell, no defaults |
| Passthrough filters | Blocked |
| Bookmark groups | Can't create navigator groups |
| Action buttons | No dedicated surface |
| Report-level objects | Can't set report background |
| Slicer sync groups | Can't configure cross-page sync |
| Mobile layout | No support |

---

## 6. Output & Structured Data

### Strengths

- Rich tables for list commands.
- Color-coded status indicators.
- `--raw` for JSON on some commands.

### Problems

- **No `--json` on most commands.** Only `capabilities --json` and `get --raw`. Agents benefit from structured output on `page list`, `visual list`, `filter list`, etc.
- **Inconsistent output formats.** `style get` → YAML, `bookmark get --raw` → JSON, `visual get` → table.

---

## 7. Edge Cases

- `pbi map` YAML vs `pbi apply` YAML are different formats with similar extensions — could confuse agents.
- Templates and style presets are project-local only.
- No bulk delete operations.

---

## 8. Prioritized Recommendations

### High Priority (benefits agents directly) — ALL RESOLVED

1. ~~Standardize verbs~~ — done
2. ~~Add `--version` flag~~ — done
3. ~~Add visual names to `pbi info`~~ — done
4. ~~Add `--json` output to list commands~~ — done
5. ~~Add "did you mean?" suggestions~~ — done (pages, visuals, tables, columns, measures, fields)
6. Fix doc examples that don't match actual command signatures — partially addressed

### Medium Priority — ALL RESOLVED

7. ~~Add page reorder / set-active commands~~ — done
8. ~~Unify filter argument grammar~~ — done (scope via `--page`/`--visual` flags, field is positional)
9. ~~Expand README~~ — done
10. ~~Visual type scaffolding~~ — done (queryState roles pre-initialized, `--title` flag, role hints in output)

### Lower Priority

11. Global template/style libraries
12. Bulk delete operations
13. `--quiet` mode for scripting
14. Shell completion setup docs

---

## Overall Assessment

Capable, well-designed tool that punches above its version number. The export-edit-apply workflow is genuinely innovative. Main barriers are naming inconsistencies and lack of structured output for agent consumption. The agent-first design philosophy is sound.
