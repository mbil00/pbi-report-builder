# Bookmarks

## Commands

```bash
pbi bookmark list
pbi bookmark get "Minimal View"
pbi bookmark get "Minimal View" --raw

pbi bookmark create "Overview State" "Sales Overview"
pbi bookmark create "Minimal View" "Sales Overview" --hide detailTable --hide filterPanel
pbi bookmark create "Layout Only" "Sales Overview" --no-capture-data
pbi bookmark create "Rich View" "Sales Overview" --state-file ./bookmark-state.json --options-file ./bookmark-options.json

pbi bookmark set "Minimal View" --hide sidebar
pbi bookmark set "Minimal View" --show detailTable --show filterPanel
pbi bookmark set "Rich View" --page "Regional Detail" --target revenueChart --target detailTable
pbi bookmark set "Rich View" --no-capture-data --state-file ./bookmark-state.json

pbi bookmark group list
pbi bookmark group create "Main Views" "Overview State" "Minimal View"
pbi bookmark group delete "Main Views" --force

pbi bookmark delete "Minimal View" --force
```

Bookmarks also integrate directly with reusable page templates and `pbi nav`:

```bash
# Save bookmarks with a reusable page template
pbi page template create "Executive Intro" corp-intro --global

# Wire a button to a bookmark
pbi nav bookmark set "Sales Overview" toggleBtn "Minimal View"
```

## Capture Flags

Bookmark creation uses paired boolean flags:

- `--capture-data/--no-capture-data`
- `--capture-display/--no-capture-display`
- `--capture-page/--no-capture-page`

This matches the rest of the CLI's boolean convention.

`bookmark set` supports the same capture toggles, plus:

- `--page` to change the bookmark's active page
- `--target` / `--clear-targets` to control targeted visuals
- `--state-file` to merge richer `explorationState` JSON
- `--options-file` to merge extra bookmark `options` JSON

`bookmark list` and `bookmark get` also summarize richer captured state counts
(hidden visuals, sort state, filter state, projections, and object state) so
bookmark diffs are readable without dropping to raw JSON.

## Template / YAML Notes

Bookmarks can be declared in apply-compatible YAML and are preserved when saving a page template. Page template application rewrites bookmark page references to the target page automatically.

Bookmark groups are stored in `definition/bookmarks/bookmarks.json` and control bookmark ordering plus grouped presentation in Power BI.

Exported YAML now includes top-level `bookmarks:` entries for full report/page
exports. Common bookmark fields remain first-class (`page`, `hide`, `target`,
capture flags, `group`), and richer state round-trips through:

```yaml
bookmarks:
- name: Detailed View
  page: Demo
  group: Views
  hide: [table1]
  target: [table1]
  state:
    version: "1.0"
    sections:
      Demo:
        visualContainers:
          table1:
            orderBy:
              Direction: 2
            singleVisual:
              objects:
                title:
                  show: true
              projections:
                Values:
                - queryRef: Product.Category
  options:
    customFlag: true
```
