# Validation & Structure

## pbi validate

Check project files for structural errors without requiring external schema downloads.

```bash
pbi validate
pbi validate -p /path/to/project
```

Exit code 0 if no errors (warnings are OK), exit code 1 if errors found.

### What it checks

**Report-level:**
- `report.json` exists and is valid JSON
- `$schema` field present

**Pages:**
- `pages.json` metadata: pageOrder references match actual page directories
- Page directories not listed in pageOrder are flagged
- Each `page.json`: valid JSON, `$schema`, `displayName`, valid dimensions
- Drillthrough/tooltip pages: `pageBinding` present and type-consistent

**Visuals:**
- Each `visual.json`: valid JSON, `$schema`, `name`, `position`
- Must have either `visual` or `visualGroup` key (not both, not neither)
- `visual.visualType` present
- `visualContainerObjects` entries are arrays of objects with `properties` keys
- `visual.objects` entries are arrays
- `parentGroupName` is a string if present

**Interactions:**
- Visual interaction source/target names reference existing visuals on the page
- Interaction types are valid (`DataFilter`, `HighlightFilter`, `NoFilter`, `Default`)

**Bookmarks:**
- Each `.bookmark.json`: valid JSON, `$schema`
- Required fields: `displayName`, `name`, `explorationState`
- `explorationState.activeSection` present

**Layout:**
- Visuals with zero or negative width/height
- Visuals extending past page bounds (x+width > page width, y+height > page height, 5px tolerance)
- Overlapping visuals (bounding box intersection > 10px in both axes)

**Model relationships:**
- Visuals referencing fields from multiple tables that have no relationship path in the semantic model
- Only warns if the model has a `relationships.tmdl` file (skipped otherwise)

### Output

```
2 error(s):
  ERROR pages/page1/page.json: Page type is 'Drillthrough' but pageBinding is missing
  ERROR pages/page1/visuals/abc123/visual.json: Missing name field

1 warning(s):
  WARN  definition/report.json: Missing $schema field
```

## PBIR File Structure

The PBIR (Enhanced Report Format) stores each element as a separate JSON file:

```
MyReport.pbip                           # project file
MyReport.Report/
  definition/
    report.json                         # report settings, theme references
    pages/
      pages.json                        # page ordering metadata
      page1/
        page.json                       # page settings (name, size, type, filters)
        visuals/
          a1b2c3/
            visual.json                 # visual definition (type, bindings, formatting)
          d4e5f6/
            visual.json
      page2/
        page.json
        visuals/
          ...
    bookmarks/
      bookmarks.json                    # bookmark ordering metadata
      abc123.bookmark.json              # individual bookmark state
    themes/
      theme.json                        # custom theme (if applied)
SemanticModel/
  definition/
    tables/
      Sales.tmdl                        # table definitions (columns, measures)
      Product.tmdl
    model.tmdl                          # model-level settings
```

### Key files

| File | Contains |
|------|----------|
| `report.json` | Report schema, theme references, report-level filters |
| `pages.json` | `pageOrder` array, `activePageName` |
| `page.json` | `displayName`, `width`, `height`, `type`, `visibility`, `pageBinding`, `filterConfig`, `visualInteractions` |
| `visual.json` | `name`, `position`, `visual` (type, bindings, objects, containerObjects) or `visualGroup` |
| `bookmarks.json` | `items` array of bookmark/group metadata |
| `*.bookmark.json` | `displayName`, `name`, `explorationState`, `options` |

### Static vs Conditional Formatting

Visual formatting can be either static or conditional:

- **Static**: Fixed values set via `pbi visual set` — stored as literal expressions in `visual.objects` or `visualContainerObjects`
- **Conditional**: Dynamic values driven by measures or gradients, set via `pbi visual format` — stored as `FillRule` or measure-reference expressions in the same objects

Both can coexist on the same visual. Conditional formatting on a property overrides the static value at runtime.
