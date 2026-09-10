#!/usr/bin/env python3
# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Tests for the voice choice rule - which stored spoken name a remove or a
re-add replaces.

Run:  python3 tests/test_voice.py     (exit 0 = all pass)

No Home Assistant required; voice.py is loaded straight from its path, the same
way test_inventory.py loads inventory.py.

WHY THIS FILE EXISTS. Scene and mode names ignore case when matched (Michel
2026-09-10). The rule used to compare exactly, so removing "relax" left an entry
added as "Relax" in place, and adding "relax" made a SECOND entry whose unique_id
(slugified, so lowercase) clashed with the first.
"""
import importlib.util
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, "..", "custom_components", "artiled_hub", "voice.py")
_spec = importlib.util.spec_from_file_location("artiled_voice", _SRC)
voice = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(voice)

FAILURES = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if condition else 'FAIL'}  {name}")
    if not condition:
        FAILURES.append(name)
        if detail:
            print(f"        {detail}")


chosen = [
    {"kind": "room", "id": 15, "scene": "Relax", "name": "Living Relax"},
    {"kind": "room", "id": 15, "scene": "Cinema", "name": "Movie Time"},
    {"kind": "zone", "id": 15, "scene": "Relax", "name": "Zone Relax"},
    {"kind": "room", "id": 16, "scene": "Relax", "name": "Kitchen Relax"},
]

print("\nremove matches the scene name ignoring case, and only in its own scope")
left = voice.without_entry(chosen, "room", 15, "scene", "relax")
check("removing 'relax' drops the entry added as 'Relax'",
      not any(t["kind"] == "room" and t["id"] == 15 and t["scene"] == "Relax" for t in left))
check("the other scene in that room stays", any(t["scene"] == "Cinema" for t in left))
check("the same scene in a zone with the same id stays", any(t["kind"] == "zone" for t in left))
check("the same scene in another room stays", any(t["id"] == 16 for t in left))
check("exactly one entry is removed", len(left) == len(chosen) - 1)
check("an exact spelling still matches", len(voice.without_entry(chosen, "room", 15, "scene", "Relax")) == len(chosen) - 1)
check("a different name removes nothing", len(voice.without_entry(chosen, "room", 15, "scene", "Relaxed")) == len(chosen))
check("an accented capital matches (\u00c9LAN vs \u00c9lan)",
      voice.without_entry([{"kind": "room", "id": 1, "mode": "\u00c9lan", "name": "x"}], "room", 1, "mode", "\u00c9LAN") == [])
check("an id given as text still matches", len(voice.without_entry(chosen, "room", "15", "scene", "RELAX")) == len(chosen) - 1)
check("no stored list is an empty list", voice.without_entry(None, "room", 1, "scene", "x") == [])

print("\nre-adding in other capitals replaces instead of duplicating")
readd = voice.without_entry(chosen, "room", 15, "scene", "relax") + [
    {"kind": "room", "id": 15, "scene": "relax", "name": "Living Relax"}]
mine = [t for t in readd if t["kind"] == "room" and t["id"] == 15 and voice.same_name(t["scene"], "Relax")]
check("one entry for room 15 and that scene", len(mine) == 1)
check("it keeps the spelling it was added with", [t["scene"] for t in mine] == ["relax"])

print("\nthe integration uses this rule")
init = open(os.path.join(os.path.dirname(_SRC), "__init__.py"), encoding="utf-8").read()
check("__init__.py imports without_entry from voice.py", "from .voice import without_entry" in init)
check("all four voice services go through it, the exact rule is gone",
      init.count("without_entry(") == 4 and "def _without(" not in init)

if FAILURES:
    print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
    sys.exit(1)
print("all voice rules pass")
sys.exit(0)
