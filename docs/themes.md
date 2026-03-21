# Themes

Themes control the default color palette, fonts, and visual formatting across the entire report. A project has a base theme (built-in) and optionally a custom theme (JSON file).

Theme defaults sit below explicit report/page/visual overrides. In the YAML round-trip workflow, `theme:` is applied before `report:`, page, and visual sections so later overrides can intentionally win.

## pbi theme list

```bash
pbi theme list
```

Shows active themes (base + custom) with their name and source.

## pbi theme apply

Apply a custom theme JSON file to the project. The file is copied into the report definition.

```bash
pbi theme apply <theme-file>
```

```bash
pbi theme apply ./corporate-theme.json
pbi theme apply /path/to/dark-theme.json
```

The theme file must be valid JSON following the Power BI theme schema. At minimum it should have a `name` field.

## pbi theme export

Export the active custom theme to a standalone JSON file.

```bash
pbi theme export <output-path>
```

```bash
pbi theme export ./exported-theme.json
```

## pbi theme delete

Remove the custom theme, reverting to the base theme only.

```bash
pbi theme delete
```

## pbi theme migrate

Migrate per-visual color overrides from an old theme to a new theme. Compares the two theme JSONs to build a color mapping, then scans all visuals and pages for properties matching old colors and replaces them with new colors.

```bash
pbi theme migrate <old-theme> <new-theme>
pbi theme migrate <old-theme> <new-theme> --dry-run
```

```bash
# Preview what would change
pbi theme migrate ./old-corporate.json ./new-corporate.json --dry-run
# Output:
# (dry run) Would update #2E7D8C -> #162F38 on 8 visual(s)
# (dry run) Would update #EDEBE9 -> #DDD6CC on 45 visual(s)
# (dry run) Would update background.color on 9 page(s)

# Apply the migration
pbi theme migrate ./old-corporate.json ./new-corporate.json
```

This is essential after applying a new theme, because visuals with per-visual property overrides (explicit colors set via `pbi visual set` or YAML) keep their old colors. `migrate` replaces those overrides with the new theme's colors.

## pbi theme style

Theme `visualStyles` can be inspected and edited directly.

```bash
pbi theme style list
pbi theme style get columnChart
pbi theme style get columnChart --role Series
pbi theme style get columnChart --all-roles
pbi theme style set columnChart legend.show=true
pbi theme style set columnChart --role Series 'legend.complex={"expr":{"ThemeDataColor":{"ColorId":2}}}'
pbi theme style delete columnChart --role Series --force
```

Notes:

- `--role` targets one `visualStyles[visualType][role]` branch. The default branch is `*`.
- `--all-roles` expands inspection across every branch for the visual type.
- Values may be plain scalars (`true`, `12`, `RightCenter`) or inline JSON for complex nested payloads.
- `--raw` dumps the underlying JSON structure instead of the flattened table view.

## pbi theme format

Theme conditional formatting uses the same `measure`, `gradient`, and `rules` vocabulary as `pbi visual format`, but writes the defaults into theme `visualStyles`.

```bash
pbi theme format get
pbi theme format get columnChart --json
pbi theme format set columnChart dataPoint.fill \
  --mode gradient \
  --source Sales.SalesAmount \
  --min-color "#FFF7E6" --min-value 0 \
  --max-color "#C50F1F" --max-value 5000
pbi theme format clear columnChart dataPoint.fill --force
```

Notes:

- `--role` targets a specific `visualStyles` role branch.
- `--selector` targets a specific `$id` entry inside the object array.
- `theme format` is the author-friendly path for conditional formatting; `theme style` remains the low-level escape hatch for arbitrary JSON shapes.

## YAML `theme:` round-trip

`pbi export`, `pbi apply`, and `pbi diff` now support a top-level `theme:` section for the active custom theme.

```yaml
version: 1
theme:
  name: Corporate
  visualStyles:
    columnChart:
      Series:
        legend:
          - complex:
              expr:
                ThemeDataColor:
                  ColorId: 2
pages:
  - name: Demo
```

Rules:

- Full-report export includes `theme:` when a custom theme is applied.
- Page-only export omits `theme:`.
- `pbi apply` creates a custom theme on the target project if needed, then merges the YAML section into it.
- `pbi diff` reports theme changes as `theme.<path>`.

## Theme JSON Structure

A Power BI theme JSON file contains color palette, visual defaults, and text formatting:

```json
{
  "name": "Corporate Theme",
  "dataColors": ["#003D6A", "#4CAF50", "#E8A83E", "#D64554", "#8E44AD", "#2980B9"],
  "background": "#FFFFFF",
  "foreground": "#333333",
  "tableAccent": "#003D6A",
  "visualStyles": {
    "*": {
      "*": {
        "title": [{ "properties": { "fontFamily": { "expr": { "Literal": { "Value": "'Segoe UI'" } } } } }]
      }
    }
  }
}
```

Key theme properties:

| Property | Description |
|----------|-------------|
| `name` | Theme display name |
| `dataColors` | Array of hex colors for data series |
| `background` | Default background color |
| `foreground` | Default text color |
| `tableAccent` | Accent color for tables and highlights |
| `visualStyles` | Per-visual-type formatting defaults |
