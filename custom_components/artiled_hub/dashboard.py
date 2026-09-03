# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Create the ArtiLED dashboard on setup (Planning #525).

Installing the integration used to leave one hand-editing step: create a
dashboard and paste the three-line strategy into the raw configuration editor.
That step was walked through at every site. This module does it from setup.

Design constraints, each a real failure mode:

1. CREATE ONCE, NEVER RE-CREATE. The config entry records that we made (or
   adopted) the dashboard. A customer who deletes it must find it stays
   deleted; recreating on every restart is a decision nobody can refuse. The
   Configure (options) flow offers to create it again, explicitly.
2. INTERNAL API, PINNED AND GUARDED. Home Assistant keeps the live dashboards
   collection only inside its websocket command handlers; there is no public
   "create a dashboard" call. Pinned against core 2026.8.3:
     hass.data["websocket_api"]["lovelace/dashboards/create"] -> (handler, schema)
       handler = require_admin(async_response(coll_ws.ws_create_item)) — TWO
       functools.wraps layers, so the registered object has __wrapped__ and no
       __self__; inspect.unwrap follows the chain to the bound method
     bound.__self__.storage_collection                          -> DashboardsCollection
     await collection.async_create_item({url_path, title, icon, ...})
       -> lovelace's own listener registers the LovelaceStorage + sidebar panel
     await hass.data[LOVELACE_DATA].dashboards[url_path].async_save(config)
   ⛔ Never instantiate a private DashboardsCollection: it writes the same
   storage file, and the live one overwrites it on the next UI change, so the
   dashboard would vanish at the next restart. If the live collection cannot
   be found, log and skip — presentation must never block control.
3. MULTI-HUB. The strategy renders every ArtiLED entity in Home Assistant, so
   ONE dashboard covers all hubs. The url path is fixed; a second entry finds
   it present and adopts it.
4. PER USER. The strategy runs per logged-in account; creating the dashboard
   does not change that.
5. NO HALF-MADE DASHBOARD THAT LOOKS FINISHED. If the item is created but the
   strategy config cannot be saved, an empty dashboard would sit there and be
   adopted (and marked done) at the next setup. So: roll the item back. If even
   that fails, record PENDING and stop: every later setup skips with a warning
   (no adopt, no save, no delete) until the installer clears it via Configure.
   ⛔ There is no automatic "finish later": the only dashboard we can PROVE is
   ours is the one created in the same call. Home Assistant derives the item id
   from the url path and reuses it after a deletion, so a customer's hand-made
   replacement at /artiled-app carries the same id 'artiled_app' — the id is
   not ownership proof, and neither is an empty config. Writing into "probably
   ours" is writing into theirs.

The decision is pure (plan_dashboard) so the fixtures can cover it without
Home Assistant; only async_create_dashboard touches hass, and it is wrapped.
"""
from __future__ import annotations

import inspect
import logging
from datetime import datetime, timezone
from typing import Any

_LOGGER = logging.getLogger(__name__)

CONF_CREATE_DASHBOARD = "create_dashboard"
DATA_DASHBOARD_CREATED = "dashboard_created_at"
DATA_DASHBOARD_PENDING = "dashboard_pending"     # {"id", "url_path"} — created, config never saved, rollback failed; blocks until Configure clears it
DASHBOARD_URL_PATH = "artiled-app"          # must contain a hyphen (HA rule)
DASHBOARD_TITLE = "ArtiLED"
DASHBOARD_ICON = "artiled:logo"
DASHBOARD_ITEM: dict[str, Any] = {
    "url_path": DASHBOARD_URL_PATH,
    "title": DASHBOARD_TITLE,
    "icon": DASHBOARD_ICON,
    "show_in_sidebar": True,
    "require_admin": False,
}
DASHBOARD_CONFIG: dict[str, Any] = {"strategy": {"type": "custom:artiled-hub"}, "views": []}
WS_CREATE_COMMAND = "lovelace/dashboards/create"


def plan_dashboard(wanted: bool, already_created: bool, exists: bool, pending: bool = False) -> str:
    """Decide what setup does. Pure.

    Returns one of:
      'skip:disabled'   the installer unticked the box
      'skip:created'    this entry already created/adopted it once (deleted later = stays deleted)
      'skip:pending'    an earlier create left an empty item we could not roll back -> touch nothing
      'adopt'           a dashboard with our url path exists (hand-made, or another hub's) -> record, don't create
      'create'          create it now, then record
    """
    if not wanted:
        return "skip:disabled"
    if already_created:
        return "skip:created"
    if pending:
        return "skip:pending"
    if exists:
        return "adopt"
    return "create"


def _find_live_collection(hass: Any) -> Any:
    """The DashboardsCollection lovelace registered its websocket commands on.

    Pinned to core 2026.8.3 (see module docstring). Any shape change returns
    None rather than a guess.
    """
    handlers = (hass.data or {}).get("websocket_api")
    if not isinstance(handlers, dict) or WS_CREATE_COMMAND not in handlers:
        return None
    entry = handlers[WS_CREATE_COMMAND]
    handler = entry[0] if isinstance(entry, (tuple, list)) else entry
    try:
        bound = inspect.unwrap(handler)   # require_admin(async_response(bound)) -> bound
    except Exception:  # noqa: BLE001 — a __wrapped__ cycle; treat as not found
        return None
    owner = getattr(bound, "__self__", None)
    coll = getattr(owner, "storage_collection", None)
    if coll is None or not hasattr(coll, "async_create_item"):
        return None
    return coll


def _lovelace_dashboards(hass: Any) -> dict | None:
    """hass.data[LOVELACE_DATA].dashboards — the live url_path -> config map."""
    try:
        from homeassistant.components.lovelace.const import LOVELACE_DATA  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — pinned internal import; absent means skip
        return None
    data = (hass.data or {}).get(LOVELACE_DATA)
    dashboards = getattr(data, "dashboards", None)
    return dashboards if isinstance(dashboards, dict) else None


def _record(hass: Any, entry: Any, **changes: Any) -> None:
    """Write marker changes to the entry; a None value removes the key."""
    data = {k: v for k, v in entry.data.items() if k not in changes}
    data.update({k: v for k, v in changes.items() if v is not None})
    hass.config_entries.async_update_entry(entry, data=data)


def _stamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


async def _save_config(dashboards: dict, url_path: str) -> bool:
    """Write the strategy config on the dashboard lovelace registered for url_path."""
    store = dashboards.get(url_path)
    if store is None or not hasattr(store, "async_save"):
        return False
    await store.async_save(dict(DASHBOARD_CONFIG))
    return True


async def async_create_dashboard(hass: Any, entry: Any) -> str:
    """Create (or adopt) the ArtiLED dashboard for this config entry. Never raises.

    Returns the plan outcome, or 'error:<reason>' when Home Assistant's internals
    did not match the pinned shape or the create failed.
    """
    try:
        wanted = bool(entry.data.get(CONF_CREATE_DASHBOARD, True))
        already = bool(entry.data.get(DATA_DASHBOARD_CREATED))
        pending = entry.data.get(DATA_DASHBOARD_PENDING) or None
        dashboards = _lovelace_dashboards(hass)
        if dashboards is None:
            _LOGGER.warning("ArtiLED dashboard not created: lovelace data not found (core version mismatch?)")
            return "error:no-lovelace-data"
        exists = DASHBOARD_URL_PATH in dashboards
        plan = plan_dashboard(wanted, already, exists, pending=bool(pending))
        if plan == "skip:pending":
            _LOGGER.warning(
                "ArtiLED dashboard: an earlier create left an empty dashboard at /%s (item %s) that "
                "could not be rolled back. Nothing is touched automatically. Delete that dashboard "
                "under Settings > Dashboards, then use Configure > 'Create the ArtiLED dashboard (again)'",
                DASHBOARD_URL_PATH, (pending or {}).get("id"),
            )
            return plan
        if plan.startswith("skip"):
            return plan

        if plan == "create":
            coll = _find_live_collection(hass)
            if coll is None:
                _LOGGER.warning("ArtiLED dashboard not created: live dashboards collection not found (core version mismatch?)")
                return "error:no-collection"
            created = await coll.async_create_item(dict(DASHBOARD_ITEM))
            item_id = str((created or {}).get("id") or "")
            try:
                saved = await _save_config(dashboards, DASHBOARD_URL_PATH)
            except Exception as err:  # noqa: BLE001
                saved = False
                _LOGGER.warning("ArtiLED dashboard: created but its config did not save: %s", err)
            if not saved:
                # Never leave an empty dashboard that the next setup would adopt as done.
                try:
                    await coll.async_delete_item(item_id)
                except Exception as err:  # noqa: BLE001
                    _LOGGER.warning("ArtiLED dashboard: rollback of item %s failed (%s); recorded as pending", item_id, err)
                    _record(hass, entry, **{DATA_DASHBOARD_PENDING: {"id": item_id, "url_path": DASHBOARD_URL_PATH, "at": _stamp()}})
                    return "error:pending"
                _LOGGER.warning("ArtiLED dashboard: empty item %s rolled back; will retry next setup", item_id)
                return "error:rolled-back"
            _LOGGER.info("ArtiLED dashboard created at /%s", DASHBOARD_URL_PATH)
        else:
            _LOGGER.info("ArtiLED dashboard already present at /%s — adopted, not re-created", DASHBOARD_URL_PATH)
        _record(hass, entry, **{DATA_DASHBOARD_CREATED: _stamp()})
        return plan
    except Exception as err:  # noqa: BLE001 — presentation must never block control
        _LOGGER.warning("ArtiLED dashboard not created: %s", err)
        return f"error:{type(err).__name__}"
