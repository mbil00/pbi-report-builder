# PBI Report Builder — Development Guide

CLI tool for editing Power BI PBIP project files. Agent-first design.

## Stack

Python 3.11+, Typer (CLI), Rich (output), PyYAML (export/apply). Source in `src/pbi/`, commands in `src/pbi/commands/`. Tests via `python -m pytest tests/`.

## Command Grammar

**Verbs:** `list`, `get`, `set`, `set-all`, `create`, `copy`, `delete`, `clear`, `export`, `apply`, `migrate`. Use `get` to view details (never `show`). Use `delete` to remove resources (never `remove`). Use `unhide` as the opposite of `hide`. Use `clear` to remove configuration (sort, formatting, interactions, drillthrough, tooltip).

**Arguments:** Targets are positional, options are named. Setters use `key=value` positional args. Field references use `Table.Field` format everywhere.

**Scope narrowing:** Use `--page` and `--visual` optional flags to narrow scope (see filter commands). Default scope is report-level. `--visual` requires `--page`.

**Common flags:**
- `--project, -p` — all commands (via `ProjectOpt`)
- `--json` — all list commands, parameter name `as_json`
- `--raw, -r` — get/detail commands (dumps full JSON)
- `--full` — `visual get` (dump properties, objects, columns, filters, sort in one call)
- `--force, -f` — all delete commands (skip confirmation)
- `--dry-run` — all mutating apply/create/edit/format commands
- `--name, -n` — create commands (friendly name)
- `--title` — visual create (sets title.show + title.text)
- `--all-pages` — `visual set-all`, `visual column` (apply across all pages, mutually exclusive with `--page`)
- `--where` — `visual set-all` (filter by current property value, e.g. `--where border.color=#EDEBE9`)
- `--exclude` — `page set-all` (skip pages matching substring)
- `--overwrite` — `apply` (full reconciliation, removes visuals not in YAML)
- `--page` — `map` (filter to single page), `apply` (filter to single page), `visual set-all` (target page)
- `--global, -g` — `style`, `component`, `template` commands (use global scope from ~/.config/pbi/)
- `--bundled` — `style list` (include built-in shape presets)
- `--from-project` — `page import` (source project path)
- `--include-resources` — `page import` (also copy image files)
- `--set` — `component apply` (parameter overrides as key=value)
- `--set-each` — `component apply --row` (per-instance values as key=v1,v2,v3)
- `--row` — `component apply` (batch stamp N instances in a row)

## Output Patterns

**Rich markup styles:**
- `[cyan]` — entity names, field references, display names
- `[dim]` — metadata, secondary info, arrows (`->`), dry-run prefix, `(none)` placeholders
- `[bold]` — headings, table titles
- `[yellow]` — warnings, hidden state, empty results with guidance
- `[red]` — errors only
- `[green]` — success/supported status

**Messages:**
- Error: `console.print(f"[red]Error:[/red] {msg}")` then `raise typer.Exit(1)`
- Warning: `console.print(f"[yellow]Warning:[/yellow] {msg}")`
- Created: `console.print(f'Created page "[cyan]{name}[/cyan]"')`
- Deleted: `console.print(f'Deleted page "[cyan]{name}[/cyan]"')`
- Changed: `console.print(f"[dim]{prop}:[/dim] {old} [dim]->[/dim] {new}")`
- No-op: `console.print(f'[dim]No change:[/dim] [cyan]{name}[/cyan] is already {state}')`
- Empty list: `console.print("[yellow]No items. Use \`pbi item create\` to add one.[/yellow]")` then `raise typer.Exit(0)`
- Dry-run prefix: `prefix = "[dim](dry run)[/dim] " if dry_run else ""`
- No changes: `console.print("[dim]No changes applied.[/dim]")`

**Tables:** `Table(box=box.SIMPLE)`. Primary column `style="cyan"`, metadata `style="dim"`, booleans as `"yes"` or `""`.

**--json:** Early return with `console.print_json(json.dumps(rows, indent=2))`. Return list of dicts.

## Lookup Resolution

All find functions follow this precedence: exact ID → exact display name (case-insensitive) → partial match (unique) → 1-based index → fuzzy suggestion → available list fallback.

Fuzzy: `difflib.get_close_matches(input, names, n=3, cutoff=0.5)`. Format: `'Not found. Did you mean: "X", "Y"?'`. If no close match, fall back to `'Not found. Available: "A", "B", "C"'`.

## Confirmation

All destructive commands prompt unless `--force/-f`:
```python
if not force:
    confirm = typer.confirm(f'Delete "{name}"?')
    if not confirm:
        raise typer.Abort()
```

## Visual Creation

`create_visual()` scaffolds `queryState` with empty role projections from the type's role catalog. The CLI command prints available roles after creation so agents know what to bind.

## Key Files

- `src/pbi/commands/common.py` — `ProjectOpt`, `console`, `get_project()`, `parse_property_assignments()`
- `src/pbi/project.py` — `Project` class, page/visual CRUD, find with fuzzy suggestions
- `src/pbi/properties.py` — `VISUAL_PROPERTIES`, `PAGE_PROPERTIES`, `get_property()`, `set_property()`
- `src/pbi/roles.py` — visual type catalog, role definitions, `normalize_visual_type()`
- `src/pbi/modeling/schema.py` — `SemanticModel`, `SemanticTable`, `Relationship`, field resolution, BFS path finding
- `src/pbi/apply.py` / `src/pbi/export.py` — YAML round-trip (the star feature)
- `src/pbi/styles.py` — style presets (project + global + bundled), capture from visual, apply to visuals
- `src/pbi/themes.py` — theme apply/export/delete/migrate, color migration
- `src/pbi/components.py` — reusable visual components (save/apply/stamp), parameter detection, `{{ }}` substitution
- `src/pbi/images.py` — image resource management (add/list/prune for RegisteredResources)
- `src/pbi/mapper.py` — `pbi map` with `--page`/`--pages`/`--model` filters
- `src/pbi/presets/` — bundled shape style presets (rounded-container, section-bg, separator, card-frame)
- `docs/agent-workflows.md` — recommended agent patterns (export → edit → apply)

## YAML Apply Features

The apply engine supports these property syntaxes in YAML:
- **Nested properties:** `title: { show: true, text: "Hello" }` → `title.show=true`
- **Bracket selectors:** `value.fontSize [Measures Table.X]: 20` → per-measure formatting
- **chart: prefix:** `chart:legend.show: true` → unregistered chart object properties
- **chart: with selector:** `chart:icon.shapeType [default]: back`
- **style: reference:** `style: card-style` → applies all properties from a saved style preset
- **interactions:** page-level `interactions:` list with source/target/type
- **bookmarks:** top-level `bookmarks:` list with name/page/hide
- **conditionalFormatting:** `mode: measure` or `mode: gradient` with min/mid/max stops
- **filters:** `type: topN` (count/by/direction), `type: range` (min/max), plus categorical/include/exclude
- **Visual type conversion:** when YAML specifies a different type for an existing visual, the old visual is deleted and a new one created with the new type
- **Overwrite mode:** `--overwrite` deletes visuals not in YAML, reports deletions
- **Dry-run completeness:** `--dry-run` lists all visuals for newly created pages
- **Diff preview:** `pbi diff <yaml>` shows property-by-property changes before applying

## Engineering Rule

New write paths must be validated against Microsoft's published PBIR schema or derived from a canonical exported PBIR sample with test coverage. No guessing JSON structures.
