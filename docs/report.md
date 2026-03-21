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

pbi report resource package list
pbi report resource package get RegisteredResources
pbi report resource package create BrandAssets --type RegisteredResources
pbi report resource package delete BrandAssets

pbi report resource item list RegisteredResources
pbi report resource item get RegisteredResources logo.png
pbi report resource item set RegisteredResources logo.png --type Image --name Logo --from-file ./logo.png
pbi report resource item delete RegisteredResources logo.png --drop-file

pbi report custom-visual list
pbi report custom-visual get "Org Timeline"
pbi report custom-visual set "Org Timeline" store/org-timeline.pbiviz --disabled
pbi report custom-visual delete "Org Timeline"

pbi report data-source-variables get
pbi report data-source-variables set --from-file variables.json
pbi report data-source-variables clear

pbi report properties
```

## Notes

- `pbi report set` remains the scalar/settings path and uses `key=value` assignments.
- `pbi report properties` lists the supported schema-backed scalar keys.
- `pbi report annotation` edits the top-level report `annotations` array using the published `{name, value}` shape.
- `pbi report object` is for top-level JSON objects/arrays such as `filterConfig`, `objects`, `resourcePackages`, `settings`, and `themeCollection`.
- `pbi report resource package` manages `resourcePackages` at the package level.
- `pbi report resource item` manages individual resource entries inside a package and can copy files into `RegisteredResources` with `--from-file`.
- `pbi report custom-visual` manages the `organizationCustomVisuals` array with `name`, `path`, and optional `disabled` state.
- `pbi report data-source-variables` manages the top-level `dataSourceVariables` string payload.
- Full `pbi export` now includes a top-level `report:` section for full-report YAML round-trip. Page-only export (`--page` / page export flows) still omits that section.
- Theme and report-level filters remain under `pbi theme` and `pbi filter`.
