# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Async client for the ArtiLED Hub ArtiAPI (HTTP POST, token + json data)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import aiohttp


class ArtiHubError(Exception):
    """Raised when the Hub returns an error or is unreachable."""


class ArtiHubAuthError(ArtiHubError):
    """Raised when the token is rejected."""


class ArtiHubClient:
    """Minimal async ArtiAPI client. The Hub stays authoritative — this
    client never caches state; the coordinator owns polling."""

    def __init__(self, session: aiohttp.ClientSession, host: str, token: str) -> None:
        self._session = session
        self._host = host
        # The Hub's web root, for assets the BROWSER fetches directly — scene
        # and mode artwork under /images/scenes/. Kept separate from _base
        # because that one is the API and carries the token.
        self.origin = f"http://{host}"
        self._base = f"http://{host}/api"
        self._token = token
        # The Hub processes set commands synchronously (a room set can take
        # 15-25s) and concurrent API calls block on it. Serialize our own
        # calls so a poll never races one of our own commands.
        self._lock = asyncio.Lock()

    async def _call(
        self, endpoint: str, data: dict[str, Any] | None = None, timeout: int = 60
    ) -> dict[str, Any]:
        payload = {"token": self._token, "data": json.dumps(data or {})}
        try:
            async with self._lock:
                resp = await self._session.post(
                    f"{self._base}/{endpoint}",
                    data=payload,
                    timeout=aiohttp.ClientTimeout(total=timeout),
                )
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ArtiHubError(f"Hub unreachable: {err}") from err
        if not isinstance(body, dict) or int(body.get("success", 0)) != 1:
            error = int(body.get("error", 0)) if isinstance(body, dict) else 0
            if error == 2:
                raise ArtiHubAuthError("Token rejected by Hub")
            raise ArtiHubError(str(body.get("error_text") or "Hub error") if isinstance(body, dict) else "Hub error")
        return body.get("data") or {}

    @staticmethod
    async def login(
        session: aiohttp.ClientSession, host: str, username: str, password: str
    ) -> str:
        """Exchange the customer's Hub login for the Hub's API token.

        ⚠ The customer should never have to go and find an API token. They
        already have a Hub username and password — the same one they use for the
        Hub's own web interface — and /api/login turns that into the token.

        ⚠ THE TOKEN IS STORED, THE PASSWORD IS NOT. What comes back is read from
        /opt/artiled/data/token: a STABLE, Hub-wide token, not a session token.
        So nothing ever needs the password again, and a token that later stops
        working is a re-auth, exactly as before.
        """
        try:
            resp = await session.post(
                f"http://{host.strip()}/api/login",
                data={"data": json.dumps({"username": username, "password": password})},
                timeout=aiohttp.ClientTimeout(total=20),
            )
            body = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ArtiHubError(f"Hub unreachable: {err}") from err
        if not isinstance(body, dict) or int(body.get("success", 0)) != 1:
            raise ArtiHubAuthError(
                str(body.get("error_text") or "Login failed")
                if isinstance(body, dict)
                else "Login failed"
            )
        token = (body.get("data") or {}).get("token")
        if not token:
            raise ArtiHubError("Hub accepted the login but returned no token")
        return str(token)

    async def alive(self) -> dict[str, Any]:
        """Unauthenticated reachability probe — returns name + ident."""
        try:
            resp = await self._session.get(
                f"{self._base}/alive", timeout=aiohttp.ClientTimeout(total=10)
            )
            body = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise ArtiHubError(f"Hub unreachable: {err}") from err
        if not isinstance(body, dict) or int(body.get("success", 0)) != 1:
            raise ArtiHubError("Unexpected alive response")
        return body.get("data") or {}

    async def version(self) -> str:
        data = await self._call("version")
        return str(data.get("version", ""))

    async def rooms(self) -> list[dict[str, Any]]:
        return (await self._call("rooms")).get("rooms", [])

    async def zones(self) -> list[dict[str, Any]]:
        return (await self._call("zones")).get("zones", [])

    async def lights(self, scope: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return (await self._call("lights", scope)).get("lights", [])

    async def scenes(self, scope: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        return (await self._call("scenes", scope)).get("scenes", [])

    async def modes(self, scope: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Modes, optionally for one room/zone.

        ⚠ Modes are NOT universal. The Hub offers a different set per scope —
        measured on the dev Hub: 14 house-wide, but 6 in the Cinema and 2 in the
        Bedroom. Asking without a scope gives the house-wide list, which is the
        wrong thing to offer on a room.
        """
        return (await self._call("modes", scope or {})).get("modes", [])

    async def flows(self) -> list[dict[str, Any]]:
        return (await self._call("flows")).get("flows", [])

    async def set_room(self, room_id: int, **fields: Any) -> None:
        await self._call("room", {"room": room_id, **fields})

    async def set_zone(self, zone_id: int, **fields: Any) -> None:
        await self._call("zone", {"zone": zone_id, **fields})

    async def set_light(self, light_id: int, **fields: Any) -> None:
        # light.php has no Hue default at all — without hue:1 a set on a
        # Hue-type light is a no-op. Harmless for ArtiLED-type lights.
        await self._call("light", {"light": light_id, "hue": 1, **fields})

    async def run_scene(self, scene: int | str, scope: dict[str, Any] | None = None, running: int = 1) -> None:
        await self._call("scene", {"scene": scene, "running": running, **(scope or {})})

    async def run_mode(self, mode: int | str, scope: dict[str, Any] | None = None, running: int = 1) -> None:
        await self._call("mode", {"mode": mode, "running": running, **(scope or {})})

    async def run_flow(self, flow: int | str) -> None:
        await self._call("flow", {"flow": flow, "action": "start"})
