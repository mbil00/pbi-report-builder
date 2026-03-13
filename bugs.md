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

## Missing CLI Features — Manual JSON Edits Required

The following formatting capabilities are not yet supported by the CLI and required
direct editing of `visual.json` files. These are candidates for new CLI commands.

### FEAT-001: Table visual formatting (`tableEx` objects)

**Status:** Implemented (2026-03-13)
**Priority:** High — tables are in nearly every report

The `tableEx` visual type supports these formatting object groups in `visual.objects`:

#### `grid` — Row/gridline formatting

```json
"grid": [{
  "properties": {
    "gridVertical": { "expr": { "Literal": { "Value": "false" } } },
    "gridHorizontal": { "expr": { "Literal": { "Value": "true" } } },
    "gridHorizontalColor": { "solid": { "color": { "expr": { "Literal": { "Value": "'#EDEBE9'" } } } } },
    "gridHorizontalWeight": { "expr": { "Literal": { "Value": "1D" } } },
    "rowPadding": { "expr": { "Literal": { "Value": "3D" } } },
    "textSize": { "expr": { "Literal": { "Value": "9D" } } }
  }
}]
```

**Properties:** `gridVertical` (bool), `gridHorizontal` (bool), `gridHorizontalColor` (color),
`gridHorizontalWeight` (double), `gridVerticalColor` (color), `gridVerticalWeight` (double),
`rowPadding` (double), `textSize` (double), `imageHeight` (double)

#### `columnHeaders` — Header row formatting

```json
"columnHeaders": [{
  "properties": {
    "fontColor": { "solid": { "color": { "expr": { "Literal": { "Value": "'#FFFFFF'" } } } } },
    "backColor": { "solid": { "color": { "expr": { "Literal": { "Value": "'#2E7D8C'" } } } } },
    "fontSize": { "expr": { "Literal": { "Value": "9D" } } },
    "fontFamily": { "expr": { "Literal": { "Value": "'Segoe UI Semibold'" } } },
    "wordWrap": { "expr": { "Literal": { "Value": "false" } } }
  }
}]
```

**Properties:** `fontColor` (color), `backColor` (color), `fontSize` (double),
`fontFamily` (string), `wordWrap` (bool), `alignment` (string), `outline` (string)

#### `values` — Data row formatting

```json
"values": [{
  "properties": {
    "fontColor": { "solid": { "color": { "expr": { "Literal": { "Value": "'#323130'" } } } } },
    "backColor": { "solid": { "color": { "expr": { "Literal": { "Value": "'#FFFFFF'" } } } } },
    "backColorAlternate": { "solid": { "color": { "expr": { "Literal": { "Value": "'#F8F8F8'" } } } } },
    "fontSize": { "expr": { "Literal": { "Value": "8D" } } },
    "fontFamily": { "expr": { "Literal": { "Value": "'Segoe UI'" } } },
    "wordWrap": { "expr": { "Literal": { "Value": "false" } } },
    "urlIcon": { "expr": { "Literal": { "Value": "true" } } }
  }
}]
```

**Properties:** `fontColor` (color), `backColor` (color), `backColorAlternate` (color),
`fontSize` (double), `fontFamily` (string), `wordWrap` (bool), `urlIcon` (bool),
`alignment` (string), `outline` (string)

#### `total` — Totals row formatting

```json
"total": [{
  "properties": {
    "fontColor": { "solid": { "color": { "expr": { "Literal": { "Value": "'#323130'" } } } } },
    "backColor": { "solid": { "color": { "expr": { "Literal": { "Value": "'#E8F5F7'" } } } } },
    "fontSize": { "expr": { "Literal": { "Value": "9D" } } },
    "fontFamily": { "expr": { "Literal": { "Value": "'Segoe UI Semibold'" } } }
  }
}]
```

**Properties:** Same as `values` minus `backColorAlternate` and `urlIcon`.

#### Suggested CLI syntax

```bash
# Table grid
pbi visual set <page> <visual> grid.gridHorizontal=true
pbi visual set <page> <visual> grid.rowPadding=3

# Column headers
pbi visual set <page> <visual> columnHeaders.backColor=#2E7D8C
pbi visual set <page> <visual> columnHeaders.fontColor=#FFFFFF

# Values / alternating rows
pbi visual set <page> <visual> values.backColorAlternate=#F8F8F8

# Totals
pbi visual set <page> <visual> total.backColor=#E8F5F7
```

---

### FEAT-002: Card visual formatting (`cardVisual` objects)

**Status:** Implemented (2026-03-13)
**Priority:** High — cards/KPIs are in nearly every report

The `cardVisual` visual type supports these formatting object groups in `visual.objects`:

#### `layout` — Card arrangement

```json
"layout": [{
  "properties": {
    "style": { "expr": { "Literal": { "Value": "'Cards'" } } },
    "columnCount": { "expr": { "Literal": { "Value": "5L" } } },
    "calloutSize": { "expr": { "Literal": { "Value": "16D" } } }
  }
}]
```

**Properties:** `style` (string: `'Cards'`|`'Callout'`), `columnCount` (long),
`calloutSize` (double)

#### `accentBar` — Colored accent bars per card

Supports **per-measure selectors** using `selector.data.dataViewWildcard.matchingOption`:

```json
"accentBar": [
  {
    "properties": {
      "show": { "expr": { "Literal": { "Value": "true" } } },
      "color": { "solid": { "color": { "expr": { "Literal": { "Value": "'#4CAF50'" } } } } }
    }
  },
  {
    "properties": {
      "color": { "solid": { "color": { "expr": { "Literal": { "Value": "'#E8A83E'" } } } } }
    },
    "selector": {
      "data": {
        "dataViewWildcard": {
          "matchingOption": "InstancesAndTotals"
        }
      },
      "id": "<queryRef of the specific measure>"
    }
  }
]
```

**Properties:** `show` (bool), `color` (color)

#### `divider` — Separator line between cards

```json
"divider": [{
  "properties": {
    "show": { "expr": { "Literal": { "Value": "true" } } },
    "color": { "solid": { "color": { "expr": { "Literal": { "Value": "'#EDEBE9'" } } } } },
    "width": { "expr": { "Literal": { "Value": "1D" } } }
  }
}]
```

#### `value` / `label` — Callout and label formatting

```json
"value": [{
  "properties": {
    "fontSize": { "expr": { "Literal": { "Value": "18D" } } },
    "bold": { "expr": { "Literal": { "Value": "true" } } },
    "fontFamily": { "expr": { "Literal": { "Value": "'Segoe UI Semibold'" } } }
  }
}]
```

```json
"label": [{
  "properties": {
    "show": { "expr": { "Literal": { "Value": "true" } } },
    "fontSize": { "expr": { "Literal": { "Value": "9D" } } },
    "fontFamily": { "expr": { "Literal": { "Value": "'Segoe UI'" } } }
  }
}]
```

#### Other cardVisual objects

- `shapeCustomRectangle` — card background shape (color, radius, transparency)
- `overFlow` — text overflow behaviour (`overflow` property)
- `padding` (card-internal) — inner padding per card cell

#### Suggested CLI syntax

```bash
# Layout
pbi visual set <page> <visual> layout.style=Cards
pbi visual set <page> <visual> layout.columnCount=5

# Accent bar (default)
pbi visual set <page> <visual> accentBar.show=true
pbi visual set <page> <visual> accentBar.color=#4CAF50

# Accent bar per measure (needs new selector syntax)
pbi visual set <page> <visual> accentBar.color=#E8A83E --measure "Stale Devices 30d"

# Divider
pbi visual set <page> <visual> divider.show=true

# Value / Label
pbi visual set <page> <visual> value.fontSize=18
pbi visual set <page> <visual> label.show=true
```

---

### FEAT-003: Per-measure selectors for formatting objects

**Status:** Implemented (2026-03-13)
**Priority:** Medium — needed for multi-measure cards and conditional formatting

Some formatting objects (like `accentBar` in cardVisuals) support per-measure selectors,
allowing different formatting for each measure in a multi-measure visual. This requires
a `selector` block referencing a specific measure's `queryRef`:

```json
{
  "properties": { ... },
  "selector": {
    "data": {
      "dataViewWildcard": {
        "matchingOption": "InstancesAndTotals"
      }
    },
    "id": "Sum(Devices.StaleDevices30d)"
  }
}
```

The CLI currently has no way to target a specific measure when setting formatting properties.

#### Suggested CLI syntax

```bash
pbi visual set <page> <visual> accentBar.color=#E8A83E --measure "Stale Devices 30d"
pbi visual set <page> <visual> value.fontColor=#D64554 --measure "Non-Compliant"
```

---

### FEAT-004: Matrix/Pivot table formatting (`pivotTable` objects)

**Status:** Implemented (2026-03-13)
**Priority:** Medium — same structure as `tableEx`

The `pivotTable` visual type uses the same formatting groups as `tableEx` plus:

- `rowHeaders` — row header formatting (fontColor, backColor, fontSize, fontFamily)
- `subTotals` — subtotal row formatting
- `columnGrandTotal` / `rowGrandTotal` — grand total formatting

---

### FEAT-005: Theme management

**Priority:** Low — can be done via PBI Desktop UI

Currently the CLI has no commands for theme management. Theme files are JSON files
that PBI Desktop manages via `report.json` → `themeCollection` + `resourcePackages`.

Useful CLI operations would be:
- `pbi theme apply <theme.json>` — copy theme to `StaticResources/RegisteredResources/`
  and update `report.json` references
- `pbi theme export` — extract current theme to a standalone JSON file
- `pbi theme list` — show active base and custom themes

Note: PBI Desktop overwrites `report.json` on save, so theme changes via file editing
only work when PBI Desktop is closed.
