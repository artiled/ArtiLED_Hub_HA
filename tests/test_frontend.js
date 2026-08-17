#!/usr/bin/env node
// Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
/* Tests for the frontend module's pure rules.
 *
 * Run:  node tests/test_frontend.js      (exit 0 = all pass)
 *
 * No browser and no build step. The module is evaluated in a vm with the few
 * browser globals it touches stubbed, then an appended epilogue hands the
 * internal functions back for testing. Production code is loaded as shipped —
 * nothing here is a copy of it.
 *
 * ⚠ WHY THIS FILE EXISTS. Two things are now implemented twice in two
 * languages and MUST agree:
 *
 *   1. which unique_id is a run picker  — entity_ids.py  vs  RUN_PICKER here.
 *      Disagreement means the dashboard silently wires the wrong dropdown onto
 *      a room, or none at all.
 *   2. the tile's luminance and gradient rules — app/js/paint.js and
 *      app/includes/tiles.php vs font_color()/background() here. These are a
 *      PAID design (CodeBee); drift is a visual regression nobody would notice
 *      until a white-lit room showed white text on white.
 *
 * The run-picker cases below are deliberately the SAME strings as
 * tests/test_entity_ids.py. Change one file and this fails.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const SRC = path.join(__dirname, "..", "custom_components", "artiled_hub", "frontend", "artiled-hub.js");

class FakeElement {
  attachShadow() { return { innerHTML: "", querySelector: () => null }; }
}
const defined = new Map();
const sandbox = {
  HTMLElement: FakeElement,
  customElements: {
    define: (tag, ctor) => defined.set(tag, ctor),
    get: (tag) => defined.get(tag),
    whenDefined: () => Promise.resolve(),
  },
  window: {},
  document: { activeElement: null, querySelector: () => null },
  location: { href: "http://ha.local/" },
  URL,
  fetch: () => Promise.resolve({ ok: false }),
  console,
  setTimeout,
  Promise,
  Date,
  JSON,
  /* The registry watcher is a real interval; capture it rather than let it
     run, so the test process exits and the poll cannot outlive the check. */
  setInterval: () => 0,
  clearInterval: () => {},
};
sandbox.globalThis = sandbox;
vm.createContext(sandbox);

const source =
  fs.readFileSync(SRC, "utf8") +
  "\n;globalThis.__t = {font_color, background, entity_rgb, tile_status, classify, run_picker_suffix, fa_name};\n";
vm.runInContext(source, sandbox, { filename: SRC });
const t = sandbox.__t;

const FAILURES = [];

/* ⚠ A stray NUL byte once made this file `file`-type "data" rather than text.
   It cost an hour: node --check PASSED (a NUL inside a string literal is legal
   JavaScript), the browser fetched it 200 OK with the right MIME, and the
   custom elements silently never registered — no console error, nothing in the
   HA log. grep stopped matching the file, which was the only visible symptom.
   Checked here because every other gate missed it. */
function guard_source() {
  const raw = fs.readFileSync(SRC);
  return {
    nul: raw.includes(0),
    utf8_clean: Buffer.compare(Buffer.from(raw.toString("utf8"), "utf8"), raw) === 0,
  };
}
function check(label, ok, hint) {
  console.log(`  ${ok ? "ok  " : "FAIL"}  ${label}`);
  if (!ok) {
    FAILURES.push(label);
    if (hint) console.log(`        ${hint}`);
  }
}

const IDENT = "SheCh6feegh9chu";

/* ------------------------------------------------------------------ */
console.log("\nthe shipped file is text a browser will actually execute");
const guard = guard_source();
check("no NUL byte in the module", !guard.nul,
      "a NUL makes the file binary; node --check still passes and the browser " +
      "loads it 200 OK, but the custom elements never register and nothing logs");
check("the module is clean UTF-8", guard.utf8_clean);
const SOURCE = fs.readFileSync(SRC, "utf8");
check("both custom elements are registered",
      defined.has("artiled-tile-card") &&
      defined.has("ll-strategy-dashboard-artiled-hub"),
      "the strategy tag must be exactly ll-strategy-dashboard-<type without custom:>");
/* ⚠ The registration must stay DEFERRED. A top-level customElements.define()
   lands ~96ms in, before HA installs scoped-custom-element-registry and
   replaces window.customElements — the elements then live in the native
   registry, which nothing looks at. It fails silently: define() succeeds, no
   console error, no HA log line, and the dashboard just reports
   "Timeout waiting for strategy element ... to be registered". */
check("registration targets BOTH registries",
      /define_all\(NATIVE_REGISTRY\)/.test(SOURCE) &&
      /define_all\(customElements\)/.test(SOURCE),
      "betting on one registry is what broke it: HA replaces window.customElements");
check("the swap is watched, and the watch is bounded",
      /customElements !== NATIVE_REGISTRY/.test(SOURCE) &&
      /clearInterval\(watcher\)/.test(SOURCE) &&
      /REGISTRY_WATCH_MS/.test(SOURCE),
      "an unbounded poll would run for the life of the page");
check("define_once swallows an already-defined error",
      /try \{\n    if \(!registry\.get\(tag\)\) registry\.define\(tag, ctor\);/.test(SOURCE),
      "a second copy of the module must not throw");

/* ⚠ The Hub has stored several generations of Font Awesome class string, and
   the icon name is what looks the path up. Taking the wrong token means every
   room silently falls back to the ArtiLED mark. */
console.log("\nthe Hub's Font Awesome class resolves to an icon name");
[
  ["fas fa-couch", "couch", "the current Hub format"],
  ["fa-solid fa-bed-alt", "bed-alt", "FA6 long form, and an ALIAS name"],
  ["fal fa-piano", "piano", "a non-solid style still names the same icon"],
  ["fa-couch", "couch", "no style prefix"],
  ["couch", "couch", "a bare name"],
  ["  fas   fa-hat-chef  ", "hat-chef", "stray whitespace"],
].forEach(([input, want, why]) =>
  check(`${why}: ${JSON.stringify(input)} -> ${want}`, t.fa_name(input) === want)
);
check("an empty icon yields an empty name, not a crash", t.fa_name("") === "");
check("a missing icon yields an empty name, not a crash", t.fa_name(undefined) === "");
check("the LAST fa- token wins, not the first",
      t.fa_name("fa-solid fa-couch") === "couch",
      "splitting on the first token would return 'solid'");

/* ⚠ COMPLIANCE RULE, not a style preference. Font Awesome Pro's licence does
   not permit distributing standalone copies of Pro icons to non-licensees, and
   this package is PUBLISHED. The paths must be read from the customer's own Hub
   at runtime (icons.py), never shipped in the package.

   These checks exist because the old bundle - 3,241 Pro icons, 1.9 MB - went
   out in a public repository on 2026-08-17 before anyone noticed. Reverting to
   a bundled file would repeat that, so it fails here first. */
console.log("\nFont Awesome Pro icons are NOT shipped in the package");
const PKG = path.join(__dirname, "..", "custom_components", "artiled_hub");
const walk = (dir) => fs.readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
  e.isDirectory() ? walk(path.join(dir, e.name)) : [path.join(dir, e.name)]);
const packaged = walk(PKG);

check("no fa-icons.json anywhere in the package",
      !packaged.some((f) => path.basename(f) === "fa-icons.json"),
      "the bundled Pro icon set must never come back");
check("no packaged file carries Font Awesome's Pro licence header",
      !packaged.some((f) => {
        if (/\.(png|woff2?|ttf|eot)$/i.test(f)) return false;
        return fs.readFileSync(f, "utf8").includes("Font Awesome Pro 6");
      }),
      "an FA Pro SVG or webfont has been copied into the package");
check("no generator script that would rebuild a bundle",
      !fs.existsSync(path.join(__dirname, "..", "tools", "generate_fa_icons.py")),
      "removed 2026-08-17 with the bundle it produced");
check("the frontend reads icons from the RUNTIME cache, not the package",
      /const FA_BASE = "\/artiled_hub_icons\/fa-icons\.json"/.test(SOURCE) &&
      !/artiled_hub_frontend\/fa-icons/.test(SOURCE),
      "pointing FA_BASE back at the package directory reships the icons");

/* ⛔ Opening a page must NEVER change a light. Both of these mount at page load
   and both libraries fire their change callback for the INITIAL colour, so an
   unguarded handler writes a colour to real fixtures just for being displayed.
   The HSV pane shipped without this guard in 0.14.3 and did exactly that. */
console.log("\nmounting a colour control cannot write to a light");
check("the HSV wheel is guarded by `touched`",
      /let touched = false;[\s\S]{0,900}if \(!touched\) return;/.test(SOURCE) &&
      /pointerdown[\s\S]{0,60}touched = true/.test(SOURCE),
      "ReinventedColorWheel calls onChange for its initial colour");
check("the palette strip is guarded by `ready`",
      /let ready = false;[\s\S]{0,300}if \(!ready\) return;/.test(SOURCE),
      "Grapick addHandler fires change, and a change reaches real fixtures");
check("the iro panes bind input:change, not color:change",
      !/\.on\("color:change"/.test(SOURCE) && /\.on\("input:change"/.test(SOURCE),
      "color:change fires for programmatic sets too; input:change is user-only");

console.log("\nvoice exposure is per assistant, and admin-gated");
check("all THREE assistants are offered, not one combined switch",
      /"conversation"[\s\S]{0,120}"cloud\.alexa"[\s\S]{0,120}"cloud\.google_assistant"/.test(SOURCE),
      "HA stores should_expose per assistant; one switch would misrepresent it");
/* ⚠ The gate is at the STRATEGY, not in the card: the Voice view is not emitted
   at all for a non-admin. Both websocket commands behind it are @require_admin,
   so a household member could only ever look — and a strategy runs per user, so
   omitting the view is the whole implementation. */
check("the Voice page is withheld from non-admins",
      /hass\.user && hass\.user\.is_admin/.test(SOURCE) &&
      /title: "Voice"/.test(SOURCE),
      "a member would otherwise get a page of controls that all error");
check("exposure uses the assistants[] websocket command",
      /type: "homeassistant\/expose_entity"[\s\S]{0,200}assistants: \[/.test(SOURCE));
check("aliases go through the entity registry, filtered of nulls",
      /type: "config\/entity_registry\/update"[\s\S]{0,120}aliases/.test(SOURCE) &&
      /aliases \|\| \[\]\)\.filter\(Boolean\)/.test(SOURCE),
      "HA leaves a stray null in aliases on some entries");
check("a failed toggle is rolled back, not left looking saved",
      /pill\.classList\.toggle\("on", !on\);/.test(SOURCE));

console.log("\nthe pickers seed the way the webapp seeds them");
check("HSV opens on a FIXED red, not the entity's colour",
      /hsv: \[0, 100, 100\]/.test(SOURCE),
      "color-bind.js mounts ReinventedColorWheel with hsv [0,100,100]");
check("RGB seeds from the Hub's own first stop, falling back to white",
      /artiled_colors \|\| \[\]\)\[0\]/.test(SOURCE) && /255, 255, 255/.test(SOURCE));
check("both iro wheels use the phone handle radius, not the Hub's mouse one",
      (SOURCE.match(/handleRadius: 12/g) || []).length >= 2,
      "the Hub leaves iro's default 8, which is a mouse target");
check("the palette strip widens its hit area for touch",
      /grp-handler-drag::before/.test(SOURCE) && /touch-action: none/.test(SOURCE),
      "grapick's handle is 4px wide and iOS steals an unguarded drag");

console.log("\nrun pickers — the SAME cases as tests/test_entity_ids.py");
check("a room scene picker matches", t.run_picker_suffix(`${IDENT}_room_15_run_scene`) === "scene");
check("a zone mode picker matches", t.run_picker_suffix(`${IDENT}_zone_16_run_mode`) === "mode");
check("multi-digit ids survive", t.run_picker_suffix(`${IDENT}_room_142_run_scene`) === "scene");

console.log("\nand the same negatives — the ids a wrong match would hijack");
[
  [`${IDENT}_room_15_on_scene`, "the turn-on picker"],
  [`${IDENT}_room_15_off_scene`, "the turn-off picker"],
  [`${IDENT}_scene_5`, "a house-wide scene entity"],
  [`${IDENT}_mode_3`, "a house-wide mode switch"],
  [`${IDENT}_light_8`, "an individual light"],
  [`${IDENT}_room_15`, "a room light entity"],
  [`${IDENT}_version`, "the firmware sensor"],
  [`${IDENT}_flow_2`, "a flow button"],
  [`${IDENT}_room_abc_run_scene`, "a non-numeric id"],
  [`${IDENT}_room_15_run_flow`, "an unknown suffix"],
  [`${IDENT}_house_15_run_scene`, "an unknown scope kind"],
  ["", "an empty unique_id"],
  [undefined, "a missing unique_id"],
].forEach(([uid, why]) => check(`${why} is not a run picker`, t.run_picker_suffix(uid) === null));

/* ------------------------------------------------------------------ */
console.log("\ndevice classification comes from the identifier, not a name");
check("a room device", JSON.stringify(t.classify({ identifiers: [["artiled_hub", `${IDENT}_room_15`]] })) === '{"kind":"room","id":15}');
check("a zone device", JSON.stringify(t.classify({ identifiers: [["artiled_hub", `${IDENT}_zone_16`]] })) === '{"kind":"zone","id":16}');
check("a light device", JSON.stringify(t.classify({ identifiers: [["artiled_hub", `${IDENT}_light_8`]] })) === '{"kind":"light","id":8}');
check("the hub device itself", (t.classify({ identifiers: [["artiled_hub", IDENT]] }) || {}).kind === "hub");
check("another integration's device is ignored", t.classify({ identifiers: [["hue", "abc"]] }) === null);
check("a device with no identifiers is ignored", t.classify({}) === null);

/* ------------------------------------------------------------------ */
console.log("\nthe luminance rule — ported from app/js/paint.js, flip at 0.725");
check("a white-lit room gets DARK text", t.font_color(["rgb(255,255,255)"]) === "#111111",
      "this is the case the rule exists for: white on white is unreadable");
check("a black/unlit card gets light text", t.font_color(["rgb(0,0,0)"]) === "#ffffff");
check("saturated red gets light text", t.font_color(["rgb(255,0,0)"]) === "#ffffff");
check("no colours at all falls back to light text", t.font_color([]) === "#ffffff");
check("stops are AVERAGED, not taken first", t.font_color(["rgb(255,255,255)", "rgb(0,0,0)"]) === "#ffffff",
      "white+black averages to mid grey, which is below the 0.725 flip");

console.log("\nthe gradient rule — LinearGradient {0,1}->{1,0} is CSS 'to top right'");
check("direction is to top right", t.background(["rgb(1,2,3)"]).startsWith("linear-gradient(to top right,"));
check("a single colour is duplicated into two stops",
      t.background(["rgb(1,2,3)"]) === "linear-gradient(to top right, rgb(1,2,3), rgb(1,2,3))",
      "one stop is not a valid CSS gradient");
check("several stops are kept in order",
      t.background(["rgb(1,2,3)", "rgb(4,5,6)"]) === "linear-gradient(to top right, rgb(1,2,3), rgb(4,5,6))");
check("no colours means no wash at all", t.background([]) === "");
check("junk stops are dropped, not rendered", t.background(["not a colour"]) === "");

/* ------------------------------------------------------------------ */
console.log("\nthe status line shows the running scene/mode, not just On");
check("a room running Cinema reads Cinema",
      t.tile_status({ state: "on", attributes: { running_name: "Cinema" } }) === "Cinema");
check("running 'Off' is not shown as a scene name",
      t.tile_status({ state: "on", attributes: { running_name: "Off" } }) === "On",
      "the Hub's own Off mode would otherwise label a lit room 'Off'");
check("plain on reads On", t.tile_status({ state: "on", attributes: {} }) === "On");
check("plain off reads Off", t.tile_status({ state: "off", attributes: {} }) === "Off");
check("a missing entity reads Unavailable", t.tile_status(null) === "Unavailable");

console.log("\ncolour is read from rgb, falling back to the Hub's rgbw");
check("rgb_color is used when present",
      t.entity_rgb({ state: "on", attributes: { rgb_color: [10, 20, 30] } }) === "rgb(10,20,30)");
check("rgbw_color falls back to its first three channels",
      t.entity_rgb({ state: "on", attributes: { rgbw_color: [10, 20, 30, 40] } }) === "rgb(10,20,30)",
      "the Hub speaks rgbw; without this a colour light would render grey");
check("an off entity contributes no colour", t.entity_rgb({ state: "off", attributes: { rgb_color: [1, 2, 3] } }) === null);
check("an unavailable entity contributes no colour", t.entity_rgb({ state: "unavailable", attributes: {} }) === null);

/* ------------------------------------------------------------------ *
 * Voice: the fallback when an entity carries no explicit exposure.
 * ------------------------------------------------------------------ */
console.log("\nvoice: duplicate-name warning");
{
  /* Object.create, not new: _clashes is a pure method and the constructor
     wants a real DOM. */
  const Voice = defined.get("artiled-voice-card");
  check("the voice card is registered at all", !!Voice);
  const card = Object.create(Voice.prototype);
  card._hass = {
    states: {
      /* a real measured case: an ArtiLED zone and an ArtiLED light,
         same Hub name, plus a Hue bulb that shares it too */
      "light.lotus":        { attributes: { friendly_name: "Lotus" } },
      "light.lotus_3":      { attributes: { friendly_name: "Lotus" } },
      "light.toilet":       { attributes: { friendly_name: "Toilet" } },
      "light.toilet_2":     { attributes: { friendly_name: "Toilet" } },
      "light.toilet_3":     { attributes: { friendly_name: "Toilet" } },
      "light.kitchen":      { attributes: { friendly_name: "Kitchen" } },
      /* case and padding must not defeat the match */
      "light.kitchen_2":    { attributes: { friendly_name: " KITCHEN " } },
      /* a NON-voice domain sharing a name is NOT a clash */
      "sensor.lotus":       { attributes: { friendly_name: "Lotus" } },
      /* unique — must never be flagged */
      "light.cinewall":     { attributes: { friendly_name: "Cinewall" } },
    },
  };
  const m = card._clashes();
  check("a zone and a light sharing a Hub name are detected",
        (m.get("lotus") || []).length === 2,
        "this is a real measured collision of the kind the warning exists for");
  check("a four-way clash is detected", (m.get("toilet") || []).length === 3);
  check("comparison is case- and whitespace-insensitive",
        (m.get("kitchen") || []).length === 2,
        "friendly_name ' KITCHEN ' must collide with 'Kitchen'");
  check("a sensor sharing the name is NOT counted",
        !(m.get("lotus") || []).includes("sensor.lotus"),
        "an assistant cannot be asked to turn on a diagnostic sensor");
  check("a unique name is not flagged",
        (m.get("cinewall") || []).length === 1);

  const seen = card._display_name({ entity: "light.lotus", name: "Hub Name" });
  check("the warning compares HA's friendly_name, not the Hub's spelling",
        seen === "Lotus",
        "friendly_name is what the assistant is actually given");
}

console.log("\nvoice: Scenes and Modes tabs");
{
  const V = fs.readFileSync(SRC, "utf8");
  const Voice = defined.get("artiled-voice-card");
  const card = Object.create(Voice.prototype);
  card._config = {
    scoped: [
      { kind: "room", id: 5, name: "Cinema",
        scenes: ["Cinema", "Warm"], modes: ["Cinema", "Music"],
        chosen_scenes: [{ item: "Warm", name: "Cinema Warm", entity: "scene.x" }],
        chosen_modes: [] },
    ],
  };

  const rows = card._scoped_rows(card._config.scoped[0], "scene");
  check("an already-added scene shows as ticked",
        /data-item="Warm"[\s\S]*?pill tick on/.test(rows),
        "chosen entries come from the artiled_scope/artiled_item attributes");
  check("a not-yet-added scene shows as addable",
        /data-item="Cinema"[\s\S]*?pill tick"/.test(rows));
  check("the added one keeps the user's name",
        rows.includes('value="Cinema Warm"'));
  check("a repeated word collapses in the suggestion",
        rows.includes('placeholder="Cinema Scene"'),
        "'Cinema' in the Cinema must not suggest 'Cinema Cinema'");
  check("modes suggest Mode, not Scene",
        card._scoped_rows(card._config.scoped[0], "mode")
            .includes('placeholder="Cinema Mode"'));

  check("rows are built lazily on <details> toggle",
        /dataset\.filled/.test(V),
        "23 scopes x ~27 scenes is ~620 rows carrying an input each");
  /* One call site handles both: `${on ? "add" : "remove"}_voice_${what}`, so
     neither literal appears on its own — assert the construct, not a substring. */
  check("one call site adds AND removes",
        /\$\{on \? "add" : "remove"\}_voice_\$\{what\}/.test(V),
        "a substring check for 'remove_voice_' passes only by accident here");
  check("renaming re-adds, which the service treats as a replace",
        /add_voice_\$\{what\}/.test(V) && V.includes("_rename_scoped"));
  check("a failed write puts the tick back",
        /put it back; the write failed/.test(V));

  /* Rooms and zones must be told apart: the Hub gives each a DIFFERENT scene
     list, and "Kitchen" (room) next to "Kitchen Spots" (zone) reads as siblings. */
  card._config.scoped.push({
    kind: "zone", id: 20, name: "Kitchen Spots",
    scenes: ["Warm"], modes: [], chosen_scenes: [], chosen_modes: [],
  });
  const panel = card._scoped_panel("scene");
  check("the scope list is split into Rooms and Zones",
        panel.includes(">Rooms (1)<") && panel.includes(">Zones (1)<"),
        "listed in one run a zone is indistinguishable from a room");
  check("rooms come before zones", panel.indexOf("Rooms (") < panel.indexOf("Zones ("));
  /* ⚠ THE HUB'S OWN ICON WINS. Every room/zone carries the icon the customer
     picked in the Hub; hardcoding mdi:sofa makes 12 rooms look identical and
     throws their choice away — the exact bug the tiles once had. */
  card._config.scoped[0].icon = "artiled:couch";
  const iconed = card._scoped_panel("scene");
  check("a scope uses the Hub's own icon when it has one",
        iconed.includes('<ha-icon icon="artiled:couch">'),
        "artiled:<name> comes from the Hub's 'fas fa-couch' via fa_name()");
  check("a scope with no Hub icon falls back to the kind icon",
        iconed.includes('<ha-icon icon="mdi:vector-rectangle">'),
        "the zone in this fixture has no icon set");
  check("a section with no scopes is omitted entirely",
        !card._scoped_panel("mode").includes("Zones ("),
        "the zone here has no modes, so a 'Zones (0)' heading would be noise");

  /* ⚠ Duplicate names matter MORE here than on the exposure tabs: the name is
     typed free-form, and `scene` is in HA's alexa_default_expose, so a clash
     reaches Amazon as a second device answering one phrase. */
  card._hass = {
    states: {
      "light.lotus":   { attributes: { friendly_name: "Kitchen Lotus" } },
      "scene.already": { attributes: { friendly_name: "Cinema Warm" } },
    },
  };
  check("a name already used elsewhere is flagged",
        card._name_taken("Kitchen Lotus") === true);
  check("a free name is not flagged",
        card._name_taken("Cinema Nightlight") === false);
  check("an entity does not flag ITSELF",
        card._name_taken("Cinema Warm", "scene.already") === false,
        "an already-added scene would otherwise always warn about itself");
  check("the check is case- and space-insensitive",
        card._name_taken("  kitchen LOTUS ") === true);
  check("an empty name is not a clash", card._name_taken("") === false);

  const warned = card._scoped_rows(card._config.scoped[0], "scene");
  /* Assert the rendered shape, not a guessed substring — the span carries a
     title attribute between the class and the marker. */
  check("the clash shows on the row", /opt__warn"[^>]*>⚠/.test(warned),
        "Cinema Warm is taken by scene.already in this fixture");
  check("a non-clashing row shows no marker",
        (warned.match(/opt__warn"[^>]*>⚠/g) || []).length === 1,
        "only the Warm row clashes; Cinema does not");
  check("names are re-checked as the user types", /_recheck_name/.test(V));
}

console.log("\nvoice exposure defaults");
const VOICE_SRC = fs.readFileSync(SRC, "utf8");
check("the no-setting fallback is per-assistant, not a blanket 'it is a light'",
      /key === "conversation" && id\.startsWith\("light\."\)/.test(VOICE_SRC),
      "HA's DEFAULT_EXPOSED_ASSISTANT is {conversation: true} — Alexa and Google " +
      "default to OFF, so showing all three pills on was wrong for two of them");
check("the integration itself exposes nothing by default",
      /for assistant in ASSISTANTS/.test(fs.readFileSync(
        path.join(__dirname, "..", "custom_components", "artiled_hub", "__init__.py"),
        "utf8")),
      "every entity of the config entry gets an explicit False — never left to " +
      "HA's default, which is ON for Assist");

/* ------------------------------------------------------------------ */
console.log("\nsensitivity: prove these checks can fail");
check("a suffix-only matcher would wrongly accept the negatives",
      /_run_(scene|mode)$/.test(`${IDENT}_room_abc_run_scene`) === true,
      "if this fails, the negative run-picker checks prove nothing");
check("a 'first stop' luminance would wrongly darken white+black",
      t.font_color(["rgb(255,255,255)", "rgb(0,0,0)"]) !== t.font_color(["rgb(255,255,255)"]),
      "if these matched, the averaging check would prove nothing");

console.log();
if (FAILURES.length) {
  console.log(`${FAILURES.length} FAILED: ${FAILURES.join(", ")}`);
  process.exit(1);
}
console.log("all frontend rules pass");
process.exit(0);
