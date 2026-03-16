# YAML Examples

Reference snippets for `pbi apply`. Each file demonstrates a specific feature. All snippets are valid YAML that can be applied directly with `pbi apply <file>`.

## Complete Example

- [complete-page.yaml](complete-page.yaml) — A full working page with multiple visual types, bindings, filters, styles, interactions, and bookmarks. Copy and adapt.

## Snippets by Feature

| File | Feature |
|------|---------|
| [visuals-basic.yaml](visuals-basic.yaml) | Common visual types: chart, table, card, slicer, shape |
| [bindings.yaml](bindings.yaml) | Data binding syntax: simple, multi-field, with display names and widths |
| [filters.yaml](filters.yaml) | Filter types: categorical, include, exclude, range, topN |
| [formatting.yaml](formatting.yaml) | Properties, chart objects, styles, per-measure formatting |
| [conditional-formatting.yaml](conditional-formatting.yaml) | Conditional formatting: measure, gradient, rules |
| [kpis.yaml](kpis.yaml) | KPI card shorthand: multi-metric cards, reference labels, accent bars |
| [interactions-bookmarks.yaml](interactions-bookmarks.yaml) | Visual interactions and bookmark definitions |
| [page-types.yaml](page-types.yaml) | Tooltip pages, drillthrough pages, hidden pages |

## Usage

```bash
# Apply any snippet (creates/updates the page)
pbi apply docs/yaml-examples/complete-page.yaml

# Preview changes first
pbi diff docs/yaml-examples/complete-page.yaml

# Dry run
pbi apply docs/yaml-examples/complete-page.yaml --dry-run
```

Adjust `name`, `bindings`, and field references (`Table.Field`) to match your semantic model.
