# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Diagnostic sensor: Hub firmware version."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ArtiHubVersionSensor(data)])


class ArtiHubVersionSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Firmware version"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:chip"

    def __init__(self, data: dict) -> None:
        self._attr_native_value = data["version"]
        self._attr_unique_id = f"{data['hub_ident']}_version"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, data["hub_ident"])},
        )
