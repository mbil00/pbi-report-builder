# PBI CLI — Known Bugs & Schema Reference

## Authoritative PBIR JSON Schemas

Microsoft publishes the official PBIR schemas at:

**Repository:** https://github.com/microsoft/json-schemas/tree/main/fabric/item/report

### Key Schema Locations

| Schema | Path | Purpose |
|--------|------|---------|
| **Visual Container** | `definition/visualContainer/{version}/schema.json` | Top-level visual structure (position, groups, annotations) |
| **Visual Configuration** | `definition/visualConfiguration/{version}/schema-embedded.json` | Visual internals: `visualContainerObjects` (title, border, background, shadow, padding), `objects` (chart formatting: legend, axes, labels) |
| **Page** | `definition/page/{version}/schema.json` | Page properties, `objects` (background, outspace) |
| **Filter Configuration** | `definition/filterConfiguration/{version}/schema-embedded.json` | Filter structure at all levels |
| **Formatting Objects** | `definition/formattingObjectDefinitions/{version}/schema.json` | Shared formatting primitives (selectors, expressions) |

### Current Versions (as of 2026-03-13)

- Visual Container: `2.7.0`
- Visual Configuration: `2.3.0`
- Page: `2.0.0`
- Filter Configuration: `1.3.0`
- Formatting Object Definitions: `1.5.0`

### How to Use for Validation

Each `visual.json` and `page.json` file has a `$schema` field pointing to its schema.
Open any PBIR file in VS Code and it will validate against the schema automatically,
showing red squiggles for invalid properties.

---

## BUG-001: `title.show` writes invalid property `titleVisibility`

**Status:** Fixed (2026-03-13)
**Severity:** Breaking — reports fail to open in Power BI Desktop
**Found:** 2026-03-13

### Symptom

After running `pbi visual set <page> <visual> title.show=true`, Power BI Desktop
refuses to open the report:

```
Property 'titleVisibility' has not been defined and the schema does not allow
additional properties. Path
'visual.visualContainerObjects.title[0].properties.titleVisibility'
```

### Root Cause

`src/pbi/properties.py` line 72 maps `title.show` to `container_prop="titleVisibility"`.

The PBIR schema (`visualConfiguration/2.3.0/schema-embedded.json`) defines the `Title`
object with `additionalProperties: false` and these allowed properties:

```
show, text, heading, titleWrap, fontColor, background,
alignment, fontSize, bold, italic, underline, fontFamily
```

The correct property name is **`show`**, not `titleVisibility`.

### Fix

```python
# src/pbi/properties.py line 72
# WRONG:
container_prop="titleVisibility",
# CORRECT:
container_prop="show",
```

---

## BUG-002: `subtitle.show` writes invalid property `subTitleVisibility`

**Status:** Fixed (2026-03-13)
**Severity:** Breaking — same pattern as BUG-001
**Found:** 2026-03-13

### Root Cause

`src/pbi/properties.py` line 98: `container_prop="subTitleVisibility"`.

The `SubTitle` schema allows the same properties as `Title`:

```
show, text, heading, titleWrap, fontColor,
alignment, fontSize, bold, italic, underline, fontFamily
```

### Fix

```python
# src/pbi/properties.py line 98
# WRONG:
container_prop="subTitleVisibility",
# CORRECT:
container_prop="show",
```

---

## BUG-003: CLI `get` display may show wrong property label

**Status:** Fixed (2026-03-13)
**Severity:** Cosmetic

### Detail

When reading back a visual's properties, the CLI shows `title.titleVisibility`
in the output. After fixing BUG-001, verify that `_get_container_prop()` and the
display formatting read `show` correctly and display it as `title.show` in the
CLI output.

---

## Schema Reference: Allowed Properties by Container Object

These are the `visualContainerObjects` keys and their allowed properties per the
`visualConfiguration/2.3.0/schema-embedded.json` schema. Every object has
`additionalProperties: false` — **any unlisted property will break the report**.

### Title

```json
"Title": {
  "properties": {
    "show": {},
    "text": {},
    "heading": {},
    "titleWrap": {},
    "fontColor": {},
    "background": {},
    "alignment": {},
    "fontSize": {},
    "bold": {},
    "italic": {},
    "underline": {},
    "fontFamily": {}
  },
  "additionalProperties": false
}
```

### SubTitle

```json
"SubTitle": {
  "properties": {
    "show": {},
    "text": {},
    "heading": {},
    "titleWrap": {},
    "fontColor": {},
    "alignment": {},
    "fontSize": {},
    "bold": {},
    "italic": {},
    "underline": {},
    "fontFamily": {}
  },
  "additionalProperties": false
}
```

### Recommendation

To prevent future bugs of this kind, the CLI should validate property names against
the published schema definitions. Consider:

1. Embedding or fetching the schema definitions as a validation layer
2. Adding a test that round-trips every property in `VISUAL_PROPERTIES` and verifies
   the output JSON passes schema validation
3. Using VS Code schema validation during development to catch mismatches early

---

## Page Background Reference

The page `objects.background` uses this format (from working pages in the project):

```json
"objects": {
  "background": [
    {
      "properties": {
        "color": {
          "solid": {
            "color": {
              "expr": {
                "Literal": {
                  "Value": "'#F5F5F5'"
                }
              }
            }
          }
        },
        "transparency": {
          "expr": {
            "Literal": {
              "Value": "0D"
            }
          }
        }
      }
    }
  ]
}
```

Note: Color literals for `solid.color` use single-quoted hex strings (`'#F5F5F5'`),
while transparency uses the `D` (double) suffix (`"0D"`). Theme colors use
`ThemeDataColor` expressions instead of `Literal`.

Page background support has been added to the CLI (2026-03-13).

---

## BUG-004: `--measure` flag generates invalid selector format for per-measure styling

**Status:** Fixed (2026-03-13)
**Severity:** Breaking — reports fail schema validation in Power BI Desktop
**Found:** 2026-03-13

### Symptom

After running `pbi visual set <page> <visual> accentBar.color="#2E7D8C" --measure "Measures Table.Compliance Rate"`,
Power BI Desktop reports schema validation errors:

```
Invalid type. Expected Array but got Object.
Path 'visual.objects.accentBar[1].selector.data', line 165, position 21.
```

This repeats for every per-measure entry (indices 1–5 in a 5-measure card).

### Root Cause

The CLI's `--measure` flag generates this selector format:

```json
{
  "properties": {
    "color": "#2E7D8C"
  },
  "selector": {
    "data": {
      "dataViewWildcard": {
        "matchingOption": "InstancesAndTotals"
      }
    },
    "id": "Measures Table.Compliance Rate"
  }
}
```

**Two problems:**

1. **`selector.data` must be an array**, not an object. The schema defines `data` as an array type.
   The CLI writes `"data": { ... }` (object) instead of `"data": [{ ... }]` (array).

2. **The selector format itself is wrong for per-measure card formatting.** Working Power BI reports
   use `"selector": { "metadata": "Measures Table.Compliance Rate" }` — a simple string reference
   to the measure's query metadata. The `data`/`dataViewWildcard`/`id` pattern is for a different
   kind of selector entirely.

3. **Color values are not wrapped in expression format.** The CLI writes flat `"color": "#hex"`
   instead of the required `"solid": { "color": { "expr": { "Literal": { "Value": "'#hex'" } } } }`.

### Correct Format

Per-measure selectors should use the `metadata` pattern:

```json
{
  "properties": {
    "color": {
      "solid": {
        "color": {
          "expr": {
            "Literal": {
              "Value": "'#2E7D8C'"
            }
          }
        }
      }
    }
  },
  "selector": {
    "metadata": "Measures Table.Compliance Rate"
  }
}
```

The default entry (shared properties like `show`, `position`, `width`) uses `"selector": { "id": "default" }`.

### Workaround

Edit the visual JSON manually. Replace the CLI-generated `selector.data`/`selector.id` entries
with `selector.metadata` entries, and wrap color values in the proper `solid.color.expr.Literal.Value`
format. See the working KPI strips on the Device Estate and Security & Compliance pages for reference.

---

## Missing CLI Features — Manual JSON Edits Required

Most formatting capabilities originally documented here have since been implemented
in the CLI. The features below are the remaining gaps that still require manual JSON
editing or are not yet available.

### Previously documented features — now implemented

The following were documented as missing but are now supported. Use these CLI commands
instead of editing JSON directly:

| Feature | CLI Command |
|---------|-------------|
| Table formatting (grid, columnHeaders, values, total) | `pbi visual set ... grid.*`, `columnHeaders.*`, `values.*`, `total.*` |
| Card visual formatting (layout, accentBar, value, label, divider, shape, padding) | `pbi visual set ... layout.*`, `accentBar.*`, `cardValue.*`, `cardLabel.*`, `cardDivider.*`, `cardShape.*`, `cardPadding.*` |
| Per-measure selectors | `pbi visual set ... --measure "Table.Measure"` |
| Matrix/pivot table formatting (rowHeaders, subTotals) | `pbi visual set ... rowHeaders.*`, `subTotals.*` |
| Chart axis/label formatting (xAxis, yAxis, labels, legend) | `pbi visual set ... xAxis.*`, `yAxis.*`, `labels.*`, `legend.*` |
| Visual deletion | `pbi visual delete <page> <visual>` |
| Data binding (add/remove fields) | `pbi visual bind`, `pbi visual unbind` |
| Slicer formatting (header, items) | `pbi visual set ... slicerHeader.*`, `slicerItems.*`, `slicer.*` |

---

### FEAT-005: Theme management

**Status:** Implemented (2026-03-13)
**Priority:** Low — can be done via PBI Desktop UI

Implemented as `pbi theme list`, `pbi theme apply`, `pbi theme export`, `pbi theme remove`.

Previously: the CLI had no commands for theme management. Theme files are JSON files
that PBI Desktop manages via `report.json` → `themeCollection` + `resourcePackages`.

Useful CLI operations would be:
- `pbi theme apply <theme.json>` — copy theme to `StaticResources/RegisteredResources/`
  and update `report.json` references
- `pbi theme export` — extract current theme to a standalone JSON file
- `pbi theme list` — show active base and custom themes

Note: PBI Desktop overwrites `report.json` on save, so theme changes via file editing
only work when PBI Desktop is closed.

---

### FEAT-010: Batch/bulk visual operations

**Status:** Implemented (2026-03-13)
**Priority:** Medium — saves significant time when styling multiple visuals

When redesigning a full page, the same styling is often applied to many visuals
(e.g. all slicers get the same border/title/header styling). Currently each visual
must be targeted individually. The batch mode of `pbi visual set` helps for a single
visual but doesn't span multiple visuals.

Useful batch operations:

```bash
# Apply same property to all visuals of a type on a page
pbi visual set <page> --all-type=slicer border.radius=4 border.show=true title.fontSize=9

# Clone visual formatting from one visual to another
pbi visual copy-style <page> <source-visual> <target-visual>

# Apply a saved style preset
pbi visual apply-style <page> <visual> --preset card-container
```

This would dramatically reduce the effort needed for page redesigns. For the User Estate
page redesign, styling 6 identical slicers required writing 6 separate JSON files with
the same `visualContainerObjects` block. A batch command would have done it in one line.

---

### FEAT-011: Page template / page style preset

**Status:** Implemented (2026-03-13)
**Priority:** Low — nice-to-have for consistency across pages

When multiple pages share the same layout pattern (slicers → KPI strip → table → charts),
it would be useful to save and apply page templates:

```bash
# Save current page layout as a template
pbi page save-template <page> <template-name>

# Apply template to a new page (creates visuals with matching positions/styles)
pbi page apply-template <page> <template-name>
```
