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

## Relationships

- A **PBIP Project** contains one **PBIR Report** and usually one **Semantic Model**.
- A **PBIR Report** contains one or more **Pages**.
- A **Page** contains zero or more **Visuals**.
- A **Visual** can bind roles to **Field References** from the **Semantic Model**.
- **YAML Round-Trip** can modify a **PBIR Report**, its **Pages**, **Visuals**, and the **Semantic Model**.
- **Conditional Formatting Intent** targets a color property on a **Visual** or theme visual style and uses a **Field Reference** as its source.

## Example dialogue

> **Dev:** "When the YAML applies a **Conditional Formatting Intent**, should it save the **Visual**?"
> **Domain expert:** "No — formatting should produce the validated PBIR value; the caller that owns the **Page** or theme save decides persistence."

## Flagged ambiguities

- "dataset" may refer to the Power BI artifact, but in this tool the editable domain object is the **Semantic Model**.
