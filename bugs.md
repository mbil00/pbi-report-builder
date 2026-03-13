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

**Status:** Partially fixed (2026-03-13) — color encoding fixed via BUG-010; selector format already uses correct `metadata` pattern
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

## BUG-005: `pbi visual column` shows `?.?` for Aggregation fields

**Status:** Fixed (2026-03-13)
**Severity:** Cosmetic — renaming by index still works
**Found:** 2026-03-13

### Symptom

When listing columns on a table or pivot that contains `Aggregation` fields (e.g. `Sum(...)`,
`Min(...)`, `Count(...)`), the CLI displays `?.?` for both the field reference and display name:

```
  #     Field                      Display Name    Type     Width   Formatting
 ──────────────────────────────────────────────────────────────────────────────
  1     LicenseUtilization.SkuP…   SkuPartNumber   column     200   -
  2     ?.?                        ?               column      90   -
  3     ?.?                        ?               column      90   -
```

Column operations by index (`pbi visual column ... 2 --rename "Enabled"`) work correctly,
but referencing these columns by field name fails since the CLI can't resolve them.

### Root Cause

The column listing logic only handles `Column` and `Measure` field types when resolving
projection references. Fields of type `Aggregation` (which wrap a `Column` in a `Function`
like Sum=0, Min=5, Count=3, etc.) are not recognized, so their `Entity.Property` and
`nativeQueryRef` are not extracted.

### Expected Behavior

Aggregation fields should display their `nativeQueryRef` (e.g. `Sum of EnabledUnits`) or
`queryRef` (e.g. `Sum(LicenseUtilization.EnabledUnits)`) as the field reference, and their
`nativeQueryRef` or `displayName` as the display name. The CLI should also allow referencing
these columns by their `queryRef` string for `--rename`, `--width`, etc.

### Affected Visuals

Any `tableEx` or `pivotTable` containing aggregation columns — common in licensing, usage,
and summary tables. Example: the Licensing & M365 Usage page has 12 aggregation columns
across 3 visuals that all show as `?.?`.

---

## BUG-006: `pbi page set` writes malformed JSON for page background

**Status:** Fixed (2026-03-13) — `page set` now supports batch `prop=value` syntax
**Severity:** Breaking — page.json becomes invalid, report may fail to load
**Found:** 2026-03-13
**Reproduced:** Twice (Licensing & M365 Usage page, Software Inventory page)

### Symptom

Running `pbi page set "Software Inventory" background.color="#F5F5F5" background.transparency=0`
writes this to page.json:

```json
"background": {
  "color=#F5F5F5": "background.transparency=0"
}
```

This is a flat key-value string — not valid PBIR format. The CLI appears to be concatenating
the `key=value` arguments into a string instead of building the nested expression structure.

### Expected Output

The correct PBIR format for page background is inside `objects.background`:

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

### Root Cause

The `pbi page set` command does not handle the page `objects` structure. Page-level objects
(background, outspacePane) live inside `page.json → objects`, using the same expression format
as visual objects. The CLI currently writes to a top-level `background` key instead of into
`objects.background[]`, and does not wrap values in the PBIR expression format.

### Workaround

Edit page.json manually. Remove the broken `background` key and add the correct
`objects.background` array.

---

## BUG-007: Card visual `pbi visual create` produces minimal layout — causes text clipping

**Status:** Fixed (2026-03-13) — cardVisual create now generates full scaffold with multi-entry objects
**Severity:** High — KPI strips created via CLI have clipped/unreadable text
**Found:** 2026-03-13

### Symptom

Card visuals created via `pbi visual create` (and subsequently styled with `pbi visual set`)
produce a minimal `objects.layout` with only `style`, `columnCount`, and `calloutSize`.
The resulting card visual has text that clips to the bottom and is unreadable, particularly
in KPI strip configurations (short height, multiple measures).

This was observed on the Security & Compliance and Licensing & M365 Usage KPI strips, both
built via CLI. The Device Estate and User Estate KPI strips (built in Power BI Desktop) render
correctly because they have a much richer layout structure.

### Root Cause

The CLI sets layout properties individually, but a working card visual requires **multiple
array entries** in several object types, with different selectors:

**Missing objects entirely** (CLI has no property mappings for these):
- `shapeCustomRectangle` — rounded card tiles (`rectangleRoundedCurve`, `tileShape`)
- `overFlow` — controls text overflow behavior (`overFlowStyle: 1D`, `overFlowDirection: 0D`)
- `shadowCustom` — card-level shadow (inside `objects`, separate from container `dropShadow`)
- `border` (inside `objects`) — card-level border (separate from container `border`)
- `padding` (inside `objects`) — card-level `paddingUniform` (separate from container `padding`)

**Missing properties in `layout`:**
- `autoGrid`, `alignment`, `contentOrder`, `orientation`, `cellPadding` — all absent
- Only one `layout` array entry when the working format requires **two**: one for the grid
  settings (no selector) and one for per-card settings (`{"selector": {"id": "default"}}`)
  with `paddingUniform` and `backgroundShow`

**Missing structure in `value`:**
- Only one `value` entry when the working format requires multiple: a `show` entry, a
  `horizontalAlignment`+`fontSize` entry (with `{"selector": {"id": "default"}}`), and
  per-measure `labelDisplayUnits` entries (each with `{"selector": {"metadata": "..."}}`
  using the numeric `1D` format, not the string `'1'`)

**Missing selectors on `divider` and `label`:**
- These need `{"selector": {"id": "default"}}` which the CLI omits

### Correct Layout Format

See the Device Estate KPI strip for the complete working structure:
`pages/4b4331154ee80a15c346/visuals/12d04b96672712dea0ee/visual.json`

Key objects and their entries:

```
objects.shapeCustomRectangle[0]  → rectangleRoundedCurve=5L, tileShape  (selector: default)
objects.padding[0]               → paddingUniform=7L                     (selector: default)
objects.layout[0]                → calloutSize, autoGrid, alignment=middle, contentOrder,
                                   columnCount, style=Cards, orientation=2D, cellPadding=8L
objects.layout[1]                → paddingUniform=6L, backgroundShow=false (selector: default)
objects.divider[0]               → show=true                             (selector: default)
objects.value[0]                 → show=true                             (no selector)
objects.value[1]                 → horizontalAlignment=center, fontSize  (selector: default)
objects.value[2..N]              → labelDisplayUnits=1D                  (selector: metadata per measure)
objects.label[0]                 → show=true, fontSize=10D               (selector: default)
objects.overFlow[0]              → overFlowStyle=1D, overFlowDirection=0D
objects.border[0]                → show=false                            (selector: default)
objects.shadowCustom[0]          → show=false                            (selector: default)
```

### Suggested Fix

When creating a `cardVisual` with `pbi visual create`, generate the full layout
structure (all objects above with correct selectors) instead of the minimal version.
Alternatively, add CLI properties for the missing objects so they can be set via
`pbi visual set`.

---

## BUG-009: `pbi visual set` writes some properties at document root instead of `visual.objects`

**Status:** Fixed (2026-03-13) — unknown properties now raise error instead of writing to raw path
**Severity:** Breaking — report fails schema validation, visuals won't render
**Found:** 2026-03-13

### Symptom

After styling a table with multiple `pbi visual set` calls, Power BI Desktop reports:

```
Property 'grid' has not been defined and the schema does not allow additional properties.
Path 'grid', line 547, position 9.
Property 'values' has not been defined and the schema does not allow additional properties.
Path 'values', line 553, position 11.
```

### Root Cause

When setting properties on a visual that **had no prior `objects` section** (brand new /
unstyled visual), the CLI splits the properties across two locations:

1. Some properties go into `visual.objects` correctly (e.g. `grid.rowPadding`,
   `grid.textSize`, `values.fontSize`, `columnHeaders.*`)
2. Other properties from the **same objects** get written as **flat key-value pairs at
   the document root** — outside the `visual` wrapper entirely:

```json
{
  "$schema": "...",
  "name": "tableDeviceApps",
  "position": { ... },
  "visual": {
    "objects": {
      "grid": [{ "properties": { "rowPadding": ..., "textSize": ... } }],
      "values": [{ "properties": { "fontSize": ..., "fontFamily": ... } }]
    }
  },
  "grid": {                          // ← WRONG: at document root
    "gridVertical": false,
    "gridHorizontal": true,
    "gridHorizontalColor": "#EDEBE9",
    "gridHorizontalWeight": 1
  },
  "values": {                        // ← WRONG: at document root
    "fontColorPrimary": "#323130",
    "backColorPrimary": "#FFFFFF",
    "backColorSecondary": "#F8F8F8"
  }
}
```

The split seems related to the property type: non-color properties go to `visual.objects`
with correct expression format, while color-based properties (`gridHorizontalColor`,
`fontColorPrimary`, `backColorPrimary`, `backColorSecondary`) and boolean grid properties
get written at the root without expression wrappers.

### Affected Properties

Observed on `tableEx` visuals. Properties that end up at root level:
- `grid.gridVertical`, `grid.gridHorizontal`, `grid.gridHorizontalColor`, `grid.gridHorizontalWeight`
- `values.fontColorPrimary`, `values.backColorPrimary`, `values.backColorSecondary`

### Workaround

After using the CLI, manually verify that no top-level keys were added outside the
`visual` object. Move them into `visual.objects` and wrap values in expression format.

---

## BUG-010: Color values written without PBIR expression wrapper

**Status:** Fixed (2026-03-13) — `encode_pbi_value("color")` now wraps in `expr.Literal.Value`
**Severity:** May cause validation errors or silent rendering failures
**Found:** 2026-03-13

### Symptom

When setting color properties via `pbi visual set`, the CLI writes some colors as:

```json
"fontColor": {
  "solid": {
    "color": "#FFFFFF"
  }
}
```

Instead of the correct PBIR expression format:

```json
"fontColor": {
  "solid": {
    "color": {
      "expr": {
        "Literal": {
          "Value": "'#FFFFFF'"
        }
      }
    }
  }
}
```

Note two differences:
1. Missing `expr.Literal.Value` wrapper around the color string
2. Missing single quotes inside the value (`'#FFFFFF'` not `#FFFFFF`)

### Affected Properties

Observed on these properties when set via CLI on previously-unstyled visuals:
- `columnHeaders.fontColor`, `columnHeaders.backColor`
- `total.fontColor`, `total.backColor`
- `grid.gridHorizontalColor` (when written to document root per BUG-009)

Properties that **are** written correctly (with expression wrapper):
- `values.fontSize`, `values.fontFamily`, `columnHeaders.fontSize`, `grid.textSize`, etc.
- All non-color literal values (booleans, numbers, strings)

### Impact

Power BI Desktop may still load these, but they may render incorrectly or cause
validation warnings. They also break strict schema validation.

---

## BUG-008: `pbi visual set-all` output does not show property changes

**Status:** Fixed (2026-03-13) — Rich markup brackets removed from output string
**Severity:** Cosmetic
**Found:** 2026-03-13

### Symptom

Running `pbi visual set-all "Software Inventory" border.show=true border.radius=4 --type slicer`
outputs only:

```
Applied  to 4 visuals (type=slicer)
```

Note the empty space between "Applied" and "to" — the property summary is missing. The individual
`pbi visual set` command correctly shows before/after values for each property, but `set-all`
does not.

### Expected Output

Should show which properties were set and their values, similar to:

```
Applied border.show=true border.radius=4 to 4 visuals (type=slicer)
```

Or per-visual output like:
```
slicerPlatform:  border.show: None → True, border.radius: None → 4.0
slicerPublisher: border.show: None → True, border.radius: None → 4.0
...
```

---

## CLI Gaps — Features That Still Require Manual JSON Editing

### GAP-001: Multi-entry object arrays with different selectors

~~The CLI can't create multi-entry object arrays with different selectors~~ — Fixed.
PropertyDef now supports a `selector` field ("default" for `{"id": "default"}`).
`_set_container_prop` routes writes to the correct entry based on the selector.
Card visual properties updated with correct selectors.

### GAP-002: Chart-level objects not exposed as properties

~~Missing property mappings for chart-level objects~~ — Fixed.
Added CLI properties for:
- `cardShape.*` → `shapeCustomRectangle` (tile shape, rounding, color)
- `cardOverflow.*` → `overFlow` (style, direction)
- `cardShadow.*` → `shadowCustom` (show)
- `cardBorder.*` → `border` inside objects (show)
- `cardPadding.*` → `padding` inside objects (uniform, top/bottom/left/right)

### GAP-003: Page-level object properties

~~`pbi page set` cannot set page `objects` properties~~ — Fixed via BUG-006.
Page background and outspace properties now work via batch syntax:
`pbi page set "Sales" background.color="#F5F5F5" background.transparency=0`

---

## Previously Implemented Features

Most formatting capabilities originally documented here have since been implemented.
See the docs for current CLI commands:
- [visuals.md](visuals.md) — visual CRUD, set, set-all, paste-style, sort, format, column
- [properties.md](properties.md) — all visual/container properties reference
- [pages.md](pages.md) — page CRUD, templates, drillthrough, tooltip
- [data.md](data.md) — data binding, semantic model, filters
- [interactions.md](interactions.md) — visual interactions, button actions
- [bookmarks.md](bookmarks.md) — bookmark management
- [themes.md](themes.md) — theme apply/export/remove
- [validation.md](validation.md) — validation, PBIR file structure
