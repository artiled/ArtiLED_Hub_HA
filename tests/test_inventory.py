#!/usr/bin/env python3
# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Tests for the inventory rules — the logic that decides whether a customer's
entities appear, stay, or are destroyed.

Run:  python3 tests/test_inventory.py     (exit 0 = all pass)

No Home Assistant required. inventory.py is loaded straight from its path
rather than imported as part of the package, because custom_components/
artiled_hub/__init__.py pulls in Home Assistant at module level and would drag
the whole framework into a test of six pure functions.

⚠ WHY THIS FILE EXISTS. 0.4.0 shipped an hour-long delete grace that did
NOTHING: a config-entry reload built a new coordinator, the seen-map was
rebuilt with it, and anything just removed looked like it had never existed and
was deleted on the spot. It failed in exactly the case it was written for,
because a disappearance is itself what triggers the reload. It was caught by
luck - a real scene deleted by hand, and a registry check rather than an entity
count. test_grace_survives_a_reload below is that bug, pinned.
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

_SRC = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "artiled_hub" / "inventory.py"
_spec = importlib.util.spec_from_file_location("artiled_inventory", _SRC)
inv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(inv)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def hub(rooms=(), zones=(), lights=(), scenes=(), modes=(), flows=()):
    """A Hub poll result. `lights` takes (id, disabled) pairs."""
    return {
        "rooms": {i: {"id": i, "name": f"room{i}"} for i in rooms},
        "zones": {i: {"id": i, "name": f"zone{i}"} for i in zones},
        "lights": {i: {"id": i, "name": f"light{i}", "disabled": d} for i, d in lights},
        "scenes": {i: {"id": i} for i in scenes},
        "modes": {i: {"id": i} for i in modes},
        "flows": {i: {"id": i} for i in flows},
    }


FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok   {name}")
    else:
        print(f"  FAIL {name}" + (f" — {detail}" if detail else ""))
        FAILURES.append(name)


# --------------------------------------------------------------------------
# signature — what exists, and whether it is enabled. Drives the reload.
# --------------------------------------------------------------------------
print("signature")

sig = inv.signature(hub(rooms=[1], zones=[2], lights=[(3, 0), (4, 1)],
                        scenes=[5], modes=[6], flows=[7]))
check("covers every kind, not just lights",
      {("room", 1, True), ("zone", 2, True), ("scene", 5, True),
       ("mode", 6, True), ("flow", 7, True)} <= sig, str(sig))
check("an enabled light is flagged enabled", ("light", 3, True) in sig)
check("a disabled light is flagged NOT enabled", ("light", 4, False) in sig)
check("no data is None, not an empty Hub", inv.signature(None) is None)
check("empty dict is None too", inv.signature({}) is None)

# The reload trigger: these must differ, or re-enabling a light would never
# recreate its entity.
check("disabling a light changes the signature",
      inv.signature(hub(lights=[(3, 0)])) != inv.signature(hub(lights=[(3, 1)])))
check("deleting a light changes the signature",
      inv.signature(hub(lights=[(3, 0)])) != inv.signature(hub(lights=[])))


# --------------------------------------------------------------------------
# presence — the ONLY deletable set. Disabled is not deleted.
# --------------------------------------------------------------------------
print("\npresence — disable is not delete")

seen: dict = {}
inv.stamp_seen(hub(lights=[(3, 0), (4, 1)]), seen, 1000.0)
pres = inv.presence(seen, 1000.0)
check("a DISABLED light is still present (never deletable)", ("light", 4) in pres)
check("an enabled light is present", ("light", 3) in pres)
check("presence ignores the enabled flag entirely",
      pres == frozenset({("light", 3), ("light", 4)}), str(pres))

# The scenario Michel raised: a LED computer upgrade takes the node down and the
# Hub auto-disables that node's lights.
upgrade: dict = {}
inv.stamp_seen(hub(lights=[(3, 0), (4, 0)]), upgrade, 1000.0)          # before
inv.stamp_seen(hub(lights=[(3, 1), (4, 1)]), upgrade, 1010.0)          # during
check("a node upgrade disabling every light deletes nothing",
      inv.presence(upgrade, 1010.0) == frozenset({("light", 3), ("light", 4)}))


# --------------------------------------------------------------------------
# presence — the grace, and the clock it runs on
# --------------------------------------------------------------------------
print("\npresence — grace")

seen = {}
inv.stamp_seen(hub(scenes=[9]), seen, 1000.0)
# Scene deleted; later polls no longer mention it, so its stamp stops moving.
check("still protected just inside the grace",
      ("scene", 9) in inv.presence(seen, 1000.0 + inv.DELETE_GRACE_SECONDS - 1))
check("deletable just outside the grace",
      ("scene", 9) not in inv.presence(seen, 1000.0 + inv.DELETE_GRACE_SECONDS + 1))
check("custom grace is honoured",
      ("scene", 9) not in inv.presence(seen, 1100.0, grace=60))

# ⚠ The clock is the last SUCCESSFUL poll, never wall time.
check("an unreachable Hub ages NOTHING out",
      ("scene", 9) in inv.presence(seen, 1000.0),
      "last_success frozen at the last good poll, so nothing expires")
check("no successful poll yet is None, so nothing is deletable",
      inv.presence(seen, None) is None)


# --------------------------------------------------------------------------
# ⚠ the 0.4.0 bug, pinned
# --------------------------------------------------------------------------
print("\nregression — the grace must survive a reload")

# A reload constructs a NEW coordinator. The seen-map is handed to it from
# hass.data; it must NOT be rebuilt.
surviving: dict = {}
inv.stamp_seen(hub(scenes=[9]), surviving, 1000.0)   # scene exists
inv.stamp_seen(hub(scenes=[]), surviving, 1010.0)    # deleted -> reload happens

check("after a reload the deleted item is still protected",
      ("scene", 9) in inv.presence(surviving, 1010.0),
      "this is the 0.4.0 bug: it was deleted on the spot")
check("and it becomes deletable once the grace really elapses",
      ("scene", 9) not in inv.presence(surviving, 1010.0 + inv.DELETE_GRACE_SECONDS + 1))

# Sensitivity: prove the test can FAIL. A map rebuilt with the coordinator - the
# broken behaviour - loses the history and deletes immediately.
rebuilt: dict = {}
inv.stamp_seen(hub(scenes=[]), rebuilt, 1010.0)      # first poll after reload
check("a REBUILT map would delete immediately (test is sensitive)",
      ("scene", 9) not in inv.presence(rebuilt, 1010.0),
      "if this fails the regression test above proves nothing")


# --------------------------------------------------------------------------
# Un-expose before delete. Source-order checks rather than behaviour, because
# the real thing needs a running Home Assistant — but the ORDER is the whole
# invariant, and it is one edit away from being silently reversed.
print("\nun-expose before delete (a deleted-while-exposed entity strands a")
print("dead tile in the customer's Alexa app, and nothing can clean it up)")
import pathlib
SRC = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "artiled_hub" / "__init__.py"
src = SRC.read_text()
body = src[src.index("async def _prune_deleted("):]

check("_unexpose() exists", "def _unexpose(" in src)
check("it clears every assistant, not just Assist",
      "for assistant in ASSISTANTS" in src[src.index("def _unexpose("):],
      "Alexa is the one that strands tiles; conversation-only would miss it")

i_unexpose_dev = body.index("_unexpose(hass, doomed_entities)")
i_remove_dev = body.index("device_registry.async_remove_device(device.id)")
check("devices: un-expose comes BEFORE async_remove_device",
      i_unexpose_dev < i_remove_dev,
      "removing the device takes its entities with it — after that there is "
      "nothing left to un-expose")

i_unexpose_ent = body.index("_unexpose(hass, doomed)")
i_remove_ent = body.index("entity_registry.async_remove(entity_id)")
check("hub entities: un-expose comes BEFORE async_remove",
      i_unexpose_ent < i_remove_ent)

check("entity ids are collected BEFORE the device is removed",
      body.index("doomed_entities.extend") < i_remove_dev,
      "async_remove_device deletes its entities, so the ids must be read first")

check("the loop yields between un-exposing and deleting",
      "await asyncio.sleep(0)" in body,
      "un-exposing only SCHEDULES the cloud sync task; deleting in the same "
      "tick gives it no chance to run")

check("_prune_deleted is awaited at its call site",
      "await _prune_deleted(" in src,
      "making it async without awaiting it would silently skip the whole prune")

# --------------------------------------------------------------------------
# Re-auth. Source-level, because the real flow needs a running Home Assistant —
# but the failure mode is a DEAD END the user cannot escape, so the pieces that
# make it completable are worth pinning.
print("\nre-auth (a rejected token must not cost the customer their setup)")
CF = (pathlib.Path(__file__).resolve().parent.parent / "custom_components"
      / "artiled_hub" / "config_flow.py").read_text()

check("async_step_reauth exists", "async def async_step_reauth(" in CF,
      "__init__.py raises ConfigEntryAuthFailed; without this step HA shows a "
      "reconfigure prompt that can never be completed")
check("async_step_reauth_confirm exists", "async def async_step_reauth_confirm(" in CF)
check("re-auth updates and reloads the EXISTING entry",
      "async_update_reload_and_abort(" in CF,
      "creating a new entry instead would lose entity_ids, areas and history")
check("re-auth refuses a token from a DIFFERENT hub",
      'reason="wrong_hub"' in CF,
      "unique_ids are built from the hub ident — rebinding would strand every entity")
check("re-auth does not re-ask for the host",
      "REAUTH_SCHEMA" in CF and "CONF_HOST" not in CF.split("REAUTH_SCHEMA")[1].split(")")[0],
      "the token failed, not the address")

strings = json.loads((pathlib.Path(__file__).resolve().parent.parent / "custom_components"
                      / "artiled_hub" / "strings.json").read_text())
for key in ("reauth_confirm",):
    check(f"strings.json has the {key} step", key in strings["config"]["step"],
          "a step with no strings renders as a blank untitled form")
for key in ("reauth_successful", "reauth_failed", "wrong_hub"):
    check(f"strings.json has the {key} abort", key in strings["config"]["abort"])

en = json.loads((pathlib.Path(__file__).resolve().parent.parent / "custom_components"
                 / "artiled_hub" / "translations" / "en.json").read_text())
check("translations/en.json matches strings.json", en == strings,
      "HA reads translations/, not strings.json — drift means the UI shows keys")

# --------------------------------------------------------------------------
# Scoped scenes for voice — opt-in, never generated.
print("\nscoped scenes (opt-in: ~620 pairs exist, only spoken ones become entities)")
SC = (pathlib.Path(__file__).resolve().parent.parent / "custom_components"
      / "artiled_hub" / "scene.py").read_text()
IN = (pathlib.Path(__file__).resolve().parent.parent / "custom_components"
      / "artiled_hub" / "__init__.py").read_text()

check("a scoped scene entity class exists", "class ArtiHubScopedScene(" in SC)
check("scoped scenes come from stored choices, not from the Hub inventory",
      'data.get("voice_scenes")' in SC,
      "generating every room x scene pair is ~620 entities, all Alexa-eligible")
check("the user's name is used verbatim",
      "_attr_has_entity_name = False" in SC.split("class ArtiHubScopedScene(")[1],
      "with has_entity_name True, HA prefixes the device: 'Cinema Cinema'")
check("activation carries the SCOPE",
      "{self._kind: self._item_id}" in SC,
      "a bare scene id fires across every light in the house")
check("the scoped scene hangs off the room/zone device",
      'f"{data[\'hub_ident\']}_{self._kind}_{self._item_id}"' in SC,
      "so deleting the room takes its scoped scenes with it")

check("add/remove services exist",
      'DOMAIN, "add_voice_scene"' in IN and 'DOMAIN, "remove_voice_scene"' in IN)
check("choosing one reloads so the entity appears now",
      "async_reload(data[\"entry_id\"])" in IN,
      "the scene platform builds entities at setup; without a reload the tick "
      "does nothing until the next restart")
check("exactly one scope is enforced",
      "_exactly_one_scope" in IN,
      "neither is not house-wide, it is a mistake; both is meaningless")
VO = (pathlib.Path(__file__).resolve().parent.parent / "custom_components"
      / "artiled_hub" / "voice.py").read_text()
check("re-adding the same pair replaces rather than duplicates",
      "so re-adding is a rename" in VO and "from .voice import without_entry" in IN,
      "the rule lives in voice.py (names ignore case, 2026-09-10); tests/test_voice.py pins its behaviour")

print("\nscoped modes (a SWITCH — a mode runs until stopped)")
SW = (pathlib.Path(__file__).resolve().parent.parent / "custom_components"
      / "artiled_hub" / "switch.py").read_text()
scoped_sw = SW.split("class ArtiHubScopedMode(")[1]

check("a scoped mode switch class exists", "class ArtiHubScopedMode(" in SW)
check("it is a SwitchEntity, not a Scene", "SwitchEntity" in SW.split("class ArtiHubScopedMode(")[0])
check("scoped modes come from stored choices",
      'data.get("voice_modes")' in SW)
check("the user's name is used verbatim",
      "_attr_has_entity_name = False" in scoped_sw)
check("is_on reads THIS SCOPE only",
      "self._item()" in scoped_sw and "for group in" not in scoped_sw,
      "the house-wide switch returns True if the mode runs in ANY scope, so "
      "Music in the kitchen would light up the bedroom's switch")
check("turn_on and turn_off both carry the scope",
      scoped_sw.count("{self._kind: self._item_id}") >= 2)
check("turn_off actually stops it (running=0)", "running=0" in scoped_sw)
check("add/remove mode services exist",
      'DOMAIN, "add_voice_mode"' in IN and 'DOMAIN, "remove_voice_mode"' in IN)

# ⚠ the bug this pins: saving one list must not erase the other
check("saving writes BOTH scenes and modes",
      '{"scenes": scenes, "modes": modes}' in IN,
      "the first scene service saved only {'scenes': ...}, which would have "
      "deleted every scoped mode the moment a scene was added")

# --------------------------------------------------------------------------
# Service targeting — the two defects Mycroft found reviewing 0.26.0.
# ⚠ These EXERCISE the real schema rather than grepping for it: both bugs were
# silent, so only running the validator proves they are closed.
print("\nservice targeting (both of these used to fail SILENTLY)")
try:
    import voluptuous as vol
except ImportError:
    print("  skip  voluptuous not installed")
else:
    _src = (pathlib.Path(__file__).resolve().parent.parent / "custom_components"
            / "artiled_hub" / "__init__.py").read_text()
    _ns = {"vol": vol}
    for _block in ("def _exactly_one_target", "def _exactly_one_scope"):
        _i = _src.index(_block)
        exec(_src[_i:_src.index("\n\n\n", _i)], _ns)
    for _name, _start in (("COLOR_SCHEMA", "COLOR_SCHEMA = vol.All("),
                          ("VOICE_SCENE_SCHEMA", "VOICE_SCENE_SCHEMA = vol.All(")):
        _i = _src.index(_start)
        exec(_src[_i:_src.index("\n)\n", _i) + 3], _ns)

    def _ok(schema, data):
        try:
            schema(data)
            return True
        except vol.Invalid:
            return False

    CS, VS = _ns["COLOR_SCHEMA"], _ns["VOICE_SCENE_SCHEMA"]
    base = {"rgbw": [1, 2, 3, 0]}
    check("set_color: one target is fine", _ok(CS, {**base, "room": 15}))
    check("set_color: TWO targets are refused",
          not _ok(CS, {**base, "room": 15, "light": 8}),
          "the handler picked light by precedence and left the room alone - a "
          "wrong target with no error")
    check("set_color: NO target is refused", not _ok(CS, base),
          "the handler simply returned, so the call looked like it worked")
    check("set_color: a NAME is refused where an id is required",
          not _ok(CS, {**base, "room": "Livingroom"}),
          "services.yaml advertised names while the handler int()'d them, so a "
          "name raised ValueError deep inside")
    check("set_color: a numeric string still coerces",
          _ok(CS, {**base, "room": "15"}))
    check("set_color: hub is accepted", _ok(CS, {**base, "room": 15, "hub": "X"}))
    check("voice services: hub is accepted",
          _ok(VS, {"scene": "Cinema", "name": "N", "room": 15, "hub": "X"}))
    check("voice services: still exactly one scope",
          not _ok(VS, {"scene": "C", "name": "N", "room": 15, "zone": 16}))

    # ⚠ The multi-Hub bug: never silently pick one of several.
    check("_entry_data replaced _first_entry_data everywhere",
          "_first_entry_data" not in _src and _src.count("_entry_data(call)") >= 9,
          "next(iter(entries.values())) sent every global service to whichever "
          "Hub HA set up first - no error, wrong house")
    check("more than one Hub without 'hub' raises",
          "More than one ArtiLED Hub is configured" in _src)
    check("the error names the choices", 'Known: ' in _src)

# services.yaml must agree with the schemas, or the UI lies about the call.
import yaml
_svc = yaml.safe_load(
    (pathlib.Path(__file__).resolve().parent.parent / "custom_components"
     / "artiled_hub" / "services.yaml").read_text())
check("every service documents the hub field",
      all("hub" in (v.get("fields") or {}) for v in _svc.values()),
      "a multi-Hub install cannot target a Hub it is not told about")
check("set_color no longer advertises names",
      "or name" not in (_svc["set_color"]["fields"]["room"]["description"]),
      "code, schema and docs must agree on ids")

# --------------------------------------------------------------------------
print()
if FAILURES:
    print(f"{len(FAILURES)} FAILED: {', '.join(FAILURES)}")
    sys.exit(1)
print("all inventory rules pass")
sys.exit(0)
