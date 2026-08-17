# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Hub scenes as HA scene entities (house-wide activation).

Scoped activation (per room/zone) goes through the artiled_hub.run_scene
service instead — a scene entity has no scope concept."""
from __future__ import annotations

from typing import Any

from homeassistant.components.scene import Scene
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities: list[Scene] = [ArtiHubScene(data, scene) for scene in data["scenes"]]
    # Scoped scenes the user asked for by name — see ArtiHubScopedScene.
    entities.extend(
        ArtiHubScopedScene(data, target) for target in data.get("voice_scenes") or []
    )
    async_add_entities(entities)


class ArtiHubScene(Scene):
    """Activating fires the scene HOUSE-WIDE.

    ⚠ Hidden by default, because house-wide is rarely what someone reaching for
    a scene in Home Assistant means. The Hub takes its execution scope from the
    REQUEST: a bare scene id applies to every light in the house, which is how
    a "PowerOff" scene can switch off an entire home from one tap. Scenes are
    normally run against a room or zone — see the per-scope scene selects, which
    offer exactly what the Hub says that scope supports.

    ⚠ Hidden, not removed: an automation may already reference one of these, and
    house-wide really is a thing the Hub supports. They stay in the registry and
    keep working; they just stop being the obvious choice.
    """

    _attr_has_entity_name = True
    _attr_entity_registry_visible_default = False

    def __init__(self, data: dict, scene: dict) -> None:
        self._client = data["client"]
        self._coordinator = data["coordinator"]
        self._scene_id = scene["id"]
        self._attr_name = scene.get("name", f"Scene {scene['id']}")
        self._attr_unique_id = f"{data['hub_ident']}_scene_{scene['id']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data["hub_ident"])},
        )

    async def async_activate(self, **kwargs: Any) -> None:
        await self._client.run_scene(self._scene_id)
        await self._coordinator.async_request_refresh()


class ArtiHubScopedScene(Scene):
    """One scene, on ONE room or zone, created because the user asked for it.

    ⚠ WHY THESE ARE OPT-IN AND NOT GENERATED. A scoped scene is the thing people
    actually say out loud - "put the living room on Cinema" - but the Hub offers
    ~27 scenes across 23 scopes, so generating every pair is ~620 entities on
    the reference install alone. Home Assistant's `alexa_default_expose` includes `scene`,
    so all of them would land in the customer's Alexa app too. That is not a
    feature, it is a flood: an entity nobody can name is an entity nobody will
    ever say. So the user ticks the handful they speak, and only those exist.

    ⚠ THE NAME IS THE USER'S, not composed. `has_entity_name` stays False on
    purpose: with it True, Home Assistant prefixes the device name and
    "Cinema" in the Cinema becomes "Cinema Cinema". The whole point of letting
    the name be assigned is that the user says it, so it is stored verbatim.

    ⚠ Attached to the ROOM/ZONE device rather than the Hub, so it groups with
    the scope it acts on - and so deleting that room on the Hub takes its scoped
    scenes with it rather than leaving them pointing at nothing.
    """

    _attr_has_entity_name = False

    def __init__(self, data: dict, target: dict) -> None:
        self._client = data["client"]
        self._coordinator = data["coordinator"]
        self._scene = target["scene"]
        self._kind = target["kind"]          # "room" | "zone"
        self._item_id = int(target["id"])
        self._attr_name = target["name"]
        self._attr_unique_id = (
            f"{data['hub_ident']}_voice_scene_{self._kind}_{self._item_id}_"
            f"{slugify(str(self._scene))}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{data['hub_ident']}_{self._kind}_{self._item_id}")},
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # ⚠ So the Voice page can tell WHICH scope+scene this entity is. The
        # name is the user's, and the entity_id is derived from it, so neither
        # can be parsed back into a scope reliably — a renamed entity would
        # simply stop matching and the page would offer to add it again.
        return {
            "artiled_scope": f"{self._kind}_{self._item_id}",
            "artiled_item": self._scene,
        }

    async def async_activate(self, **kwargs: Any) -> None:
        # ⚠ Scope comes from the REQUEST — a bare scene id runs house-wide.
        await self._client.run_scene(self._scene, {self._kind: self._item_id})
        await self._coordinator.async_request_refresh()
