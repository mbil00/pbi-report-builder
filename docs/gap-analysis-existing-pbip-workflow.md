# Gap Analysis: Existing PBIP Report-Building Workflow

Scope here is the in-project authoring workflow inside an existing PBIP: model tweaks, new measures/columns, visual updates, page work, reuse, and validation.

Out of scope:
- data acquisition / model onboarding
- publishing / deployment

This project is not trying to be a full Power BI Desktop replacement. It is closer to a PBIP authoring and refactoring layer for existing reports: inspect what already exists, mutate it safely, scale changes across many visuals/pages, and keep the result diffable and automatable.

## Gap Matrix

| Workflow step | Power BI Desktop strength | This app strength | Gap / limitation | Overall |
|---|---|---|---|---|
| Discover existing report structure | Visual browsing is easy, but large reports become click-heavy | `info`, `map`, `visual tree`, `page export`, `visual get --full`, diff, validate make inspection much more systematic | Render is only a mockup, not a true report preview | Better than Desktop for auditability |
| Create/edit measures | Native measure editing is straightforward | Very strong: create/edit/delete, dependency analysis, cascading rename, YAML apply | No major practical gap for normal report work | Strong |
| Create/edit calculated columns | Native flow is easy | Strong: create/edit/delete, formatting, YAML apply | Less interactive than Desktop for trial-and-error authoring | Strong |
| Manage relationships | Native model view is excellent visually | Strong enough: list/create/delete/set, path finding, validation | Harder than Desktop for spatial understanding of large models | Strong but less visual |
| Hierarchies / perspectives / RLS / partitions | Available, but spread across model UI areas | Strong CLI coverage | Still not as discoverable as Desktop UI | Strong |
| Field parameters | Native UI is easy | Supported now, including creation and model export/apply | Workflow is less polished than Desktop wizardry | Strong enough |
| Inspect current visual bindings/properties | Desktop exposes this imperfectly and inconsistently | One of the app's best areas: full property inspection, schema-backed property catalog, bindings, sort, filters | Some edge-case objects depend on schema extraction completeness | Very strong |
| Tweak existing visuals | Good for one-off edits | Excellent: `visual set`, `set-all`, conditional formatting, sort, column rename, style copy, layout commands | None major in the stated scope | Excellent |
| Bulk restyling many visuals/pages | Desktop is weak and repetitive | Major advantage: bulk set, styles, themes, components, YAML find/replace style workflows | Some visual-specific polish defaults still need more presets | Better than Desktop |
| Re-layout / resize / align report pages | Strong interactively | Strong and scalable: move/resize/arrange/grid/align, page sections, templates | Less intuitive for freeform visual design exploration | Strong |
| Reuse patterns across reports | Desktop has limited reuse patterns | Major advantage: page templates, components, cross-project import, styles, YAML round-trip | Needs more canned recipes/scaffolds | Better than Desktop |
| Build a new visual from scratch | Desktop is best here: drag-drop, instant feedback, easy experimentation | Partial: `visual create` can scaffold, bind roles, auto-title, preset, auto-sort, or clone | This is the main weakness: common families work, edge-case visuals/query shapes are not first-class | Partial |
| Build a new page from scratch | Desktop gives immediate WYSIWYG layouting | Reasonable via YAML apply, templates, components, sections | Slower for exploratory page composition; stronger when reusing patterns than inventing from zero | Partial-to-strong |
| Advanced visual query shapes / aggregations | Desktop handles these via visual UX and internal query generation | Partial | Advanced aggregation/query shapes still need deeper builders | Partial |
| Interactions / bookmarks / nav / drillthrough / tooltips | Native UI is usable but repetitive | Strong primitive coverage, especially for batch/YAML authoring | Missing higher-level recipes for common interaction patterns | Strong |
| Themes / report-wide visual consistency | Good, but manual cleanup is tedious | Strong: theme editing, migration, visualStyles, format defaults, style presets | Obscure Desktop-exported theme payloads may still need low-level edits | Strong |
| Preview results before opening Desktop | Desktop is the real preview | Useful HTML mockup and screenshot flow | Not pixel-perfect, no live data, limited fidelity for images/conditional formatting/theme rendering | Partial |
| Validate structural safety after edits | Desktop gives some feedback, but not as a batch validation tool | Strong: validate, diff, schema-backed writes | Validation is stronger than visual confidence; layout aesthetics still need judgment | Strong |
| Advanced metadata and niche report/model payloads | Desktop sometimes hides this too | Core report metadata is covered well | Cultures/translations and some obscure payloads still need lower-level editing | Partial |
| Agent/automation friendliness | Desktop is poor for automation | This is the app's design center | Depends on export-edit-apply discipline rather than interactive trial-and-error | Excellent |

## Practical Conclusion

For an established PBIP, this app is strongest where work is repetitive, structural, or broad in scope:

- model maintenance
- report/page inspection
- bulk visual mutation
- layout normalization
- theme/style consistency
- reuse across pages/projects
- diff/validate/apply workflows

It is weaker where Power BI Desktop's interactive canvas and query designer matter most:

- inventing visuals from scratch
- exploratory page composition
- unusual visual/query shapes
- high-fidelity preview

## Recommended Split Of Labor

- Use this app as the primary tool for modifying, standardizing, scaling, and validating an existing report.
- Use Power BI Desktop when inventing a brand-new visual/page pattern or when a visual needs complex query shaping.
- Once a pattern exists, bring it back into this tool's world via export/template/component/style so future work becomes scalable.

## Basis

This assessment is based on:

- the project's stated positioning as an agent-first PBIP editor
- the documented export-edit-apply workflow
- the current capability inventory in the codebase
- the current implementation maturity verified by running the full test suite successfully
