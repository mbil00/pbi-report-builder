# Architecture Audit Recommendations

This document summarizes the architectural review of the codebase with a focus on abstraction level, fit of patterns, and whether the current structure is making common work simpler or harder.

The goal is not purity. The goal is to keep the codebase easy to extend without turning every new feature into glue code, special cases, or one more large command module.

## Executive Summary

The codebase is already strong in a few important areas:

- the YAML round-trip surface is intentionally centralized
- the report apply flow is split into useful submodules
- lookup behavior is standardized instead of reimplemented ad hoc
- the semantic-model layer has a reasonably plain domain representation

The main architectural pressure points are different:

- `Project` owns too many unrelated responsibilities
- CLI command modules are acting as both UI and application layer
- internal package boundaries are porous, with business logic depending on CLI helpers and modules reaching into private internals
- some compatibility facades have grown into broad export surfaces, which hides the real intended abstractions

None of these problems require a rewrite. They do suggest a cleanup direction: make the domain and application services more explicit, and make the CLI thinner.

## Review Scope

This review focused on:

- abstraction level
- fit of patterns over time
- whether functions and modules are simplifying the problem or carrying accidental complexity
- whether older patterns appear to have been extended instead of rethought

This review did not focus primarily on:

- correctness bugs
- performance tuning
- style-only changes

## Recommendation 1: Split `Project` Into Clearer Responsibilities

### Observation

`src/pbi/project.py` currently owns:

- project discovery
- file-system paths and JSON I/O
- caching of pages and visuals
- page CRUD
- visual CRUD
- grouping behavior
- binding mutation
- sort mutation

That makes `Project` the default place to put any report-related behavior, whether or not it belongs there.

### Recommendation

Keep `Project` as the project/report access root, but narrow its role to:

- locating the project
- loading pages and visuals
- persisting page and visual files
- managing caches

Move authoring behavior into explicit services or modules, for example:

- `report_editor` or `page_editor` for page and visual CRUD
- `visual_queries` for bindings and sort logic
- `visual_groups` for group semantics

### Why

`Project` is currently both a filesystem abstraction and a report authoring API. Those are related, but not the same abstraction. Once both live in one class, new features naturally accumulate there even when they belong to a narrower concept.

The main issue is not class size by itself. The issue is that the class boundary no longer communicates intent.

### Benefits

- clearer ownership of behavior
- easier testing of authoring logic without pulling in full project lifecycle concerns
- less risk that one change in caching or I/O accidentally affects authoring semantics
- easier future reuse outside the CLI

### Costs

- some churn in imports and call sites
- a short period where names and responsibilities need to be stabilized
- likely a moderate test update cost where modules currently import `Project` helpers directly

### Suggested Priority

High. This is the most structural issue in the review.

## Recommendation 2: Make the CLI a Thin Adapter Layer

### Observation

The command modules often do all of the following in one place:

- argument handling
- object lookup
- normalization and coercion
- business rules
- persistence
- CLI rendering

This is especially visible in the larger command files such as `pages.py`, `reports.py`, `themes.py`, and `visuals/inspection.py`.

### Recommendation

Adopt a more explicit layering model:

- CLI module: parse arguments, call service, render result
- service/application layer: execute use case and return structured results
- domain/data layer: project/model/property helpers

This does not mean every command needs its own service class. Simple functions are enough. The important change is where the business logic lives.

### Why

Right now the CLI is not just the presentation layer. It is also where important behavior is encoded. That makes the command surface the de facto API of the application.

That tends to work early in a CLI project, but it becomes a drag as the command set grows:

- logic gets duplicated across commands
- non-CLI workflows become harder to support
- command files become the easiest place to add one more special case

### Benefits

- commands become easier to read and maintain
- business logic becomes reusable by apply/export/automation paths
- better separation between user messaging and actual state transitions
- easier unit testing of the behavior itself

### Costs

- moderate refactor work in large command modules
- some helper functions in `commands/common.py` will need to move
- a few command handlers may temporarily look more indirect

### Suggested Priority

High. This is the second most important change after narrowing `Project`.

## Recommendation 3: Fix the Dependency Direction

### Observation

Some lower-level modules depend on higher-level CLI code or private internals:

- report apply helpers depend on `commands.common.resolve_field_info`
- report logic reaches into private helpers like `pbi.project._write_json`
- apply validation reaches into bookmark internals

### Recommendation

Make dependency direction one-way:

- CLI depends on domain/application modules
- apply/export/domain modules do not depend on CLI modules
- private helpers stay private; if they are shared, promote them properly

Concretely, move shared logic out of `commands.common.py` into a neutral module such as:

- `pbi.fields`
- `pbi.report_io`
- `pbi.report_services`

### Why

When internal layers depend upward on the CLI, the structure stops reflecting the real design. It becomes harder to know where logic belongs, and “helper” modules become accidental foundations.

This is usually a sign of growth, not bad intent. But it is worth correcting before it spreads further.

### Benefits

- more coherent package boundaries
- easier reuse of core logic in tests and non-CLI flows
- lower chance of import tangles and hidden side effects
- a clearer public vs internal API

### Costs

- mostly organizational refactoring
- some rename/move churn
- low implementation risk, but moderate breadth

### Suggested Priority

High. This can be done incrementally alongside Recommendation 2.

## Recommendation 4: Consolidate Field and Binding Resolution

### Observation

Field resolution currently exists in overlapping forms:

- CLI helpers resolve `Table.Field`
- apply wraps that resolution
- round-trip binding code contains its own variant

The overlap is not massive, but it is enough to suggest the abstraction has not fully settled.

### Recommendation

Create one shared field-resolution module that owns:

- parsing `Table.Field`
- optional measure marker handling
- semantic-model-aware canonicalization
- resolved field type and data type

Then make command helpers, apply, and round-trip all call that same surface.

### Why

Field resolution is real domain logic, not a CLI convenience. It is used across multiple subsystems and affects how bindings, filters, and modeling features behave.

That is exactly the kind of logic that should have one owner.

### Benefits

- fewer subtle behavior differences across surfaces
- easier to extend resolution rules in one place
- less duplicated error handling
- cleaner mental model for agents and maintainers

### Costs

- light-to-moderate refactor
- some tests will need re-baselining if error messages are normalized

### Suggested Priority

Medium-high. Good candidate for an early cleanup because the blast radius is manageable.

## Recommendation 5: Tighten Public Surfaces and Compatibility Facades

### Observation

Two facades stand out:

- `pbi.properties` re-exports many underscore-prefixed internals
- `pbi.model` re-exports a very large portion of the modeling package

These facades are convenient, but they also make it hard to tell what is intentionally public.

### Recommendation

Keep compatibility facades where they reduce churn, but narrow them to stable, intended entrypoints.

For example:

- `pbi.properties` should export the property catalogs and the supported runtime API
- `pbi.model` should export the modeling types and explicitly supported operations

Avoid re-exporting underscore-prefixed functions unless the plan is to make them truly public.

### Why

Broad re-export layers make refactoring harder because every internal helper becomes effectively public by accident.

A facade is useful when it hides complexity. It is less useful when it simply republishes a large implementation surface.

### Benefits

- clearer boundaries for future refactors
- lower accidental coupling
- easier onboarding for contributors

### Costs

- small to moderate import cleanup
- potential deprecation work if external users rely on these imports

### Suggested Priority

Medium.

## Recommendation 6: Keep the Good Modularization Trend in Apply and Round-Trip

### Observation

The best architectural direction in the codebase is already visible in:

- `src/pbi/roundtrip.py`
- `src/pbi/apply/engine.py`
- `src/pbi/apply/pages.py`
- `src/pbi/apply/visuals.py`
- `src/pbi/lookup.py`

These modules are not tiny, but they are organized around real responsibilities rather than command grouping alone.

### Recommendation

Use these areas as the model for future refactors:

- centralize format ownership in one place
- split orchestration from low-level mutation helpers
- make shared policies explicit

### Why

The codebase does not need a new architectural style invented for it. It already contains a better style in parts of the implementation. The practical move is to extend that style to weaker areas.

### Benefits

- lower redesign risk
- more consistency with existing successful patterns
- easier incremental refactoring

### Costs

- mostly discipline and sequencing
- little direct implementation cost by itself

### Suggested Priority

Ongoing guiding principle, not a separate refactor project.

## Custom Visual Initialization: Make It Explicit

### Observation

The CLI needs project-local custom visual schemas before custom-visual-aware commands can fully validate properties and roles.

Earlier, `get_project()` also:

- auto-installed custom visual schemas from `.pbiviz`
- registered custom schemas for the session

### Assessment

That behavior reduced friction, but it also made ordinary project resolution perform hidden setup work. Once an explicit initialization command exists, keeping both paths creates unnecessary ambiguity.

### Recommendation

Make `pbi init` the explicit and documented project bootstrap command.

Recommended direction:

1. Keep project lookup side-effect free.
2. Move bootstrap work behind `pbi init`.
3. Point users to `pbi init` anywhere the CLI detects missing custom visual schemas.

### Why

There are still two separate concerns:

- project resolution
- project initialization

Once both are explicit, command behavior is easier to reason about and easier to document.

### Benefits

- project lookup is predictable again
- bootstrap work becomes visible and diagnosable
- CI and agent workflows can follow one explicit preparation step
- future project scaffolding has a natural home

### Costs

- users must run one extra command when entering a project
- commands that depend on custom visual schemas now rely on documented setup instead of silent recovery
- some help text and workflow docs must be updated to reflect the explicit initialization model

### Recommended Direction

- document `pbi init` as the standard project-preparation step
- keep `get_project()` side-effect free
- route any future project scaffolding through the same initialization surface

## Suggested Refactor Sequence

This is the lowest-risk order:

1. Document current behavior and intended boundaries.
2. Extract shared field resolution into a neutral module.
3. Move shared non-CLI logic out of `commands.common.py`.
4. Thin the largest command modules by introducing application-service functions.
5. Narrow `Project` by moving authoring semantics into dedicated modules.
6. Tighten compatibility facades once the new boundaries are in place.

## Expected Outcome

If the recommendations above are followed, the codebase should end up with:

- a clearer separation between CLI, application services, and domain helpers
- fewer ambiguous “helper” modules that secretly own core logic
- a `Project` abstraction that is easier to understand and less likely to bloat further
- better reuse of shared logic across imperative commands, apply, and round-trip paths
- preserved ease of use for custom visuals, with better documentation and cleaner placement

## Non-Goals

These recommendations do not imply:

- replacing the current apply architecture
- removing the YAML round-trip approach
- forcing every feature into classes
- requiring an explicit init step for ordinary CLI use

The overall direction should stay pragmatic: keep what is already working well, and refactor the areas where convenience has started to blur the real boundaries.
