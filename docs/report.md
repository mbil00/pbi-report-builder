# Report Commands

The `pbi report` group edits report-level data in `definition/report.json`.

## Commands

```bash
pbi report get
pbi report get layoutOptimization
pbi report get layoutOptimization settings.pagesPosition

pbi report set layoutOptimization=PhonePortrait
pbi report set settings.useEnhancedTooltips=true settings.pagesPosition=Bottom

pbi report annotation list
pbi report annotation get README
pbi report annotation set README "Owned by BI team"
pbi report annotation delete README

pbi report object list
pbi report object get resourcePackages
pbi report object get filterConfig --raw
pbi report object set objects --from-file report-objects.json
pbi report object clear annotations

pbi report properties
```

## Notes

- `pbi report set` remains the scalar/settings path and uses `key=value` assignments.
- `pbi report properties` lists the supported schema-backed scalar keys.
- `pbi report annotation` edits the top-level report `annotations` array using the published `{name, value}` shape.
- `pbi report object` is for top-level JSON objects/arrays such as `filterConfig`, `objects`, `resourcePackages`, `settings`, and `themeCollection`.
- Theme and report-level filters remain under `pbi theme` and `pbi filter`.
