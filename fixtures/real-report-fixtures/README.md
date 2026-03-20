# Real Report Fixtures

This directory contains source assets for building two realistic PBIP fixtures on a machine that can run Power BI Desktop.

Structure:

- `report-01-kitchen-sink/`
  - `SPEC.md`: target fixture specification
  - `BUILD-CHECKLIST.md`: step-by-step Power BI build checklist
  - `data/`: deterministic CSV inputs and dataset notes
- `report-02-model-heavy/`
  - `SPEC.md`
  - `BUILD-CHECKLIST.md`
  - `data/`
- `manifest.json`: row counts for generated CSV inputs

Regenerate deterministic data:

```bash
python scripts/generate_fixture_datasets.py
python scripts/generate_fixture_build_checklists.py
```

The dataset generator only rewrites each report's `data/` subdirectory so `SPEC.md` and `BUILD-CHECKLIST.md` remain intact.
