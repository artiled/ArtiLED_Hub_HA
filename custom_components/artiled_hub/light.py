# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Room and zone light entities — Hue-style, one light per room/zone."""
from __future__ import annotations

import re
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGBW_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ArtiHubError
from .const import DOMAIN, MIRED_MAX, MIRED_MIN

RGB_RE = re.compile(r"rgb\((\d+),\s*(\d+),\s*(\d+)\)")

KELVIN_MIN = round(1_000_000 / MIRED_MAX)  # 2000 K (warm)
KELVIN_MAX = round(1_000_000 / MIRED_MIN)  # 6536 K (cold)


def _kelvin_to_arti_temperature(kelvin: int) -> int:
    """Kelvin → ArtiLED white temperature 0..255.

    Same mapping the old YAML shim used: mired 153 (cold) → 0,
    mired 500 (warm) → 255."""
    mired = 1_000_000 / max(KELVIN_MIN, min(KELVIN_MAX, kelvin))
    return round((mired - MIRED_MIN) / (MIRED_MAX - MIRED_MIN) * 255)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator = data["coordinator"]
    entities: list[ArtiHubLight] = []
    for room_id in coordinator.data["rooms"]:
        entities.append(ArtiHubLight(entry, data, "room", room_id))
    for zone_id in coordinator.data["zones"]:
        entities.append(ArtiHubLight(entry, data, "zone", zone_id))
    for light_id, light in coordinator.data["lights"].items():
        if str(light.get("disabled", 0)) != "1":
            entities.append(ArtiHubLight(entry, data, "light", light_id))
    async_add_entities(entities)


class ArtiHubLight(CoordinatorEntity, LightEntity):
    """One room or zone. State always comes from the Hub — the only local
    memory is the last color temperature we set, because the Hub reports
    RGB readback only."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.RGBW}
    _attr_min_color_temp_kelvin = KELVIN_MIN
    _attr_max_color_temp_kelvin = KELVIN_MAX

    def __init__(self, entry: ConfigEntry, data: dict, kind: str, item_id: int) -> None:
        super().__init__(data["coordinator"])
        self._entry = entry
        self._client = data["client"]
        self._kind = kind  # "room" | "zone" | "light"
        self._item_id = item_id
        self._hub_ident = data["hub_ident"]
        self._scoped_scenes = data["scoped_scenes"]
        self._scoped_modes = data.get("scoped_modes") or {}
        self._origin = data["client"].origin
        self._members = data.get("members") or {}
        self._onoff = data["onoff"]
        self._last_color_temp_kelvin: int | None = None
        self._last_mode: ColorMode = ColorMode.RGBW
        self._attr_unique_id = f"{self._hub_ident}_{kind}_{item_id}"
        item = self._item() or {}
        # Every kind is its own device (pre-registered in __init__):
        # rooms/zones like Hue Rooms, individual lights like Hue bulbs.
        # The light entity is the device's primary entity (name = None).
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{self._hub_ident}_{kind}_{item_id}")},
        )

    def _item(self) -> dict | None:
        return self.coordinator.data[f"{self._kind}s"].get(self._item_id)

    @property
    def available(self) -> bool:
        item = self._item()
        if not super().available or item is None:
            return False
        if self._kind == "light" and str(item.get("down", 0)) == "1":
            return False
        # Disabled on the Hub. The entity is deliberately NOT deleted — the
        # customer means to bring it back, and deleting would take its
        # history, its area and any automation pointing at it. It reports
        # unavailable until the reload drops it from the offered set.
        if self._kind == "light" and str(item.get("disabled", 0)) == "1":
            return False
        return True

    @property
    def is_on(self) -> bool | None:
        item = self._item()
        if item is None:
            return None
        return str(item.get("state", "0")) == "1"

    @property
    def brightness(self) -> int | None:
        item = self._item()
        if item is None:
            return None
        try:
            return int(item.get("brightness", 0))
        except (TypeError, ValueError):
            return None

    @property
    def color_mode(self) -> ColorMode:
        return self._last_mode

    @property
    def color_temp_kelvin(self) -> int | None:
        return self._last_color_temp_kelvin

    @property
    def rgbw_color(self) -> tuple[int, int, int, int] | None:
        item = self._item()
        if not item:
            return None
        colors = item.get("colors") or []
        if not colors:
            return None
        match = RGB_RE.match(str(colors[0]))
        if not match:
            return None
        r, g, b = (int(v) for v in match.groups())
        return (r, g, b, 0)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        item = self._item() or {}
        running = item.get("running") or {}
        attributes: dict[str, Any] = {
            "artiled_id": self._item_id,
            "artiled_type": self._kind,
            "power": item.get("power"),
            "running_type": running.get("type"),
            "running_name": running.get("name"),
        }
        # ⚠ The Hub's FULL palette, not just the first stop.
        #
        # rgbw_color above must collapse to one colour - that is what a HA light
        # entity is - but the Hub sends an ordered ['rgb(r,g,b)', ...] palette,
        # and the gradient in the ArtiLED app IS that array. aggregate_lights_for()
        # in the Hub's functions.php takes it "verbatim from the FIRST on-light
        # ... preserves [start, end] shape so the app gets a real palette, not a
        # deduped scalar", so a two-stop wash comes from ONE light having a start
        # and an end colour - never from mixing several lights.
        #
        # Dropping it here is why the tile could only ever paint a flat fill.
        colors = item.get("colors")
        if colors:
            attributes["artiled_colors"] = list(colors)
        # ⚠ The Hub's OWN icon for this room/zone, e.g. "fas fa-couch". The
        # webapp renders exactly this (app/includes/tiles.php:
        # <i class="app-tile__icon <?php echo $item['icon']; ?>">), so the
        # dashboard has to carry it rather than invent one — hardcoding
        # mdi:sofa ignored every icon the customer chose in the Hub.
        icon = item.get("icon")
        if icon:
            attributes["artiled_icon"] = icon
        # ⚠ What this scope can actually run, WITH its artwork — the room screen
        # in the app is a grid of scene/mode pictures, not a list of names
        # (app/includes/entity-screen.php -> app_render_item_tiles). Neither the
        # id nor the image is recoverable from the select entity's options, so
        # the card would have to invent them; this is the same "port the input,
        # not just the function" trap that flattened the gradient.
        #
        # ⚠ The image path is ABSOLUTISED against the Hub's own web root: the
        # BROWSER fetches it, and it has no idea which host the Hub is on.
        if self._kind in ("room", "zone"):
            key = f"{self._kind}_{self._item_id}"
            for attr, source in (
                ("artiled_scenes", self._scoped_scenes),
                ("artiled_modes", self._scoped_modes),
            ):
                entries = []
                for entry in source.get(key, []) or []:
                    image = str(entry.get("image") or "")
                    entries.append({
                        "id": entry.get("id"),
                        "name": entry.get("name"),
                        "image": (self._origin + image) if image.startswith("/") else image,
                    })
                if entries:
                    attributes[attr] = entries
        # ⚠ Which Hub lights this scope contains. A ZONE's membership has
        # nowhere else to live: a device has one via_device and a light's is its
        # ROOM, so the device registry can express "this light is in the
        # Kitchen" but never "and also in the Kitchen Spots zone". Hub ids
        # rather than entity ids, because an entity id is not known here and is
        # a user-renameable thing; the frontend maps them through the device
        # identifiers, which cannot change.
        if self._kind != "light":
            member_ids = self._members.get(f"{self._kind}_{self._item_id}")
            if member_ids:
                attributes["member_light_ids"] = member_ids
        return attributes

    def _scope(self) -> dict[str, int]:
        return {self._kind: self._item_id}

    def _onoff_scene(self, action: str) -> str | None:
        """The scene id selected for this room/zone's turn-on/turn-off
        (the per-device select entities write it), or None for raw state."""
        if self._kind == "light":
            return None
        return (self._onoff.get(f"{self._kind}_{self._item_id}") or {}).get(action)

    async def _set(self, **fields: Any) -> None:
        if self._kind == "room":
            await self._client.set_room(self._item_id, **fields)
        elif self._kind == "zone":
            await self._client.set_zone(self._item_id, **fields)
        else:
            await self._client.set_light(self._item_id, **fields)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs: Any) -> None:
        fields: dict[str, Any] = {}

        if ATTR_RGBW_COLOR in kwargs:
            r, g, b, w = kwargs[ATTR_RGBW_COLOR]
            fields["color_rgbw"] = {"red": r, "green": g, "blue": b, "white": w}
            self._last_mode = ColorMode.RGBW
            self._last_color_temp_kelvin = None
        elif ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = int(kwargs[ATTR_COLOR_TEMP_KELVIN])
            # Intensity is part of the white color definition and always
            # goes full; the Hub's separate global brightness dims it.
            # (Same semantics as the old YAML shim.)
            fields["color_w"] = {
                "intensity": 255,
                "temperature": _kelvin_to_arti_temperature(kelvin),
            }
            self._last_mode = ColorMode.COLOR_TEMP
            self._last_color_temp_kelvin = kelvin

        if ATTR_BRIGHTNESS in kwargs:
            fields["brightness"] = int(kwargs[ATTR_BRIGHTNESS])

        if fields:
            # NEVER send state alongside brightness/color: state=1 fires
            # restore() (reload of saved output) and visibly kills lit
            # lights. Color commands wake lights by themselves; state is
            # only for plain on/off.
            #
            # Color changes exclude associated Hue lights by default (the
            # Hub UI sends hue:1 on its final color commit). HA commands
            # are always final commits, so include Hue. State/brightness
            # already include Hue by default in room.php/zone.php.
            if "color_rgbw" in fields or "color_w" in fields:
                fields["hue"] = 1
            await self._set(**fields)
            return

        # Plain turn_on: run the scene selected for this room/zone (the
        # per-device "Turn-on scene" select), so it comes up exactly the
        # way the Hub defines it.
        scene_id = self._onoff_scene("on")
        if scene_id:
            try:
                await self._client.run_scene(scene_id, self._scope())
                await self.coordinator.async_request_refresh()
                return
            except ArtiHubError:
                pass  # scene gone/out of scope — fall back to raw state
        await self._set(state=1)

    async def async_turn_off(self, **kwargs: Any) -> None:
        scene_id = self._onoff_scene("off")
        if scene_id:
            try:
                await self._client.run_scene(scene_id, self._scope())
                await self.coordinator.async_request_refresh()
                return
            except ArtiHubError:
                pass
        await self._set(state=0)
