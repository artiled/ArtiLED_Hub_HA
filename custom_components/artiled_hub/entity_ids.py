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


def voice_scene_unique_id(hub_ident: str, kind: str, item_id: int, scene_slug: str) -> str:
    """"<ident>_voice_scene_room_15_cinema" - the one key of a voice scene.

    ⚠ The scene name goes in SLUGIFIED (the caller passes HA's slugify of it),
    so "Relax" and "relax" are one scene, as everywhere else. scene.py builds
    its unique_id here, and __init__.py finds the registry entry of a choice
    here, so the two can never drift apart. A voice scene is on NO device
    (see ArtiHubScopedScene), so this is how it is found, never by device.
    """
    return f"{hub_ident}_voice_scene_{kind}_{int(item_id)}_{scene_slug}"


def voice_mode_unique_id(hub_ident: str, kind: str, item_id: int, mode_slug: str) -> str:
    """"<ident>_voice_mode_room_15_music" - the one key of a voice mode switch.
    Same rules as voice_scene_unique_id: slugified name, on NO device."""
    return f"{hub_ident}_voice_mode_{kind}_{int(item_id)}_{mode_slug}"
