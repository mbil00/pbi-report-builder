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

**Status:** Fixed
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

**Status:** Fixed
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

**Status:** Fixed (resolved by BUG-001/002 fixes)
**Severity:** Cosmetic

### Detail

When reading back a visual's properties, the CLI shows `title.titleVisibility`
in the output. After fixing BUG-001, verify that `_get_container_prop()` and the
display formatting read `show` correctly and display it as `title.show` in the
CLI output.

**Verified:** The `visual get` display iterates raw JSON keys, so old data with
`titleVisibility` still shows the old name. New writes produce `show` correctly.
Existing visuals with the bad property need manual cleanup or re-set via CLI.

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

Page background is now supported via `pbi page set`:

```bash
pbi page set "Sales" background.color "#F5F5F5"
pbi page set "Sales" background.transparency 0
```
