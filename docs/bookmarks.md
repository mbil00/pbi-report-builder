# Bookmarks

## Commands

```bash
pbi bookmark list
pbi bookmark get "Minimal View"
pbi bookmark get "Minimal View" --raw

pbi bookmark create "Overview State" "Sales Overview"
pbi bookmark create "Minimal View" "Sales Overview" --hide detailTable --hide filterPanel
pbi bookmark create "Layout Only" "Sales Overview" --no-capture-data

pbi bookmark set "Minimal View" --hide sidebar
pbi bookmark set "Minimal View" --show detailTable --show filterPanel

pbi bookmark delete "Minimal View" --force
```

## Capture Flags

Bookmark creation uses paired boolean flags:

- `--capture-data/--no-capture-data`
- `--capture-display/--no-capture-display`
- `--capture-page/--no-capture-page`

This matches the rest of the CLI's boolean convention.
