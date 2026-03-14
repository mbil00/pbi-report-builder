# Report Commands

The `pbi report` group edits schema-backed properties in `definition/report.json`.

## Commands

```bash
pbi report get
pbi report get layoutOptimization
pbi report get layoutOptimization settings.pagesPosition

pbi report set layoutOptimization=PhonePortrait
pbi report set settings.useEnhancedTooltips=true settings.pagesPosition=Bottom

pbi report properties
```

## Notes

- Report mutation uses `key=value` only.
- `pbi report properties` lists the supported schema-backed keys.
- Theme and report-level filters remain under `pbi theme` and `pbi filter`.
