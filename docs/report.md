# Report Commands

The `pbi report` group edits schema-backed properties in `definition/report.json`.

## Supported commands

```bash
pbi report get
pbi report get layoutOptimization
pbi report set layoutOptimization=PhonePortrait
pbi report set settings.useEnhancedTooltips=true settings.pagesPosition=Bottom
pbi report props
```

## Current property coverage

The first report surface focuses on core metadata and exploration settings:

- `layoutOptimization`
- `reportSource`
- `settings.*` values such as:
  - `settings.useEnhancedTooltips`
  - `settings.useCrossReportDrillthrough`
  - `settings.allowInlineExploration`
  - `settings.exportDataMode`
  - `settings.pagesPosition`
  - `settings.queryLimitOption`

## Notes

- These commands are intentionally schema-backed rather than free-form JSON mutation.
- Theme and report-level filter management continue to live under `pbi theme` and `pbi filter`.
- Report resources, annotations, and other advanced report metadata are planned next.
