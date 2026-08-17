# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Hub modes as switch entities — on = running somewhere, per Hub readback."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    entities: list[SwitchEntity] = [
        ArtiHubModeSwitch(data, mode) for mode in data["modes"]
    ]
    # Scoped modes the user asked for by name — see ArtiHubScopedMode.
    entities.extend(
        ArtiHubScopedMode(data, target) for target in data.get("voice_modes") or []
    )
    async_add_entities(entities)


class ArtiHubModeSwitch(CoordinatorEntity, SwitchEntity):
    """is_on is derived from the Hub's running info on rooms/zones —
    never assumed from our own commands."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:motion-play-outline"
    # ⚠ Hidden by default for the same reason as the house-wide scenes: turning
    # one of these on runs the mode across the WHOLE house, and modes are not
    # even universal — the Hub offers 14 house-wide but only 2 in the Bedroom
    # and 6 in the Cinema. The per-scope mode selects offer what each scope
    # actually supports. Hidden, not removed, so existing automations survive.
    _attr_entity_registry_visible_default = False

    def __init__(self, data: dict, mode: dict) -> None:
        super().__init__(data["coordinator"])
        self._client = data["client"]
        self._mode_id = mode["id"]
        self._mode_name = str(mode.get("name", mode["id"]))
        self._attr_name = f"Mode {self._mode_name}"
        self._attr_unique_id = f"{data['hub_ident']}_mode_{mode['id']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data["hub_ident"])},
        )

    @property
    def is_on(self) -> bool:
        for group in ("rooms", "zones"):
            for item in self.coordinator.data[group].values():
                running = item.get("running") or {}
                if (
                    running.get("type") == "mode"
                    and str(running.get("name", "")).lower() == self._mode_name.lower()
                ):
                    return True
        return False

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.run_mode(self._mode_id)
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.run_mode(self._mode_id, running=0)
        await self.coordinator.async_request_refresh()


class ArtiHubScopedMode(CoordinatorEntity, SwitchEntity):
    """One mode, on ONE room or zone, created because the user asked for it.

    ⚠ A SWITCH, not a scene — this is the difference from a scoped scene. A
    scene is one-shot ("run Cinema"); a mode RUNS UNTIL STOPPED, so it needs an
    off as much as an on. That is also why the house-wide modes are switches.

    ⚠ is_on reads THIS SCOPE ONLY, which the house-wide switch above cannot do:
    it returns true if the mode is running in ANY room or zone, so "Music" in
    the kitchen makes the bedroom's switch look on too. Here the scope is known,
    so the answer is exact — and it is still read back from the Hub, never
    assumed from our own command.

    ⚠ Opt-in and verbatim-named, for the same reasons as ArtiHubScopedScene:
    modes are fewer than scenes (~3-7 per scope) but the same flood argument
    applies, and "Cinema" in the Cinema must not become "Cinema Cinema".
    """

    _attr_has_entity_name = False
    _attr_icon = "mdi:motion-play-outline"

    def __init__(self, data: dict, target: dict) -> None:
        super().__init__(data["coordinator"])
        self._client = data["client"]
        self._mode = str(target["mode"])
        self._kind = target["kind"]          # "room" | "zone"
        self._item_id = int(target["id"])
        self._attr_name = target["name"]
        self._attr_unique_id = (
            f"{data['hub_ident']}_voice_mode_{self._kind}_{self._item_id}_"
            f"{slugify(self._mode)}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{data['hub_ident']}_{self._kind}_{self._item_id}")},
        )

    @property
    def available(self) -> bool:
        return super().available and self._item() is not None

    def _item(self) -> dict | None:
        return (self.coordinator.data.get(f"{self._kind}s") or {}).get(self._item_id)

    @property
    def is_on(self) -> bool:
        item = self._item() or {}
        running = item.get("running") or {}
        return (
            running.get("type") == "mode"
            and str(running.get("name", "")).lower() == self._mode.lower()
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        # ⚠ So the Voice page can tell WHICH scope+mode this entity is — the
        # user's name and the derived entity_id cannot be parsed back.
        return {
            "artiled_scope": f"{self._kind}_{self._item_id}",
            "artiled_item": self._mode,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._client.run_mode(self._mode, {self._kind: self._item_id})
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._client.run_mode(self._mode, {self._kind: self._item_id}, running=0)
        await self.coordinator.async_request_refresh()
