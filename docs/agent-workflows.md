# Agent Workflows

This guide is the shortest path for an agent to make reliable PBIR changes without fighting internal IDs or partial feature coverage.

## Recommended Order

1. Run `pbi info` or `pbi map` to understand the current report.
2. Prefer targeted schema-backed commands for small edits:
   - `pbi visual set`
   - `pbi visual bind`
   - `pbi filter add`
   - `pbi page set`
   - `pbi bookmark create/update`
3. Use `pbi page export` + `pbi apply` for larger declarative page reconstruction.
4. Run `pbi validate` after structural edits.
5. Run `pbi capabilities` when deciding whether a workflow is fully supported or still partial.

## Naming Strategy

Give visuals friendly names early.

```bash
pbi visual create "Sales" clusteredColumnChart --name revenueChart
pbi visual rename "Sales" 3 detailTable
```

Why:

- friendly names make later `visual`, `filter`, `bookmark`, and `interaction` commands deterministic
- unnamed visuals are still round-trippable because export includes stable visual IDs, but friendly names are easier for both humans and agents
- template application now keeps names unique, but meaningful names are still better than generated suffixes

## Export / Apply Workflow

Use this for page-level reconstruction, bulk layout edits, or when an agent needs a human-readable spec.

```bash
pbi page export "Sales Overview" -o sales.yaml
pbi apply sales.yaml --page "Sales Overview"
```

Notes:

- export includes stable visual `id` values so re-apply updates the same visuals
- export may include a raw `pbir` block for each visual to preserve unsupported or selector-heavy PBIR details
- high-level YAML fields still override the raw payload where supported:
  - `position`
  - `size`
  - `isHidden`
  - `bindings`
  - `sort`
  - `filters`
- use `pbi apply --dry-run` before larger imports

## Overwrite Mode

Use overwrite only when the YAML should fully define the page.

```bash
pbi apply sales.yaml --page "Sales Overview" --overwrite
```

Behavior:

- visuals missing from the YAML are removed
- a backup YAML file is written for each affected page
- failed overwrite applies now roll back the PBIR definition automatically

## Templates vs Exported YAML

Use templates when you want reusable layout/style scaffolds without data.

```bash
pbi page save-template "Sales Overview" sales-layout
pbi page apply-template "Q2 Sales" sales-layout
```

Templates keep:

- page size
- page objects
- visual positions
- visual types
- formatting
- hidden flags

Templates do not keep:

- bindings
- sort
- filters

Template names must be file-safe and stay inside `.pbi-templates`.

## Filters

Prefer `pbi filter add` and `pbi filter tuple` over manual JSON edits.

Supported schema-backed filter families:

- categorical
- include
- exclude
- tuple
- range
- Top N
- relative date
- relative time

Useful patterns:

```bash
pbi filter add Product.Category --values "Bikes,Accessories" --mode include
pbi filter add Sales.Revenue --min 1000 --max 50000 --locked
pbi filter add Customers.Region --topn 5 --topn-by Sales.TotalRevenue
pbi filter tuple "Product.Color=Red,Product.Size=Large"
```

`pbi filter list` now shows filter names as well as field references. That matters for tuple or generated filters.

`Passthrough` is still not implemented because the project does not have a canonical exported PBIR sample for it.

## Bookmarks and Interactions

Preferred pattern:

```bash
pbi bookmark create "Minimal View" "Sales" --hide detailTable
pbi bookmark update "Minimal View" --show detailTable
pbi interaction set "Sales" regionSlicer revenueChart NoFilter
pbi interaction set "Sales" regionSlicer revenueChart Default
```

Notes:

- bookmark lookup supports exact and partial matching, but ambiguous matches now fail instead of picking the first result
- bookmark visibility updates preserve other bookmark state
- interaction type `Default` removes the custom override instead of persisting a fake `"Default"` interaction row

## Drillthrough and Tooltip Pages

Configure these with page commands, then point visuals/buttons at them with normal property writes.

```bash
pbi page set-drillthrough "Product Details" Product.Category
pbi page set-tooltip "Sales Tooltip" Product.Category -W 400 -H 300
```

When a semantic model is present, field references are resolved to canonical PBIR entity/property names before writing the page binding.

## When To Use Raw PBIR

Use exported `pbir` payloads when:

- the visual contains selector-heavy formatting that the named property registry does not model
- the visual type is only sample-backed
- you need full-fidelity round-trip preservation

Prefer schema-backed commands when:

- the change is already represented by a CLI command
- you want the agent to reason at the level of fields, properties, filters, bookmarks, or interactions instead of raw JSON nodes

## Validation Loop

After any significant batch of changes:

```bash
pbi validate
pbi page export "Sales Overview" -o verify.yaml
```

Use `pbi validate` for structural issues and `page export` to inspect the normalized state the CLI can round-trip.
