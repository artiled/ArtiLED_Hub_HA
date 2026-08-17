# ArtiLED Hub — Home Assistant integration

Native local integration for the ArtiLED Hub. Home Assistant controls and
observes the Hub over its local HTTP API (ArtiAPI); the Hub remains the
single source of truth — this integration never invents state.

Proprietary ArtiLED source — published so it can be **installed and updated**,
not to invite forks. See Copyright below.

## Features

- **Config flow** — add via Settings → Devices & services → Add integration →
  "ArtiLED Hub". Enter host + API token; validated against `/alive` and
  `/version`. The Hub ident is the unique id, so the same Hub can't be added
  twice.
- **Lights** — one HA light entity per Hub **room**, per **zone**, and per
  **individual light**. Hue-style device model: rooms/zones are devices
  (like Hue Rooms) and every individual light is its own device (like Hue
  bulbs), nested under its room and suggested into the room's area.
  Hub-disabled lights are skipped, down lights show unavailable. All with:
  - on/off, brightness (native 0–255, no scaling loss)
  - RGBW color (`rgbw_color` → Hub `color_rgbw`)
  - color temperature (kelvin → Hub white channel `color_w`; 2000–6536 K
    mapped to the Hub's 0–255 temperature scale)
  - state, brightness and color read back from the Hub every 10 s via a
    DataUpdateCoordinator polling `/rooms` + `/zones` + `/lights`, plus
    `/scenes` + `/modes` + `/flows` for inventory changes (cheap — 16–23 ms
    each against 78 ms for `/rooms`)
  - `running_type` / `running_name` attributes showing the scene or mode the
    Hub reports as active on that room/zone/light
- **Turn-on / Turn-off scene pickers** — every room and zone device has two
  config dropdowns ("Turn-on scene", "Turn-off scene") listing the scenes
  the Hub offers **for that scope**, plus "None (plain on/off)". The
  selection drives what the light's turn on/off does and persists across
  restarts. Defaults to the Hub scenes named `On`/`Off` where they exist;
  falls back to a raw state command if the selected scene disappears.
- **Scenes and modes are run PER ROOM/ZONE** — every room and zone device has a
  **Scene** and a **Mode** dropdown offering exactly what the Hub says that
  scope supports, and running one applies it to that scope only.
  - ⚠ Nothing is universal. On a 12-room Hub measured during development: 40
    scenes house-wide but only 26–31 offered in any given room, and 14 modes
    against 2–6. Two scenes were offered in **no** room at all.
  - The Hub's scoped list already includes global scenes (`scene_rooms`
    containing `0`) alongside that scope's own, so the integration never has to
    model "global" itself.
  - ⚠ A mode picker's **None** stops whatever is running; it is not the same as
    the Hub's own **Off** mode, which is a mode that darkens the lights.
  - Their ids follow the Hub, not the HA area: `select.living_room_scene`,
    `select.cinema_mode`. Home Assistant would otherwise build the id from the
    device's **area** as well as its name, giving
    `select.living_room_living_room_scene` for a room sitting in an area of the
    same name, and `select.woonkamer_living_room_scene` where the two differ.
    ⚠ Each picker is renamed **once**, when it first appears, and never onto an
    id something else already holds — rename one yourself afterwards and your
    choice stands.
- **House-wide scene entities and mode switches** — still present, **hidden by
  default**. Activating one applies to *every* light in the house, which is
  rarely what someone reaching for a scene means, and is how a "PowerOff" scene
  can switch off a whole home from one tap. ⚠ Hidden rather than removed, so any
  automation already referencing one keeps working. Existing installs get a
  one-time hide that never re-hides anything you choose to show.
- **Flows** — button entities; press starts the flow.
- **Services** — scoped scene/mode control for automations:
  `artiled_hub.run_scene`, `artiled_hub.stop_scene`, `artiled_hub.run_mode`,
  `artiled_hub.stop_mode` — each takes `name` plus optional `room` or `zone`.
- **Follows the Hub's inventory** — create a room, zone, light, scene, mode or
  flow on the Hub and it appears in Home Assistant on its own within about ten
  seconds; delete one and its entity and device go. No Reload, no restart.
  - ⚠ **Disabling a light is not deleting it.** A light disabled on the Hub
    stops being offered and reports unavailable, but keeps its entity id,
    history, area and any automation or dashboard card pointing at it — so
    re-enabling it gives all of that back. This matters in normal use:
    upgrading a LED computer takes its node down and the Hub auto-disables
    that node's lights.
  - ⚠ Deletion waits for an item to be **absent for an hour**, measured on the
    last successful poll, so neither an odd response nor an unreachable Hub can
    remove a customer's entities. A stale entity is untidy; a deleted one takes
    its history with it. The "last seen" record survives a reload (it has to —
    a disappearance is what triggers the reload); a full HA restart re-baselines
    to whatever the Hub reports.
- **Dashboard that builds itself** — the integration ships its own frontend
  module (no HACS, no manual resource, nothing for a customer to install). Point
  a dashboard at it and the whole config is three lines:

  ```yaml
  strategy:
    type: custom:artiled-hub
  views: []
  ```

  Views are generated at page load from the Hub's own inventory. Create a room
  on the Hub and it appears — no YAML, no entity ids to maintain, nothing
  house-specific.
  - Shaped like the ArtiLED app's home screen: one page with a
    **Rooms** heading and its tiles, then a **Zones** heading and its tiles.
    Tapping one opens **that scope's own page** (an HA subview, with a back
    arrow) carrying its Scene and Mode pickers and the lights that belong to it.
    The overview is not an endless scroll of every light in the house.
  - ⚠ A scope's lights come from the `member_light_ids` attribute on its light
    entity, **not** from `via_device`. A device has exactly one parent and a
    light's is its *room*, so via_device can say "this light is in the Kitchen"
    but never "and also in the Kitchen Spots zone" — zones would get an empty
    page and a flat single-colour tile.
  - A **Hub** view carries flows and diagnostics.
  - Rooms and zones are matched by **device identifier**, and their Scene/Mode
    dropdowns by **unique_id** — never by entity_id or display name, both of
    which a user may rename.
  - ⚠ House-wide scene entities and mode switches are deliberately **not** on
    the generated dashboard, for the same reason they are hidden by default.
- **ArtiLED tile card** — `custom:artiled-tile-card`, the room/zone/light tile
  from the ArtiLED app: name, running scene or mode, iOS-style switch and a
  brightness slider. When a room is on, **its own LED colours wash across the
  card** as a gradient and the text flips dark or light by luminance, so a
  white-lit room is a white card with black text.
  - ⚠ It is a **port**, not a reinterpretation — the design is a paid asset.
    Geometry, gradient direction and the luminance rule are transcribed from the
    ArtiLED app itself, and `tests/test_frontend.js` pins them so the two
    implementations cannot drift.
  - ⚠ The wash comes from the Hub's **own palette**, exposed as the
    `artiled_colors` attribute. A HA light entity's `rgb_color` is by definition
    a single colour, so reading that alone flattens every gradient — the Hub
    sends an ordered `['rgb(r,g,b)', ...]` array and `aggregate_lights_for()`
    takes it verbatim from the first on-light, preserving the [start, end]
    shape so the app gets a real palette, not a deduped scalar. A two-stop wash is
    therefore **one light's start and end colour**, never a blend across lights.
- **The ArtiLED logo as an icon** — the module registers an `artiled:` iconset,
  so `artiled:logo` works anywhere Home Assistant takes an icon name (the
  sidebar item, a heading card, a tile). It inherits `currentColor`, so it
  follows the sidebar's active state like any built-in icon.
  - ⚠ The path is **measured** from `app/img/icon-512.png` (arch centre
    255.5,259 · outer r 205 · inner r 98 · dot 255.5,322 r 52, scaled by
    24/512), not drawn by eye — rendered back against the original it scores
    IoU 0.966 with area within 1.8%.
- **Diagnostics** — Hub firmware version sensor on the hub device.
- **Devices** — one hub device, one device per room and zone
  (`via_device` → hub), one device per individual light (`via_device` →
  its room), Hue-style.

## State semantics

- Hub says off → HA shows off. Hub unreachable → entities go *unavailable*.
  Nothing is ever assumed from our own commands.
- The one exception: the Hub reads back RGB only, so the last color
  temperature **we** set is remembered locally for display until a color
  command replaces it.

## Install via HACS (recommended)

1. HACS → ⋮ → **Custom repositories**
2. Repository `https://github.com/artiled/ArtiLED_Hub_HA`, type **Integration**
3. Install **ArtiLED Hub**, then restart Home Assistant
4. Settings → Devices & services → **Add integration** → ArtiLED Hub
5. Host = Hub IP, token = Hub API token (Hub UI → Settings → API)

HACS then offers updates whenever a new release is tagged — that is the whole
reason for publishing here.

## Install (manual)

1. Copy `custom_components/artiled_hub/` into the HA config dir:
   `/config/custom_components/artiled_hub/`
2. Restart Home Assistant.
3. Settings → Devices & services → **Add integration** → ArtiLED Hub.
4. Host = Hub IP, token = Hub API token.

⚠ A manual install does not update itself. Use HACS unless you have a reason
not to.

Nothing to migrate — this integration replaces any hand-written YAML you may
have had, and no ArtiLED install ships YAML templates.

## Requirements

- Hub firmware 1.60+ (ArtiAPI 1.45)
- No extra Python dependencies (uses HA's shared aiohttp session)

## Copyright

Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.

This is proprietary software. Not open source. Not for redistribution, and not
open to derivative works. It is published in a public repository for one reason:
so that ArtiLED customers and resellers can install and update it through HACS,
which reads from GitHub only.

Being readable here grants no licence to reuse it. The bundled browser libraries
are the exception — they are third-party, keep their own licences, and are listed
in [THIRD-PARTY.md](THIRD-PARTY.md) with their full texts in `LICENSES/`.

Issues and questions: <https://github.com/artiled/ArtiLED_Hub_HA/issues>
