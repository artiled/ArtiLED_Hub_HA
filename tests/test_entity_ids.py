#!/usr/bin/env python3
# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Tests for parse_run_picker — the rule that decides which entities get their
entity_id RENAMED.

Run:  python3 tests/test_entity_ids.py     (exit 0 = all pass)

No Home Assistant required; entity_ids.py is loaded straight from its path, the
same way test_inventory.py loads inventory.py.

⚠ WHY THIS FILE EXISTS. A rename is destructive in a way an added entity is
not: an entity_id that a dashboard, script or automation references stops
resolving, silently. The same config entry owns four other families of
unique_id that look similar — the turn-on/turn-off pickers
("<ident>_room_15_on_scene"), house-wide scenes ("<ident>_scene_5"), mode
switches and lights. If the parser matched any of those, the migration would
rename entities that have been stable since 0.1 and are exactly the ones most
likely to be referenced. Every one of them is pinned as a negative below.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_SRC = (
    pathlib.Path(__file__).resolve().parent.parent
    / "custom_components"
    / "artiled_hub"
    / "entity_ids.py"
)
_spec = importlib.util.spec_from_file_location("artiled_entity_ids", _SRC)
ids = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ids)

IDENT = "SheCh6feegh9chu"

FAILURES: list[str] = []


def check(label: str, ok: bool, hint: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
    if not ok:
        FAILURES.append(label)
        if hint:
            print(f"        {hint}")


print("\nrun pickers are recognised")
check(
    "a room scene picker parses",
    ids.parse_run_picker(f"{IDENT}_room_15_run_scene", IDENT) == ("room", 15, "scene"),
)
check(
    "a zone mode picker parses",
    ids.parse_run_picker(f"{IDENT}_zone_16_run_mode", IDENT) == ("zone", 16, "mode"),
)
check(
    "multi-digit ids survive",
    ids.parse_run_picker(f"{IDENT}_room_142_run_scene", IDENT) == ("room", 142, "scene"),
)

print("\nnothing else is EVER matched (these are the ids a rename would break)")
for unique_id, why in (
    (f"{IDENT}_room_15_on_scene", "the turn-on picker"),
    (f"{IDENT}_room_15_off_scene", "the turn-off picker"),
    (f"{IDENT}_scene_5", "a house-wide scene entity"),
    (f"{IDENT}_mode_3", "a house-wide mode switch"),
    (f"{IDENT}_light_8", "an individual light"),
    (f"{IDENT}_room_15", "a room light entity"),
    (f"{IDENT}_version", "the firmware sensor"),
    (f"{IDENT}_flow_2", "a flow button"),
):
    check(f"{why} is left alone", ids.parse_run_picker(unique_id, IDENT) is None)

print("\nmalformed input is refused rather than half-parsed")
check(
    "another Hub's entity is not ours to rename",
    ids.parse_run_picker(f"OTHERIDENT_room_15_run_scene", IDENT) is None,
)
check(
    "a non-numeric id is refused",
    ids.parse_run_picker(f"{IDENT}_room_abc_run_scene", IDENT) is None,
)
check(
    "an unknown suffix is refused",
    ids.parse_run_picker(f"{IDENT}_room_15_run_flow", IDENT) is None,
)
check(
    "an unknown scope kind is refused",
    ids.parse_run_picker(f"{IDENT}_house_15_run_scene", IDENT) is None,
)
check("the bare ident is refused", ids.parse_run_picker(IDENT, IDENT) is None)
check("an empty unique_id is refused", ids.parse_run_picker("", IDENT) is None)

print("\na hub ident containing underscores still works")
UND = "hub_with_underscores"
check(
    "the ident is stripped by length, not by splitting",
    ids.parse_run_picker(f"{UND}_room_15_run_scene", UND) == ("room", 15, "scene"),
    "splitting on '_' would read the ident's own words as the scope kind",
)
check(
    "and its on/off picker is still left alone",
    ids.parse_run_picker(f"{UND}_room_15_on_scene", UND) is None,
)

print("\nsensitivity: prove a sloppier parser would FAIL these")


def naive(unique_id: str, hub_ident: str):
    """What a 'looks close enough' version does — matches on the suffix alone."""
    return unique_id.endswith(("_run_scene", "_run_mode")) or None


check(
    "the negatives above are real (a suffix-only parser passes them wrongly)",
    naive(f"{IDENT}_room_15_run_scene", IDENT) is not None
    and naive(f"{IDENT}_room_abc_run_scene", IDENT) is not None,
    "if this fails the malformed-input checks above prove nothing",
)

print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
    sys.exit(1)
print("all entity-id rules pass")
sys.exit(0)
