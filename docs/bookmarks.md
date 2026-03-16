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

Bookmarks also integrate directly with reusable page templates and `pbi nav`:

```bash
# Save bookmarks with a reusable page template
pbi page template create "Executive Intro" corp-intro --global

# Wire a button to a bookmark
pbi nav set-bookmark "Sales Overview" toggleBtn "Minimal View"
```

## Capture Flags

Bookmark creation uses paired boolean flags:

- `--capture-data/--no-capture-data`
- `--capture-display/--no-capture-display`
- `--capture-page/--no-capture-page`

This matches the rest of the CLI's boolean convention.

## Template / YAML Notes

Bookmarks can be declared in apply-compatible YAML and are preserved when saving a page template. Page template application rewrites bookmark page references to the target page automatically.
