# Bookmarks

Bookmarks capture page state — active page, visual visibility, display states — as snapshots that can be restored by users or button actions.

## pbi bookmark list

```bash
pbi bookmark list
```

Table of all bookmarks with name, display name, active page, target visuals, and options.

## pbi bookmark show

```bash
pbi bookmark show <bookmark>                  # formatted overview
pbi bookmark show <bookmark> --raw            # full JSON
```

Bookmark is matched by name or display name (case-insensitive, partial match supported).

If a partial match is ambiguous, the CLI now fails instead of picking the first bookmark.

## pbi bookmark create

```bash
pbi bookmark create <display-name> <page> [options]
```

By default captures the active page and all visual states.

**Options:**

| Option | Description |
|--------|-------------|
| `--hide` | Visual names to mark as hidden (repeatable) |
| `--target` | Only apply bookmark to these visuals (repeatable) |
| `--no-data` | Don't capture data/filter state |
| `--no-display` | Don't capture display state |
| `--no-page` | Don't switch page when applying bookmark |

```bash
# Basic bookmark
pbi bookmark create "Overview State" "Sales Overview"

# Hide specific visuals
pbi bookmark create "Minimal View" "Sales" --hide detailTable --hide filterPanel

# Target-scoped bookmark (applies only to named visuals)
pbi bookmark create "Chart Focus" "Sales" --target revenueChart --target profitChart

# Bookmark that doesn't change filters
pbi bookmark create "Layout Only" "Sales" --no-data
```

## pbi bookmark update

Update visual visibility in an existing bookmark.

```bash
pbi bookmark update <bookmark> --hide <visual> [--hide <visual> ...]
pbi bookmark update <bookmark> --show <visual> [--show <visual> ...]
```

```bash
pbi bookmark update "Minimal View" --hide sidebar
pbi bookmark update "Minimal View" --show detailTable
pbi bookmark update "Full View" --show detailTable --show filterPanel
```

Visibility updates preserve unrelated bookmark state for the affected visual container instead of replacing it wholesale.

## pbi bookmark delete

```bash
pbi bookmark delete <bookmark>           # interactive confirmation
pbi bookmark delete <bookmark> -f        # skip confirmation
```

## File Structure

Bookmarks are stored in `definition/bookmarks/`:

```
definition/
  bookmarks/
    bookmarks.json                    # metadata (schema, items)
    a1b2c3d4e5.bookmark.json         # individual bookmark
    f6g7h8i9j0.bookmark.json
```

Each bookmark file (schema v2.1.0):

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmark/2.1.0/schema.json",
  "displayName": "Overview State",
  "name": "a1b2c3d4e5",
  "explorationState": {
    "version": "2.1",
    "activeSection": "page1",
    "sections": {
      "page1": {
        "visualContainers": {
          "detailTable": {
            "singleVisual": {
              "display": { "mode": "hidden" }
            }
          }
        }
      }
    }
  },
  "options": {
    "suppressData": false,
    "suppressDisplay": false,
    "applyOnlyToTargetVisuals": true,
    "targetVisualNames": ["revenueChart", "profitChart"]
  }
}
```

The `bookmarks.json` metadata tracks ordering with schema-defined `items`:

```json
{
  "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/bookmarksMetadata/1.0.0/schema.json",
  "items": [
    { "name": "a1b2c3d4e5" },
    { "name": "f6g7h8i9j0" }
  ]
}
```

## Using Bookmarks with Button Actions

Link a bookmark to a button for interactive toggling:

```bash
pbi visual create "Sales" actionButton -n toggleView -W 100 -H 30
pbi visual set "Sales" toggleView action.show=true action.type=Bookmark action.bookmark="Minimal View"
```
