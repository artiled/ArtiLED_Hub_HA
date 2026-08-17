# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Per-room/zone 'Turn-on scene' / 'Turn-off scene' pickers.

Each room/zone device gets two config dropdowns listing the scenes the
Hub offers for that scope, plus 'None (plain on/off)'. The choice drives
what the light entity's turn_on/turn_off does, and persists across
restarts via the integration's store."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

NONE_OPTION = "None (plain on/off)"
# The run pickers' idle/stop entry. Worded differently from NONE_OPTION on
# purpose: that one configures what on/off does, this one stops what is
# running in the scope.
NONE_OPTION_RUN = "None"


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities: list[SelectEntity] = []
    for key in data["scoped_scenes"]:
        for action in ("on", "off"):
            entities.append(ArtiHubOnOffSceneSelect(data, key, action))
        entities.append(ArtiHubRunSceneSelect(data, key))
    for key in data["scoped_modes"]:
        entities.append(ArtiHubRunModeSelect(data, key))
    async_add_entities(entities)


def _scope_of(item_key: str) -> dict[str, int]:
    """"room_15" -> {"room": 15}. The Hub takes execution scope from the
    request, so this is what stops a scene applying to the whole house."""
    kind, _, item_id = item_key.partition("_")
    return {kind: int(item_id)}


def _labels(items: list[dict]) -> dict[str, str]:
    """Display label -> id. Duplicate names get their id appended, so every
    option maps back to exactly one scene/mode (same rule as the pickers)."""
    names = [str(i.get("name", i["id"])) for i in items]
    out: dict[str, str] = {}
    for item, name in zip(items, names):
        label = name if names.count(name) == 1 else f"{name} [{item['id']}]"
        out[label] = str(item["id"])
    return out


class ArtiHubOnOffSceneSelect(SelectEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:palette-outline"

    def __init__(self, data: dict, item_key: str, action: str) -> None:
        self._onoff = data["onoff"]
        self._store = data["onoff_store"]
        self._item_key = item_key  # "room_15" / "zone_16"
        self._action = action  # "on" | "off"
        self._attr_name = f"Turn-{action} scene"
        self._attr_unique_id = f"{data['hub_ident']}_{item_key}_{action}_scene"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{data['hub_ident']}_{item_key}")},
        )
        # Display names; duplicates get the scene id appended so every
        # option string stays unique and maps back to exactly one scene.
        scenes = data["scoped_scenes"].get(item_key, [])
        names = [str(s.get("name", s["id"])) for s in scenes]
        self._by_label: dict[str, str] = {}
        for scene, name in zip(scenes, names):
            label = name if names.count(name) == 1 else f"{name} [{scene['id']}]"
            self._by_label[label] = str(scene["id"])
        self._attr_options = [NONE_OPTION, *self._by_label]

    @property
    def current_option(self) -> str:
        selected = (self._onoff.get(self._item_key) or {}).get(self._action)
        if selected is not None:
            for label, scene_id in self._by_label.items():
                if scene_id == str(selected):
                    return label
        return NONE_OPTION

    async def async_select_option(self, option: str) -> None:
        self._onoff.setdefault(self._item_key, {"on": None, "off": None})[
            self._action
        ] = self._by_label.get(option)  # None for NONE_OPTION
        await self._store.async_save(self._onoff)
        self.async_write_ha_state()


class _ArtiHubScopedRunSelect(CoordinatorEntity, SelectEntity):
    """Base for the per-room/zone run pickers.

    ⚠ These exist because the Hub's scenes and modes are NOT house-wide and NOT
    universal. Execution scope comes from the REQUEST - a bare id applies to
    every light in the house - and each scope offers a different set: on the dev
    Hub, 40 scenes house-wide but 26-31 per room, and modes 14 against 2-6.
    Asking the Hub per scope is the whole answer: its scoped list already
    includes the global entries (scene_rooms containing 0) alongside that
    scope's own, so nothing here needs to model "global" itself.
    """

    _attr_has_entity_name = True

    def __init__(self, data: dict, item_key: str, items: list[dict], suffix: str) -> None:
        super().__init__(data["coordinator"])
        self._client = data["client"]
        self._item_key = item_key            # "room_15" / "zone_16"
        self._scope = _scope_of(item_key)
        self._by_label = _labels(items)
        self._attr_options = [NONE_OPTION_RUN, *self._by_label]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{data['hub_ident']}_{item_key}")},
        )
        # ⚠ Do NOT try to pin self.entity_id here. Home Assistant builds the id
        # from the device's AREA as well as its name, so a room device in an
        # area of the same name gives select.living_room_living_room_scene, and
        # an id suggested by the entity loses to the registry's own generation.
        # _pin_run_picker_ids() in __init__.py renames these once instead.

    def _running(self) -> dict:
        """What the Hub reports running in THIS scope, e.g.
        {"type": "mode", "name": "Game"}."""
        kind, _, item_id = self._item_key.partition("_")
        item = (self.coordinator.data.get(f"{kind}s") or {}).get(int(item_id)) or {}
        return item.get("running") or {}

    def _current_for(self, kind: str) -> str:
        running = self._running()
        if running.get("type") != kind:
            return NONE_OPTION_RUN
        name = str(running.get("name", ""))
        # The running report carries a name, not an id; match it back to a label.
        for label in self._by_label:
            if label == name or label.startswith(f"{name} ["):
                return label
        return NONE_OPTION_RUN


class ArtiHubRunSceneSelect(_ArtiHubScopedRunSelect):
    """Run one of the scenes this room/zone actually offers."""

    _attr_icon = "mdi:palette"

    def __init__(self, data: dict, item_key: str) -> None:
        super().__init__(data, item_key, data["scoped_scenes"].get(item_key, []), "scene")
        self._attr_name = "Scene"
        self._attr_unique_id = f"{data['hub_ident']}_{item_key}_run_scene"

    @property
    def current_option(self) -> str:
        return self._current_for("scene")

    async def async_select_option(self, option: str) -> None:
        scene_id = self._by_label.get(option)
        if scene_id is None:
            # "None" stops the scene running in this scope rather than firing
            # one; the Hub's stop dispatch mirrors its start dispatch.
            running = self._running()
            if running.get("type") == "scene":
                await self._client.run_scene(running.get("name"), self._scope, running=0)
        else:
            await self._client.run_scene(int(scene_id), self._scope)
        await self.coordinator.async_request_refresh()


class ArtiHubRunModeSelect(_ArtiHubScopedRunSelect):
    """Run one of the modes this room/zone actually offers.

    ⚠ The Hub's scoped list usually contains its own "Off" mode, which is a mode
    that darkens the lights. That is NOT the same as this picker's "None", which
    stops whatever mode is running and leaves the lights alone.
    """

    _attr_icon = "mdi:motion-play-outline"

    def __init__(self, data: dict, item_key: str) -> None:
        super().__init__(data, item_key, data["scoped_modes"].get(item_key, []), "mode")
        self._attr_name = "Mode"
        self._attr_unique_id = f"{data['hub_ident']}_{item_key}_run_mode"

    @property
    def current_option(self) -> str:
        return self._current_for("mode")

    async def async_select_option(self, option: str) -> None:
        mode_id = self._by_label.get(option)
        if mode_id is None:
            running = self._running()
            if running.get("type") == "mode":
                await self._client.run_mode(running.get("name"), self._scope, running=0)
        else:
            await self._client.run_mode(int(mode_id), self._scope)
        await self.coordinator.async_request_refresh()
