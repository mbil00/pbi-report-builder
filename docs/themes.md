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
