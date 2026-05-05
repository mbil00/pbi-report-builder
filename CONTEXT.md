# PBI Report Builder Context

This context describes the domain language for the PBIP/PBIR report authoring CLI.

## Language

**PBIP Project**:
A Power BI project folder containing a `.pbip` file, report definition, and semantic model files.
_Avoid_: workspace, repository

**PBIR Report**:
The file-based Power BI report definition edited by this tool.
_Avoid_: dashboard, canvas app

**Page**:
A report page within a PBIR report, stored as a page folder with page metadata and visuals.
_Avoid_: tab, sheet

**Visual**:
A report element on a Page with a visual type, position, bindings, objects, and optional formatting.
_Avoid_: widget, component

**Semantic Model**:
The Power BI model containing tables, columns, measures, relationships, roles, perspectives, and TMDL metadata.
_Avoid_: dataset, schema

**Field Reference**:
A user-facing `Table.Field` reference to a column or measure in the Semantic Model.
_Avoid_: column string, measure string

**YAML Round-Trip**:
The export/edit/apply workflow that represents PBIR Report and Semantic Model changes declaratively in YAML.
_Avoid_: config sync, template import

**PBIR Report Authoring**:
Mutation of Pages, Visuals, grouping, Visual bindings, and Visual sort definitions in a PBIR Report.
_Avoid_: project authoring, report service

**Conditional Formatting Intent**:
A user-facing request to derive a visual or theme color property from a measure, gradient, or rule set.
_Avoid_: formatting payload, color expression

**Theme Schema**:
The static, closed-set schema defining writable properties on a theme document — top-level theme entries (e.g. `dataColors`, `foreground`, `textClasses.title.color`) and their types (color, number, string, color list). Authoritative: every writable property is known up front, so validation against this schema can hard-reject invalid writes.
_Avoid_: theme registry, theme metadata

**Visual Schema**:
The per-visual-type schema extracted from Power BI Desktop capabilities, defining which objects and properties are valid on a **Visual** and the type of each property. Open: extended at runtime by custom visuals shipped inside a **PBIP Project**, so validation is advisory rather than authoritative.
_Avoid_: capabilities, visual registry, property catalog

**Apply Session**:
The per-run rollback frame for one execution of the **YAML Round-Trip** apply engine. Defines a `begin`/`commit`/`rollback`/`cleanup` lifecycle that the engine drives via a shared `run_apply` helper. Two substrate adapters: a PBIR Apply Session that owns every filesystem-mutating operation against a **PBIR Report** (page/visual structure and save, plus document-level theme/report/bookmark writes) behind a write protocol so apply leaf code never reaches around it to touch disk; and a TMDL buffer session (deferred-flush in-memory line buffer for the **Semantic Model**, dropped on failure).
_Avoid_: transaction, unit of work

**Apply Plan**:
The pure-function output of computing what one section of a **YAML Round-Trip** apply *would* write to a PBIR-substrate document (theme, report, bookmarks), without performing the write. The apply engine drives the **Apply Session** to persist a plan; the same plan can be inspected by `pbi diff` without touching disk.
_Avoid_: change set, transaction log

## Relationships

- A **PBIP Project** contains one **PBIR Report** and usually one **Semantic Model**.
- A **PBIR Report** contains one or more **Pages**.
- A **Page** contains zero or more **Visuals**.
- A **Visual** can bind roles to **Field References** from the **Semantic Model**.
- **YAML Round-Trip** can modify a **PBIR Report**, its **Pages**, **Visuals**, and the **Semantic Model**.
- **Conditional Formatting Intent** targets a color property on a **Visual** or theme visual style and uses a **Field Reference** as its source.
- A **Theme Schema** governs writes to a theme document (the JSON file referenced by a **PBIR Report**'s registered resources).
- A **Visual Schema** governs writes to **Visual** properties on a **Page**, and also to the visualStyles defaults embedded inside a theme document.
- An **Apply Session** scopes one execution of the **YAML Round-Trip** apply engine, with one adapter per write substrate (PBIR Report definition vs. Semantic Model TMDL).
- An **Apply Plan** is computed for each PBIR-substrate document (theme, report, bookmarks) that a **YAML Round-Trip** apply would touch, and is persisted by the **Apply Session**.

## Example dialogue

> **Dev:** "When the YAML applies a **Conditional Formatting Intent**, should it save the **Visual**?"
> **Domain expert:** "No — formatting should produce the validated PBIR value; the caller that owns the **Page** or theme save decides persistence."

## Flagged ambiguities

- "dataset" may refer to the Power BI artifact, but in this tool the editable domain object is the **Semantic Model**.
