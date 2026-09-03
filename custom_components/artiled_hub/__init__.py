# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""ArtiLED Hub integration — HA is an adapter; the Hub stays authoritative."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import voluptuous as vol

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    ServiceValidationError,
)
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.loader import async_get_integration
from homeassistant.helpers.storage import Store
from homeassistant.util import slugify

from .api import ArtiHubAuthError, ArtiHubClient, ArtiHubError
from .dashboard import async_create_dashboard
from .const import (
    ASSISTANTS,
    CONF_TOKEN,
    DOMAIN,
    FRONTEND_BASE,
    FRONTEND_DIR,
    FRONTEND_URL,
    ICON_BASE,
    ICON_CACHE_DIR,
    OFF_SCENE_NAME,
    ON_SCENE_NAME,
    PLATFORMS,
    STORAGE_VERSION,
)
from .coordinator import ArtiHubCoordinator
from .icons import HubIcons
from .entity_ids import parse_run_picker

_LOGGER = logging.getLogger(__name__)


async def _register_frontend(hass: HomeAssistant) -> None:
    """Serve the tile card and dashboard strategy from the integration itself.

    ⚠ Registered ONCE per Home Assistant, not once per config entry — a second
    Hub would otherwise register the same static path twice and raise.

    ⚠ The URL carries the integration version. Without it a customer upgrading
    the integration keeps the browser's cached copy of the old module: deployed,
    running, and invisible. The version comes from manifest.json so there is one
    source of truth for it.

    ⚠ add_extra_js_url rather than a Lovelace resource, because a dashboard
    STRATEGY has to be defined before the dashboard renders. It also means the
    customer never has to add a resource by hand.
    """
    if hass.data.get(f"{DOMAIN}_frontend"):
        return
    hass.data[f"{DOMAIN}_frontend"] = True

    integration = await async_get_integration(hass, DOMAIN)
    version = integration.version or "0"
    # ⚠ TWO static paths. The frontend directory ships in the package; the icon
    # cache is written at RUNTIME into the CONFIG directory, because it holds
    # Font Awesome Pro paths read from the customer's own Hub and must never
    # live inside a published package. See icons.py.
    icon_dir = Path(hass.config.path(ICON_CACHE_DIR))
    await hass.async_add_executor_job(
        lambda: icon_dir.mkdir(parents=True, exist_ok=True)
    )
    await hass.http.async_register_static_paths(
        [
            StaticPathConfig(
                FRONTEND_BASE, str(Path(__file__).parent / FRONTEND_DIR), True
            ),
            StaticPathConfig(ICON_BASE, str(icon_dir), True),
        ]
    )
    frontend.add_extra_js_url(hass, f"{FRONTEND_URL}?v={version}")
    _LOGGER.debug("ArtiLED frontend module registered at %s?v=%s", FRONTEND_URL, version)



def _icon_names(data: dict) -> set[str]:
    """Every icon the Hub's rooms and zones ask for. Usually a few dozen."""
    names: set[str] = set()
    for scope in ("rooms", "zones"):
        for item in (data.get(scope) or {}).values():
            icon = item.get("icon")
            if icon:
                names.add(str(icon))
    return names


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    try:
        await _register_frontend(hass)
    except Exception as err:  # noqa: BLE001 — presentation must never block control
        _LOGGER.warning("ArtiLED frontend module not registered: %s", err)

    session = async_get_clientsession(hass)
    client = ArtiHubClient(session, entry.data[CONF_HOST], entry.data[CONF_TOKEN])

    try:
        alive = await client.alive()
        version = await client.version()
        scenes = await client.scenes()
        modes = await client.modes()
        flows = await client.flows()
    except ArtiHubAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except ArtiHubError as err:
        raise ConfigEntryNotReady(str(err)) from err

    # Survives a reload on purpose — see ArtiHubCoordinator.__init__. Kept at
    # the top level of hass.data rather than under hass.data[DOMAIN], because
    # the scoped services iterate that dict's values expecting entry data and
    # would hand a caller this bookkeeping instead.
    memory = hass.data.setdefault(f"{DOMAIN}_memory", {}).setdefault(entry.entry_id, {})
    coordinator = ArtiHubCoordinator(hass, client, alive.get("name", "Hub"), memory)
    await coordinator.async_config_entry_first_refresh()

    room_ids = list(coordinator.data["rooms"])
    zone_ids = list(coordinator.data["zones"])

    # Font Awesome paths for the icons THIS Hub uses, read from the Hub itself.
    # ⚠ Not awaited: a Hub that is slow to serve an icon must not delay setup,
    # and an icon is cosmetic — the iconset falls back to the ArtiLED mark.
    icons = HubIcons(hass, async_get_clientsession(hass), client.origin)
    entry.async_create_background_task(
        hass,
        icons.async_refresh(_icon_names(coordinator.data)),
        f"{DOMAIN}_icons",
    )

    # Per-room/zone scene availability (the Hub applies its own scoping
    # rules) and the light -> room mapping, fetched once at setup.
    try:
        scoped_results = await asyncio.gather(
            *[client.scenes({"room": rid}) for rid in room_ids],
            *[client.scenes({"zone": zid}) for zid in zone_ids],
            *[client.lights({"room": rid}) for rid in room_ids],
            *[client.lights({"zone": zid}) for zid in zone_ids],
        )
    except ArtiHubError as err:
        raise ConfigEntryNotReady(str(err)) from err

    scoped_scenes: dict[str, list[dict]] = {}
    for i, rid in enumerate(room_ids):
        scoped_scenes[f"room_{rid}"] = scoped_results[i]
    for i, zid in enumerate(zone_ids):
        scoped_scenes[f"zone_{zid}"] = scoped_results[len(room_ids) + i]
    # Which lights each scope contains. ⚠ A ZONE's membership cannot be
    # expressed through the device registry: a device has exactly one
    # via_device and a light's is its ROOM. So it is carried as an attribute on
    # the room/zone light entity instead - see `members` in light.py - which is
    # what lets a zone's page list its lights and its tile draw a wash from all
    # of their colours rather than one flat fill.
    members: dict[str, list[int]] = {}
    light_room: dict[int, int] = {}
    offset = len(room_ids) + len(zone_ids)
    for i, rid in enumerate(room_ids):
        ids = [int(light["id"]) for light in scoped_results[offset + i]]
        members[f"room_{rid}"] = ids
        for light_id in ids:
            light_room[light_id] = rid
    for i, zid in enumerate(zone_ids):
        members[f"zone_{zid}"] = [
            int(light["id"]) for light in scoped_results[offset + len(room_ids) + i]
        ]

    # Which MODES each scope offers. ⚠ Modes are no more universal than scenes -
    # the dev Hub has 14 house-wide but 6 in the Cinema and 2 in the Bedroom -
    # so a room must be offered what the Hub says that room supports.
    # Gathered separately from the block above on purpose: folding four groups
    # into one gather means indexing them back out by arithmetic, which is
    # where a silent mis-slice would live.
    try:
        mode_results = await asyncio.gather(
            *[client.modes({"room": rid}) for rid in room_ids],
            *[client.modes({"zone": zid}) for zid in zone_ids],
        )
    except ArtiHubError as err:
        raise ConfigEntryNotReady(str(err)) from err
    scoped_modes: dict[str, list[dict]] = {}
    for i, rid in enumerate(room_ids):
        scoped_modes[f"room_{rid}"] = mode_results[i]
    for i, zid in enumerate(zone_ids):
        scoped_modes[f"zone_{zid}"] = mode_results[len(room_ids) + i]

    # Per-room/zone on/off scene selection, persisted across restarts.
    # Default: the scenes named On/Off where the Hub offers them in scope.
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_onoff")
    onoff: dict[str, dict] = await store.async_load() or {}
    for key, available in scoped_scenes.items():
        if key in onoff:
            continue
        defaults: dict[str, str | None] = {"on": None, "off": None}
        for scene in available:
            name = str(scene.get("name", "")).strip().lower()
            if name == ON_SCENE_NAME:
                defaults["on"] = str(scene["id"])
            elif name == OFF_SCENE_NAME:
                defaults["off"] = str(scene["id"])
        onoff[key] = defaults
    await store.async_save(onoff)

    # ⚠ SCOPED SCENES THE USER ASKED FOR, BY NAME. Opt-in, never generated: the
    # Hub offers ~27 scenes across 23 scopes here, so every pair would be ~620
    # entities — and `scene` is in HA's alexa_default_expose, so all of them
    # would reach the customer's Alexa app. Only what someone actually says
    # out loud earns an entity. See ArtiHubScopedScene.
    voice_store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_voice")
    voice: dict = await voice_store.async_load() or {}
    voice_scenes = voice.get("scenes") or []
    voice_modes = voice.get("modes") or []

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "entry_id": entry.entry_id,
        "voice_scenes": voice_scenes,
        "voice_modes": voice_modes,
        "voice_store": voice_store,
        "coordinator": coordinator,
        "hub_ident": alive.get("ident", entry.data[CONF_HOST]),
        "hub_name": alive.get("name", "ArtiLED Hub"),
        "version": version,
        "scenes": scenes,
        "modes": modes,
        "flows": flows,
        "scoped_scenes": scoped_scenes,
        "scoped_modes": scoped_modes,
        "light_room": light_room,
        "members": members,
        "onoff": onoff,
        "onoff_store": store,
    }

    # Register the hub and every room/zone device up front, fully named,
    # so entity_id generation never races platform setup order.
    hub_ident = alive.get("ident", entry.data[CONF_HOST])
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, hub_ident)},
        manufacturer="ArtiLED B.V.",
        model="ArtiLED Hub",
        name=alive.get("name", "ArtiLED Hub"),
        sw_version=version,
    )
    for kind, items in (("room", coordinator.data["rooms"]), ("zone", coordinator.data["zones"])):
        for item_id, item in items.items():
            device_registry.async_get_or_create(
                config_entry_id=entry.entry_id,
                identifiers={(DOMAIN, f"{hub_ident}_{kind}_{item_id}")},
                manufacturer="ArtiLED B.V.",
                model=f"ArtiLED {kind.title()}",
                name=item.get("name", f"{kind.title()} {item_id}"),
                via_device=(DOMAIN, hub_ident),
                # No suggested_area here: it would assign the area before
                # entity_ids are generated, and HA then bakes the area into
                # the id -> "light.living_room_living_room". Users assign
                # room/zone areas manually after setup; ids stay clean.
            )
    # Individual lights are their own devices, Hue-style: nested under
    # their room device, suggested into the room's area.
    for light_id, light in coordinator.data["lights"].items():
        if str(light.get("disabled", 0)) == "1":
            continue
        room_id = light_room.get(light_id)
        room = coordinator.data["rooms"].get(room_id, {}) if room_id else {}
        device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, f"{hub_ident}_light_{light_id}")},
            manufacturer="ArtiLED B.V.",
            model="ArtiLED Light",
            name=light.get("name", f"Light {light_id}"),
            via_device=(
                (DOMAIN, f"{hub_ident}_room_{room_id}")
                if room_id is not None
                else (DOMAIN, hub_ident)
            ),
            suggested_area=room.get("name"),
        )

    await _prune_deleted(hass, entry, hub_ident, coordinator)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Follow the Hub's inventory. A customer who adds a light, room or zone
    # on the Hub should see it in Home Assistant without being told that a
    # Reload button exists — and one they delete should go.
    entry_data = hass.data[DOMAIN][entry.entry_id]
    entry_data["inventory"] = coordinator.inventory
    entry_data["present"] = coordinator.present

    @callback
    def _inventory_changed() -> None:
        current = coordinator.inventory
        still_present = coordinator.present
        # None = no data yet. Never reload on that: a failed poll must not
        # read as "the customer deleted everything".
        if current is None or still_present is None:
            return
        # `present` is watched as well as `inventory` because it is what
        # shrinks when an item's grace finally expires — and pruning only runs
        # during setup. Without this the tidy-up would never be triggered: the
        # reload happened an hour earlier, when the item vanished, and nothing
        # would run setup again until some unrelated change or a restart.
        if current == entry_data.get("inventory") and still_present == entry_data.get("present"):
            return
        entry_data["inventory"] = current
        entry_data["present"] = still_present
        # Reload rather than adding entities here: setup also registers
        # devices, fetches each room's scoped scenes and seeds its on/off
        # defaults. Rebuilding that by hand in five platforms is where the
        # subtle bugs would live, and an inventory change is rare enough that
        # the second of unavailability costs nothing.
        hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))

    entry.async_on_unload(coordinator.async_add_listener(_inventory_changed))
    await _pin_run_picker_ids(hass, entry, hub_ident, coordinator)
    # #525 — the dashboard, created once, from here. Wrapped inside as well:
    # presentation must never block control.
    try:
        await async_create_dashboard(hass, entry)
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("ArtiLED dashboard step failed: %s", err)
    await _voice_defaults_once(hass, entry)
    await _hide_house_wide_once(hass, entry, hub_ident)
    _register_services(hass)
    return True


def _pinned_run_picker_id(unique_id: str, hub_ident: str, coordinator) -> str | None:
    """"<ident>_room_15_run_scene" -> "select.living_room_scene", or None if
    this is not a run picker (or its room/zone has since gone)."""
    parsed = parse_run_picker(unique_id, hub_ident)
    if parsed is None:
        return None
    kind, item_id, suffix = parsed
    item = ((coordinator.data.get(f"{kind}s") or {}).get(item_id)) or {}
    name = item.get("name")
    if not name:
        return None
    return f"select.{slugify(name)}_{suffix}"


async def _pin_run_picker_ids(
    hass: HomeAssistant, entry: ConfigEntry, hub_ident: str, coordinator
) -> None:
    """Give each scoped run picker the id select.<room>_scene / _mode, once.

    ⚠ Home Assistant composes an entity_id from the device's AREA as well as the
    device and entity names, so a room device sitting in an area of the same
    name — which is what a user naturally sets up — gives
    select.living_room_living_room_scene. Suggesting an id from the entity is
    not enough to prevent that; the registry's own generation wins. The first
    attempt here dropped the registry entry and let the platform re-add it, and
    got the identical id straight back.

    So rename explicitly, which is what the UI's own rename does — and unlike
    dropping the entry, it keeps the entity's recorded history.

    ⚠ Each picker is pinned EXACTLY ONCE, on its first appearance, and never
    over an id something else holds. An entity_id that anything references
    cannot be changed without silently breaking dashboards, scripts and
    automations, so this is only defensible while an entity is brand new. That
    is why the record is per unique_id rather than a single install-wide flag:
    a room created on the Hub next month gets the same clean id as the ones set
    up today, while a picker a user has deliberately renamed is left alone.
    """
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_flags")
    flags: dict = await store.async_load() or {}
    already: set[str] = set(flags.get("run_pickers_pinned") or [])

    registry = er.async_get(hass)
    renamed = 0
    pinned: set[str] = set()
    try:
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            wanted = _pinned_run_picker_id(entity.unique_id, hub_ident, coordinator)
            if wanted is None or entity.unique_id in already:
                continue
            pinned.add(entity.unique_id)
            if wanted == entity.entity_id:
                continue
            # Never take an id something else holds — the state machine is
            # checked too, since not every entity is in the registry.
            if registry.async_get(wanted) is not None or hass.states.get(wanted):
                _LOGGER.debug("Leaving %s alone: %s is taken", entity.entity_id, wanted)
                continue
            registry.async_update_entity(entity.entity_id, new_entity_id=wanted)
            renamed += 1
    except Exception as err:  # noqa: BLE001 — cosmetic; must never block setup
        _LOGGER.warning("Could not re-id the scoped run pickers: %s", err)
        return

    if pinned:
        flags["run_pickers_pinned"] = sorted(already | pinned)
        await store.async_save(flags)
    if renamed:
        _LOGGER.info("Renamed %s scoped run pickers to their pinned ids", renamed)


async def _voice_defaults_once(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Expose NOTHING we create to voice until someone asks for it.

    Michel, 2026-08-17: "I think they all should be off by default." The Voice
    page is how a customer turns things on, so the default is plain opt-in.

    ⚠ THIS CANNOT BE LEFT TO HOME ASSISTANT'S DEFAULT — that default is ON, and
    the earlier version of this function only turned off the individual lights
    because I mis-read which parts a fresh install already gets right. Measured
    in HA's own exposed_entities.py:

        DEFAULT_EXPOSED_ASSISTANT = {"conversation": True}

    so when a user has never touched the "expose new entities" switch, every new
    `light` entity is exposed to Assist — all 12 rooms and 11 zones included.
    The reference install happens to have expose_new:false recorded for conversation, which
    is why the rooms there looked correctly off; that is one instance's setting,
    not the product's behaviour. Relying on it shipped a voice default that
    differed per customer.

    ⚠ EVERY entity of the config entry, not just the lights. The scenes, mode
    switches and selects are already excluded by _is_default_exposed() (hidden,
    or entity_category set) — but that is a second thing outside our control: it
    stops being true the moment a customer un-hides a scene. Writing the setting
    explicitly means the answer does not depend on HA's domain list, on
    expose_new, or on anything a user did elsewhere.

    ⚠ Home Assistant PERSISTS whatever async_should_expose() computes back into
    the registry, so entities acquire an explicit should_expose merely by being
    asked about. An explicit False here is therefore the same kind of record HA
    writes itself — not an unusual thing to leave behind.

    ⚠ ONCE PER ENTITY, recorded by unique_id - never on every setup. This writes
    an EXPLICIT setting, so re-applying it would silently overrule a customer
    who deliberately exposed a light. Recording per entity rather than one
    install-wide flag also means a light added next month gets the same default.

    ⚠ Hiding them was NOT an option: they belong on the dashboard's Lights tab
    and have their own pages. Hidden would remove them from the UI as well.
    """
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_flags")
    flags: dict = await store.async_load() or {}
    already: set[str] = set(flags.get("voice_defaults") or [])

    try:
        from homeassistant.components.homeassistant.exposed_entities import (
            async_expose_entity,
        )
    except ImportError:  # pragma: no cover - the helper moved or went away
        _LOGGER.debug("Voice-exposure helper unavailable; leaving defaults alone")
        return

    registry = er.async_get(hass)
    done: set[str] = set()
    try:
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            if entity.unique_id in already:
                continue
            done.add(entity.unique_id)
            for assistant in ASSISTANTS:
                async_expose_entity(hass, assistant, entity.entity_id, False)
    except Exception as err:  # noqa: BLE001 - a default must never block setup
        _LOGGER.warning("Could not apply the voice defaults: %s", err)
        return

    if done:
        flags["voice_defaults"] = sorted(already | done)
        await store.async_save(flags)
        _LOGGER.info("Kept %s entities out of voice by default", len(done))


async def _hide_house_wide_once(hass: HomeAssistant, entry: ConfigEntry, hub_ident: str) -> None:
    """Hide the pre-existing house-wide scene/mode entities, exactly once.

    ⚠ `_attr_entity_registry_visible_default = False` only applies to entities
    being registered for the FIRST time. On an existing install the 40 scenes
    and 14 mode switches are already in the registry and would stay visible, so
    the change would look like it had done nothing — deployed and invisible.

    ⚠ Run ONCE and remember it. Hiding on every setup would override a user who
    deliberately un-hid one, and quietly re-hiding something someone chose to
    show is worse than never hiding it.
    """
    store = Store(hass, STORAGE_VERSION, f"{DOMAIN}_{entry.entry_id}_flags")
    flags: dict = await store.async_load() or {}
    if flags.get("house_wide_hidden"):
        return

    registry = er.async_get(hass)
    prefixes = (f"{hub_ident}_scene_", f"{hub_ident}_mode_")
    hidden = 0
    try:
        for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
            # ⚠ Prefix match, not "contains": a per-scope picker's unique_id
            # ends in "_on_scene"/"_off_scene" and must not be caught by this.
            if entity.unique_id.startswith(prefixes) and entity.hidden_by is None:
                registry.async_update_entity(
                    entity.entity_id, hidden_by=er.RegistryEntryHider.INTEGRATION
                )
                hidden += 1
    except Exception as err:  # noqa: BLE001 - see below
        # ⚠ Deliberately swallowed, and deliberately NOT flagged as done. This
        # is a cosmetic tidy-up; if a future Home Assistant renames the hider
        # enum or changes the registry API, the integration must still load and
        # control the customer's lights. Leaving the flag unset means it simply
        # tries again next time rather than being silently skipped forever.
        _LOGGER.warning("Could not hide the house-wide scene/mode entities: %s", err)
        return

    flags["house_wide_hidden"] = True
    await store.async_save(flags)
    if hidden:
        _LOGGER.info(
            "Hid %s house-wide scene/mode entities; they still work and any "
            "automation referencing them is unaffected", hidden
        )


def _unexpose(hass: HomeAssistant, entity_ids: list[str]) -> bool:
    """Tell every assistant these entities are going, BEFORE they go.

    ⚠ DELETING AN EXPOSED ENTITY STRANDS IT IN THE ASSISTANT FOREVER. Amazon is
    never told the device vanished, so the tile survives in the Alexa app as
    permanently "unresponsive" — and there is no API to clean it up afterwards:
    Alexa's Smart Home API only lets a skill OFFER devices, it cannot enumerate
    or remove what an account already has. The customer is left deleting tiles
    by hand. Measured on the reference install: retiring 10 lights left 10 dead tiles.

    Un-exposing FIRST turns the removal into a change Home Assistant can report
    onward ("this was exposed, now it is not"). Deleting outright is a change it
    cannot report at all, because the exposure record goes with the entity.

    Returns True if anything was actually un-exposed, so the caller knows
    whether it needs to give the cloud a moment before deleting.
    """
    try:
        from homeassistant.components.homeassistant.exposed_entities import (
            async_expose_entity,
            async_should_expose,
        )
    except ImportError:  # pragma: no cover - helper moved or went away
        return False

    touched = False
    for entity_id in entity_ids:
        for assistant in ASSISTANTS:
            try:
                if not async_should_expose(hass, assistant, entity_id):
                    continue
                async_expose_entity(hass, assistant, entity_id, False)
                touched = True
            except Exception as err:  # noqa: BLE001 - never block a delete
                _LOGGER.debug("Could not un-expose %s: %s", entity_id, err)
    return touched


async def _prune_deleted(
    hass: HomeAssistant,
    entry: ConfigEntry,
    hub_ident: str,
    coordinator: ArtiHubCoordinator,
) -> None:
    """Remove entities and devices for things DELETED on the Hub.

    ⚠ Driven by `coordinator.present` (does the Hub still have it) and never
    by `inventory` (which also tracks enabled/disabled). A light the customer
    DISABLED is one they mean to bring back: deleting its entity would take
    its history, its area assignment and any automation or dashboard card
    pointing at it, and re-enabling would not give those back. Disabled lights
    simply stop being offered and report unavailable.

    ⚠ EVERY removal here is preceded by _unexpose(). See its docstring: a
    deleted-while-exposed entity leaves a dead tile in the customer's Alexa app
    that nothing can ever clean up.
    """
    present = coordinator.present
    if present is None:  # No data — prune nothing.
        return

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    keep = {hub_ident} | {f"{hub_ident}_{kind}_{item_id}" for kind, item_id in present}
    doomed_devices = [
        device
        for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id)
        if (ours := {ident for domain, ident in device.identifiers if domain == DOMAIN})
        and not (ours & keep)
    ]

    # ⚠ Collect the entity ids BEFORE removing the device — async_remove_device
    # takes its entities with it, and by then there is nothing left to name.
    doomed_entities: list[str] = []
    for device in doomed_devices:
        doomed_entities.extend(
            e.entity_id
            for e in er.async_entries_for_device(
                entity_registry, device.id, include_disabled_entities=True
            )
        )

    if _unexpose(hass, doomed_entities):
        # ⚠ Yield before deleting. Un-exposing schedules the cloud's own
        # sync task on the event loop; removing the entity in the same tick
        # gives that task no chance to run. One loop iteration is enough to let
        # it start, and this only costs anything when something was really
        # deleted.
        await asyncio.sleep(0)

    for device in doomed_devices:
        device_registry.async_remove_device(device.id)

    # Scenes, modes and flows hang off the hub device itself, so the sweep
    # above never reaches them. Prune them by unique_id, scoped to that one
    # device so a room/zone/light entity can't be caught by accident.
    hub_device = device_registry.async_get_device(identifiers={(DOMAIN, hub_ident)})
    if hub_device is None:
        return
    # From `present`, not the lists fetched above: those carry no grace, so a
    # scene missing from one odd response would be deleted on the spot.
    keep_ids = {f"{hub_ident}_version"} | {
        f"{hub_ident}_{kind}_{item_id}"
        for kind, item_id in present
        if kind in ("scene", "mode", "flow")
    }
    doomed = [
        entity.entity_id
        for entity in er.async_entries_for_device(
            entity_registry, hub_device.id, include_disabled_entities=True
        )
        if entity.unique_id not in keep_ids
    ]
    if _unexpose(hass, doomed):
        await asyncio.sleep(0)
    for entity_id in doomed:
        entity_registry.async_remove(entity_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
        # ⚠ hass.data[f"{DOMAIN}_memory"] is deliberately NOT dropped here: an
        # unload is half of every reload, and forgetting when each item was
        # last seen is exactly what made the delete grace useless.
    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """The integration is being removed for good — drop its bookkeeping."""
    hass.data.get(f"{DOMAIN}_memory", {}).pop(entry.entry_id, None)


SCOPED_SCHEMA = vol.Schema(
    {
        vol.Required("name"): vol.Any(str, int),
        vol.Optional("room"): vol.Any(str, int),
        vol.Optional("zone"): vol.Any(str, int),
        # Which Hub, when more than one is configured. See _entry_data().
        vol.Optional("hub"): str,
    }
)


def _exactly_one_scope(value: dict) -> dict:
    """A scoped scene entity must name ONE room or ONE zone.

    ⚠ Neither is not "house-wide" here, it is a mistake: house-wide scenes are
    already entities (the hidden scene.hub_*), and a bare scene id fires across
    every light in the house. Both at once is meaningless — the Hub takes a
    single scope from the request.
    """
    if ("room" in value) == ("zone" in value):
        raise vol.Invalid("give exactly one of room or zone")
    return value


VOICE_SCENE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional("hub"): str,
            vol.Required("scene"): str,
            vol.Required("name"): str,
            vol.Optional("room"): vol.Coerce(int),
            vol.Optional("zone"): vol.Coerce(int),
        }
    ),
    _exactly_one_scope,
)

VOICE_MODE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional("hub"): str,
            vol.Required("mode"): str,
            vol.Required("name"): str,
            vol.Optional("room"): vol.Coerce(int),
            vol.Optional("zone"): vol.Coerce(int),
        }
    ),
    _exactly_one_scope,
)

VOICE_MODE_REMOVE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional("hub"): str,
            vol.Required("mode"): str,
            vol.Optional("room"): vol.Coerce(int),
            vol.Optional("zone"): vol.Coerce(int),
        }
    ),
    _exactly_one_scope,
)

VOICE_SCENE_REMOVE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional("hub"): str,
            vol.Required("scene"): str,
            vol.Optional("room"): vol.Coerce(int),
            vol.Optional("zone"): vol.Coerce(int),
        }
    ),
    _exactly_one_scope,
)

# ⚠ `channel` is a STRING on purpose — it is a digit-concat selector ("13" =
# channels 1 and 3), not a count. Coercing it to int would turn "13" into
# thirteen and lose the leading-zero and ordering semantics the Hub parses.
def _exactly_one_target(value: dict) -> dict:
    """set_color must name EXACTLY ONE of room / zone / light.

    ⚠ It used to accept any combination and the handler picked by precedence
    (light, then zone, then room), so passing room AND light silently coloured
    the light and left the room alone — a wrong target with no error. Mycroft,
    reviewing 2026-08-17. Zero targets was equally silent: the handler simply
    returned.
    """
    given = [k for k in ("room", "zone", "light") if k in value]
    if len(given) != 1:
        raise vol.Invalid(
            "give exactly one of room, zone or light"
            + (f" (got {', '.join(given)})" if given else "")
        )
    return value


COLOR_SCHEMA = vol.All(
    vol.Schema(
        {
        # ⚠ IDs, not names. The handler int()s these, so a name raised a
        # ValueError deep inside it while services.yaml advertised names.
        # Coercing here fails validation with a message the caller can read.
        # (run_scene/run_mode DO take names — the Hub resolves those itself.)
        vol.Optional("room"): vol.Coerce(int),
        vol.Optional("zone"): vol.Coerce(int),
        vol.Optional("light"): vol.Coerce(int),
        vol.Optional("hub"): str,
        vol.Optional("channel", default="0"): vol.Any(str, int),
        vol.Optional("rgbw"): [vol.All(int, vol.Range(min=0, max=255))],
        vol.Optional("temperature"): vol.All(int, vol.Range(min=0, max=255)),
        vol.Optional("intensity"): vol.All(int, vol.Range(min=0, max=255)),
        # HSV, three components 0-255 (the Hub's scale, not 0-360/0-100).
        vol.Optional("hsv"): [vol.All(int, vol.Range(min=0, max=255))],
        # ⚠ color_array is a JSON STRING of [position, r, g, b] quads, exactly
        # as the Hub wants it - room.php json_decode()s it. Passing an array of
        # rgb() strings 400'd every palette drag in the webapp.
        vol.Optional("color_array"): str,
        vol.Optional("blend"): vol.All(int, vol.Range(min=0, max=2)),
        vol.Optional("scale"): vol.All(int, vol.Range(min=0, max=4)),
        vol.Optional("alternate"): vol.All(int, vol.Range(min=0, max=1)),
        vol.Optional("start_index"): vol.All(int, vol.Range(min=0, max=255)),
        vol.Optional("end_index"): vol.All(int, vol.Range(min=0, max=255)),
        }
    ),
    _exactly_one_target,
)


def _register_services(hass: HomeAssistant) -> None:
    """Scoped scene/mode services — Hue-style extras beyond the entities."""
    if hass.services.has_service(DOMAIN, "run_scene"):
        return

    def _entry_data(call: ServiceCall | None = None):
        """The Hub a service call is for.

        ⚠ NEVER SILENTLY PICK ONE OF SEVERAL. This used to be
        next(iter(entries.values())): with two Hubs configured, every global
        service hit whichever Home Assistant happened to set up first — no
        error, no warning, the wrong house. Mycroft, reviewing 2026-08-17.

        One Hub: used, so single-Hub callers need no `hub` field. More than one
        and no `hub` given: RAISE and name the choices, because guessing which
        building to change the lights in is not a recoverable mistake.
        """
        entries = hass.data.get(DOMAIN, {})
        if not entries:
            return None
        wanted = (call.data.get("hub") if call else None)
        if wanted:
            key = str(wanted).strip().lower()
            for data in entries.values():
                if key in (str(data.get("hub_ident", "")).lower(),
                           str(data.get("hub_name", "")).lower()):
                    return data
            raise ServiceValidationError(
                f"No configured ArtiLED Hub matches '{wanted}'. Known: "
                + ", ".join(sorted(str(d.get("hub_name") or d.get("hub_ident"))
                                   for d in entries.values()))
            )
        if len(entries) > 1:
            raise ServiceValidationError(
                "More than one ArtiLED Hub is configured, so this service needs "
                "a 'hub' to say which one. Known: "
                + ", ".join(sorted(str(d.get("hub_name") or d.get("hub_ident"))
                                   for d in entries.values()))
            )
        return next(iter(entries.values()))

    def _scope(call: ServiceCall) -> dict:
        scope: dict = {}
        if "room" in call.data:
            scope["room"] = call.data["room"]
        if "zone" in call.data:
            scope["zone"] = call.data["zone"]
        return scope

    async def run_scene(call: ServiceCall) -> None:
        data = _entry_data(call)
        if data:
            await data["client"].run_scene(call.data["name"], _scope(call))
            await data["coordinator"].async_request_refresh()

    async def stop_scene(call: ServiceCall) -> None:
        data = _entry_data(call)
        if data:
            await data["client"].run_scene(call.data["name"], _scope(call), running=0)
            await data["coordinator"].async_request_refresh()

    async def run_mode(call: ServiceCall) -> None:
        data = _entry_data(call)
        if data:
            await data["client"].run_mode(call.data["name"], _scope(call))
            await data["coordinator"].async_request_refresh()

    async def stop_mode(call: ServiceCall) -> None:
        data = _entry_data(call)
        if data:
            await data["client"].run_mode(call.data["name"], _scope(call), running=0)
            await data["coordinator"].async_request_refresh()

    async def set_color(call: ServiceCall) -> None:
        """Set colour on a room, zone or light — optionally on SOME CHANNELS.

        ⚠ This exists because HA's light.turn_on has no channel concept, and an
        ArtiLED light is up to four independent channels. The webapp's colour
        panel has had a four-channel selector all along
        (app/includes/colors-tab.php); without this service the dashboard could
        only ever drive the whole light.

        ⚠ CHANNEL IS A DIGIT-CONCAT SELECTOR, not a number or a list — the Hub's
        own convention (channel_selector_to_list in its functions.php):
            0    whole light      13   channels 1 AND 3
            2    channel 2 only   1234 all four -> the API reads >255, so the
                                       webapp sends "0" for that case instead.
        color-bind.js builds it exactly this way; the caller passes the same
        string so both interfaces mean the same thing.

        ⚠ hue=0 on a colour-only set. reference_set_hue_semantics: state and
        brightness include Hue lights, colour alone does not.
        """
        data = _entry_data(call)
        if not data:
            return
        fields: dict = {"channel": str(call.data.get("channel", "0")), "hue": 0}
        if "rgbw" in call.data:
            r, g, b, w = list(call.data["rgbw"]) + [0] * (4 - len(call.data["rgbw"]))
            fields["color_rgbw"] = {"red": r, "green": g, "blue": b, "white": w}
        elif "temperature" in call.data:
            fields["color_w"] = {
                "temperature": int(call.data["temperature"]),
                "intensity": int(call.data.get("intensity", 255)),
            }
        elif "hsv" in call.data:
            h, sat, val = (list(call.data["hsv"]) + [0, 0, 0])[:3]
            fields["color_hsv"] = {"hue": h, "saturation": sat, "value": val}
        elif "color_array" in call.data:
            # ⚠ ALL SIX or nothing. room.php only sets $set_advanced_palette
            # when color_array, blend, scale, alternate, start_index AND
            # end_index are all present - miss one and the call is accepted and
            # silently does nothing. Defaults mirror the webapp's own initial
            # state (gradient-slider: alternate 0, blend 0, scale 1, 0..255).
            fields["advanced_palette"] = {
                "color_array": call.data["color_array"],
                "blend": int(call.data.get("blend", 0)),
                "scale": int(call.data.get("scale", 1)),
                "alternate": int(call.data.get("alternate", 0)),
                "start_index": int(call.data.get("start_index", 0)),
                "end_index": int(call.data.get("end_index", 255)),
            }
        else:
            return
        client = data["client"]
        if "light" in call.data:
            await client.set_light(int(call.data["light"]), **fields)
        elif "zone" in call.data:
            await client.set_zone(int(call.data["zone"]), **fields)
        elif "room" in call.data:
            await client.set_room(int(call.data["room"]), **fields)
        else:
            return
        await data["coordinator"].async_request_refresh()

    async def _save_voice(data: dict, scenes: list, modes: list) -> None:
        """Persist BOTH lists, then reload.

        ⚠ WRITE BOTH, ALWAYS. The store holds scenes and modes in one file, so
        saving only the list you changed silently erases the other one — the
        first version of the scene service did exactly that and would have
        deleted every scoped mode the moment a scene was added.

        ⚠ RELOAD after saving. The scene and switch platforms build their
        entities at setup, so a new choice is not a real entity until the entry
        is set up again. Without this the tick appears to do nothing until the
        next restart.
        """
        await data["voice_store"].async_save({"scenes": scenes, "modes": modes})
        await hass.config_entries.async_reload(data["entry_id"])

    def _without(chosen: list, kind: str, item_id: int, field: str, value: str) -> list:
        """Everything except this exact scope+item — so re-adding is a rename,
        not a duplicate."""
        return [
            t for t in (chosen or [])
            if not (t["kind"] == kind and int(t["id"]) == item_id
                    and str(t.get(field)) == str(value))
        ]

    async def add_voice_scene(call: ServiceCall) -> None:
        """Give one room/zone + scene a NAME, and an entity to answer to it."""
        data = _entry_data(call)
        if not data:
            return
        kind = "room" if "room" in call.data else "zone"
        item_id = int(call.data[kind])
        scenes = _without(data.get("voice_scenes"), kind, item_id, "scene",
                          call.data["scene"])
        scenes.append({
            "kind": kind, "id": item_id,
            "scene": call.data["scene"], "name": call.data["name"],
        })
        await _save_voice(data, scenes, data.get("voice_modes") or [])

    async def remove_voice_scene(call: ServiceCall) -> None:
        data = _entry_data(call)
        if not data:
            return
        kind = "room" if "room" in call.data else "zone"
        scenes = _without(data.get("voice_scenes"), kind, int(call.data[kind]),
                          "scene", call.data["scene"])
        await _save_voice(data, scenes, data.get("voice_modes") or [])

    async def add_voice_mode(call: ServiceCall) -> None:
        """Same as add_voice_scene, but a SWITCH — a mode runs until stopped."""
        data = _entry_data(call)
        if not data:
            return
        kind = "room" if "room" in call.data else "zone"
        item_id = int(call.data[kind])
        modes = _without(data.get("voice_modes"), kind, item_id, "mode",
                         call.data["mode"])
        modes.append({
            "kind": kind, "id": item_id,
            "mode": call.data["mode"], "name": call.data["name"],
        })
        await _save_voice(data, data.get("voice_scenes") or [], modes)

    async def remove_voice_mode(call: ServiceCall) -> None:
        data = _entry_data(call)
        if not data:
            return
        kind = "room" if "room" in call.data else "zone"
        modes = _without(data.get("voice_modes"), kind, int(call.data[kind]),
                         "mode", call.data["mode"])
        await _save_voice(data, data.get("voice_scenes") or [], modes)

    hass.services.async_register(DOMAIN, "set_color", set_color, schema=COLOR_SCHEMA)
    hass.services.async_register(
        DOMAIN, "add_voice_scene", add_voice_scene, schema=VOICE_SCENE_SCHEMA)
    hass.services.async_register(
        DOMAIN, "remove_voice_scene", remove_voice_scene, schema=VOICE_SCENE_REMOVE_SCHEMA)
    hass.services.async_register(
        DOMAIN, "add_voice_mode", add_voice_mode, schema=VOICE_MODE_SCHEMA)
    hass.services.async_register(
        DOMAIN, "remove_voice_mode", remove_voice_mode, schema=VOICE_MODE_REMOVE_SCHEMA)
    hass.services.async_register(DOMAIN, "run_scene", run_scene, schema=SCOPED_SCHEMA)
    hass.services.async_register(DOMAIN, "stop_scene", stop_scene, schema=SCOPED_SCHEMA)
    hass.services.async_register(DOMAIN, "run_mode", run_mode, schema=SCOPED_SCHEMA)
    hass.services.async_register(DOMAIN, "stop_mode", stop_mode, schema=SCOPED_SCHEMA)
