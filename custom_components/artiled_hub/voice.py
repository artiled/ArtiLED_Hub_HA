# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Voice choices: which room/zone + scene/mode a spoken name belongs to.

Pure rules with no Home Assistant import, so tests/test_voice.py loads this file
by path, the same way test_inventory.py loads inventory.py.

Scene and mode names ignore case when they are MATCHED (Michel 2026-09-10): the
Hub and every node already start a scene or mode whatever its capitals, so
"Relax" and "relax" are one scene. A stored entry keeps the spelling it was
added with - names are shown as written, only the comparison ignores case.
"""


def same_name(a, b) -> bool:
    """Two scene/mode names are the same name, ignoring capitals."""
    return str("" if a is None else a).lower() == str("" if b is None else b).lower()


def without_entry(chosen, kind, item_id, field, value):
    """Everything except this scope+item - so re-adding is a rename, not a
    duplicate, and removing works whatever capitals the name arrives in."""
    return [
        t for t in (chosen or [])
        if not (t["kind"] == kind and int(t["id"]) == int(item_id)
                and same_name(t.get(field), value))
    ]
