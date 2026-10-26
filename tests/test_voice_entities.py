#!/usr/bin/env python3
# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Voice scenes as Home Assistant 2026.10 really names, exposes and removes them.

Run:  python3 tests/test_voice_entities.py     (exit 0 = all pass)

No Home Assistant on this VM. The integration is loaded AS SHIPPED (scene.py
and __init__.py, by path) against small stand-ins for the Home Assistant pieces
it touches. Each stand-in records what was done to it, so a test asks "what is
the name?", "what was exposed?" instead of trusting a log line.

WHY THIS FILE EXISTS (Michel 2026-10-26, measured on the Control's master on
HA 2026.10.4, same pattern here):
- A voice scene on the room's device read "Kitchen Relax time": HA 2026.10
  names any entity ON A DEVICE "<device> <name>" even with has_entity_name
  False (helpers/entity_registry.py async_get_legacy_friendly_name) and its
  entity_id "<area> <device> <name>" (_async_generate_entity_id).
- No assistant heard a new one: every entity we create was defaulted to
  "exposed to nothing", including the scene someone had just asked for.
- Removed and added again, it came back under its OLD id: HA keeps a
  DeletedRegistryEntry and restores entity_id/options from it - and up to
  0.32.1 the Hub did not even delete the registry entry on remove.

The stand-in registry below names entities the way HA 2026.10 does and keeps
deleted entries, so these cases fail on 0.32.1 and pass after.
"""
from __future__ import annotations

import asyncio
import enum
import importlib.abc
import importlib.machinery
import importlib.util
import pathlib
import re
import sys
import types

PKG_DIR = pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "artiled_hub"
IDENT = "hub0test01"
DOMAIN = "artiled_hub"
ASSIST = ("conversation", "cloud.alexa", "cloud.google_assistant")

FAILURES: list[str] = []
PASSED = [0]


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if condition else 'FAIL'}  {name}")
    if condition:
        PASSED[0] += 1
    else:
        FAILURES.append(name)
        if detail:
            print(f"        {detail}")


# ---------------------------------------------------------------------------
# Home Assistant stand-ins
# ---------------------------------------------------------------------------

class _Anything:
    """Whatever an unused Home Assistant name is - importable, never called here."""

    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _Anything()

    def __getattr__(self, name):
        return _Anything()


class _StubModule(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        value = type(name, (_Anything,), {})
        setattr(self, name, value)
        return value


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Any homeassistant.* (and aiohttp, if absent) module not set up below."""

    ROOTS = ("homeassistant", "aiohttp")

    def find_spec(self, fullname, path, target=None):
        if fullname.split(".")[0] in self.ROOTS:
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        mod = _StubModule(spec.name)
        mod.__path__ = []
        return mod

    def exec_module(self, module):
        pass


try:
    import aiohttp  # noqa: F401
    _StubFinder.ROOTS = ("homeassistant",)
except ImportError:
    pass
sys.meta_path.insert(0, _StubFinder())


def _module(name: str, **attrs) -> types.ModuleType:
    mod = importlib.import_module(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    return mod


def slugify(text) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(text).lower()).strip("_") or "unknown"


class HomeAssistantError(Exception):
    pass


class ServiceValidationError(HomeAssistantError):
    pass


class Store:
    """helpers.storage.Store over hass.storage (key -> data)."""

    def __init__(self, hass, version, key):
        self.hass, self.key = hass, key

    async def async_load(self):
        import copy
        return copy.deepcopy(self.hass.storage.get(self.key))

    async def async_save(self, data):
        import copy
        self.hass.storage[self.key] = copy.deepcopy(data)


class RegistryEntry:
    def __init__(self, entity_id, unique_id, platform, config_entry_id, device_id):
        self.entity_id, self.unique_id, self.platform = entity_id, unique_id, platform
        self.config_entry_id, self.device_id = config_entry_id, device_id
        self.hidden_by = None
        self.disabled_by = None


class RegistryEntryHider(str, enum.Enum):
    INTEGRATION = "integration"
    USER = "user"


class EntityRegistry:
    """helpers.entity_registry as core 2026.10.4 behaves for us.

    ⚠ Keeps a removed entry as a deleted entry keyed (domain, platform,
    unique_id) and RESTORES its entity_id when that unique_id comes back
    (async_get_or_create), exactly what made a re-added voice scene reappear
    under its old id.
    """

    def __init__(self, hass):
        self.hass = hass
        self.entities: dict[str, RegistryEntry] = {}
        self.deleted_entities: dict[tuple[str, str, str], types.SimpleNamespace] = {}
        self.saves = 0

    def async_schedule_save(self):
        self.saves += 1

    def async_get(self, entity_id):
        return self.entities.get(entity_id)

    def async_get_entity_id(self, domain, platform, unique_id):
        for entry in self.entities.values():
            if entry.entity_id.startswith(domain + ".") and entry.platform == platform and entry.unique_id == unique_id:
                return entry.entity_id
        return None

    def get_or_create(self, domain, platform, unique_id, config_entry_id, suggested, device_id):
        existing = self.async_get_entity_id(domain, platform, unique_id)
        if existing:
            self.entities[existing].device_id = device_id   # HA: follows the entity's device
            return self.entities[existing]
        base = f"{domain}.{slugify(suggested)}"
        entity_id, n = base, 2
        while entity_id in self.entities:
            entity_id, n = f"{base}_{n}", n + 1
        deleted = self.deleted_entities.pop((domain, platform, unique_id), None)
        if deleted is not None and deleted.entity_id not in self.entities:
            entity_id = deleted.entity_id
            for assistant, should in deleted.exposure.items():   # options come back too
                self.hass.exposure[(assistant, entity_id)] = should
        entry = RegistryEntry(entity_id, unique_id, platform, config_entry_id, device_id)
        self.entities[entity_id] = entry
        return entry

    def async_update_entity(self, entity_id, new_entity_id=None, hidden_by=None):
        entry = self.entities[entity_id]
        if hidden_by is not None:
            entry.hidden_by = hidden_by
        if new_entity_id and new_entity_id != entity_id:
            del self.entities[entity_id]
            entry.entity_id = new_entity_id
            self.entities[new_entity_id] = entry
            for (assistant, eid), should in list(self.hass.exposure.items()):
                if eid == entity_id:
                    self.hass.exposure[(assistant, new_entity_id)] = should
        return entry

    def async_remove(self, entity_id):
        entry = self.entities.pop(entity_id, None)
        self.hass.log.append(("remove", entity_id))
        if entry is None:
            return
        exposure = {a: s for (a, eid), s in self.hass.exposure.items() if eid == entity_id}
        key = (entity_id.split(".", 1)[0], entry.platform, entry.unique_id)
        self.deleted_entities[key] = types.SimpleNamespace(entity_id=entity_id, exposure=exposure)
        self.hass.live.pop(entity_id, None)
        self.hass.states.pop(entity_id, None)


def _entries_for_config_entry(registry, entry_id):
    return [e for e in registry.entities.values() if e.config_entry_id == entry_id]


def _entries_for_device(registry, device_id, include_disabled_entities=False):
    return [e for e in registry.entities.values() if e.device_id == device_id]


class Device:
    def __init__(self, device_id, identifiers, config_entry_id, name, area):
        self.id, self.identifiers = device_id, set(identifiers)
        self.config_entry_id, self.name, self.area = config_entry_id, name, area


class DeviceRegistry:
    def __init__(self):
        self.devices: dict[str, Device] = {}

    def add(self, entry_id, ident, name, area=None):
        device = Device(f"dev_{ident}", {(DOMAIN, ident)}, entry_id, name, area)
        self.devices[device.id] = device
        return device

    def async_get_device(self, identifiers):
        for device in self.devices.values():
            if device.identifiers & set(identifiers):
                return device
        return None

    def async_remove_device(self, device_id):
        self.devices.pop(device_id, None)


def _devices_for_config_entry(registry, entry_id):
    return [d for d in registry.devices.values() if d.config_entry_id == entry_id]


def async_expose_entity(hass, assistant, entity_id, should_expose):
    hass.log.append(("expose", assistant, entity_id, should_expose))
    hass.exposure[(assistant, entity_id)] = should_expose


def async_should_expose(hass, assistant, entity_id):
    return hass.exposure.get((assistant, entity_id), False)


class Scene:
    hass = None
    entity_id = None
    _attr_has_entity_name = False
    _attr_entity_registry_visible_default = True
    _attr_device_info = None
    _attr_name = None
    _attr_unique_id = None

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def extra_state_attributes(self):
        return None


class SwitchEntity(Scene):
    pass


class CoordinatorEntity:
    def __init__(self, coordinator, context=None):
        self.coordinator = coordinator


_module("homeassistant.util", slugify=slugify)
_module("homeassistant.core", callback=lambda f: f, HomeAssistant=object, ServiceCall=object)
_module("homeassistant.exceptions", HomeAssistantError=HomeAssistantError,
        ServiceValidationError=ServiceValidationError,
        ConfigEntryAuthFailed=type("ConfigEntryAuthFailed", (HomeAssistantError,), {}),
        ConfigEntryNotReady=type("ConfigEntryNotReady", (HomeAssistantError,), {}))
_module("homeassistant.helpers.storage", Store=Store)
_module("homeassistant.helpers.entity_registry", async_get=lambda hass: hass.entity_registry,
        async_entries_for_config_entry=_entries_for_config_entry,
        async_entries_for_device=_entries_for_device, RegistryEntryHider=RegistryEntryHider)
_module("homeassistant.helpers.device_registry", async_get=lambda hass: hass.device_registry,
        async_entries_for_config_entry=_devices_for_config_entry, DeviceInfo=dict)
_module("homeassistant.helpers", entity_registry=sys.modules["homeassistant.helpers.entity_registry"],
        device_registry=sys.modules["homeassistant.helpers.device_registry"])
_module("homeassistant.components.homeassistant.exposed_entities",
        async_expose_entity=async_expose_entity, async_should_expose=async_should_expose)
_module("homeassistant.components.scene", Scene=Scene)
_module("homeassistant.components.switch", SwitchEntity=SwitchEntity)
_module("homeassistant.helpers.update_coordinator", CoordinatorEntity=CoordinatorEntity)


def _load_package():
    spec = importlib.util.spec_from_file_location(
        DOMAIN, PKG_DIR / "__init__.py", submodule_search_locations=[str(PKG_DIR)])
    pkg = importlib.util.module_from_spec(spec)
    sys.modules[DOMAIN] = pkg
    spec.loader.exec_module(pkg)
    return pkg, importlib.import_module(f"{DOMAIN}.scene"), importlib.import_module(f"{DOMAIN}.switch")


hub, scene_mod, switch_mod = _load_package()


# ---------------------------------------------------------------------------
# A Home Assistant, a Hub entry
# ---------------------------------------------------------------------------

class Services:
    def __init__(self):
        self.handlers = {}

    def has_service(self, domain, service):
        return (domain, service) in self.handlers

    def async_register(self, domain, service, handler, schema=None):
        self.handlers[(domain, service)] = (handler, schema)

    async def call(self, domain, service, data):
        handler, schema = self.handlers[(domain, service)]
        await handler(types.SimpleNamespace(data=schema(data) if schema else data))


class ConfigEntries:
    def __init__(self, hass):
        self.hass = hass

    async def async_reload(self, entry_id):
        """What a reload does to the voice scenes: the platform builds them
        again from the stored choices, then the voice defaults run."""
        data = self.hass.data[DOMAIN][entry_id]
        voice = await data["voice_store"].async_load() or {}
        data["voice_scenes"] = voice.get("scenes") or []
        data["voice_modes"] = voice.get("modes") or []
        await self.hass.setup_scenes()
        await hub._voice_defaults_once(self.hass, self.hass.entry)


class FakeHass:
    def __init__(self):
        self.storage: dict = {}
        self.exposure: dict = {}
        self.log: list = []
        self.live: dict = {}
        self.states: dict = {}
        self.entity_registry = EntityRegistry(self)
        self.device_registry = DeviceRegistry()
        self.services = Services()
        self.config_entries = ConfigEntries(self)
        self.entry = types.SimpleNamespace(entry_id="e1")
        self.data: dict = {}

    def register(self, entity, domain):
        """What entity_platform + entity_registry do for one entity, named the
        way Home Assistant 2026.10 names it."""
        info = entity._attr_device_info
        device = None
        if info:
            device = self.device_registry.async_get_device(info["identifiers"])
        own = entity._attr_name
        if entity._attr_has_entity_name:
            suggested = friendly = " ".join(p for p in (device and device.name, own) if p)
        elif device is not None:
            # ⚠ HA 2026.10 LEGACY naming (has_entity_name False) on an entity WITH
            # a device: friendly "<device> <name>", entity_id "<area> <device>
            # <name>", the name's own device prefix stripped first.
            bare = own or ""
            if bare.lower().startswith(device.name.lower() + " "):
                bare = bare[len(device.name) + 1:]
            suggested = " ".join(p for p in (device.area, device.name, bare) if p)
            friendly = " ".join(p for p in (device.name, bare) if p)
        else:
            suggested = friendly = own
        reg = self.entity_registry.get_or_create(
            domain, DOMAIN, entity.unique_id, self.entry.entry_id, suggested, device and device.id)
        entity.entity_id = reg.entity_id
        entity.hass = self
        self.live[reg.entity_id] = entity
        attrs = dict(entity.extra_state_attributes or {})
        attrs["friendly_name"] = friendly
        self.states[reg.entity_id] = attrs

    async def setup_scenes(self):
        """The scene AND switch platforms (voice scenes and voice modes)."""
        for eid in [e for e in self.live if e.startswith(("scene.", "switch."))]:
            self.live.pop(eid)
            self.states.pop(eid, None)
        for domain, mod in (("scene", scene_mod), ("switch", switch_mod)):
            added = []
            await mod.async_setup_entry(self, self.entry, added.extend)
            for entity in added:
                self.register(entity, domain)


class Client:
    async def run_scene(self, *args):
        pass


class Coordinator:
    def __init__(self, present):
        self.present = present

    async def async_request_refresh(self):
        pass


async def make_hass(voice_scenes=(), present=None, voice_modes=()):
    hass = FakeHass()
    entry_id = hass.entry.entry_id
    hass.device_registry.add(entry_id, IDENT, "Hub")
    hass.device_registry.add(entry_id, f"{IDENT}_room_7", "Kitchen", area="Kitchen")
    hass.device_registry.add(entry_id, f"{IDENT}_zone_3", "Cinewall", area="Living Room")
    store = Store(hass, 1, f"{DOMAIN}_{entry_id}_voice")
    await store.async_save({"scenes": list(voice_scenes), "modes": list(voice_modes)})
    hass.data[DOMAIN] = {entry_id: {
        "client": Client(),
        "coordinator": Coordinator(present if present is not None
                                   else frozenset({("room", 7), ("zone", 3), ("scene", 5), ("mode", 2)})),
        "entry_id": entry_id,
        "hub_ident": IDENT,
        "hub_name": "Hub",
        "scenes": [{"id": 5, "name": "Sunset"}],
        "modes": [{"id": 2, "name": "Music"}],
        "voice_scenes": list(voice_scenes),
        "voice_modes": list(voice_modes),
        "voice_store": store,
    }}
    # The room/zone lights (light.py: unique_id "<ident>_<kind>_<id>").
    for ident, eid in ((f"{IDENT}_room_7", "light.kitchen"), (f"{IDENT}_zone_3", "light.cinewall")):
        device = hass.device_registry.async_get_device({(DOMAIN, ident)})
        hass.entity_registry.entities[eid] = RegistryEntry(eid, ident, DOMAIN, entry_id, device.id)
    # Home Assistant Cloud as core 2026.10.4 keeps it: hass.data[DATA_CLOUD]
    # (HassKey "cloud") with is_logged_in and client.prefs.alexa_enabled /
    # google_enabled. Here: logged in, Alexa on, Google off.
    hass.data["cloud"] = types.SimpleNamespace(is_logged_in=True, client=types.SimpleNamespace(
        prefs=types.SimpleNamespace(alexa_enabled=True, google_enabled=False)))
    hub._register_services(hass)
    return hass


def scene_ids(hass):
    return sorted(e for e in hass.entity_registry.entities if e.startswith("scene."))


def flags(hass):
    return (hass.storage.get(f"{DOMAIN}_e1_flags") or {}).get("voice_defaults") or []


UID = f"{IDENT}_voice_scene_room_7_relax"


# ---------------------------------------------------------------------------

async def naming():
    print("\nthe spoken name is the whole name (HA 2026.10 prefixes a device's)")
    hass = await make_hass([{"kind": "room", "id": 7, "scene": "Relax", "name": "Relax time"}])
    await hass.setup_scenes()
    check("the entity_id is the spoken name's slug - no area, no device prefix",
          "scene.relax_time" in hass.entity_registry.entities, str(scene_ids(hass)))
    attrs = hass.states.get("scene.relax_time") or {}
    check("the friendly name is EXACTLY the spoken name",
          attrs.get("friendly_name") == "Relax time", str(attrs.get("friendly_name")))
    reg = hass.entity_registry.async_get("scene.relax_time")
    check("the voice scene is on no device", reg is not None and reg.device_id is None)
    check("its unique_id is unchanged (the existing scenes keep their entries)",
          reg is not None and reg.unique_id == UID)
    check("it still says which scope + scene it runs",
          attrs.get("artiled_scope") == "room_7" and attrs.get("artiled_item") == "Relax")
    house = hass.entity_registry.async_get("scene.hub_sunset")
    hub_dev = hass.device_registry.async_get_device({(DOMAIN, IDENT)})
    check("the house-wide scene is unchanged: on the Hub device, 'Hub Sunset', hidden by default",
          house is not None and house.device_id == hub_dev.id
          and hass.states["scene.hub_sunset"]["friendly_name"] == "Hub Sunset"
          and hass.entity_registry.async_get("switch.hub_mode_music").device_id == hub_dev.id
          and hass.live["scene.hub_sunset"]._attr_entity_registry_visible_default is False,
          str(scene_ids(hass)))

    # An install from before: its entry still on the room device moves off it.
    old = await make_hass([{"kind": "room", "id": 7, "scene": "Relax", "name": "Relax time"}])
    room = old.device_registry.async_get_device({(DOMAIN, f"{IDENT}_room_7")})
    old.entity_registry.entities["scene.relax_time"] = RegistryEntry(
        "scene.relax_time", UID, DOMAIN, "e1", room.id)
    await old.setup_scenes()
    check("an existing entry keeps its entity_id and leaves the room device",
          old.entity_registry.async_get("scene.relax_time").device_id is None)


async def defaults():
    print("\na voice scene someone ADDS is heard: Assist + every enabled cloud assistant - once")
    hass = await make_hass()
    # The rooms are known and defaulted earlier, and exposed to NOTHING - the
    # live case (Michel 2026-10-26): scene.kitchen_aurora followed its room
    # into silence and Alexa said "Kitchen doesn't support that".
    hass.storage[f"{DOMAIN}_e1_flags"] = {"voice_defaults": [f"{IDENT}_room_7", f"{IDENT}_zone_3"]}
    await hass.setup_scenes()
    await hub._voice_defaults_once(hass, hass.entry)
    check("the house-wide scene keeps the plain default: exposed to nothing",
          all(hass.exposure.get((a, "scene.hub_sunset")) is False for a in ASSIST))

    await hass.services.call(DOMAIN, "add_voice_scene", {"room": 7, "scene": "Relax", "name": "Relax time"})
    check("exposed to Assist and to Alexa (enabled) although the room is exposed to nothing",
          hass.exposure.get(("conversation", "scene.relax_time")) is True
          and hass.exposure.get(("cloud.alexa", "scene.relax_time")) is True,
          str({k: v for k, v in hass.exposure.items() if k[1] == "scene.relax_time"}))
    check("...and not to Google, which is not enabled in this Home Assistant",
          hass.exposure.get(("cloud.google_assistant", "scene.relax_time")) is False)
    check("recorded once-only", UID in flags(hass))

    hass.exposure[("cloud.alexa", "scene.relax_time")] = False      # the user changes it
    hass.data["cloud"].client.prefs.google_enabled = True            # and switches Google on
    await hass.config_entries.async_reload("e1")
    check("applied ONCE: a later user change stands across a reload",
          hass.exposure.get(("cloud.alexa", "scene.relax_time")) is False
          and hass.exposure.get(("cloud.google_assistant", "scene.relax_time")) is False
          and hass.exposure.get(("conversation", "scene.relax_time")) is True)

    await hass.services.call(DOMAIN, "add_voice_scene", {"room": 7, "scene": "Relax", "name": "Chill out"})
    check("a rename keeps the entity and its exposure",
          "scene.relax_time" in hass.entity_registry.entities
          and hass.states["scene.relax_time"]["friendly_name"] == "Chill out"
          and hass.exposure.get(("conversation", "scene.relax_time")) is True, str(scene_ids(hass)))

    await hass.services.call(DOMAIN, "add_voice_scene", {"zone": 3, "scene": "Movie", "name": "Movie night"})
    check("a zone exposed to nothing: its new voice scene is still heard (Assist, Alexa, Google now on)",
          all(hass.exposure.get((a, "scene.movie_night")) is True for a in ASSIST), str(scene_ids(hass)))
    check("the zone itself is left as it was (exposed to nothing)",
          all(not hass.exposure.get((a, "light.cinewall")) for a in ASSIST))

    print("\nno Home Assistant Cloud, or logged out: Assist only")
    for cloud in (None, types.SimpleNamespace(is_logged_in=False, client=types.SimpleNamespace(
            prefs=types.SimpleNamespace(alexa_enabled=True, google_enabled=True)))):
        h = await make_hass()
        h.storage[f"{DOMAIN}_e1_flags"] = {"voice_defaults": [f"{IDENT}_room_7", f"{IDENT}_zone_3"]}
        if cloud is None:
            h.data.pop("cloud")
        else:
            h.data["cloud"] = cloud
        await h.setup_scenes()
        await h.services.call(DOMAIN, "add_voice_scene", {"room": 7, "scene": "Relax", "name": "Relax time"})
        check(f"{'no cloud' if cloud is None else 'cloud logged out'}: exposed to Assist, not to Alexa/Google",
              h.exposure.get(("conversation", "scene.relax_time")) is True
              and h.exposure.get(("cloud.alexa", "scene.relax_time")) is False
              and h.exposure.get(("cloud.google_assistant", "scene.relax_time")) is False)

    print("\na first setup that defaults the room AND its voice scene in one pass")
    first = await make_hass([{"kind": "room", "id": 7, "scene": "Relax", "name": "Relax time"}])
    await first.setup_scenes()
    # Registered before the light, so a plain registry walk would reach the
    # scene first and copy the room's PRE-default exposure (Assist on, HA's own).
    light = first.entity_registry.entities.pop("light.kitchen")
    first.entity_registry.entities["light.kitchen"] = light
    first.exposure[("conversation", "light.kitchen")] = True
    await hub._voice_defaults_once(first, first.entry)
    check("the room gets the plain default (nothing), the voice scene is heard regardless",
          first.exposure.get(("conversation", "light.kitchen")) is False
          and first.exposure.get(("conversation", "scene.relax_time")) is True
          and first.exposure.get(("cloud.alexa", "scene.relax_time")) is True)


async def removal():
    print("\nremoved: nothing left behind, a re-add is clean")
    hass = await make_hass()
    hass.storage[f"{DOMAIN}_e1_flags"] = {"voice_defaults": [f"{IDENT}_room_7", f"{IDENT}_zone_3"]}
    hass.exposure[("cloud.alexa", "light.kitchen")] = True
    await hass.setup_scenes()
    await hass.services.call(DOMAIN, "add_voice_scene", {"room": 7, "scene": "Relax", "name": "Relax time"})
    hass.entity_registry.async_update_entity(   # the user renames it
        hass.entity_registry.async_get_entity_id("scene", DOMAIN, UID), new_entity_id="scene.my_relax")
    hass.log.clear()

    await hass.services.call(DOMAIN, "remove_voice_scene", {"room": 7, "scene": "relax"})
    stored = (hass.storage.get(f"{DOMAIN}_e1_voice") or {}).get("scenes")
    check("the choice is gone from the store", stored == [], str(stored))
    check("removed: no registry entry", "scene.my_relax" not in hass.entity_registry.entities, str(scene_ids(hass)))
    check("un-exposed BEFORE it was deleted (no dead Alexa tile)",
          ("expose", "cloud.alexa", "scene.my_relax", False) in hass.log
          and hass.log.index(("expose", "cloud.alexa", "scene.my_relax", False))
          < hass.log.index(("remove", "scene.my_relax")), str(hass.log))
    check("removed: no deleted-entry leftover HA would restore the old id from",
          not any(k[2] == UID for k in hass.entity_registry.deleted_entities),
          str(list(hass.entity_registry.deleted_entities)))
    check("removed: its once-only voice default is forgotten, so a re-add is new", UID not in flags(hass))
    check("the room's own entity and default are untouched",
          "light.kitchen" in hass.entity_registry.entities and f"{IDENT}_room_7" in flags(hass))

    hass.data["cloud"].client.prefs.google_enabled = True
    await hass.services.call(DOMAIN, "add_voice_scene", {"room": 7, "scene": "Relax", "name": "Relax time"})
    check("re-added: the clean entity_id again, not the old one",
          "scene.relax_time" in hass.entity_registry.entities
          and "scene.my_relax" not in hass.entity_registry.entities, str(scene_ids(hass)))
    check("re-added: exposed again by the rule as it is now (Alexa, Google on)",
          hass.exposure.get(("cloud.alexa", "scene.relax_time")) is True
          and hass.exposure.get(("cloud.google_assistant", "scene.relax_time")) is True)

    print("\na leftover from 0.32.1 (removed there, registry entry kept) does not come back")
    old = await make_hass()
    old.storage[f"{DOMAIN}_e1_flags"] = {"voice_defaults": [f"{IDENT}_room_7", f"{IDENT}_zone_3", UID]}
    old.exposure[("conversation", "light.kitchen")] = True
    room = old.device_registry.async_get_device({(DOMAIN, f"{IDENT}_room_7")})
    old.entity_registry.entities["scene.kitchen_kitchen_relax_time"] = RegistryEntry(
        "scene.kitchen_kitchen_relax_time", UID, DOMAIN, "e1", room.id)
    old.exposure[("conversation", "scene.kitchen_kitchen_relax_time")] = False
    await old.setup_scenes()
    await old.services.call(DOMAIN, "add_voice_scene", {"room": 7, "scene": "Relax", "name": "Relax time"})
    check("added again: the clean entity_id, not the leftover's",
          scene_ids(old) == ["scene.hub_sunset", "scene.relax_time"], str(scene_ids(old)))
    check("added again: heard (the leftover's once-only flag is gone)",
          old.exposure.get(("conversation", "scene.relax_time")) is True)


async def prune():
    print("\na room deleted on the Hub takes its voice scenes along (they are on no device now)")
    choices = [{"kind": "room", "id": 7, "scene": "Relax", "name": "Relax time"},
               {"kind": "zone", "id": 3, "scene": "Movie", "name": "Movie night"}]
    hass = await make_hass(choices)
    await hass.setup_scenes()
    hass.exposure[("cloud.alexa", "scene.relax_time")] = True
    data = hass.data[DOMAIN]["e1"]
    data["coordinator"].present = frozenset({("zone", 3), ("scene", 5)})   # room 7 gone past the grace
    hass.log.clear()
    await hub._prune_deleted(hass, hass.entry, IDENT, data["coordinator"])
    stored = (hass.storage.get(f"{DOMAIN}_e1_voice") or {}).get("scenes")
    check("its choice is dropped from the store (the platform would build it again)",
          stored == [choices[1]] and data["voice_scenes"] == [choices[1]], str(stored))
    check("its registry entry is gone, un-exposed first",
          "scene.relax_time" not in hass.entity_registry.entities
          and ("expose", "cloud.alexa", "scene.relax_time", False) in hass.log
          and ("remove", "scene.relax_time") in hass.log
          and hass.log.index(("expose", "cloud.alexa", "scene.relax_time", False))
          < hass.log.index(("remove", "scene.relax_time")), str(hass.log))
    check("no deleted-entry leftover", not any(k[2] == UID for k in hass.entity_registry.deleted_entities))
    check("the other zone's voice scene stays", "scene.movie_night" in hass.entity_registry.entities)
    hass2 = await make_hass(choices, present=None)
    hass2.data[DOMAIN]["e1"]["coordinator"].present = None
    await hass2.setup_scenes()
    await hub._prune_deleted(hass2, hass2.entry, IDENT, hass2.data[DOMAIN]["e1"]["coordinator"])
    check("no Hub data yet: nothing is pruned", len(hass2.data[DOMAIN]["e1"]["voice_scenes"]) == 2
          and "scene.relax_time" in hass2.entity_registry.entities)


MUID = f"{IDENT}_voice_mode_room_7_music"


def switch_ids(hass):
    return sorted(e for e in hass.entity_registry.entities if e.startswith("switch."))


async def modes():
    """Voice MODES (switches) are built the same way as voice scenes and had
    the same three faults (Michel 2026-10-26: same fix)."""
    print("\nvoice modes: the spoken name, heard, cleanly removed")
    hass = await make_hass(voice_modes=[{"kind": "room", "id": 7, "mode": "Music", "name": "Party time"}])
    await hass.setup_scenes()
    check("mode: the entity_id is the spoken name's slug", "switch.party_time" in hass.entity_registry.entities,
          str(switch_ids(hass)))
    check("mode: the friendly name is EXACTLY the spoken name",
          (hass.states.get("switch.party_time") or {}).get("friendly_name") == "Party time")
    reg = hass.entity_registry.async_get("switch.party_time")
    check("mode: on no device, unique_id unchanged", reg is not None and reg.device_id is None and reg.unique_id == MUID)
    check("mode: the house-wide mode switch is unchanged (Hub device, 'Hub Mode Music', hidden)",
          hass.states.get("switch.hub_mode_music", {}).get("friendly_name") == "Hub Mode Music"
          and hass.live["switch.hub_mode_music"]._attr_entity_registry_visible_default is False)

    hass = await make_hass()
    hass.storage[f"{DOMAIN}_e1_flags"] = {"voice_defaults": [f"{IDENT}_room_7", f"{IDENT}_zone_3"]}
    await hass.setup_scenes()
    await hub._voice_defaults_once(hass, hass.entry)
    check("mode: the house-wide mode switch keeps the plain default (nothing)",
          all(hass.exposure.get((a, "switch.hub_mode_music")) is False for a in ASSIST))
    await hass.services.call(DOMAIN, "add_voice_mode", {"room": 7, "mode": "Music", "name": "Party time"})
    check("mode: exposed to Assist + enabled Alexa, not disabled Google; room exposed to nothing",
          hass.exposure.get(("conversation", "switch.party_time")) is True
          and hass.exposure.get(("cloud.alexa", "switch.party_time")) is True
          and hass.exposure.get(("cloud.google_assistant", "switch.party_time")) is False,
          str({k: v for k, v in hass.exposure.items() if k[1] == "switch.party_time"}))
    hass.exposure[("cloud.alexa", "switch.party_time")] = False
    await hass.config_entries.async_reload("e1")
    check("mode: applied ONCE - a later user change stands",
          hass.exposure.get(("cloud.alexa", "switch.party_time")) is False)
    await hass.services.call(DOMAIN, "add_voice_mode", {"zone": 3, "mode": "Music", "name": "Wall music"})
    check("mode: a zone exposed to nothing -> its voice mode is heard anyway",
          hass.exposure.get(("conversation", "switch.wall_music")) is True
          and hass.exposure.get(("cloud.alexa", "switch.wall_music")) is True, str(switch_ids(hass)))

    eid = hass.entity_registry.async_get_entity_id("switch", DOMAIN, MUID)
    if eid:
        hass.entity_registry.async_update_entity(eid, new_entity_id="switch.my_party")
    hass.exposure[("conversation", "switch.my_party")] = True
    hass.log.clear()
    await hass.services.call(DOMAIN, "remove_voice_mode", {"room": 7, "mode": "music"})
    check("mode removed: no registry entry", "switch.my_party" not in hass.entity_registry.entities)
    check("mode removed: un-exposed BEFORE deleted",
          ("expose", "conversation", "switch.my_party", False) in hass.log
          and ("remove", "switch.my_party") in hass.log
          and hass.log.index(("expose", "conversation", "switch.my_party", False))
          < hass.log.index(("remove", "switch.my_party")), str(hass.log))
    check("mode removed: no deleted-entry leftover",
          not any(k[2] == MUID for k in hass.entity_registry.deleted_entities))
    check("mode removed: its once-only default is forgotten", MUID not in flags(hass))
    check("mode removed: the other voice mode stays", "switch.wall_music" in hass.entity_registry.entities)
    hass.data["cloud"].client.prefs.google_enabled = True
    await hass.services.call(DOMAIN, "add_voice_mode", {"room": 7, "mode": "Music", "name": "Party time"})
    check("mode re-added: the clean entity_id, exposed by the rule as it is now",
          "switch.party_time" in hass.entity_registry.entities and "switch.my_party" not in hass.entity_registry.entities
          and hass.exposure.get(("cloud.google_assistant", "switch.party_time")) is True, str(switch_ids(hass)))

    old = await make_hass()
    old.storage[f"{DOMAIN}_e1_flags"] = {"voice_defaults": [f"{IDENT}_room_7", f"{IDENT}_zone_3", MUID]}
    old.exposure[("conversation", "light.kitchen")] = True
    room = old.device_registry.async_get_device({(DOMAIN, f"{IDENT}_room_7")})
    old.entity_registry.entities["switch.kitchen_kitchen_party_time"] = RegistryEntry(
        "switch.kitchen_kitchen_party_time", MUID, DOMAIN, "e1", room.id)
    await old.setup_scenes()
    await old.services.call(DOMAIN, "add_voice_mode", {"room": 7, "mode": "Music", "name": "Party time"})
    check("mode: a 0.32.1 leftover does not come back; the add is clean and heard",
          switch_ids(old) == ["switch.hub_mode_music", "switch.party_time"]
          and old.exposure.get(("conversation", "switch.party_time")) is True, str(switch_ids(old)))

    choices = [{"kind": "room", "id": 7, "mode": "Music", "name": "Party time"},
               {"kind": "zone", "id": 3, "mode": "Music", "name": "Wall music"}]
    pr = await make_hass(voice_modes=choices)
    await pr.setup_scenes()
    data = pr.data[DOMAIN]["e1"]
    data["coordinator"].present = frozenset({("zone", 3), ("scene", 5), ("mode", 2)})
    await hub._prune_deleted(pr, pr.entry, IDENT, data["coordinator"])
    stored = (pr.storage.get(f"{DOMAIN}_e1_voice") or {}).get("modes")
    check("mode: a room gone from the Hub drops its voice modes from the store and the registry",
          stored == [choices[1]] and data["voice_modes"] == [choices[1]]
          and "switch.party_time" not in pr.entity_registry.entities
          and "switch.wall_music" in pr.entity_registry.entities, str(stored))


async def backfill():
    """Once, for voice scenes/modes 0.32.2/0.32.3 left exposed to NOTHING
    (they followed a room exposed to nothing)."""
    print("\nexisting voice scenes/modes exposed to nothing are made heard - once")
    hass = await make_hass(
        [{"kind": "room", "id": 7, "scene": "Aurora", "name": "Kitchen aurora"},
         {"kind": "zone", "id": 3, "scene": "Movie", "name": "Movie night"}],
        voice_modes=[{"kind": "room", "id": 7, "mode": "Music", "name": "Party time"}])
    await hass.setup_scenes()
    known = [e.unique_id for e in hass.entity_registry.entities.values()]
    hass.storage[f"{DOMAIN}_e1_flags"] = {"voice_defaults": known}   # all defaulted by 0.32.2/0.32.3
    for eid in hass.entity_registry.entities:
        for a in ASSIST:
            hass.exposure[(a, eid)] = False
    hass.exposure[("conversation", "scene.movie_night")] = True        # someone chose this one
    await hub._voice_defaults_once(hass, hass.entry)
    check("a voice scene exposed to nothing: now Assist + Alexa (enabled), not Google (off)",
          hass.exposure.get(("conversation", "scene.kitchen_aurora")) is True
          and hass.exposure.get(("cloud.alexa", "scene.kitchen_aurora")) is True
          and hass.exposure.get(("cloud.google_assistant", "scene.kitchen_aurora")) is False,
          str({k: v for k, v in hass.exposure.items() if k[1] == "scene.kitchen_aurora"}))
    check("a voice mode exposed to nothing: likewise",
          hass.exposure.get(("conversation", "switch.party_time")) is True
          and hass.exposure.get(("cloud.alexa", "switch.party_time")) is True)
    check("a voice scene exposed to something is left exactly as it is",
          hass.exposure.get(("conversation", "scene.movie_night")) is True
          and hass.exposure.get(("cloud.alexa", "scene.movie_night")) is False)
    check("rooms, lights and the house-wide scenes are not touched",
          all(hass.exposure.get((a, e)) is False for a in ASSIST
              for e in ("light.kitchen", "light.cinewall", "scene.hub_sunset", "switch.hub_mode_music")))
    check("flagged as done", (hass.storage.get(f"{DOMAIN}_e1_flags") or {}).get("voice_heard_backfill") is True)
    hass.exposure[("cloud.alexa", "scene.kitchen_aurora")] = False      # the user changes it
    hass.exposure[("conversation", "switch.party_time")] = False
    hass.exposure[("cloud.alexa", "switch.party_time")] = False         # ...to nothing
    await hass.config_entries.async_reload("e1")
    check("never re-applied: the user's changes stand, even back to nothing",
          hass.exposure.get(("cloud.alexa", "scene.kitchen_aurora")) is False
          and hass.exposure.get(("conversation", "switch.party_time")) is False)


async def main():
    await naming()
    await defaults()
    await removal()
    await prune()
    await modes()
    await backfill()


asyncio.run(main())
print(f"\n{PASSED[0]} passed, {len(FAILURES)} failed")
if FAILURES:
    sys.exit(1)
print("all voice entity rules pass")
