# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Config flow for ArtiLED Hub."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ArtiHubAuthError, ArtiHubClient, ArtiHubError
from .const import CONF_TOKEN, DOMAIN

# ⚠ LOGIN, NOT A TOKEN. The customer has a Hub username and password already —
# the one they use for the Hub's own web interface — and the integration turns
# that into the API token itself via /api/login. Asking them to go and find a
# token in the Hub UI was work we could do for them, and it is what the Homey
# app does too.
#
# ⚠ What gets STORED is still the token, under the same CONF_TOKEN key as
# before, so existing config entries keep working untouched and no migration is
# needed. The password is used once and never persisted.
DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)

# Re-auth asks for the login only. The host is not re-asked on purpose: this
# flow exists because the CREDENTIALS stopped working, and re-typing an IP that
# was already right is a chance to get it wrong.
REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class ArtiHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the ArtiLED config flow (host + Hub login, Hue-style)."""

    VERSION = 1

    def __init__(self) -> None:
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            host = user_input[CONF_HOST]
            try:
                # Reachability first, so an unreachable Hub reports as such
                # rather than as a rejected password.
                probe = ArtiHubClient(session, host, "")
                alive = await probe.alive()
                token = await ArtiHubClient.login(
                    session, host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
                client = ArtiHubClient(session, host, token)
                version = await client.version()  # proves the token works
            except ArtiHubAuthError:
                errors["base"] = "invalid_auth"
            except ArtiHubError:
                errors["base"] = "cannot_connect"
            else:
                ident = alive.get("ident") or host
                await self.async_set_unique_id(ident)
                self._abort_if_unique_id_configured()
                # ⚠ Only host + token are persisted. The password did its one
                # job and is deliberately not written to the config entry.
                return self.async_create_entry(
                    title=f"{alive.get('name', 'ArtiLED Hub')} ({version})",
                    data={CONF_HOST: host, CONF_TOKEN: token},
                )
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        """The Hub rejected our token — ask for the login again.

        ⚠ WITHOUT THIS STEP THE PROMPT IS A DEAD END. __init__.py raises
        ConfigEntryAuthFailed when the Hub answers error 2, which makes Home
        Assistant show "reconfigure" on the integration — but a flow with no
        async_step_reauth cannot complete it. The customer's only way out was
        to DELETE the integration and add it again, which throws away every
        entity_id, area assignment, alias, voice exposure and history: a
        rotated Hub token would cost them their whole setup.
        """
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}
        entry = self._reauth_entry
        if entry is None:  # the entry vanished mid-flow
            return self.async_abort(reason="reauth_failed")

        if user_input is not None:
            host = entry.data[CONF_HOST]
            session = async_get_clientsession(self.hass)
            token = None
            try:
                probe = ArtiHubClient(session, host, "")
                alive = await probe.alive()
                token = await ArtiHubClient.login(
                    session, host, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
                )
                client = ArtiHubClient(session, host, token)
                await client.version()  # the call that actually validates a token
            except ArtiHubAuthError:
                errors["base"] = "invalid_auth"
            except ArtiHubError:
                errors["base"] = "cannot_connect"
            else:
                # ⚠ Must still be the SAME Hub. Without this, pointing a
                # re-auth at a different Hub would silently rebind every
                # existing entity to another device's rooms and zones —
                # unique_ids are built from the ident, so they would all go
                # stale at once and the entities would never come back.
                ident = alive.get("ident")
                if ident and entry.unique_id and ident != entry.unique_id:
                    return self.async_abort(reason="wrong_hub")
                return self.async_update_reload_and_abort(
                    entry, data={**entry.data, CONF_TOKEN: token}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={"host": entry.data[CONF_HOST]},
        )
