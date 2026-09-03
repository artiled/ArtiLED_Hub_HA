#!/usr/bin/env python3
"""Hermetic fixtures for custom_components/artiled_hub/dashboard.py (#525).

No Home Assistant on this VM: the lovelace const module is stubbed and hass
is a duck. What is proven here is the contract, not HA's internals (those are
pinned by hand in the module docstring against core 2026.8.3).
"""
import asyncio
import importlib.util
import os
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
MOD = os.path.join(HERE, "..", "custom_components", "artiled_hub", "dashboard.py")

# Stub homeassistant.components.lovelace.const.LOVELACE_DATA (a HassKey in HA; any hashable here).
LOVELACE_KEY = "lovelace-key"
for name in ("homeassistant", "homeassistant.components", "homeassistant.components.lovelace"):
    sys.modules.setdefault(name, types.ModuleType(name))
const_mod = types.ModuleType("homeassistant.components.lovelace.const")
const_mod.LOVELACE_DATA = LOVELACE_KEY
sys.modules["homeassistant.components.lovelace.const"] = const_mod

spec = importlib.util.spec_from_file_location("artiled_dashboard", MOD)
dash = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dash)

passed = failed = 0


def check(name, cond):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("FAIL:", name)


# ---- pure planner -----------------------------------------------------------
check("plan: unticked wins", dash.plan_dashboard(False, False, False) == "skip:disabled")
check("plan: unticked wins even if absent+never created", dash.plan_dashboard(False, False, True) == "skip:disabled")
check("plan: created once stays deleted", dash.plan_dashboard(True, True, False) == "skip:created")
check("plan: existing is adopted", dash.plan_dashboard(True, False, True) == "adopt")
check("plan: fresh install creates", dash.plan_dashboard(True, False, False) == "create")
check("url path has a hyphen (HA rejects single words)", "-" in dash.DASHBOARD_URL_PATH)
check("config is the three-line strategy", dash.DASHBOARD_CONFIG == {"strategy": {"type": "custom:artiled-hub"}, "views": []})
check("item matches the hand-made dashboard on the master", dash.DASHBOARD_ITEM == {
    "url_path": "artiled-app", "title": "ArtiLED", "icon": "artiled:logo", "show_in_sidebar": True, "require_admin": False})


# ---- duck-typed Home Assistant ---------------------------------------------
import functools


class Store:
    def __init__(self, fail_save=False, config=None):
        self.saved = None
        self.save_calls = 0
        self.config = config          # what a customer already put in it (None = never saved)
        self.fail_save = fail_save

    async def async_save(self, config):
        self.save_calls += 1
        if self.fail_save:
            raise OSError("disk full")
        self.saved = config
        self.config = config


class Collection:
    """Stands in for lovelace's DashboardsCollection (helpers.collection.DictStorageCollection).

    Creating registers the LovelaceStorage under the url path, as lovelace's own
    listener does; deleting removes it again. Switches inject the failures.
    """

    def __init__(self, dashboards, fail=False, fail_save=False, fail_delete=False, no_register=False):
        self.dashboards = dashboards
        self.created = []
        self.deleted = []
        self.data = {}             # id -> item, like DictStorageCollection.data
        self.fail = fail
        self.fail_save = fail_save
        self.fail_delete = fail_delete
        self.no_register = no_register

    def preload(self, url_path="artiled-app", title="ArtiLED", icon="artiled:logo", config=None):
        """A dashboard that already exists — hand-made or from another hub — represented the
        way real HA represents it: in BOTH the lovelace map and the collection data, with the
        id HA derives from the url path (slug; reused after a deletion)."""
        item_id = url_path.replace("-", "_")
        self.data[item_id] = {"id": item_id, "url_path": url_path, "title": title, "icon": icon,
                              "show_in_sidebar": True, "require_admin": False}
        store = Store(config=config)
        self.dashboards[url_path] = store
        return store

    async def async_create_item(self, item):
        if self.fail:
            raise RuntimeError("Url path needs to contain a hyphen (-)")
        self.created.append(item)
        item_id = item["url_path"].replace("-", "_")
        stored = {"id": item_id, **item}
        self.data[item_id] = stored
        if not self.no_register:
            self.dashboards[item["url_path"]] = Store(fail_save=self.fail_save)
        return stored

    async def async_delete_item(self, item_id):
        if self.fail_delete:
            raise RuntimeError("storage write failed")
        item = self.data.pop(item_id)
        self.deleted.append(item_id)
        self.dashboards.pop(item["url_path"], None)


class WsOwner:
    """The StorageCollectionWebsocket instance whose bound method HA registers."""

    def __init__(self, coll):
        self.storage_collection = coll

    async def ws_create_item(self, hass, connection, msg):
        pass


# --- Home Assistant's exact registration shape (core 2026.8.3) ---------------
# helpers/collection.py registers  require_admin(async_response(self.ws_create_item))
# and components/websocket_api/decorators.py wraps each with functools.wraps, so the
# registered object has __wrapped__ (twice) and NO __self__.
def ha_async_response(func):
    @functools.wraps(func)
    def schedule_handler(hass, connection, msg):
        return None
    schedule_handler._hass_callback = True   # what @callback adds
    return schedule_handler


def ha_require_admin(func):
    @functools.wraps(func)
    def with_admin(hass, connection, msg):
        return func(hass, connection, msg)
    return with_admin


def ha_registered_handler(owner):
    return ha_require_admin(ha_async_response(owner.ws_create_item))


class Entries:
    def __init__(self):
        self.updates = []

    def async_update_entry(self, entry, data=None):
        self.updates.append(data)
        entry.data = data


class Entry:
    def __init__(self, data):
        self.data = dict(data)


def make_hass(dashboards, with_collection=True, fail_create=False, **coll_kw):
    coll = Collection(dashboards, fail=fail_create, **coll_kw)
    data = {LOVELACE_KEY: types.SimpleNamespace(dashboards=dashboards)}
    if with_collection:
        # registered exactly as HA does: decorated twice, no __self__ on the outer object
        handler = ha_registered_handler(WsOwner(coll))
        assert not hasattr(handler, "__self__") and hasattr(handler, "__wrapped__")
        data["websocket_api"] = {dash.WS_CREATE_COMMAND: (handler, None)}
    return types.SimpleNamespace(data=data, config_entries=Entries()), coll


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# fresh install: creates, writes the strategy config, records the marker
dashboards = {}
hass, coll = make_hass(dashboards)
entry = Entry({"host": "1.2.3.4", "token": "t", "create_dashboard": True})
out = run(dash.async_create_dashboard(hass, entry))
check("fresh: outcome create", out == "create")
check("fresh: created exactly one item with the pinned fields", coll.created == [dash.DASHBOARD_ITEM])
check("fresh: strategy config saved on the new store", dashboards["artiled-app"].saved == dash.DASHBOARD_CONFIG)
check("fresh: marker recorded on the entry", bool(entry.data.get(dash.DATA_DASHBOARD_CREATED)))
check("fresh: original entry data kept", entry.data["host"] == "1.2.3.4" and entry.data["token"] == "t")

# same entry again (restart) with the dashboard deleted by the customer: stays deleted
dashboards.clear()
out2 = run(dash.async_create_dashboard(hass, entry))
check("restart after delete: skipped", out2 == "skip:created")
check("restart after delete: nothing created", len(coll.created) == 1 and dashboards == {})

# second hub (new entry) while the first hub's dashboard exists: adopt, never a second dashboard
dashboards2 = {}
hass2, coll2 = make_hass(dashboards2)
coll2.preload()   # the first hub's dashboard, live-consistent
entry2 = Entry({"host": "5.6.7.8", "token": "u", "create_dashboard": True})
out3 = run(dash.async_create_dashboard(hass2, entry2))
check("second hub: adopted", out3 == "adopt")
check("second hub: no create call", coll2.created == [])
check("second hub: existing config untouched", dashboards2["artiled-app"].saved is None)
check("second hub: marker recorded so it never creates later", bool(entry2.data.get(dash.DATA_DASHBOARD_CREATED)))

# hand-made dashboard on an existing install (the master): adopted, config not overwritten
dashboards3 = {}
hass3, coll3 = make_hass(dashboards3)
coll3.preload(config={"views": [{"title": "Home", "cards": []}]})   # hand-made, with content
entry3 = Entry({"host": "h", "token": "t"})  # pre-0.32 entry: no checkbox key -> default on
out4 = run(dash.async_create_dashboard(hass3, entry3))
check("pre-0.32 entry with hand-made dashboard: adopt, zero saves", out4 == "adopt" and coll3.created == [] and dashboards3["artiled-app"].save_calls == 0)

# unticked at setup: nothing happens, no marker
hass4, coll4 = make_hass({})
entry4 = Entry({"host": "h", "token": "t", "create_dashboard": False})
out5 = run(dash.async_create_dashboard(hass4, entry4))
check("unticked: skipped, nothing created, no marker", out5 == "skip:disabled" and coll4.created == [] and not entry4.data.get(dash.DATA_DASHBOARD_CREATED))

# HA internals not matching the pin: log and continue, never raise, no marker (so a later fixed version may create)
hass5, coll5 = make_hass({}, with_collection=False)
entry5 = Entry({"host": "h", "token": "t"})
out6 = run(dash.async_create_dashboard(hass5, entry5))
check("no live collection: error outcome, no raise", out6 == "error:no-collection")
check("no live collection: no marker", not entry5.data.get(dash.DATA_DASHBOARD_CREATED))
hass6 = types.SimpleNamespace(data={}, config_entries=Entries())
out7 = run(dash.async_create_dashboard(hass6, Entry({"host": "h"})))
check("no lovelace data: error outcome, no raise", out7 == "error:no-lovelace-data")

# create itself failing inside HA: swallowed, no marker
hass7, coll7 = make_hass({}, fail_create=True)
entry7 = Entry({"host": "h", "token": "t"})
out8 = run(dash.async_create_dashboard(hass7, entry7))
check("create raises: error outcome, no raise, no marker", out8 == "error:RuntimeError" and not entry7.data.get(dash.DATA_DASHBOARD_CREATED))

# the collection finder resolves HA's real registration and is strict about shape
real = ha_registered_handler(WsOwner(coll))
check("finder: HA's require_admin(async_response(bound)) resolves to the live collection",
      dash._find_live_collection(types.SimpleNamespace(data={"websocket_api": {dash.WS_CREATE_COMMAND: (real, None)}})) is coll)
check("finder: a plain bound method also resolves", dash._find_live_collection(types.SimpleNamespace(data={"websocket_api": {dash.WS_CREATE_COMMAND: (WsOwner(coll).ws_create_item, None)}})) is coll)
check("finder: bare handler (not tuple) also resolved", dash._find_live_collection(types.SimpleNamespace(data={"websocket_api": {dash.WS_CREATE_COMMAND: real}})) is coll)
check("finder: undecorated function without __self__ -> None", dash._find_live_collection(types.SimpleNamespace(data={"websocket_api": {dash.WS_CREATE_COMMAND: (lambda *a: None, None)}})) is None)
check("finder: missing command -> None", dash._find_live_collection(types.SimpleNamespace(data={"websocket_api": {}})) is None)
check("finder: decorated function whose innermost has no storage_collection -> None",
      dash._find_live_collection(types.SimpleNamespace(data={"websocket_api": {dash.WS_CREATE_COMMAND: (ha_require_admin(ha_async_response(lambda *a: None)), None)}})) is None)

# ---- partial creation must never become a permanent false success ----------
# save fails after create: the empty item is rolled back, nothing recorded
d8 = {}
hass8, coll8 = make_hass(d8, fail_save=True)
entry8 = Entry({"host": "h", "token": "t"})
out9 = run(dash.async_create_dashboard(hass8, entry8))
check("save fails: rolled back", out9 == "error:rolled-back" and coll8.deleted == ["artiled_app"] and d8 == {})
check("save fails: no marker, no pending", not entry8.data.get(dash.DATA_DASHBOARD_CREATED) and not entry8.data.get(dash.DATA_DASHBOARD_PENDING))
# ...and the next setup simply creates again
coll8.fail_save = False
out10 = run(dash.async_create_dashboard(hass8, entry8))
check("after rollback: next setup creates fresh with config", out10 == "create" and d8["artiled-app"].saved == dash.DASHBOARD_CONFIG and bool(entry8.data.get(dash.DATA_DASHBOARD_CREATED)))

# listener did not register the store: same rollback
d9 = {}
hass9, coll9 = make_hass(d9, no_register=True)
entry9 = Entry({"host": "h", "token": "t"})
out11 = run(dash.async_create_dashboard(hass9, entry9))
check("store never registered: rolled back, no marker", out11 == "error:rolled-back" and coll9.deleted == ["artiled_app"] and not entry9.data.get(dash.DATA_DASHBOARD_CREATED))

# save fails AND rollback fails: recorded as pending with OUR id, never as created
d10 = {}
hass10, coll10 = make_hass(d10, fail_save=True, fail_delete=True)
entry10 = Entry({"host": "h", "token": "t"})
out12 = run(dash.async_create_dashboard(hass10, entry10))
pend = entry10.data.get(dash.DATA_DASHBOARD_PENDING) or {}
check("rollback fails: pending recorded with our id + url path + time", out12 == "error:pending" and pend.get("id") == "artiled_app" and pend.get("url_path") == "artiled-app" and bool(pend.get("at")))
check("rollback fails: not marked created", not entry10.data.get(dash.DATA_DASHBOARD_CREATED))
# next setup with pending: our empty item still exists -> NOTHING is touched (no adopt, no save, no delete)
d10["artiled-app"].fail_save = False
saves_before = d10["artiled-app"].save_calls      # the failed save of the first run is expected; nothing may be ADDED
out13 = run(dash.async_create_dashboard(hass10, entry10))
check("pending + our empty item present: skipped", out13 == "skip:pending")
check("pending: zero new saves, zero deletes, no second create", d10["artiled-app"].save_calls == saves_before and coll10.deleted == [] and len(coll10.created) == 1)
check("pending: still pending, still not created", entry10.data.get(dash.DATA_DASHBOARD_PENDING) and not entry10.data.get(dash.DATA_DASHBOARD_CREATED))

# THE SAME-ID REPLACEMENT CASE (review finding): pending, our empty item was deleted, the customer made a hand-made replacement at the
# same url path. HA derives the id from the url path and reuses it, so the replacement is ALSO artiled_app,
# in both the lovelace map and the collection data. It must receive zero async_save calls.
d12 = {}
hass12, coll12 = make_hass(d12)
replacement = coll12.preload(config={"views": [{"title": "Mine", "cards": [{"type": "markdown", "content": "hands off"}]}]})
entry12 = Entry({"host": "h", "token": "t", dash.DATA_DASHBOARD_PENDING: {"id": "artiled_app", "url_path": "artiled-app"}})
out15 = run(dash.async_create_dashboard(hass12, entry12))
check("pending + same-id hand-made replacement: skipped, not adopted", out15 == "skip:pending" and not entry12.data.get(dash.DATA_DASHBOARD_CREATED))
check("pending + same-id hand-made replacement: ZERO async_save calls, content intact", replacement.save_calls == 0 and replacement.config["views"][0]["title"] == "Mine")
check("pending + same-id hand-made replacement: nothing created or deleted", coll12.created == [] and coll12.deleted == [])
# ...and even an EMPTY same-id replacement gets no write: emptiness is not ownership either
d12b = {}
hass12b, coll12b = make_hass(d12b)
empty_replacement = coll12b.preload()
entry12b = Entry({"host": "h", "token": "t", dash.DATA_DASHBOARD_PENDING: {"id": "artiled_app", "url_path": "artiled-app"}})
out15b = run(dash.async_create_dashboard(hass12b, entry12b))
check("pending + EMPTY same-id replacement: zero saves, skipped", out15b == "skip:pending" and empty_replacement.save_calls == 0)

# the only way out is Configure -> "create again": it clears pending + marker (as the options flow does) and re-plans
# (a) the installer deleted the empty dashboard first -> fresh create
d13 = {}
hass13, coll13 = make_hass(d13)
entry13 = Entry({"host": "h", "token": "t", dash.DATA_DASHBOARD_PENDING: {"id": "artiled_app", "url_path": "artiled-app"}})
entry13.data = {k: v for k, v in entry13.data.items() if k not in (dash.DATA_DASHBOARD_CREATED, dash.DATA_DASHBOARD_PENDING)}
out16 = run(dash.async_create_dashboard(hass13, entry13))
check("configure after deleting the empty one: created fresh with config", out16 == "create" and len(coll13.created) == 1 and d13["artiled-app"].saved == dash.DASHBOARD_CONFIG)
# (b) something still exists at our url path -> adopted, never written into
d14 = {}
hass14, coll14 = make_hass(d14)
kept = coll14.preload(config={"views": [{"title": "Mine"}]})
entry14 = Entry({"host": "h", "token": "t", dash.DATA_DASHBOARD_PENDING: {"id": "artiled_app", "url_path": "artiled-app"}})
entry14.data = {k: v for k, v in entry14.data.items() if k not in (dash.DATA_DASHBOARD_CREATED, dash.DATA_DASHBOARD_PENDING)}
out17 = run(dash.async_create_dashboard(hass14, entry14))
check("configure with a dashboard present: adopted, zero saves", out17 == "adopt" and kept.save_calls == 0 and coll14.created == [])

# planner: pending wins over exists, created wins over pending
check("plan: pending -> skip, whether or not something exists", dash.plan_dashboard(True, False, True, pending=True) == "skip:pending" and dash.plan_dashboard(True, False, False, pending=True) == "skip:pending")
check("plan: created beats pending", dash.plan_dashboard(True, True, True, pending=True) == "skip:created")
check("plan: unticked beats pending", dash.plan_dashboard(False, False, True, pending=True) == "skip:disabled")

print(f"{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
