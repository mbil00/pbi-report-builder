# Real Report Fixtures

This directory holds realistic PBIP fixtures and the source assets for building them on a machine that can run Power BI Desktop.

Structure:

- `report-01-kitchen-sink/`: widest report-authoring surface
  - `SPEC.md`: target fixture specification
  - `BUILD-CHECKLIST.md`: step-by-step Power BI build checklist
  - `data/`: deterministic CSV inputs and dataset notes
- `report-02-model-heavy/`: semantic-model editing, dependencies, metadata
  - `SPEC.md`
  - `BUILD-CHECKLIST.md`
  - `data/`
- `report-03-authoring-parity-lab/`: built mainly with `pbi` on top of the report-02 model
  - `SPEC.md`
- `report-04-desktop-shapes/`: ground-truth Desktop output for shapes the CLI writes or should write (textbox runs, `///` descriptions, one-sided cardinality, data colours, slicer sync groups and saved selections, measure filter literals, calculated table columns, TMDL naming). Built **only** in Power BI Desktop; see its `SPEC.md` for the issue mapping.
  - `SPEC.md`
  - `BUILD-CHECKLIST.md`
  - `data/`: CSVs plus `Desktop Shapes Theme.json` and `Team Logo.png`
  - `BUILD-NOTES.md`: written by the builder (Desktop version, deviations)
  - `04-desktop-shapes.*`: the Desktop output, committed as saved
- `report-04-desktop-shapes-renamed/`: the same project after two renames in Desktop (`Total Hours` to `Hours Logged`, `Person[PersonName]` to `Person Name`); diff it against report-04 to see what Desktop rewrites
- `manifest.json`: row counts for generated CSV inputs

Regenerate deterministic data and checklists:

```bash
uv run python scripts/generate_fixture_datasets.py
uv run python scripts/generate_fixture_build_checklists.py
```

Both accept a selector (`--dataset desktop-shapes`, `--fixture report-04-desktop-shapes`) to regenerate one fixture. The dataset generator only rewrites each report's `data/` subdirectory, so `SPEC.md` and `BUILD-CHECKLIST.md` remain intact, and it merges into `manifest.json` rather than replacing it. The report-04 checklist is generated from a template in the checklist script; edit the script, not the Markdown.
