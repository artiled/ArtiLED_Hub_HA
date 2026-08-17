# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Data update coordinator — polls the Hub's aggregated room/zone state."""
from __future__ import annotations

import logging
import time
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ArtiHubClient, ArtiHubError
from .const import DOMAIN, UPDATE_INTERVAL_SECONDS
from .inventory import presence, signature, stamp_seen

_LOGGER = logging.getLogger(__name__)


class ArtiHubCoordinator(DataUpdateCoordinator):
    """Polls /rooms + /zones. The Hub aggregates real per-light state at
    read time, so what we get here is the truth — never invented."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: ArtiHubClient,
        hub_name: str,
        memory: dict,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN} {hub_name}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.client = client
        self._failures = 0
        # When each item was last seen, on the last-successful-poll clock.
        # Drives `present`, which is what may be deleted.
        #
        # ⚠ THIS MUST OUTLIVE A RELOAD, so it is owned by hass.data and passed
        # in, not created here. Found the hard way 2026-08-14: a reload builds
        # a NEW coordinator, so a `_seen` created here started empty, its first
        # refresh recorded only what the Hub still had, and anything just
        # removed looked like it had never existed — deleted on the spot with
        # the grace period never getting a chance to run. Since a
        # disappearance is itself what triggers the reload, the protection was
        # defeated in exactly the case it existed for.
        self._memory = memory
        self._memory.setdefault("seen", {})
        self._memory.setdefault("last_success", None)

    @property
    def _seen(self) -> dict[tuple[str, int], float]:
        return self._memory["seen"]

    @property
    def _last_success(self) -> float | None:
        return self._memory["last_success"]

    @property
    def inventory(self) -> frozenset[tuple[str, int, bool]] | None:
        """What the Hub HAS, and whether each item is enabled — not what it is
        doing. Turning a light on or off does not change this; creating,
        deleting, disabling or re-enabling one does.

        `__init__` watches it and reloads the config entry when it moves, so a
        light, room or zone the customer adds on the Hub shows up in Home
        Assistant on its own, instead of waiting for someone to know that
        Reload exists.

        ⚠ The enabled flag is part of the signature ONLY so that re-enabling a
        light triggers the reload that recreates its entity. It must NOT be
        used to decide what to delete — see `present`.

        None while there is no data yet, so a failed first poll is never
        mistaken for an empty Hub.
        """
        return signature(self.data)

    @property
    def present(self) -> frozenset[tuple[str, int]] | None:
        """Everything the Hub still HAS, disabled or not — plus anything it
        had recently. This, never `inventory`, is what may be DELETED.

        ⚠ A light the customer DISABLED is one they intend to bring back: its
        entity keeps its id, history, area and any automation or dashboard
        card pointing at it, and simply stops being offered. Only a light they
        actually DELETED may have its entity and device removed.

        ⚠ AND NOT IMMEDIATELY. Michel, 2026-08-14: upgrading a LED computer
        takes its node down and the Hub auto-disables that node's lights. A
        disabled light is still returned by /lights (verified: the 11 disabled
        lights on the dev Hub all come back with disabled=1, down=1), so an
        upgrade does not empty this set — but a partial or odd response during
        one must not be able to delete a customer's entities either. So an
        item is only forgotten once it has been ABSENT for
        inventory.DELETE_GRACE_SECONDS. Deletion is irreversible and takes the
        entity's history with it; waiting an hour to tidy up costs nothing.

        ⚠ The clock is the last SUCCESSFUL poll, not wall time. If the Hub
        goes unreachable, nothing ages out while it is gone — otherwise an
        outage longer than the grace would silently mark every item deletable
        and the next reload would wipe the lot.

        ⚠ The backing map lives in hass.data and survives a reload, without
        which this grace is decorative — see __init__. It does NOT survive a
        full Home Assistant restart: after one, whatever the Hub reports is
        the new baseline, and anything genuinely gone is pruned on the next
        change. That is acceptable — a restart is a deliberate act, not
        something a passing glitch causes.
        """
        if not self.data:
            return None
        return presence(self._seen, self._last_success)

    async def _async_update_data(self) -> dict:
        try:
            rooms = await self.client.rooms()
            zones = await self.client.zones()
            lights = await self.client.lights()
            # Scenes, modes and flows are polled for one reason: so that a
            # scene the customer creates or deletes on the Hub reaches Home
            # Assistant on its own. They are cheap — get_scenes/get_modes
            # measured 16-23 ms against 78 ms for /rooms (card #388) — so
            # they ride the normal cycle rather than a second timer.
            scenes = await self.client.scenes()
            modes = await self.client.modes()
            flows = await self.client.flows()
        except ArtiHubError as err:
            # The Hub blocks reads while it executes a (slow, synchronous)
            # set command — possibly issued by another client. Keep serving
            # the last known state through brief hiccups; only mark
            # everything unavailable after repeated failures.
            self._failures += 1
            if self._failures < 3 and self.data:
                _LOGGER.debug("Hub poll failed (%s/2), keeping last state: %s", self._failures, err)
                return self.data
            raise UpdateFailed(str(err)) from err
        self._failures = 0
        data = {
            "rooms": {int(r["id"]): r for r in rooms},
            "zones": {int(z["id"]): z for z in zones},
            "lights": {int(l["id"]): l for l in lights},
            "scenes": {int(s["id"]): s for s in scenes},
            "modes": {int(m["id"]): m for m in modes},
            "flows": {int(f["id"]): f for f in flows},
        }
        # Stamp everything the Hub still has. Only a successful poll moves
        # this clock, so absence is counted in polls that actually answered.
        now = time.monotonic()
        self._memory["last_success"] = now
        stamp_seen(data, self._seen, now)
        return data
