# PBI Report Builder — Development Guide

CLI tool for editing Power BI PBIP project files. Agent-first design.

## Stack

Python 3.11+, Typer (CLI), Rich (output), PyYAML (export/apply). Source in `src/pbi/`, commands in `src/pbi/commands/`. Tests via `python -m pytest tests/`.

## Command Grammar

**Verbs:** `list`, `get`, `set`, `set-all`, `create`, `copy`, `delete`, `clear`, `export`, `apply`, `migrate`. Use `get` to view details (never `show`). Use `delete` to remove resources (never `remove`). Use `unhide` as the opposite of `hide`. Use `clear` to remove configuration (sort, formatting, interactions, drillthrough, tooltip).

**Arguments:** Targets are positional, options are named. Setters use `key=value` positional args. Field references use `Table.Field` format everywhere.

**Scope narrowing:** Use `--page` and `--visual` optional flags to narrow scope (see filter commands). Default scope is report-level. `--visual` requires `--page`.

**Subgroup grammar:** Prefer noun subgroups before verbs when a feature has variants, e.g. `page tooltip set`, `bookmark group create`, `nav page set`, `nav action get`, `nav tooltip clear`.

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
- `--continue-on-error` — `apply` (apply what is possible, report errors without rollback)
- `--from` — `visual create` (reference visual as 'page/visual' to clone type, style, bindings)
- `--page` — `map` (filter to single page), `apply` (filter to single page), `visual set-all` (target page)
- `--global, -g` — `style`, `component`, `template`, `theme save/load/preset` commands (use global scope from ~/.config/pbi/)
- `--no-cascade` — `theme set` (don't cascade derived colors)
- `--to-global` / `--to-project` — `theme preset clone` (clone between scopes)
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

`create_visual()` scaffolds `queryState` with empty role projections from the type's role catalog. The CLI command prints available roles after creation so agents know what to bind. Use `--from page/visual` to clone from a reference visual. `visual export` exports a single visual as apply-compatible YAML.

## Name Sanitization

All visual `name` fields are sanitized via `sanitize_visual_name()` in `project.py` — strips spaces, colons, and special characters to identifier-safe format. Applied in: `visual create`, `visual rename`, `visual copy`, `apply`, `component apply`, `create_group`.

## Key Files

- `src/pbi/commands/common.py` — `ProjectOpt`, `console`, `get_project()`, `parse_property_assignments()`
- `src/pbi/project.py` — `Project` class, page/visual CRUD, find with fuzzy suggestions
- `src/pbi/properties.py` — `VISUAL_PROPERTIES`, `PAGE_PROPERTIES`, `get_property()`, `set_property()`, auto-resolve chart properties via schema
- `src/pbi/roles.py` — visual type catalog, role definitions, `normalize_visual_type()`, schema-backed role fallback
- `src/pbi/visual_schema.py` — schema-powered validation: `validate_object()`, `validate_property()`, `validate_value()`, `get_object_names()`, `get_property_type()`
- `src/pbi/data/visual_capabilities.json` — extracted PBI Desktop capability schema (57 visual types, 611 objects, 7094 properties with types)
- `src/pbi/validate.py` — project validation engine (`pbi validate`), structural checks, schema validation of visual objects
- `src/pbi/modeling/schema.py` — `SemanticModel`, `SemanticTable`, `Relationship`, `Hierarchy`, `HierarchyLevel`, field resolution, BFS path finding
- `src/pbi/modeling/dax_refs.py` — DAX reference scanner: `extract_refs()`, `replace_refs()`, `find_dependents()` for dependency analysis and cascading renames
- `src/pbi/model_export.py` — `export_model_yaml()` for YAML round-trip of model definitions
- `src/pbi/apply.py` / `src/pbi/export.py` — YAML round-trip (the star feature)
- `src/pbi/styles.py` — style presets (project + global + bundled), capture from visual, apply to visuals
- `src/pbi/themes.py` — theme create/get/set/apply/export/delete/migrate, color cascade, brand scaffolding
- `src/pbi/components.py` — reusable visual components (create/apply/stamp), parameter detection, `{{ }}` substitution
- `src/pbi/images.py` — image resource management (create/list/prune for RegisteredResources)
- `src/pbi/mapper.py` — `pbi map` with `--page`/`--pages`/`--model` filters
- `src/pbi/presets/` — bundled shape style presets (rounded-container, section-bg, separator, card-frame)
- `docs/agent-workflows.md` — recommended agent patterns (export → edit → apply)
- `docs/cheatsheet.md` — complete CLI cheatsheet with patterns and examples for every command
- `docs/design-guidelines.md` — visual design rules: slicer configuration, sizing, layout patterns, common pitfalls

## Model Commands

All model subgroups follow the standard CLI verb pattern: `list`, `get`, `set`, `create`, `delete`, `rename`.

**Table:** `model table list`, `model table create <name> <DAX>` (calculated tables)

**Column:** `model column list <table>`, `model column get <Table.Column>`, `model column set <Table.Column> key=value...`, `model column create`, `model column edit`, `model column delete`, `model column rename <table> <old> <new>`, `model column hide`, `model column unhide`
- Writable properties via `set`: `description`, `displayFolder`, `sortByColumn`, `summarizeBy`, `dataCategory`, `formatString`
- `hide`/`unhide` accept `Table.Column` args or `--table <table> --pattern <regex>` for bulk operations (e.g. `--pattern "ID$"`)

**Measure:** `model measure list <table>`, `model measure get`, `model measure set <Table.Measure> key=value...`, `model measure create`, `model measure edit`, `model measure delete`, `model measure rename <table> <old> <new>`
- `rename` cascades through all `[OldName]` and `Table[OldName]` DAX references across the model

**Relationship:** `model relationship list`, `model relationship create <from> <to>` (with `--cross-filter`, `--inactive`), `model relationship delete <from> <to>`, `model relationship set <from> <to> key=value...`

**Hierarchy:** `model hierarchy list <table>`, `model hierarchy create <table> <name> <columns...>`, `model hierarchy delete <table> <name>`

**Field Parameter:** `model field-parameter create <name> <Table.Field...> [--labels Label...]` — scaffolds a field parameter table with `isParameterType`, three columns (Name/Fields/Order), and a DAX `NAMEOF` table constructor. Labels default to field names if omitted.

**Other model commands:**
- `model export [-o file.yaml]` — YAML round-trip through `model apply`
- `model apply <yaml>` — declarative model changes
- `model deps <Table.Field>` — forward/reverse dependency analysis
- `model check` — validate relationships (bidirectional cross-filters, auto-detected, missing)
- `model search <keyword>` — cross-table field search
- `model path <from_table> <to_table>` — BFS relationship path
- `model fields <table>` — columns + measures for visual binding

## Model Apply YAML Sections

The `model apply` engine supports these top-level sections:
- **measures:** table-keyed list with `name`, `expression`, `format`, `description`, `displayFolder`
- **columns:** table-keyed mapping with `format`, `hidden`, `type`, `expression`, `dataType`, `description`, `displayFolder`, `sortByColumn`, `summarizeBy`, `dataCategory`
- **relationships:** list of `{from, to, crossFilteringBehavior, isActive, ...}` — creates or updates
- **hierarchies:** table-keyed list of `{name, levels: [col1, col2]}` — creates or delete-and-recreates if levels differ
- **fieldParameters:** name-keyed mapping with `fields` list of `{field: Table.Field, label: DisplayName}` — creates field parameter tables

## YAML Apply Features

The apply engine supports these property syntaxes in YAML:
- **Nested properties:** `title: { show: true, text: "Hello" }` → `title.show=true`
- **Bracket selectors:** `value.fontSize [Measures Table.X]: 20` → per-measure formatting
- **Chart object properties:** `legend.show: true` → auto-resolved via schema when the object+property is valid for the visual type. `chart:` prefix also supported explicitly.
- **Chart with selector:** `legend.position [default]: Top` or `chart:icon.shapeType [default]: back`
- **style: reference:** `style: card-style` → applies all properties from a saved style preset
- **interactions:** page-level `interactions:` list with source/target/type
- **bookmarks:** top-level `bookmarks:` list with name/page/hide
- **conditionalFormatting:** `mode: measure`, `mode: gradient` with min/mid/max stops, or `mode: rules` with `rules:` list of `{if, color}` and optional `else:`
- **filters:** `type: topN` (count/by/direction), `type: range` (min/max), categorical/include/exclude, `type: advanced` with `operator:` (contains, starts-with, is, is-not, greater-than, less-than, is-blank, is-not-blank, is-empty, is-not-empty, and negated variants). Compound: `operator2:`/`value2:`/`logic: and|or`. `type: relative` with `operator` (InLast/InThis/InNext), `count`, `unit` (Days/Weeks/Months/Years/Minutes/Hours/etc.), and optional `includeToday`
- **Visual type conversion:** when YAML specifies a different type for an existing visual, the old visual is deleted and a new one created with the new type
- **Overwrite mode:** `--overwrite` deletes visuals not in YAML, reports deletions
- **Dry-run completeness:** `--dry-run` lists all visuals for newly created pages
- **Diff preview:** `pbi diff <yaml>` shows property-by-property changes before applying

## Schema Validation

All chart property writes are validated against the extracted PBI Desktop capability schema (`src/pbi/data/visual_capabilities.json`). The schema provides:
- **Per-visual-type object validation** — catches invalid objects (e.g., `categoryAxis` on `cardVisual`)
- **Property name validation** — catches typos with fuzzy suggestions (e.g., `showTitl` → `showTitle`)
- **Type-aware encoding** — bool/int/number/color/enum properties are encoded correctly (prevents silent PBI Desktop failures)
- **Auto-resolve** — YAML properties like `legend.show` transparently resolve to `chart:legend.show` when the schema confirms validity
- **Role supplementation** — `get_visual_roles()` merges handcrafted descriptions with schema data roles

Discovery: `pbi visual properties --visual-type <type>` shows all schema-derived properties. Regenerate with `schema-analysis/generate_compact_schema.py`.

## Engineering Rule

New write paths must be validated against the extracted PBI Desktop schema or derived from a canonical exported PBIR sample with test coverage. No guessing JSON structures.
