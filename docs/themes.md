# Themes

Themes control the default color palette, fonts, and visual formatting across the entire report. A project has a base theme (built-in) and optionally a custom theme (JSON file).

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
