# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Hub flows as button entities — press = start the flow."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ArtiHubFlowButton(data, flow)
        for flow in data["flows"]
        if str(flow.get("enable") or "1") == "1"
    )


class ArtiHubFlowButton(ButtonEntity):
    _attr_has_entity_name = True
    _attr_icon = "mdi:play-network-outline"

    def __init__(self, data: dict, flow: dict) -> None:
        self._client = data["client"]
        self._coordinator = data["coordinator"]
        self._flow_id = flow["id"]
        self._attr_name = f"Flow {flow.get('name', flow['id'])}"
        self._attr_unique_id = f"{data['hub_ident']}_flow_{flow['id']}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data["hub_ident"])},
        )

    async def async_press(self) -> None:
        await self._client.run_flow(self._flow_id)
        await self._coordinator.async_request_refresh()
