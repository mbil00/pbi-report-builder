"""Visual interaction management for PBIR reports.

Controls how visuals cross-filter, cross-highlight, or ignore each other's
selections. Interactions are stored as a `visualInteractions` array in page.json.
"""

from __future__ import annotations

from pbi.project import Page


# Valid interaction types
INTERACTION_TYPES = {"Default", "DataFilter", "HighlightFilter", "NoFilter"}


def get_interactions(page: Page) -> list[dict]:
    """Get all visual interactions on a page.

    Returns list of dicts with keys: source, target, type.
    """
    return page.data.get("visualInteractions", [])


def set_interaction(
    page: Page,
    source: str,
    target: str,
    interaction_type: str,
) -> None:
    """Set the interaction type between two visuals.

    Args:
        page: The page containing both visuals.
        source: Source visual name.
        target: Target visual name.
        interaction_type: One of Default, DataFilter, HighlightFilter, NoFilter.
    """
    if interaction_type not in INTERACTION_TYPES:
        raise ValueError(
            f'Invalid interaction type "{interaction_type}". '
            f"Must be one of: {', '.join(sorted(INTERACTION_TYPES))}"
        )

    if interaction_type == "Default":
        remove_interaction(page, source, target)
        return

    interactions = page.data.setdefault("visualInteractions", [])

    # Update existing or add new
    for entry in interactions:
        if entry.get("source") == source and entry.get("target") == target:
            entry["type"] = interaction_type
            return

    interactions.append({
        "source": source,
        "target": target,
        "type": interaction_type,
    })


def remove_interaction(
    page: Page,
    source: str,
    target: str | None = None,
) -> int:
    """Remove interactions. If target is None, removes all from source.

    Returns count of removed interactions.
    """
    interactions = page.data.get("visualInteractions", [])
    if not interactions:
        return 0

    if target:
        new = [
            e for e in interactions
            if not (e.get("source") == source and e.get("target") == target)
        ]
    else:
        new = [e for e in interactions if e.get("source") != source]

    removed = len(interactions) - len(new)
    if removed:
        if new:
            page.data["visualInteractions"] = new
        else:
            page.data.pop("visualInteractions", None)

    return removed
