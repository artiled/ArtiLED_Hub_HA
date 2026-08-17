# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""What the Hub has, what changed, and what may be deleted.

These are the rules that decide whether a customer's entities appear, stay, or
are destroyed. They are deliberately kept here as plain functions over plain
data - no Home Assistant imports - so they can be read on their own and tested
without a running Home Assistant, a Hub, or a light.

That is not decoration. The first version of this logic had a grace period that
did nothing at all (see `presence`), and it was caught only because someone
happened to delete a real scene and someone happened to check the entity
registry rather than the entity count. Everything here is now pinned by
tests/test_inventory.py.
"""
from __future__ import annotations

# Everything whose creation or deletion on the Hub should reach Home Assistant.
# ⚠ Keys are the plural data keys; the singular (minus the trailing "s") is the
# entity unique_id kind - "scene" for scenes, and so on. Keep both in step.
INVENTORY_KINDS = ("rooms", "zones", "lights", "scenes", "modes", "flows")

# How long an item must be ABSENT before its entity and device may be deleted.
# Generous on purpose: deletion cannot be undone and takes the entity's history,
# area and automation references with it, whereas a stale entity is merely
# untidy.
DELETE_GRACE_SECONDS = 3600


def is_enabled(item: dict) -> bool:
    """Is this item offered to Home Assistant?

    Only lights carry a disabled flag; everything else is always enabled.
    """
    return str(item.get("disabled", 0)) != "1"


def signature(data: dict | None) -> frozenset[tuple[str, int, bool]] | None:
    """What the Hub HAS, and whether each item is enabled.

    Turning a light on or off does not change this; creating, deleting,
    disabling or re-enabling one does. A change means Home Assistant should
    reload, so that a light the customer adds shows up on its own.

    ⚠ The enabled flag is here ONLY so that re-enabling a light triggers the
    reload that recreates its entity. It must NEVER decide what to delete -
    that is `presence`.

    None while there is no data, so a failed first poll is not read as an empty
    Hub.
    """
    if not data:
        return None
    items: set[tuple[str, int, bool]] = set()
    for kind in INVENTORY_KINDS:
        singular = kind[:-1]
        for item_id, item in (data.get(kind) or {}).items():
            items.add((singular, item_id, is_enabled(item)))
    return frozenset(items)


def stamp_seen(data: dict | None, seen: dict[tuple[str, int], float], now: float) -> None:
    """Record that everything in `data` still exists, at time `now`.

    ⚠ `seen` is mutated in place and MUST outlive a config-entry reload. A
    reload builds a new coordinator; if this map is rebuilt with it, anything
    just removed looks like it never existed and is deleted on the spot - which
    defeats the grace in exactly the case it exists for, because a
    disappearance is itself what triggers the reload.
    """
    if not data:
        return
    for kind in INVENTORY_KINDS:
        singular = kind[:-1]
        for item_id in data.get(kind) or {}:
            seen[(singular, item_id)] = now


def presence(
    seen: dict[tuple[str, int], float],
    last_success: float | None,
    grace: float = DELETE_GRACE_SECONDS,
) -> frozenset[tuple[str, int]] | None:
    """Everything the Hub still has, or had recently. The ONLY deletable set.

    ⚠ A DISABLED light is one the customer means to bring back - it keeps its
    entity, id, history, area and any automation pointing at it, and merely
    stops being offered. This function therefore ignores the enabled flag
    entirely; `stamp_seen` records disabled items too. Upgrading a LED computer
    takes its node down and the Hub auto-disables that node's lights, so
    deleting on disable would destroy a customer's entities during routine
    maintenance.

    ⚠ The clock is the LAST SUCCESSFUL POLL, not wall time. If the Hub goes
    unreachable nothing ages out while it is gone - otherwise an outage longer
    than the grace would mark every item deletable at once and the next reload
    would wipe the lot.
    """
    if last_success is None:
        return None
    cutoff = last_success - grace
    return frozenset(key for key, at in seen.items() if at >= cutoff)
