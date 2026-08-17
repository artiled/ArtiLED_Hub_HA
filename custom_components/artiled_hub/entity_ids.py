# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Pure helpers for deciding entity ids. No Home Assistant imports, so the
rules can be tested without the framework."""
from __future__ import annotations

RUN_SUFFIXES = ("scene", "mode")
SCOPE_KINDS = ("room", "zone")


def parse_run_picker(unique_id: str, hub_ident: str) -> tuple[str, int, str] | None:
    """"<ident>_room_15_run_scene" -> ("room", 15, "scene"); anything else None.

    ⚠ This decides which entities get RENAMED, so it has to be exact. The same
    config entry also owns "<ident>_room_15_on_scene" (the turn-on picker),
    "<ident>_scene_5" (a house-wide scene) and "<ident>_light_8" — renaming any
    of those would break ids a user may already reference. Everything is
    matched positively; nothing is assumed from a prefix alone.
    """
    prefix = f"{hub_ident}_"
    if not unique_id.startswith(prefix):
        return None
    kind, _, rest = unique_id[len(prefix) :].partition("_")
    if kind not in SCOPE_KINDS:
        return None
    item_id, marker, suffix = rest.partition("_run_")
    if not marker or suffix not in RUN_SUFFIXES or not item_id.isdigit():
        return None
    return kind, int(item_id), suffix
