"""Internal filter/bookmark/interaction helpers for the report apply engine."""

from __future__ import annotations

import copy

from pbi.commands.common import resolve_field_info
from pbi.filters import add_categorical_filter
from pbi.project import Page, Project

from .state import ApplyResult, ApplySession, PageVisualState


def resolve_apply_field(
    field_ref: str,
    project: Project,
    *,
    session: ApplySession | None = None,
) -> tuple[str, str, str, str | None]:
    """Resolve a field reference to (entity, prop, field_type, data_type)."""
    model = session.get_model(project) if session is not None else None
    return resolve_field_info(project, field_ref, "auto", model=model, strict=True)


def apply_filters_spec(
    data: dict,
    filters_spec: list,
    result: ApplyResult,
    *,
    context: str,
    dry_run: bool,
    project: Project | None = None,
    session: ApplySession | None = None,
) -> None:
    """Apply filters from the YAML spec."""
    from pbi.visual_analysis import normalize_semantic_data_type

    if filters_spec and not dry_run:
        config = data.setdefault("filterConfig", {})
        config["filters"] = []

    for filter_spec in filters_spec:
        if not isinstance(filter_spec, dict):
            result.errors.append(f"{context}: filter must be a mapping.")
            continue

        model = session.get_model(project) if project is not None and session is not None else None
        field_ref = filter_spec.get("field", "")
        filter_type = filter_spec.get("type", "Categorical")
        values = filter_spec.get("values", [])
        is_hidden = filter_spec.get("hidden", False)
        is_locked = filter_spec.get("locked", False)

        dot = field_ref.find(".")
        if dot == -1:
            result.errors.append(f"{context}: filter field must be Table.Field format: {field_ref}")
            continue

        entity = field_ref[:dot]
        prop = field_ref[dot + 1:]
        field_type_name = "column"
        data_type = None
        if project is not None:
            try:
                entity, prop, field_type_name, data_type = resolve_apply_field(
                    field_ref,
                    project,
                    session=session,
                )
            except ValueError as e:
                result.errors.append(f"{context}: {e}")
                continue

        if dry_run:
            result.filters_added += 1
            continue

        raw_filter = filter_spec.get("raw")
        if isinstance(raw_filter, dict):
            config = data.setdefault("filterConfig", {})
            config.setdefault("filters", []).append(copy.deepcopy(raw_filter))
            result.filters_added += 1
        elif filter_type.lower() in ("categorical", "include", "exclude"):
            str_values = [str(value) for value in values] if values else []
            if str_values:
                if filter_type.lower() == "include":
                    from pbi.filters import add_include_filter

                    add_include_filter(
                        data, entity, prop, str_values,
                        field_type=field_type_name,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                        data_type=data_type,
                    )
                elif filter_type.lower() == "exclude":
                    from pbi.filters import add_exclude_filter

                    add_exclude_filter(
                        data, entity, prop, str_values,
                        field_type=field_type_name,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                        data_type=data_type,
                    )
                else:
                    add_categorical_filter(
                        data, entity, prop, str_values,
                        field_type=field_type_name,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                        data_type=data_type,
                    )
                result.filters_added += 1
            elif filter_type.lower() == "categorical":
                from pbi.filters import add_empty_categorical_filter

                add_empty_categorical_filter(
                    data,
                    entity,
                    prop,
                    field_type=field_type_name,
                    is_hidden=is_hidden,
                    is_locked=is_locked,
                )
                result.filters_added += 1
        elif filter_type.lower() == "topn":
            from pbi.filters import add_topn_filter

            count = filter_spec.get("count", 10)
            by_ref = filter_spec.get("by", "")
            direction = filter_spec.get("direction", "Top")
            by_dot = by_ref.find(".")
            if by_dot == -1:
                result.errors.append(f"{context}: topN filter 'by' must be Table.Field format: {by_ref}")
                continue
            by_entity = by_ref[:by_dot]
            by_prop = by_ref[by_dot + 1:]

            order_field_type = "measure"
            if project is not None:
                try:
                    by_entity, by_prop, order_field_type, _ = resolve_apply_field(
                        by_ref,
                        project,
                        session=session,
                    )
                except ValueError as e:
                    result.errors.append(f"{context}: {e}")
                    continue

            add_topn_filter(
                data, entity, prop,
                n=int(count),
                order_entity=by_entity,
                order_prop=by_prop,
                order_field_type=order_field_type,
                direction=direction.capitalize(),
                is_hidden=is_hidden,
                is_locked=is_locked,
                field_type=field_type_name,
            )
            result.filters_added += 1
        elif filter_type.lower() == "range":
            from pbi.filters import add_range_filter

            min_val = filter_spec.get("min")
            max_val = filter_spec.get("max")

            add_range_filter(
                data, entity, prop,
                min_val=str(min_val) if min_val is not None else None,
                max_val=str(max_val) if max_val is not None else None,
                field_type=field_type_name,
                is_hidden=is_hidden,
                is_locked=is_locked,
                data_type=data_type,
            )
            result.filters_added += 1
        elif filter_type.lower() == "advanced":
            from pbi.filters import ADVANCED_OPERATORS, add_advanced_filter

            adv_operator = filter_spec.get("operator", "")
            if adv_operator not in ADVANCED_OPERATORS:
                result.errors.append(
                    f"{context}: unknown advanced operator '{adv_operator}'. "
                    f"Use one of: {', '.join(sorted(ADVANCED_OPERATORS))}."
                )
                continue

            adv_value = filter_spec.get("value")
            if adv_value is not None:
                adv_value = str(adv_value)

            adv_operator2 = filter_spec.get("operator2")
            adv_value2 = filter_spec.get("value2")
            if adv_value2 is not None:
                adv_value2 = str(adv_value2)
            adv_logic = str(filter_spec.get("logic", "and")).lower()

            try:
                add_advanced_filter(
                    data, entity, prop,
                    operator=adv_operator,
                    value=adv_value,
                    field_type=field_type_name,
                    is_hidden=is_hidden,
                    is_locked=is_locked,
                    data_type=data_type,
                    operator2=adv_operator2,
                    value2=adv_value2,
                    logic=adv_logic,
                )
                result.filters_added += 1
            except ValueError as e:
                result.errors.append(f"{context}: {e}")
        elif filter_type.lower() == "relative":
            from pbi.filters import add_relative_date_filter, add_relative_time_filter

            rel_operator = filter_spec.get("operator", "")
            rel_count = filter_spec.get("count")
            rel_unit = filter_spec.get("unit", "")
            include_today = filter_spec.get("includeToday", True)

            time_units = {"Minutes", "Hours"}
            date_units = {"Days", "Weeks", "CalendarWeeks", "Months", "CalendarMonths", "Years", "CalendarYears"}
            all_units = time_units | date_units
            is_time = rel_unit in time_units

            valid_ops = {"InLast", "InNext"} if is_time else {"InLast", "InThis", "InNext"}
            if rel_operator not in valid_ops:
                result.errors.append(
                    f"{context}: relative filter operator must be one of: {', '.join(sorted(valid_ops))}."
                )
                continue

            if not rel_count or int(rel_count) <= 0:
                result.errors.append(f"{context}: relative filter requires a positive 'count'.")
                continue

            if rel_operator == "InThis":
                rel_count = 1

            if rel_unit not in all_units:
                result.errors.append(
                    f"{context}: relative filter unit '{rel_unit}' not recognized. "
                    f"Use one of: {', '.join(sorted(all_units))}."
                )
                continue

            if field_type_name != "column":
                result.errors.append(
                    f"{context}: relative filters only support column fields, not {field_type_name}."
                )
                continue
            semantic_types = normalize_semantic_data_type(field_type_name, data_type)
            if model is not None and "dateTime" not in semantic_types:
                result.errors.append(
                    f"{context}: relative filters require a date/time column, not {entity}.{prop}."
                )
                continue

            try:
                if is_time:
                    add_relative_time_filter(
                        data, entity, prop,
                        operator=rel_operator,
                        time_units_count=int(rel_count),
                        time_unit_type=rel_unit,
                        field_type=field_type_name,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                    )
                else:
                    add_relative_date_filter(
                        data, entity, prop,
                        operator=rel_operator,
                        time_units_count=int(rel_count),
                        time_unit_type=rel_unit,
                        include_today=bool(include_today),
                        field_type=field_type_name,
                        is_hidden=is_hidden,
                        is_locked=is_locked,
                    )
                result.filters_added += 1
            except (ValueError, NotImplementedError) as e:
                result.errors.append(f"{context}: {e}")
        else:
            result.warnings.append(
                f"{context}: filter type '{filter_type}' not yet supported in apply."
            )


def apply_bookmarks_spec(
    project: Project,
    bookmarks_spec: list,
    result: ApplyResult,
    *,
    dry_run: bool,
    session: ApplySession,
) -> None:
    """Apply bookmark definitions from the YAML spec."""
    from pbi.bookmarks import normalize_bookmark_state, reconcile_bookmark_groups, upsert_bookmark

    bookmark_groups: list[tuple[str, str | None]] = []

    for entry in bookmarks_spec:
        if not isinstance(entry, dict):
            result.errors.append("Bookmark must be a mapping.")
            continue

        name = entry.get("name", "")
        page_ref = entry.get("page", "")
        if not name or not page_ref:
            result.errors.append("Bookmark requires 'name' and 'page'.")
            continue

        hide = entry.get("hide", [])
        target = entry.get("target")
        capture_data = entry.get("captureData", True)
        capture_display = entry.get("captureDisplay", True)
        capture_page = entry.get("capturePage", True)
        group = entry.get("group")
        state = entry.get("state")
        options = entry.get("options")

        if dry_run:
            result.properties_set += 1
            if isinstance(group, str):
                bookmark_groups.append((str(name), group))
            continue

        try:
            page = project.find_page(page_ref)
            visuals = project.get_visuals(page)
            session.ensure_snapshot(project)
            normalized_state = normalize_bookmark_state(project, state) if isinstance(state, dict) else None
            upsert_bookmark(
                project,
                display_name=name,
                page=page,
                visuals=visuals,
                hidden_visuals=hide if hide else None,
                target_visuals=target if target else None,
                suppress_data=not bool(capture_data),
                suppress_display=not bool(capture_display),
                suppress_active_section=not bool(capture_page),
                exploration_state_patch=normalized_state,
                options_patch=options if isinstance(options, dict) else None,
            )
            bookmark_groups.append((str(name), str(group) if isinstance(group, str) and group else None))
            result.properties_set += 1
        except (ValueError, FileNotFoundError) as e:
            result.errors.append(f'Bookmark "{name}": {e}')

    if bookmark_groups and not dry_run:
        try:
            reconcile_bookmark_groups(project, bookmark_groups)
        except (ValueError, FileNotFoundError) as e:
            result.errors.append(f"Bookmark groups: {e}")


def apply_interactions_spec(
    project: Project,
    page: Page,
    interactions_spec: list,
    result: ApplyResult,
    *,
    context: str,
    dry_run: bool,
    session: ApplySession | None = None,
    page_state: PageVisualState,
) -> None:
    """Apply interaction definitions from the YAML spec."""
    from pbi.interactions import set_interaction

    for entry in interactions_spec:
        if not isinstance(entry, dict):
            result.errors.append(f"{context}: interaction must be a mapping.")
            continue

        source = entry.get("source", "")
        target = entry.get("target", "")
        interaction_type = entry.get("type", "DataFilter")

        if not source or not target:
            result.errors.append(f"{context}: interaction requires 'source' and 'target'.")
            continue

        if dry_run:
            result.properties_set += 1
            result.interactions_set.append((page.display_name, str(source), str(target), str(interaction_type)))
            continue

        try:
            source_visual = page_state.find_visual(source)
            target_visual = page_state.find_visual(target)
            set_interaction(page, source_visual.name, target_visual.name, interaction_type)
            result.properties_set += 1
            result.interactions_set.append((page.display_name, source_visual.name, target_visual.name, interaction_type))
        except ValueError as e:
            result.errors.append(f"{context}: interaction {source}->{target}: {e}")
