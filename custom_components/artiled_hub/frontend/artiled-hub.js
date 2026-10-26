// Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
/* ArtiLED Hub — Home Assistant frontend module.
 *
 * Two things live here, and they answer two different questions:
 *
 *   ll-strategy-dashboard-artiled-hub   builds the dashboard from the Hub's
 *                                       own inventory, so nothing is hard-coded
 *   artiled-tile-card                   draws a room/zone/light the way the
 *                                       ArtiLED app draws it
 *
 * ⚠ THE TILE IS A PORT, NOT A REINTERPRETATION. The design is a paid asset
 * (CodeBee). Every value below comes from the app source by way of the
 * webapp's app/app.css and app/includes/tiles.php — geometry 92.5/16/#444,
 * the gradient direction, and the luminance rule. Do not adjust them to taste.
 *
 * ⚠ The luminance and gradient rules now exist in FOUR places: the app's
 * determ-controller-font-color.js, the webapp's includes/tiles.php and
 * js/paint.js, and here. They cannot share code — three runtimes — so a change
 * to one is a change to all four. font_color()/background() below are
 * transcribed from js/paint.js deliberately, line for line.
 */

/* ------------------------------------------------------------------ *
 * The ported rules. Keep byte-identical in behaviour to js/paint.js.
 * ------------------------------------------------------------------ */

/* determ-controller-font-color.js: average the stops, linearise, weight,
   flip at 0.725. A white-lit room is a white card with BLACK text. */
function font_color(colors) {
  const r = [], g = [], b = [];
  (colors || []).forEach((c) => {
    const m = String(c).match(/\d+/g);
    if (m && m.length >= 3) {
      r.push(+m[0]); g.push(+m[1]); b.push(+m[2]);
    }
  });
  if (!r.length) return "#ffffff";
  const avg = (list) => Math.ceil(list.reduce((a, n) => a + n, 0) / list.length);
  const lin = (v) => {
    v = v / 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  };
  const luminance =
    0.2126 * lin(avg(r)) + 0.7152 * lin(avg(g)) + 0.0722 * lin(avg(b));
  return luminance > 0.725 ? "#111111" : "#ffffff";
}

/* LinearGradient start {x:0,y:1} -> end {x:1,y:0} = CSS `to top right`.
   A single colour still needs two stops for a valid gradient. */
function background(colors) {
  const clean = (colors || [])
    .map((c) => {
      const m = String(c).match(/\d+/g);
      return m && m.length >= 3 ? `rgb(${+m[0]},${+m[1]},${+m[2]})` : null;
    })
    .filter(Boolean);
  if (!clean.length) return "";
  if (clean.length === 1) clean.push(clean[0]);
  return `linear-gradient(to top right, ${clean.join(", ")})`;
}

/* HA gives rgb_color on a colour light; rgbw_color is what the Hub speaks, so
   fall back to its first three channels rather than showing a grey card. */
function entity_rgb(state) {
  if (!state || state.state !== "on") return null;
  const a = state.attributes || {};
  const rgb = a.rgb_color || (a.rgbw_color ? a.rgbw_color.slice(0, 3) : null);
  if (!rgb || rgb.length < 3) return null;
  return `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
}

/* app_tile_status(): the running scene or mode when there is one, so a room
   running Cinema reads "Cinema" rather than "On". */
function tile_status(state) {
  if (!state) return "Unavailable";
  const running = (state.attributes || {}).running_name;
  if (running && String(running).toLowerCase() !== "off") return running;
  return state.state === "on" ? "On" : "Off";
}

const STYLE = `
:host { display: block; }
/* app.css --black-light, --purple, font scale */
.tile {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  height: 92.5px;
  border-radius: 16px;
  background: #444;
  box-shadow: 0 2px 4px rgba(0,0,0,.2);
  overflow: hidden;
  color: #fff;
  font-family: -apple-system, BlinkMacSystemFont, system-ui, "Segoe UI", Roboto, sans-serif;
}
.wash { position: absolute; inset: 0; border-radius: 16px; }
.inner {
  position: relative; display: flex; flex-direction: column;
  justify-content: space-between; height: 85%; width: 90%;
}
.top { display: flex; align-items: center; height: 50px; }
.icon { flex: 1.5; font-size: 34px; display: flex; align-items: center; }
.icon ha-icon { --mdc-icon-size: 34px; }
.text { flex: 3.5; min-width: 0; }
.name {
  font-size: 20px; font-weight: 600;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.status { font-size: 16px; }
/* ui/button-switch.tsx — iOS switch 51x31, thumb 27 inset 2, scale .8 */
.sw {
  cursor: pointer; flex: 0 0 auto; position: relative; display: inline-block;
  width: 51px; height: 31px; margin-top: -1px; border-radius: 15.5px;
  background: #767577; transform: scale(.8);
  transition: background-color .18s ease;
  -webkit-tap-highlight-color: transparent; touch-action: manipulation;
}
.sw::after {
  content: ''; position: absolute; top: 2px; left: 2px;
  width: 27px; height: 27px; border-radius: 50%;
  background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,.3);
  transition: left .18s ease;
}
.sw.on { background: #7a51a1; }
.sw.on::after { left: 22px; }
.sw.busy { opacity: .7; }
.slider {
  --knob: 20px; display: flex; align-items: center; height: 20px;
  touch-action: none; cursor: pointer; -webkit-tap-highlight-color: transparent;
}
.track {
  position: relative; width: 100%; height: 3px; border-radius: 2px;
  background: currentColor; opacity: .55;
}
/* slider.js: the thumb is track_background_color = font_color, so on a
   white-lit card it is DARK. currentColor gives that for free. */
.knob {
  position: absolute; top: 50%;
  left: calc(var(--p, 0) * (100% - var(--knob)));
  width: var(--knob); height: var(--knob); border-radius: 50%;
  background: currentColor; transform: translateY(-50%);
  box-shadow: 0 6px 10px rgba(0,0,0,.6);
}
.picks { display: flex; gap: 8px; margin-top: 8px; }
.picks select {
  flex: 1; min-width: 0; padding: 6px 8px; font-size: 14px;
  color: #fff; background: #444; border: 1px solid rgba(255,255,255,.15);
  border-radius: 8px; font-family: inherit;
}
.picks select:disabled { opacity: .4; }
.unavail { opacity: .45; }
@media (prefers-reduced-motion: reduce) {
  .sw, .sw::after { transition: none; }
}

/* ---- the webapp's layouts (Settings > Layout, app/js/layout.js) ----------
   PORTED from app/app.css, rule for rule; only the selectors change
   (.layout-grid .app-tile__text -> :host([layout="grid"]) .text). No layout
   attribute = Rows, the card above, which is also what a room's or a light's
   own card stays (the webapp's room screen, .app-rows). Square carries every
   Grid rule, as html.layout-grid.layout-square does. The spacing between
   cards and the columns are the list's (TILES_STYLE). */

/* Grid - controller-grid.tsx: [icon | toggle] on top, the NAME ALONE in a
   38-high box below; no status line, no slider. Inner box padded 6/10. */
:host([layout="grid"]) .inner,
:host([layout="square"]) .inner {
  padding: 6px 10px;
  justify-content: flex-start;
}
:host([layout="grid"]) .top,
:host([layout="square"]) .top {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  height: auto;
}
:host([layout="grid"]) .icon,
:host([layout="square"]) .icon {
  flex: 0 0 auto;
  margin-right: 1px;
}
/* ControllerToggleButton: position absolute right -10, pinned to the top */
:host([layout="grid"]) .sw,
:host([layout="square"]) .sw {
  margin-left: auto;
  align-self: flex-start;
  margin-right: -10px;
}
/* the markup order is icon, text, switch: the text is ordered LAST or its
   100% basis pushes the switch onto a third line */
:host([layout="grid"]) .text,
:host([layout="square"]) .text {
  order: 1;
  flex: 0 0 100%;
  display: flex;
  flex-direction: column;
  justify-content: center;
  height: 38px;
}
:host([layout="grid"]) .status,
:host([layout="grid"]) .slider,
:host([layout="square"]) .status,
:host([layout="square"]) .slider {
  display: none;
}
:host([layout="grid"]) .name,
:host([layout="square"]) .name {
  font-size: 18px;            /* font_size.lg semi_bold */
}
/* A light's card has no icon: Grid keeps it the line the icon gives every
   other card, so a light's name sits where a zone's does. */
:host([layout="grid"][kind="light"]) .top::before,
:host([layout="square"][kind="light"]) .top::before {
  content: '';
  height: 34px;
}

/* Square - the Grid card as a square the size of a Scenes/Modes image; its two
   lines go to the top and the foot of the square. */
:host([layout="square"]) .tile {
  height: auto;
  aspect-ratio: 1;
}
:host([layout="square"]) .top {
  height: 100%;
  align-content: space-between;
}

/* List - one slim line per room or zone: the Rows card's top line with no
   card round it, no wash and no slider (the settings row: padding 8, radius 8,
   the same press highlight). The divider between lines is the list's. */
:host([layout="list"]) .tile {
  height: auto;
  padding: 0 8px;
  border-radius: 8px;
  background: transparent;
  box-shadow: none;
  overflow: visible;
  -webkit-tap-highlight-color: transparent;
}
:host([layout="list"]) .tile:active {
  background: rgba(127, 127, 127, .15);
  background: color-mix(in srgb, var(--primary-text-color, #fff) 10%, transparent);
}
:host([layout="list"]) .wash,
:host([layout="list"]) .slider {
  display: none;
}
:host([layout="list"]) .inner {
  width: 100%;
  height: auto;
}
/* No card, so no dark text for a white-lit card: the words sit on the page.
   ⚠ HA's theme text colour, not the app's white (see ENTITY_STYLE): on HA's
   light theme white words would be invisible. */
:host([layout="list"]) .icon,
:host([layout="list"]) .name,
:host([layout="list"]) .status {
  color: var(--primary-text-color, #fff);
}
/* The LED colour on the icon, only while on and coloured. ⚠ DEVIATION: the
   webapp clips its gradient to the Font Awesome GLYPH (background-clip: text);
   an HA icon is an SVG inside ha-icon's own shadow root, which that cannot
   reach, so the icon takes the gradient's START colour (--first). */
:host([layout="list"]) .tile.washed .icon {
  color: var(--first);
}
`;

class ArtiLedTileCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
  }

  setConfig(config) {
    if (!config || !config.entity) {
      throw new Error("artiled-tile-card needs an entity");
    }
    this._config = config;
    /* the layout CSS keys a light's card (no icon) off this */
    if (config.kind) this.setAttribute("kind", config.kind);
    else this.removeAttribute("kind");
    this._built = false;
    if (this.shadowRoot) this.shadowRoot.innerHTML = "";
  }

  getCardSize() {
    return this._config && (this._config.scene || this._config.mode) ? 3 : 2;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this._paint();
  }

  _build() {
    const c = this._config;
    const picks =
      c.scene || c.mode
        ? `<div class="picks">
             ${c.scene ? '<select class="pick-scene"></select>' : ""}
             ${c.mode ? '<select class="pick-mode"></select>' : ""}
           </div>`
        : "";
    /* A light card has no icon and its second line is the literal "ArtiLED"
       (controller.tsx lines 191 and 226). Rooms and zones keep both. */
    const is_light = c.kind === "light";
    this.shadowRoot.innerHTML = `
      <style>${STYLE}</style>
      <div class="tile">
        <div class="wash"></div>
        <div class="inner">
          <div class="top">
            ${is_light ? "" : `<div class="icon"><ha-icon></ha-icon></div>`}
            <div class="text">
              <div class="name"></div>
              <div class="status"></div>
            </div>
            <span class="sw" role="switch" tabindex="0"></span>
          </div>
          <div class="slider"><div class="track"><div class="knob"></div></div></div>
        </div>
      </div>
      ${picks}
    `;
    const root = this.shadowRoot;
    this._el = {
      tile: root.querySelector(".tile"),
      wash: root.querySelector(".wash"),
      icon: root.querySelector("ha-icon"),
      name: root.querySelector(".name"),
      status: root.querySelector(".status"),
      sw: root.querySelector(".sw"),
      slider: root.querySelector(".slider"),
      knob: root.querySelector(".knob"),
      scene: root.querySelector(".pick-scene"),
      mode: root.querySelector(".pick-mode"),
    };
    this._el.sw.addEventListener("click", (e) => {
      e.stopPropagation();
      this._toggle();
    });
    /* controller.tsx wraps the card in a Pressable that navigates to that
       entity's screen. The switch and slider stop the click first, which is
       the same thing the app's Switch-inside-Pressable does. */
    if (c.navigate) {
      this._el.tile.style.cursor = "pointer";
      this._el.tile.addEventListener("click", () => {
        history.pushState(null, "", c.navigate);
        window.dispatchEvent(
          new CustomEvent("location-changed", { bubbles: true, composed: true })
        );
      });
    }
    this._bind_slider();
    if (this._el.scene) {
      this._el.scene.addEventListener("change", (e) =>
        this._select(this._config.scene, e.target.value)
      );
    }
    if (this._el.mode) {
      this._el.mode.addEventListener("change", (e) =>
        this._select(this._config.mode, e.target.value)
      );
    }
    this._built = true;
  }

  /* Drag anywhere on the track sets brightness, as the app's PanResponder
     does. Pointer events cover mouse and touch in one path. */
  _bind_slider() {
    const el = this._el.slider;
    const send = (ev) => {
      const rect = el.getBoundingClientRect();
      if (!rect.width) return;
      const frac = Math.min(1, Math.max(0, (ev.clientX - rect.left) / rect.width));
      this._dragging = frac;
      this._el.knob.style.setProperty("--p", String(frac));
      this._hass.callService("light", "turn_on", {
        entity_id: this._config.entity,
        brightness: Math.round(frac * 255),
      });
    };
    el.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      el.setPointerCapture(e.pointerId);
      this._down = true;
      send(e);
    });
    el.addEventListener("pointermove", (e) => {
      if (this._down) send(e);
    });
    const up = () => {
      this._down = false;
      /* Let the Hub's own reading win again once the drag ends. */
      window.setTimeout(() => { this._dragging = null; }, 1500);
    };
    el.addEventListener("pointerup", up);
    el.addEventListener("pointercancel", up);
  }

  _toggle() {
    this._el.sw.classList.add("busy");
    this._hass
      .callService("light", "toggle", { entity_id: this._config.entity })
      .finally(() => this._el.sw.classList.remove("busy"));
  }

  _select(entity_id, option) {
    this._hass.callService("select", "select_option", { entity_id, option });
  }

  /* The colour stops for the wash.
   *
   * ⚠ Use the Hub's OWN palette (artiled_colors), verbatim and in order. The
   * gradient in the ArtiLED app is a single light's [start, end] palette, NOT a
   * blend of several lights: aggregate_lights_for() in the Hub's functions.php
   * takes the array "verbatim from the FIRST on-light ... preserves [start,
   * end] shape so the app gets a real palette, not a deduped scalar".
   *
   * An earlier version of this walked the room's member lights and collected
   * one rgb from each. That is a different picture from the app's, and it could
   * only ever be flat where it mattered, because a HA light entity's rgb_color
   * is one colour - a two-stop light collapsed to a single stop before it ever
   * reached this card.
   *
   * Falls back to the entity's own rgb so a light with no palette still paints.
   */
  _stops(state) {
    const palette = (state && state.attributes && state.attributes.artiled_colors) || [];
    if (palette.length) return palette.slice(0, MAX_STOPS);
    const own = entity_rgb(state);
    return own ? [own] : [];
  }

  _paint() {
    const c = this._config;
    const state = this._hass.states[c.entity];
    const el = this._el;

    if (!state) {
      el.tile.classList.add("unavail");
      el.name.textContent = c.name || c.entity;
      el.status.textContent = "Unavailable";
      return;
    }
    const unavailable = state.state === "unavailable";
    el.tile.classList.toggle("unavail", unavailable);

    const on = state.state === "on";
    const stops = on ? this._stops(state) : [];
    const bg = background(stops);
    const font = on ? font_color(stops) : "#ffffff";

    el.tile.style.color = font;
    el.wash.style.background = bg;
    /* List has no card to wash: its icon takes the colour instead */
    el.tile.classList.toggle("washed", !!bg);
    if (stops.length) el.tile.style.setProperty("--first", stops[0]);
    else el.tile.style.removeProperty("--first");
    el.name.textContent =
      c.name || state.attributes.friendly_name || c.entity;
    el.status.textContent = c.kind === "light" ? "ArtiLED" : tile_status(state);
    /* ⚠ The Hub's own icon wins. The card config carries a fallback only for
       the moment before the entity has state, or a Hub that stored none. */
    if (el.icon) {
      const hub_icon = state.attributes.artiled_icon;
      const icon = hub_icon ? `artiled:${fa_name(hub_icon)}` : c.icon;
      if (icon && el.icon.getAttribute("icon") !== icon) {
        el.icon.setAttribute("icon", icon);
      }
    }

    el.sw.classList.toggle("on", on);
    el.sw.setAttribute("aria-checked", on ? "true" : "false");
    el.sw.setAttribute("aria-label", el.name.textContent);

    /* Do not fight a drag in progress: the Hub's poll is up to 10s behind. */
    if (this._dragging === null || this._dragging === undefined) {
      const bright = on ? state.attributes.brightness || 0 : 0;
      el.knob.style.setProperty("--p", String(bright > 0 ? bright / 255 : 0));
    }

    this._paint_pick(el.scene, c.scene);
    this._paint_pick(el.mode, c.mode);
  }

  _paint_pick(node, entity_id) {
    if (!node || !entity_id) return;
    const state = this._hass.states[entity_id];
    if (!state) {
      node.disabled = true;
      return;
    }
    node.disabled = state.state === "unavailable";
    const options = state.attributes.options || [];
    /* Rebuild only when the Hub's offer actually changed — otherwise an open
       dropdown would close under the user on every 10s poll. */
    const signature = JSON.stringify(options);
    if (node._signature !== signature) {
      node._signature = signature;
      node.innerHTML = options
        .map((o) => `<option value="${o.replace(/"/g, "&quot;")}">${o}</option>`)
        .join("");
    }
    if (document.activeElement !== node && node.value !== state.state) {
      node.value = state.state;
    }
  }
}

/* ------------------------------------------------------------------ *
 * Tile layouts - the webapp's Settings > Layout (Michel 2026-10-26).
 * ------------------------------------------------------------------ */

/* PORTED FROM app/js/layout.js: the same four words, the same default and the
 * same localStorage key. Grid is the default ("Grid is the DEFAULT layout
 * everywhere", Michel 2026-10-24); a word this version does not know is Grid,
 * and 'compact' (Square's name for a day) reads as Square.
 *
 * Per BROWSER, as in the webapp: a phone and a wall tablet can reasonably want
 * different layouts. The strategy option `layout:` fixes one for a dashboard
 * instead (the switch is then not drawn).
 *
 * ⚠ localStorage can throw (private mode, blocked site data). The layout is a
 * nicety, so a throw is the default rather than a broken dashboard. */
const LAYOUTS = ["rows", "grid", "square", "list"];   /* the webapp's order */
const LAYOUT_DEFAULT = "grid";
const LAYOUT_KEY = "artiled_layout";
const LAYOUT_EVENT = "artiled-layout";
const LAYOUT_OLD_NAMES = { compact: "square" };
const LAYOUT_LABEL = { rows: "Rows", grid: "Grid", square: "Square", list: "List" };

function layout_word(value) {
  if (typeof value === "string" && Object.prototype.hasOwnProperty.call(LAYOUT_OLD_NAMES, value)) {
    value = LAYOUT_OLD_NAMES[value];
  }
  return LAYOUTS.includes(value) ? value : LAYOUT_DEFAULT;
}

/* A valid fixed (strategy) choice wins; otherwise this browser's. */
/* The choice made on this page when storage refused it. */
let layout_unsaved = null;

function layout_read(fixed, win) {
  if (fixed && LAYOUTS.includes(fixed)) return fixed;
  try {
    return layout_word((win || window).localStorage.getItem(LAYOUT_KEY));
  } catch (e) {
    return layout_word(layout_unsaved);
  }
}

/* Stores the choice and tells every list on every view of this page. */
function layout_store(value) {
  const word = layout_word(value);
  layout_unsaved = word;
  try {
    window.localStorage.setItem(LAYOUT_KEY, word);
  } catch (e) {
    /* nothing to do: the page still shows the choice until it is left */
  }
  window.dispatchEvent(new CustomEvent(LAYOUT_EVENT, { detail: word }));
}

/* How many cards share a row - app.css on a phone, tablet.css on an iPad.
 *
 *   phone              Rows 1   Grid 2   Square 2   List 1
 *   tablet portrait    Rows 2   Grid 4   Square 4   List 2
 *   tablet landscape   Rows 2   Grid 6   Square 6   List 2
 *     ...under 1100 px wide: Grid 5 (at 6 "Living Room" was cut)
 *
 * ⚠ Keyed off the LIST's width, not the viewport's as tablet.css is: a
 * dashboard sits beside HA's sidebar and inside its padding, so a viewport
 * width says little about the room the tiles have. The webapp's thresholds
 * are translated to the content width they leave: its tablet step (700) less
 * the 2 x 24 gutter = 652; a landscape iPad 1024 wide less 2 x 40 = 944, and
 * the 1100 cut-off = 1020. A wide card in portrait keeps the portrait counts,
 * as tablet.css's orientation queries do. */
function layout_columns(layout, width, landscape) {
  const word = layout_word(layout);
  const w = Number(width) || 0;
  let tier = "phone";
  if (w >= 652) tier = landscape && w >= 900 ? "landscape" : "portrait";
  let cols;
  if (tier === "phone") {
    cols = word === "grid" || word === "square" ? 2 : 1;
  } else if (word === "rows" || word === "list") {
    cols = 2;
  } else if (tier === "portrait") {
    cols = 4;
  } else {
    cols = word === "grid" && w < 1020 ? 5 : 6;
  }
  return { cols, tier };
}

function is_landscape() {
  try {
    return !!(window.matchMedia && window.matchMedia("(orientation: landscape)").matches);
  } catch (e) {
    return true;
  }
}

/* The LIST: .app-tiles from app.css and tablet.css. The cards are separate
 * custom elements, so the spacing between them lives here, on the hosts. */
const TILES_STYLE = `
.app-tiles {
  display: grid;
  grid-template-columns: repeat(var(--cols, 1), minmax(0, 1fr));
}
.app-tiles > artiled-tile-card {
  position: relative;
  margin-top: 15px;                 /* controller.tsx marginTop 15 */
}
/* Grid on a phone: two cells of 48.75%, 2.5% apart */
.app-tiles[data-layout="grid"][data-tier="phone"] { column-gap: 2.5%; }
/* tablet.css: --tablet-gap 15, landscape 24 (Rows, List)... */
.app-tiles[data-tier="portrait"] { column-gap: 15px; }
.app-tiles[data-tier="landscape"] { column-gap: 24px; }
.app-tiles[data-tier="landscape"]:not([data-layout="square"]):not([data-layout="list"]) > artiled-tile-card {
  margin-top: 24px;
}
/* ...but Grid's many across keep 15 between columns */
.app-tiles[data-layout="grid"][data-tier="landscape"] { column-gap: 15px; }
/* Square: each square W/n - 10.5, the Scenes/Modes image's size; 10.5 between
   columns and rows, 5.25 at either edge */
.app-tiles[data-layout="square"][data-tier] {
  column-gap: 10.5px;
  padding: 0 5.25px;
}
.app-tiles[data-layout="square"] > artiled-tile-card { margin-top: 10.5px; }
/* List: lines 4 apart, the 1px rule at .3 between them, hanging 4px above */
.app-tiles[data-layout="list"] > artiled-tile-card { margin: 4px 0; }
.app-tiles[data-layout="list"] > artiled-tile-card + artiled-tile-card::before {
  content: '';
  position: absolute;
  top: -4px;
  left: 0;
  right: 0;
  height: 1px;
  background: var(--primary-text-color, #fff);
  opacity: .3;
}
/* two across: the divider runs between ROWS, so the first row's right-hand
   line has none above it */
.app-tiles[data-layout="list"]:not([data-tier="phone"]) > artiled-tile-card:nth-child(2)::before {
  display: none;
}
`;

/* Builds one list of tiles into `parent`. */
function tiles_list(parent, configs, hass) {
  const box = document.createElement("div");
  box.className = "app-tiles";
  configs.forEach((cfg) => {
    const card = document.createElement("artiled-tile-card");
    card.setConfig(cfg);
    card.hass = hass;
    box.appendChild(card);
  });
  parent.appendChild(box);
  return box;
}

/* Puts a list into a layout at its current width. */
function tiles_layout(box, layout) {
  const { cols, tier } = layout_columns(layout, box.clientWidth, is_landscape());
  box.dataset.layout = layout;
  box.dataset.tier = tier;
  box.style.setProperty("--cols", String(cols));
  for (const card of box.children) {
    if (card.getAttribute("layout") !== layout) card.setAttribute("layout", layout);
  }
}

/* Keeps the lists in `root` in the layout: on a switch anywhere on the page,
 * on a resize of the card, on a rotation. Returns the function that stops it. */
function tiles_follow(host, root, fixed) {
  const redo = () => {
    const layout = layout_read(fixed);
    root.querySelectorAll(".app-tiles").forEach((box) => tiles_layout(box, layout));
    return layout;
  };
  const on_event = () => redo();
  window.addEventListener(LAYOUT_EVENT, on_event);
  let ro = null;
  if (typeof ResizeObserver === "function") {
    ro = new ResizeObserver(() => redo());
    ro.observe(host);
  }
  let mq = null;
  try {
    mq = window.matchMedia ? window.matchMedia("(orientation: landscape)") : null;
    if (mq && mq.addEventListener) mq.addEventListener("change", on_event);
  } catch (e) {
    mq = null;
  }
  return {
    redo,
    stop() {
      window.removeEventListener(LAYOUT_EVENT, on_event);
      if (ro) ro.disconnect();
      if (mq && mq.removeEventListener) mq.removeEventListener("change", on_event);
    },
  };
}

/* The switch - the webapp's Settings > Layout choices (.tt-tile with the
 * app's own phone-preview artwork, the chosen one framed), drawn small on the
 * dashboard because HA has no Settings > Layout of ours to put it in. The
 * artwork is settings/layout/index.php's, stroked in currentColor so it
 * follows HA's theme instead of the app's white. */
const LAYOUT_ART_FRAME =
  '<rect x="0.5" y="0.5" width="87.7" height="158.9" rx="8.6" stroke="currentColor" stroke-opacity="0.8"/>' +
  '<path d="M24 1.1H65.1V4.6C65.1 7.1 63.1 9.1 60.6 9.1H28.6C26 9.1 24 7.1 24 4.6V1.1Z" fill="currentColor" fill-opacity="0.85"/>' +
  '<path d="M8 37.4H81.1" stroke="currentColor" stroke-opacity="0.7" stroke-width="0.5"/>';
const art_rect = (x, y, w, h, rx) =>
  `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="${rx}" fill="currentColor" fill-opacity="0.8"/>`;
const LAYOUT_ART = {
  rows: [43.4, 74.3, 105.1, 136].map((y) => art_rect(8, y, 73.1, 22.9, 4.6)).join(""),
  grid: [43.4, 74.3, 105.1].map((y) => art_rect(8, y, 34.3, 22.9, 4.6) + art_rect(46.9, y, 34.3, 22.9, 4.6)).join(""),
  square: [43.4, 82.3, 121.2].map((y) => art_rect(8, y, 34.3, 34.3, 4.6) + art_rect(46.9, y, 34.3, 34.3, 4.6)).join(""),
  list: [0, 1, 2, 3, 4, 5, 6].map((i) => {
    const y = 44 + i * 16;
    return art_rect(8, y, 8, 8, 2) + art_rect(22, y + 1.5, 36, 5, 2.5) + art_rect(69, y + 0.5, 12.1, 7, 3.5) +
      (i < 6 ? `<path d="M8 ${y + 12}H81.1" stroke="currentColor" stroke-opacity="0.7" stroke-width="0.5"/>` : "");
  }).join(""),
};

/* app.css .tt-tiles / .tt-tile, at the size of a toolbar: the face 44 px
   instead of a third of the phone, its radius 20 scaled with it. */
const HOME_STYLE = `
:host { display: block; }
.layouts {
  display: flex; justify-content: flex-end; gap: 10px;
  margin: 4px 0 0;
}
.tt-tile {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 0; border: 0; background: none; font: inherit; cursor: pointer;
  color: var(--primary-text-color, #fff);
  -webkit-tap-highlight-color: transparent;
}
.tt-tile__face {
  width: 44px; aspect-ratio: 1; box-sizing: border-box;
  display: flex; align-items: center; justify-content: center;
  border: 1px solid rgba(127, 127, 127, .45);
  border: 1px solid color-mix(in srgb, var(--primary-text-color, #fff) 30%, transparent);
  border-radius: 9px;
  opacity: .72;
}
.tt-tile:active .tt-tile__face {
  background: color-mix(in srgb, var(--primary-text-color, #fff) 10%, transparent);
}
.tt-tile.is-running .tt-tile__face {
  opacity: 1;
  background: rgba(127, 127, 127, .15);
  background: color-mix(in srgb, var(--primary-text-color, #fff) 12%, transparent);
  border-color: rgba(127, 127, 127, .9);
  border-color: color-mix(in srgb, var(--primary-text-color, #fff) 80%, transparent);
}
.tt-tile__face svg { width: 46%; height: auto; }
.tt-tile__name { font-size: 12px; line-height: 1.2; }
/* app.css .app-section: the Rooms / Zones headings */
.app-section {
  margin: 18px 0 0; font-size: 16px; font-weight: 400;
  color: var(--primary-text-color, #fff);
}
.layouts + .app-section { margin-top: 0; }
${TILES_STYLE}
`;

/* Home - app/index.php: "Rooms" and its tiles, then "Zones" and its tiles,
 * in the chosen layout, under the layout switch. ONE card, not a card per
 * tile: HA's section grid cannot give a list the webapp's column counts and
 * gaps, and a per-browser switch could not regenerate it. */
class ArtiLedHomeCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
  }

  setConfig(config) {
    if (!config || !Array.isArray(config.groups)) {
      throw new Error("artiled-home-card needs groups");
    }
    this._config = config;
    this._built = false;
    if (this._follow) this._follow.stop();
    this._follow = null;
    if (this.shadowRoot) this.shadowRoot.innerHTML = "";
  }

  getCardSize() { return 12; }

  getGridOptions() { return { columns: "full" }; }

  /* a valid strategy `layout:` fixes it; anything else leaves it to the switch */
  _fixed() {
    const l = this._config && this._config.layout;
    return LAYOUTS.includes(l) ? l : null;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
    this.shadowRoot.querySelectorAll("artiled-tile-card").forEach((c) => { c.hass = hass; });
  }

  connectedCallback() {
    if (this._built && !this._follow) this._start();
  }

  disconnectedCallback() {
    if (this._follow) this._follow.stop();
    this._follow = null;
  }

  _build() {
    const root = this.shadowRoot;
    const fixed = this._fixed();
    const esc = (v) => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    root.innerHTML = `<style>${HOME_STYLE}</style>` + (fixed ? "" :
      `<div class="layouts" role="radiogroup" aria-label="Layout">${LAYOUTS.map((l) => `
        <button class="tt-tile" type="button" role="radio" data-layout="${l}" title="${LAYOUT_LABEL[l]}">
          <span class="tt-tile__face"><svg viewBox="0 0 90 160" fill="none" aria-hidden="true">${LAYOUT_ART_FRAME}${LAYOUT_ART[l]}</svg></span>
          <span class="tt-tile__name">${LAYOUT_LABEL[l]}</span>
        </button>`).join("")}</div>`);
    this._config.groups.forEach((g) => {
      if (!g || !Array.isArray(g.tiles) || !g.tiles.length) return;
      const h = document.createElement("h2");
      h.className = "app-section";
      h.innerHTML = esc(g.heading || "");
      root.appendChild(h);
      tiles_list(root, g.tiles, this._hass);
    });
    root.querySelectorAll(".tt-tile[data-layout]").forEach((b) =>
      b.addEventListener("click", () => layout_store(b.dataset.layout))
    );
    this._built = true;
    this._start();
  }

  _start() {
    this._follow = tiles_follow(this, this.shadowRoot, this._fixed());
    const paint = () => {
      const layout = this._follow.redo();
      this.shadowRoot.querySelectorAll(".tt-tile[data-layout]").forEach((b) => {
        const on = b.dataset.layout === layout;
        b.classList.toggle("is-running", on);
        b.setAttribute("aria-checked", on ? "true" : "false");
      });
    };
    const stop = this._follow.stop;
    window.addEventListener(LAYOUT_EVENT, paint);
    this._follow.stop = () => { stop(); window.removeEventListener(LAYOUT_EVENT, paint); };
    paint();
  }
}

/* Registration happens at the bottom of this file — see register(). */

/* ------------------------------------------------------------------ *
 * The room / zone screen.
 * ------------------------------------------------------------------ */

/* ⚠ PORTED FROM app/includes/entity-screen.php, not designed here. That screen
 * is the scope's tile, then a TAB STRIP — Scenes · Modes · Colors · [Zones] ·
 * Lights — with each tab a panel that is already in the page and shown by a
 * class swap. Scenes and Modes are grids of ARTWORK, not lists of names.
 *
 * ⚠ A departure the webapp already made and this keeps: the app's own
 * top-tab-navigator sets tabBarScrollEnabled once the Zones tab appears, which
 * pushes Lights off-screen. Michel asked for the strip to fit instead, so every
 * tab is `flex: 1 1 0` and the horizontal padding is 2. Do not "fix" this back.
 *
 * Geometry from app.css: strip margin 12.5/10/0 over a 2px rgba(255,255,255,.5)
 * rule, active tab #fff with a 2px indicator at bottom -2; item tile 50% wide,
 * artwork square with radius 16, name 14px/600 centred 12px below.
 */
/* ⚠ TEXT COLOURS FOLLOW HOME ASSISTANT'S THEME, not the app's white.
 * app.css can say #fff because the app paints its own dark page
 * (linear-gradient(#111, #444)). A Lovelace view is whatever theme the user
 * picked, and on the default light one white-on-white made the tab labels and
 * every scene name INVISIBLE — the layout was right and the page looked empty.
 * The tiles keep the app's own colours because they carry their own dark
 * background; only text sitting directly on the page is themed.
 */
const ENTITY_STYLE = `
:host { display: block; }
.tabs {
  display: flex; margin: 12.5px 10px 0; background: transparent;
  border-bottom: 2px solid var(--divider-color, rgba(255,255,255,.5));
}
.tab {
  position: relative; flex: 1 1 0; min-width: 0;
  display: flex; align-items: center; justify-content: center;
  min-height: 48px; padding: 14px 2px;
  font-size: 14px; color: var(--secondary-text-color, rgba(255,255,255,.5));
  background: none; border: 0; cursor: pointer;
  font-family: inherit; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis;
  -webkit-tap-highlight-color: transparent;
}
.tab.on { color: var(--primary-text-color, #fff); }
.tab.on::after {
  content: ''; position: absolute; left: 0; right: 0; bottom: -2px;
  height: 2px; background: var(--primary-text-color, #fff);
}
.panel { display: none; }
.panel.on { display: block; }
.items { display: flex; flex-wrap: wrap; }
.item {
  display: flex; flex-direction: column; align-items: center;
  width: 50%; padding: 8px 0 4px; margin-bottom: 4px; border-radius: 16px;
  background: none; border: 0; cursor: pointer; font-family: inherit;
  -webkit-tap-highlight-color: transparent;
}
.item__art { position: relative; width: calc(100% - 10.5px); border-radius: 24px; }
.item__img {
  display: block; width: 100%; aspect-ratio: 1;
  border-radius: 16px; object-fit: cover; background: #444;
}
.item__stop {
  position: absolute; inset: 0; display: none;
  align-items: center; justify-content: center;
  border-radius: 16px; background: rgba(0,0,0,.5);
}
.item.running .item__stop { display: flex; }
.item__stop img { width: 40%; height: 40%; object-fit: contain; }
.item__name {
  width: calc(100% - 10.5px); margin-top: 12px;
  color: var(--primary-text-color, #fff);
  font-size: 14px; font-weight: 600; text-align: center;
}
${TILES_STYLE}
.empty {
  color: var(--secondary-text-color, rgba(255,255,255,.5));
  font-size: 14px; padding: 24px 12px; text-align: center;
}
`;

class ArtiLedEntityCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
    this._tab = null;
  }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("artiled-entity-card needs an entity");
    this._config = config;
    this._built = false;
    this._tab = null;
    if (this._follow) this._follow.stop();
    this._follow = null;
    if (this.shadowRoot) this.shadowRoot.innerHTML = "";
  }

  connectedCallback() {
    if (this._built && !this._follow && this.shadowRoot.querySelector(".app-tiles")) {
      this._follow = tiles_follow(this, this.shadowRoot, this._config.layout);
      this._follow.redo();
    }
  }

  disconnectedCallback() {
    if (this._follow) this._follow.stop();
    this._follow = null;
  }

  getCardSize() { return 12; }

  set hass(hass) {
    this._hass = hass;
    const state = hass.states[this._config.entity];
    if (!state) return;
    if (!this._built) this._build(state);
    this._paint(state);
  }

  /* entity-screen.php builds the tab list in top-tab-navigator's order, and
     only offers Zones on a room that HAS zones. */
  _tabs(state) {
    const a = state.attributes || {};
    const tabs = [["scenes", "Scenes"], ["modes", "Modes"], ["colors", "Colors"]];
    if ((this._config.zones || []).length) tabs.push(["zones", "Zones"]);
    tabs.push(["lights", "Lights"]);
    return tabs;
  }

  _build(state) {
    const tabs = this._tabs(state);
    this._tab = this._tab || tabs[0][0];
    this.shadowRoot.innerHTML = `
      <style>${ENTITY_STYLE}</style>
      <div class="tabs" role="tablist">
        ${tabs.map(([k, label]) =>
          `<button class="tab" role="tab" data-tab="${k}">${label}</button>`).join("")}
      </div>
      ${tabs.map(([k]) => `<div class="panel" data-panel="${k}"></div>`).join("")}
    `;
    this.shadowRoot.querySelectorAll(".tab").forEach((t) =>
      t.addEventListener("click", () => { this._tab = t.dataset.tab; this._paint(state, true); })
    );
    this._built = true;
  }

  _paint(state, force) {
    const tabs = this._tabs(state);
    if (!tabs.some(([k]) => k === this._tab)) this._tab = tabs[0][0];
    this.shadowRoot.querySelectorAll(".tab").forEach((t) =>
      t.classList.toggle("on", t.dataset.tab === this._tab)
    );
    this.shadowRoot.querySelectorAll(".panel").forEach((p) => {
      const on = p.dataset.panel === this._tab;
      p.classList.toggle("on", on);
      if (on) this._fill(p, p.dataset.panel, state, force);
    });
  }

  _fill(panel, which, state, force) {
    const a = state.attributes || {};
    if (which === "scenes" || which === "modes") {
      const items = a[which === "scenes" ? "artiled_scenes" : "artiled_modes"] || [];
      const runningName =
        a.running_type === (which === "scenes" ? "scene" : "mode") ? a.running_name : null;
      const sig = JSON.stringify([items.map((i) => i.id), runningName]);
      if (panel._sig === sig && !force) return;
      panel._sig = sig;
      if (!items.length) {
        panel.innerHTML = `<div class="empty">The Hub offers no ${which} here.</div>`;
        return;
      }
      panel.innerHTML = `<div class="items">${items.map((i) => `
        <button class="item${i.name === runningName ? " running" : ""}" data-id="${i.id}">
          <div class="item__art">
            <img class="item__img" src="${i.image || ""}" alt="" loading="lazy">
            <span class="item__stop"><img src="${this._config.stop_image || ""}" alt=""></span>
          </div>
          <div class="item__name">${i.name}</div>
        </button>`).join("")}</div>`;
      panel.querySelectorAll(".item").forEach((el) =>
        el.addEventListener("click", () =>
          this._run(which === "scenes" ? "scene" : "mode", el.dataset.id,
                    el.classList.contains("running")))
      );
      return;
    }
    /* Zones and Lights are Controller rows — the same tile as everywhere else. */
    if (which === "zones" || which === "lights") {
      const ids = (which === "zones" ? this._config.zones : this._config.lights) || [];
      if (panel._sig === String(ids) && !force) return;
      panel._sig = String(ids);
      if (!ids.length) {
        panel.innerHTML = `<div class="empty">Nothing here.</div>`;
        return;
      }
      /* ⚠ Home's lists, in Home's layout (tablet.css: "Zones and Lights are
         Home's .app-tiles"). The room's OWN card above the tabs stays Rows. */
      panel.innerHTML = "";
      tiles_list(panel, ids.map((cfg) => (typeof cfg === "string"
        ? { entity: cfg, kind: which === "zones" ? "zone" : "light" } : cfg)), this._hass);
      if (!this._follow) this._follow = tiles_follow(this, this.shadowRoot, this._config.layout);
      this._follow.redo();
      return;
    }
    if (which === "colors") this._fill_colors(panel, state, force);
  }

  /* Scene and mode firing goes through the integration's SCOPED services, not
     the house-wide entity — the whole point of #425. */
  _run(kind, id, running) {
    const scope = this._config.scope || {};
    const a = (this._hass.states[this._config.entity] || {}).attributes || {};
    if (running) {
      this._hass.callService("artiled_hub", kind === "scene" ? "stop_scene" : "stop_mode",
        { name: a.running_name, ...scope });
    } else {
      const items = a[kind === "scene" ? "artiled_scenes" : "artiled_modes"] || [];
      const item = items.find((i) => String(i.id) === String(id));
      if (item) {
        this._hass.callService("artiled_hub", kind === "scene" ? "run_scene" : "run_mode",
          { name: item.name, ...scope });
      }
    }
  }

  _fill_colors(panel, state, force) {
    if (panel._sig === "colors" && !force) return;
    panel._sig = "colors";
    panel.innerHTML = "";
    const card = document.createElement("artiled-colors-card");
    /* The White and RGB variant buttons are the app's own wheel artwork, served
       by the Hub — same origin as the scene images. */
    card.setConfig({ entity: this._config.entity, origin: this._config.origin || "" });
    card.hass = this._hass;
    panel.appendChild(card);
  }
}

/* ------------------------------------------------------------------ *
 * The Colors tab.
 * ------------------------------------------------------------------ */

/* ⚠ SCOPE, stated honestly. The webapp's Colors panel
 * (app/includes/colors-tab.php + app/js/color.js) has FIVE variants — RGB,
 * AMBIANCE, RGBW, HSV, GRADIENT — a mode selector and a four-channel selector.
 * Only the RGB wheel and its brightness slider are ported here. The other four
 * variants and the channel checkboxes are NOT done; the tab says so rather than
 * pretending to be complete.
 *
 * ⚠ iro.js is the Hub's OWN copy, patched — see the reference_hub_iro_is_patched
 * memory. It is served from this integration and loaded lazily, on first use of
 * the tab, exactly like the icon bundle: 70 KB has no business in the module
 * every HA page loads.
 */
const IRO_URL = "/artiled_hub_frontend/iro.js";
const RCW_URL = "/artiled_hub_frontend/reinvented-color-wheel.min.js";
const RCW_CSS = "/artiled_hub_frontend/reinvented-color-wheel.min.css";
const GRAPICK_URL = "/artiled_hub_frontend/grapick.min.js";
const GRAPICK_CSS = "/artiled_hub_frontend/grapick.min.css";
let iro_promise = null;
const script_promises = {};

/* ⚠ Each library is fetched at most once, on the first use of ITS variant.
   None of them is in the module every HA page loads. */
function load_script(url, test) {
  if (!script_promises[url]) {
    script_promises[url] = new Promise((resolve, reject) => {
      if (test && test()) return resolve();
      const s = document.createElement("script");
      s.src = url;
      s.onload = () => resolve();
      s.onerror = () => reject(new Error(url + " failed to load"));
      document.head.appendChild(s);
    });
  }
  return script_promises[url];
}

function load_iro() {
  if (!iro_promise) {
    iro_promise = new Promise((resolve, reject) => {
      if (window.iro) return resolve(window.iro);
      const s = document.createElement("script");
      s.src = IRO_URL;
      s.onload = () => resolve(window.iro);
      s.onerror = () => reject(new Error("iro.js failed to load"));
      document.head.appendChild(s);
    });
  }
  return iro_promise;
}

const COLORS_STYLE = `
:host { display: block; }
.wrap { padding: 12px 0 8px; }
/* The variant selector. ⚠ White FIRST, then RGB, then RGBW — the order the
   webapp AND the Hub's Control tabs both use. Do not reorder to RGB-first.
   The only thing that leads with RGB is the old React Native app's
   color-wheel-selector.js; the webapp moved away from it at Michel's request
   (2026-08-12: "On Hub we have White first the RGB"), so matching the webapp
   and matching the Hub are the same thing here. */
.variants { display: flex; justify-content: center; gap: 10px; margin-bottom: 14px; }
.variant {
  display: flex; align-items: center; justify-content: center;
  width: 56px; height: 56px; border-radius: 50%;
  border: 2px solid transparent; background: #444; cursor: pointer;
  padding: 0; overflow: hidden;
  -webkit-tap-highlight-color: transparent;
}
.variant.on { border-color: #7a51a1; }
.variant img { width: 100%; height: 100%; object-fit: cover; }
.variant ha-icon { --mdc-icon-size: 26px; color: #fff; }
.stage { display: flex; flex-direction: column; align-items: center; min-height: 300px; }
.pane { display: none; width: 100%; align-items: center; flex-direction: column; }
.pane.on { display: flex; }
/* The Hub's own RGBW sliders — css/artiled.css .color-slider, verbatim:
   10px track, radius 25, 1px white border, and a 15x45 thumb in house purple. */
.sliders { width: 100%; max-width: 320px; padding: 8px 12px; box-sizing: border-box; }
/* ⚠ The thumb is 45px TALL on a 10px track, so it overhangs 17.5px each side.
   Rows closer together than ~45px make the four thumbs overlap into one solid
   purple bar - which is exactly what 18px margins produced. The Hub gives each
   slider its own table cell with padding:10px; this is the same clearance. */
.sliders label { display: block; margin: 0; padding: 22px 0; }
.color-slider {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 10px; border-radius: 25px;
  border: solid 1px #fff; outline: none; opacity: 1;
}
.color-slider::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 15px; height: 45px; border-radius: 10px; background: #7a51a1;
  cursor: pointer; border: 0;
}
.color-slider::-moz-range-thumb {
  width: 15px; height: 45px; border-radius: 10px; background: #7a51a1;
  cursor: pointer; border: 0;
}
/* ⚠ The handle picker is INLINE, where spectrum was a popup. Grapick puts
   colorEl inside the handle, so a wheel left there drifts to whichever side
   the handle sits on. The holder is appended to THIS container instead and
   simply flows below the strip, centred.

   ⚠ Deliberately NOT absolutely positioned. The first attempt pinned it with
   top/padding magic numbers and it overlapped the channel row underneath —
   an absolutely positioned child escapes its parent's height, so the reserved
   space and the real height drift apart the moment either changes. */
.grapick {
  display: flex; flex-direction: column; align-items: center;
  width: 100%; max-width: 320px; padding: 24px 12px 8px; box-sizing: border-box;
}
/* ⚠ ONE picker at a time. setColorPicker runs per HANDLE, so every handle
   builds its own wheel; spectrum hid that behind a popup, and leaving them all
   in flow stacked a wheel per stop down the page. Hidden by default, shown for
   the handle you tap. */
.grapick .gp-pick { display: none; margin-top: 28px; }
.grapick .gp-pick.on { display: block; }
/* ⚠ THE PALETTE STRIP IS BARELY USABLE ON A PHONE WITHOUT THIS, and the webapp
   already worked out why (css/color.css):
     1. THE TARGET IS 4px. grapick.min.css gives .grp-handler width:4px, and
        the drag area fills it. Apple's guidance is 44pt. The circle only
        appears once a handle is selected, so there is not even a big thing to
        grab first.
     2. iOS STEALS THE GESTURE. Without touch-action, a horizontal drag that
        starts on a 4px bar is as likely to be read as a page pan, and the
        handle stops following the finger halfway.
   The hit area is widened with a PSEUDO-ELEMENT rather than by resizing the
   handle, so nothing moves visually — the bar, the circle and the close cross
   all stay exactly where the Hub puts them. 36px wide: a real target. */
.grapick .grp-handler,
.grapick .grp-preview { touch-action: none; }
.grapick .grp-handler-drag { position: relative; }
.grapick .grp-handler-drag::before {
  content: ''; position: absolute;
  top: -8px; bottom: -8px; left: -16px; right: -16px;
}
.err { color: #c0392b; font-size: 14px; padding: 24px; text-align: center; }
/* color.css .ac-channels / .ac-channel: a flat row of four, 23.5% each with a
   2% gap, an 18px box and a 14px label.

   ⚠ DELIBERATE DEVIATION from the webapp, which labels these "Channel 1".
   23.5% of this card is ~80px and "Channel 1" wraps onto two lines there, which
   is what Michel saw. Labelled CH1..CH4 and pinned to one line instead. The
   webapp's own panel is phone-width where the full word fits, so this is a
   difference in the container, not a disagreement about the design. */
/* ⚠ Centred as a group under the wheel, not stretched across the card. With
   CH1..CH4 the labels are short, so the webapp's fixed 23.5%-per-cell split
   would leave three wide gaps; the row is sized to its content and centred
   instead (Michel, 2026-08-17). */
.channels {
  display: flex; align-items: center; justify-content: center;
  gap: 18px; margin: 20px auto 0; padding: 0 12px;
  width: 100%; box-sizing: border-box;
}
.channel {
  display: flex; align-items: center; padding: 0; border: 0;
  background: none; color: var(--primary-text-color, #fff);
  font: inherit; font-size: 14px; cursor: pointer;
  -webkit-tap-highlight-color: transparent;
}
.channel ha-icon { --mdc-icon-size: 18px; margin-right: 5px; flex: 0 0 auto; }
.channel span { white-space: nowrap; }
.channel.off { opacity: .55; }
`;

/* ⚠ The Hub's White is TWO axes, not one. artiled_color_pickers.js: "BOTH
 * temperature AND intensity fade — they are the two halves of White, not one
 * axis plus a constant." So the White pane carries a kelvin ring AND a value
 * slider, and writes colour temperature and brightness together.
 *
 * ⚠ The kelvin RANGE comes from the entity, not from the Hub's picker. That
 * picker spans 2193-10991K; this integration maps HA kelvin to the Hub's 0-255
 * white channel over 2000-6536K (const.py MIRED_MIN/MAX). Writing
 * color_temp_kelvin goes through that existing, tested mapping instead of
 * inventing a second one that would disagree with it.
 *
 * All FIVE variants are built. HSV uses ReinventedColorWheel (8 KB, WTFPL) and
 * Palette uses Grapick (13 KB, MIT) with IRO on the handles instead of
 * spectrum - setColorPicker is a hook, so the Hub's jQuery + spectrum pair
 * (~180 KB and a global) is not needed to get the Hub's own strip.
 *
 * ⚠ Licences, checked rather than assumed: iro.js is MPL 2.0 and is PATCHED
 * here (kelvin gradient 2200..8000) - MPL is file-level copyleft, so it ships
 * as readable source with its header intact and must never be minified,
 * re-headered or relicensed. The rest are permissive: ReinventedColorWheel
 * WTFPL, Grapick MIT.
 */
/* The Hub's Control tabs, in order: White, RGB, RGBW, HSV, Palette
   (control/index.php, where tab-white carries `checked`). */
const COLOR_VARIANTS = [
  ["white", "White", "/app/img/wheel-white.png", null],
  ["rgb", "RGB", "/app/img/wheel-rgb.png", null],
  ["rgbw", "RGBW", null, "mdi:tune-vertical"],
  ["hsv", "HSV", null, "mdi:water"],
  ["palette", "Palette", null, "mdi:palette"],
];
/* ⚠ The HUB's default palette, not the app's. control/index.php line 31:
   $scene_palette_1 = "[[0,0,255,0],[255,0,0,255]]" — quads of
   [position, r, g, b] with position 0..255, which its loop divides by 2.55
   into Grapick's 0..100, so the two handles land hard left and hard right.
   Seeding from the app's 5/95 instead is what Michel spotted: "On hub
   positions are more left and right." */
const HUB_DEFAULT_PALETTE = [[0, 0, 255, 0], [255, 0, 0, 255]];
const RGBW_CHANNELS = [
  ["Red", "#770000"], ["Green", "#007700"], ["Blue", "#000077"], ["White", "#7F654C"],
];
const COLOR_WRITE_MS = 250;

class ArtiLedColorsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
    this._variant = "white";
    /* ⚠ All four ON by default, like ui/channel-selector.tsx. */
    this._channels = { 1: true, 2: true, 3: true, 4: true };
  }

  /* ⚠ The Hub's DIGIT-CONCAT selector, transcribed from color-bind.js:
     channels 1 and 3 -> "13"; all four -> "1234", which the API would read as a
     number over 255, so that case becomes "0" (= every channel); none selected
     is also "0". Do not "simplify" this to a list or an int. */
  _channel_state() {
    const on = [1, 2, 3, 4].filter((c) => this._channels[c]).join("");
    if (on === "") return "0";
    return parseInt(on, 10) > 255 ? "0" : on;
  }

  _whole_light() { return this._channel_state() === "0"; }

  setConfig(config) {
    if (!config || !config.entity) throw new Error("artiled-colors-card needs an entity");
    this._config = config;
    this._built = false;
  }

  getCardSize() { return 10; }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
  }

  _state() { return this._hass.states[this._config.entity] || { attributes: {} }; }

  /* ⚠ Throttle every write. The Hub serialises commands and a room set can take
     15-25s; an unthrottled drag queues one per frame and the lights end up
     minutes behind the finger. */
  /* ⚠ Two write paths, and the channel decides which.
   *
   * WHOLE LIGHT -> light.turn_on. HA owns the entity's state, so going through
   * the light domain keeps brightness/colour in the state machine where every
   * other card and automation can see it.
   *
   * A CHANNEL SUBSET -> artiled_hub.set_color. HA's light domain has no channel
   * concept at all, so this cannot be expressed as light.turn_on; the service
   * carries the Hub's digit-concat selector through untouched.
   */
  _write(data) {
    this._last = data;
    const now = window.performance ? performance.now() : Date.now();
    clearTimeout(this._pending);
    const send = () => {
      this._sent = now;
      /* ⚠ HSV and palette have NO light.turn_on equivalent — HA's light domain
         cannot express either — so they always take the service, whatever the
         channel selection is. */
      const hub_only = data.hsv || data.color_array;
      if (!hub_only && this._whole_light()) {
        this._hass.callService("light", "turn_on",
          { entity_id: this._config.entity, ...data });
        return;
      }
      const scope = this._config.scope || {};
      const call = { ...scope, channel: this._channel_state() };
      if (data.hsv) call.hsv = data.hsv;
      else if (data.color_array) call.color_array = data.color_array;
      else if (data.rgbw_color) call.rgbw = data.rgbw_color;
      else if (data.color_temp_kelvin != null) {
        const a = this._state().attributes;
        const minK = a.min_color_temp_kelvin || 2000;
        const maxK = a.max_color_temp_kelvin || 6536;
        /* The Hub's white channel is 0..255 with 0 = coldest, matching
           _kelvin_to_arti_temperature in light.py. */
        const frac = (data.color_temp_kelvin - minK) / Math.max(1, maxK - minK);
        call.temperature = Math.round((1 - frac) * 255);
      } else return;
      this._hass.callService("artiled_hub", "set_color", call);
    };
    if (!this._sent || now - this._sent > COLOR_WRITE_MS) send();
    else this._pending = setTimeout(send, COLOR_WRITE_MS);
  }

  async _build() {
    this._built = true;
    const origin = this._config.origin || "";
    this.shadowRoot.innerHTML = `<style>${COLORS_STYLE}</style>
      <div class="wrap">
        <div class="variants">
          ${COLOR_VARIANTS.map(([k, label, img, icon]) => `
            <button class="variant" data-v="${k}" title="${label}" aria-label="${label}">
              ${img ? `<img src="${origin}${img}" alt="">`
                    : `<ha-icon icon="${icon}"></ha-icon>`}
            </button>`).join("")}
        </div>
        <div class="stage">
          <div class="pane" data-v="white"></div>
          <div class="pane" data-v="rgb"></div>
          <div class="pane" data-v="rgbw"></div>
          <div class="pane" data-v="hsv"></div>
          <div class="pane" data-v="palette"></div>
        </div>
        <div class="channels">
          ${[1, 2, 3, 4].map((c) => `
            <button class="channel" data-c="${c}" aria-pressed="true"
                    title="Channel ${c}" aria-label="Channel ${c}">
              <ha-icon icon="mdi:checkbox-marked"></ha-icon><span>CH${c}</span>
            </button>`).join("")}
        </div>
      </div>`;
    this.shadowRoot.querySelectorAll(".variant").forEach((b) =>
      b.addEventListener("click", () => this._select(b.dataset.v)));
    this.shadowRoot.querySelectorAll(".channel").forEach((b) =>
      b.addEventListener("click", () => {
        const c = b.dataset.c;
        this._channels[c] = !this._channels[c];
        b.classList.toggle("off", !this._channels[c]);
        b.setAttribute("aria-pressed", this._channels[c] ? "true" : "false");
        b.querySelector("ha-icon").setAttribute(
          "icon", this._channels[c] ? "mdi:checkbox-marked" : "mdi:checkbox-blank-outline");
        /* color-bind.js re-sends the LAST colour under the new channel, so
           changing channels re-applies what is on screen rather than waiting
           for the next drag. Nothing to re-send before the first colour. */
        if (this._last) this._write(this._last);
      }));
    this._build_rgbw();
    this._select(this._variant);
  }

  _select(which) {
    this._variant = which;
    this.shadowRoot.querySelectorAll(".variant").forEach((b) =>
      b.classList.toggle("on", b.dataset.v === which));
    this.shadowRoot.querySelectorAll(".pane").forEach((p) =>
      p.classList.toggle("on", p.dataset.v === which));
    if (which === "rgb" || which === "white") this._build_iro(which);
    else if (which === "hsv") this._build_hsv();
    else if (which === "palette") this._build_palette();
  }

  _build_rgbw() {
    const pane = this.shadowRoot.querySelector('.pane[data-v="rgbw"]');
    const a = this._state().attributes;
    const cur = a.rgbw_color || [127, 127, 127, 127];
    pane.innerHTML = `<div class="sliders">${RGBW_CHANNELS.map(([name, bg], i) => `
      <label><input class="color-slider" type="range" min="0" max="255"
        data-i="${i}" value="${cur[i] != null ? cur[i] : 127}"
        style="background-color:${bg};" aria-label="${name}"></label>`).join("")}</div>`;
    pane.querySelectorAll(".color-slider").forEach((el) =>
      el.addEventListener("input", () => {
        const vals = Array.from(pane.querySelectorAll(".color-slider"))
          .map((s) => parseInt(s.value, 10));
        this._write({ rgbw_color: vals });
      }));
  }

  /* HSV — ReinventedColorWheel, the same wheel the Hub's lighting action uses.
     ⚠ Stored 0-255 per channel; the wheel speaks 0-360 / 0-100
     (artiled_color_pickers.js hsvPair). Converting in only one direction is the
     easy mistake: read the wheel /360*255 and /100*255, seed it the other way. */
  async _build_hsv() {
    const pane = this.shadowRoot.querySelector('.pane[data-v="hsv"]');
    if (pane._done) return;
    pane._done = true;
    try {
      if (!this.shadowRoot.querySelector("link[data-rcw]")) {
        const link = document.createElement("link");
        link.rel = "stylesheet"; link.href = RCW_CSS; link.dataset.rcw = "1";
        this.shadowRoot.appendChild(link);
      }
      await load_script(RCW_URL, () => window.ReinventedColorWheel);
    } catch (e) {
      pane.innerHTML = `<div class="err">The HSV wheel could not be loaded.</div>`;
      pane._done = false;
      return;
    }
    const host = document.createElement("div");
    pane.appendChild(host);
    /* ⛔ NOTHING MAY BE SENT BECAUSE THE CONTROL MOUNTED. ReinventedColorWheel
       calls onChange for its INITIAL colour, and this pane can mount at page
       load - a colour write actuates real fixtures, so opening a page must
       never change a light. color-bind.js guards it exactly this way, and the
       first version of this pane did NOT: opening the HSV tab wrote a colour.
       Writes stay shut until the user has actually touched the wheel. */
    let touched = false;
    host.addEventListener("pointerdown", () => { touched = true; }, true);
    /* ⚠ Seed and geometry are the webapp's, verbatim: hsv [0,100,100] - a FIXED
       red, not the entity's colour - with thickness 30, handle 24 and
       wheelReflectsSaturation on. */
    this._hsv_wheel = new window.ReinventedColorWheel({
      appendTo: host,
      hsv: [0, 100, 100],
      wheelDiameter: 240,
      wheelThickness: 30,
      handleDiameter: 24,
      wheelReflectsSaturation: true,
      onChange: (cw) => {
        if (!touched) return;
        /* The Hub's own conversion: the wheel works in 0..360 / 0..100 / 0..100
           and the API wants three bytes. */
        this._write({
          hsv: [
            parseInt((cw.hsv[0] * 255) / 360, 10),
            parseInt((cw.hsv[1] * 255) / 100, 10),
            parseInt((cw.hsv[2] * 255) / 100, 10),
          ],
        });
      },
    });
  }

  /* Palette — the Hub's Grapick strip.
     ⚠ The per-handle picker is IRO, not spectrum. control/index.php and the
     webapp bind spectrum through setColorPicker(), which drags in jQuery for
     that one plugin; setColorPicker is just a hook, so iro (already shipped
     here) does the same job with no jQuery. The strip, the stop maths and the
     Hub's defaults are unchanged - only the handle's picker differs. */
  async _build_palette() {
    const pane = this.shadowRoot.querySelector('.pane[data-v="palette"]');
    if (pane._done) return;
    pane._done = true;
    try {
      if (!this.shadowRoot.querySelector("link[data-gp]")) {
        const link = document.createElement("link");
        link.rel = "stylesheet"; link.href = GRAPICK_CSS; link.dataset.gp = "1";
        this.shadowRoot.appendChild(link);
      }
      await Promise.all([
        load_script(GRAPICK_URL, () => window.Grapick),
        load_iro(),
      ]);
    } catch (e) {
      pane.innerHTML = `<div class="err">The palette strip could not be loaded.</div>`;
      pane._done = false;
      return;
    }
    const host = document.createElement("div");
    host.className = "grapick";
    pane.appendChild(host);
    const gp = new window.Grapick({ el: host, colorEl: '<input class="gp-color"/>' });

    /* The Hub's setColorPicker body with iro in spectrum's place. Returns a
       destroy function, as Grapick expects. */
    gp.setColorPicker((handler) => {
      const el = handler.getEl().querySelector(".gp-color");
      const holder = document.createElement("div");
      holder.className = "gp-pick";
      /* Anchored to the strip container, not to the handle — see .gp-pick. */
      host.appendChild(holder);
      el.style.display = "none";
      const show = () => {
        host.querySelectorAll(".gp-pick").forEach((n) => n.classList.remove("on"));
        holder.classList.add("on");
      };
      handler.getEl().addEventListener("click", show, true);
      /* The first handle built is the one on screen, so the pane is never blank. */
      if (!host.querySelector(".gp-pick.on")) holder.classList.add("on");
      const m = String(handler.getColor()).match(/\d+/g) || [255, 255, 255];
      const picker = new window.iro.ColorPicker(holder, {
        width: 140, borderWidth: 1, borderColor: "#fff",
        color: { r: +m[0], g: +m[1], b: +m[2] },
        layout: [{ component: window.iro.ui.Wheel }],
      });
      picker.on("input:change", (c) => handler.setColor(c.rgbString, 0));
      picker.on("input:end", (c) => handler.setColor(c.rgbString));
      return () => { holder.remove(); };
    });

    /* ⛔ addHandler fires `change`, and a change sends colour to REAL FIXTURES.
       Nothing may leave here merely because the control was built. */
    let ready = false;
    gp.on("change", () => {
      if (!ready) return;
      const handlers = gp.getHandlers();
      /* The Hub's own rule: one handle is not a gradient, so send a plain
         colour instead of a palette (control/index.php, `if (arrayLength > 1)`). */
      if (handlers.length === 1) {
        const rgb = String(handlers[0].color).match(/\d+/g) || [0, 0, 0];
        this._write({ rgbw_color: [+rgb[0], +rgb[1], +rgb[2], 0] });
        return;
      }
      const quads = handlers.map((h, i) => {
        const position = i === 0 ? 0
          : i === handlers.length - 1 ? 255
          : Math.round(h.position * 2.55);
        const rgb = String(h.color).match(/\d+/g) || [0, 0, 0];
        return [position, +rgb[0], +rgb[1], +rgb[2]];
      });
      /* ⚠ color_array is a JSON STRING - room.php json_decode()s it. Sending an
         array of rgb() strings 400'd every palette drag in the webapp. */
      this._write({ color_array: JSON.stringify(quads) });
    });

    HUB_DEFAULT_PALETTE.forEach((quad) =>
      gp.addHandler(quad[0] / 2.55, `rgba(${quad[1]}, ${quad[2]}, ${quad[3]}, 1)`, 1));
    ready = true;
  }

  async _build_iro(which) {
    const pane = this.shadowRoot.querySelector(`.pane[data-v="${which}"]`);
    if (pane._done) return;
    pane._done = true;
    let iro;
    try {
      iro = await load_iro();
    } catch (e) {
      pane.innerHTML = `<div class="err">The colour wheel could not be loaded.</div>`;
      pane._done = false;
      return;
    }
    const host = document.createElement("div");
    pane.appendChild(host);
    const a = this._state().attributes;
    const bri = typeof a.brightness === "number" ? a.brightness : 255;

    if (which === "rgb") {
      /* ⚠ The webapp's seed: the entity's OWN first colour, falling back to
         white — colors-tab.php passes item.colors[0] and color-bind.js reads
         `data-initial || 'rgb(255,255,255)'`. artiled_colors is that same Hub
         array, so use it before HA's collapsed rgb_color. */
      const stop = (a.artiled_colors || [])[0];
      const m = stop && String(stop).match(/\d+/g);
      const rgb = m && m.length >= 3
        ? [+m[0], +m[1], +m[2]]
        : (a.rgb_color || [255, 255, 255]);
      let picker;
      const opts = {
        width: 240, borderWidth: 1, borderColor: "#fff",
        /* ⚠ handleRadius 12, a deliberate deviation from the Hub's default 8.
           The Hub's is a mouse target; this is a phone. */
        handleRadius: 12,
        layout: [
          { component: iro.ui.Wheel },
          { component: iro.ui.Slider, options: { sliderType: "value" } },
        ],
      };
      try {
        picker = new iro.ColorPicker(host, { ...opts, color: { r: rgb[0], g: rgb[1], b: rgb[2] } });
      } catch (e) {
        /* A colour iro cannot parse must not cost the user the control. */
        picker = new iro.ColorPicker(host, { ...opts, color: "#ffffff" });
      }
      picker.color.value = Math.round((bri / 255) * 100);
      picker.on("input:change", (c) => this._write({
        rgbw_color: [c.rgb.r, c.rgb.g, c.rgb.b, 0],
        brightness: Math.round((c.value / 100) * 255),
      }));
      return;
    }

    /* White: kelvin ring + value, the Hub's own two-axis control. */
    const minK = a.min_color_temp_kelvin || 2000;
    const maxK = a.max_color_temp_kelvin || 6536;
    const picker = new iro.ColorPicker(host, {
      width: 240, borderWidth: 1, borderColor: "#fff", handleRadius: 12,
      layout: [
        { component: iro.ui.Slider,
          options: { sliderType: "kelvin", sliderShape: "circle", sliderSize: 30,
                     minTemperature: minK, maxTemperature: maxK } },
        { component: iro.ui.Slider, options: { sliderType: "value" } },
      ],
    });
    try {
      picker.color.set({ kelvin: a.color_temp_kelvin || Math.round((minK + maxK) / 2) });
      picker.color.value = Math.round((bri / 255) * 100);
    } catch (e) { /* an out-of-range seed must not kill the pane */ }
    picker.on("input:change", (c) => this._write({
      color_temp_kelvin: Math.max(minK, Math.min(maxK, Math.round(c.kelvin))),
      brightness: Math.round((c.value / 100) * 255),
    }));
  }
}

/* ------------------------------------------------------------------ *
 * Voice: exposure and aliases.
 * ------------------------------------------------------------------ */

/* ⚠ NO WEBAPP EQUIVALENT — this is new UI, deliberately. Voice exposure is a
 * Home Assistant concept, so there is nothing to port; the rest of this file is
 * a port and this is not. It exists because the alternative is telling every
 * customer to go and find Settings > Voice assistants > Expose.
 *
 * ⚠ EXPOSURE IS PER ASSISTANT, three of them (Michel, 2026-08-17). HA stores a
 * separate should_expose per assistant key, and the websocket command takes an
 * `assistants` array — one combined switch would be a lie about the model.
 *
 * ⚠ BOTH websocket commands are @require_admin: homeassistant/expose_entity and
 * config/entity_registry/update. A household member who is not an admin gets an
 * error, so the controls are DISABLED for them and say why, rather than looking
 * available and failing on tap.
 */
const ASSISTANTS = [
  ["conversation", "Assist", "mdi:home-assistant"],
  ["cloud.alexa", "Alexa", "mdi:microphone"],
  ["cloud.google_assistant", "Google", "mdi:google"],
];

/* Domains an assistant can actually be asked to control. A name clash only
   matters between two things a person could mean by the same sentence, so a
   diagnostic sensor sharing a name with a light is not a clash. */
/* Scene and mode names ignore case when MATCHED (Michel 2026-09-10): the Hub and the
   nodes start "relax" and "Relax" as one scene. A voice entry keeps and shows the
   spelling it was added with; only the comparison lowercases. */
function voice_item_key(item) {
  return String(item === undefined || item === null ? "" : item).toLowerCase();
}

/* Aliases as the "also called" field shows them, and back (Michel 2026-10-26,
   as the Control). ⚠ HA 2026.10 keeps the entity's OWN computed name IN its
   aliases list - the websocket shows it as null, and a new entity starts with
   just that entry. The field shows only the user's words; a save puts the null
   back first. Saving without it took the entity's own name out of what Assist
   answers to. An entry read without a null (older HA, or the user's own list)
   is saved as typed; one never read keeps HA's default, the null. */
function aliases_shown(raw) {
  return (raw || []).filter((a) => typeof a === "string" && a.trim() !== "").join(", ");
}

function aliases_to_save(text, raw) {
  const typed = String(text || "").split(",").map((a) => a.trim()).filter(Boolean);
  const keep_computed = raw === undefined || raw === null || (raw || []).some((a) => a === null);
  return keep_computed ? [null, ...typed] : typed;
}

const VOICE_DOMAINS = new Set([
  "light", "switch", "cover", "media_player", "climate", "fan", "lock", "scene",
]);

const VOICE_STYLE = `
:host { display: block; }
.wrap { padding: 4px 12px 16px; }
.head {
  font-size: 13px; font-weight: 600; letter-spacing: .04em;
  text-transform: uppercase; margin: 22px 0 10px;
  color: var(--secondary-text-color, #aaa);
}
.head:first-child { margin-top: 4px; }
/* Same tab strip as the room screen, so the two pages read as one product. */
.tabs {
  display: flex; margin: 0 0 4px; background: transparent;
  border-bottom: 2px solid var(--divider-color, rgba(255,255,255,.5));
}
.tab {
  position: relative; flex: 1 1 0; min-width: 0;
  display: flex; align-items: center; justify-content: center;
  min-height: 48px; padding: 14px 2px; font-size: 14px;
  color: var(--secondary-text-color, rgba(255,255,255,.5));
  background: none; border: 0; cursor: pointer; font-family: inherit;
  -webkit-tap-highlight-color: transparent;
}
.tab.on { color: var(--primary-text-color, #fff); }
.tab.on::after {
  content: ''; position: absolute; left: 0; right: 0; bottom: -2px;
  height: 2px; background: var(--primary-text-color, #fff);
}
.panel { display: none; }
.panel.on { display: block; }
.item {
  padding: 12px 0;
  border-bottom: 1px solid var(--divider-color, rgba(255,255,255,.12));
}
.name {
  font-size: 16px; font-weight: 600; margin-bottom: 8px;
  color: var(--primary-text-color, #fff);
}
details > summary {
  cursor: pointer; font-size: 13px; font-weight: 600;
  letter-spacing: .04em; text-transform: uppercase; margin: 22px 0 10px;
  color: var(--secondary-text-color, #aaa);
}
/* The duplicate-name warning. Amber rather than red: it is an advisory, not a
   failure — and it must stay readable on the user's theme, light or dark, so
   the colour is a token with a literal fallback rather than a hardcoded hex. */
.clash {
  display: flex; gap: 6px; align-items: flex-start;
  margin: 0 0 8px; padding: 8px 10px;
  border-radius: 4px; font-size: 13px; line-height: 1.35;
  color: var(--primary-text-color, #fff);
  background: var(--warning-color, #ffa726);
  background: color-mix(in srgb, var(--warning-color, #ffa726) 18%, transparent);
  border-left: 3px solid var(--warning-color, #ffa726);
}
.clash ha-icon {
  --mdc-icon-size: 18px; flex: 0 0 auto; margin-top: 1px;
  color: var(--warning-color, #ffa726);
}
/* Scenes / Modes tabs: one collapsible per scope, rows filled on open. */
details { border-bottom: 1px solid var(--divider-color, rgba(255,255,255,.12)); }
details > summary {
  margin: 0; padding: 12px 0; text-transform: none; letter-spacing: 0;
  font-size: 16px; color: var(--primary-text-color, #fff);
  display: flex; align-items: center; gap: 8px;
}
/* The marker would otherwise sit after the flex children. */
details > summary::-webkit-details-marker { display: none; }
details > summary ha-icon {
  --mdc-icon-size: 18px; flex: 0 0 auto;
  color: var(--secondary-text-color, #aaa);
}
.opts { padding: 0 0 10px 4px; }
.opt {
  display: flex; align-items: center; gap: 10px; padding: 5px 0;
}
.opt__name {
  flex: 0 0 34%; min-width: 0; font-size: 14px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
  color: var(--primary-text-color, #fff);
}
.opt input {
  flex: 1 1 auto; min-width: 0; padding: 6px 8px; font-size: 13px;
  color: var(--primary-text-color, #fff); font-family: inherit;
  background: var(--card-background-color, rgba(255,255,255,.06));
  border: 1px solid var(--divider-color, rgba(255,255,255,.25)); border-radius: 4px;
}
.pill.tick { padding: 4px 8px; min-width: 0; }
.opt__warn {
  flex: 0 0 16px; text-align: center; font-size: 15px; cursor: help;
  color: var(--warning-color, #ffa726);
}
.row { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.pill {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 12px; border-radius: 16px; cursor: pointer;
  border: 1px solid var(--divider-color, rgba(255,255,255,.25));
  background: none; color: var(--secondary-text-color, #aaa);
  font: inherit; font-size: 14px;
  -webkit-tap-highlight-color: transparent;
}
.pill.on {
  background: #7a51a1; border-color: #7a51a1; color: #fff;
}
.pill[disabled] { opacity: .5; cursor: default; }
.pill ha-icon { --mdc-icon-size: 18px; }
.aliases { margin-top: 8px; }
.aliases input {
  width: 100%; box-sizing: border-box; padding: 8px 10px; font: inherit;
  font-size: 13px; border-radius: 8px;
  color: var(--primary-text-color, #fff);
  background: var(--card-background-color, #444);
  border: 1px solid var(--divider-color, rgba(255,255,255,.25));
}
.aliases input:disabled { opacity: .5; }
.note {
  margin-top: 10px; font-size: 12px; line-height: 1.4;
  color: var(--secondary-text-color, #aaa);
}
`;

/* What the person was doing on the Voice page (Michel 2026-10-26, as the
   Control). Adding or renaming a voice scene/mode reloads the integration, the
   strategy hands the card a NEW config (often a new card element), and the page
   is drawn again: without this it jumped back to the first tab the moment + was
   pressed, closed the room, and showed the old name until the reload finished.
   Page state only, kept per browser tab. */
const VOICE_UI = { tab: null, open: new Set(), typed: new Map() };
const open_key = (kind, id, what) => `${kind}|${Number(id)}|${what}`;
const typed_key = (kind, id, what, item) => `${kind}|${Number(id)}|${what}|${voice_item_key(item)}`;

class ArtiLedVoiceCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._built = false;
    this._alias_raw = new Map();   /* entity_id -> its registry aliases as read */
  }

  setConfig(config) {
    this._config = config || {};
    this._built = false;
    this._alias_raw = new Map();
  }

  getCardSize() { return 14; }

  set hass(hass) {
    this._hass = hass;
    if (!this._built) this._build();
  }

  get _admin() {
    return !!(this._hass && this._hass.user && this._hass.user.is_admin);
  }

  /* ⚠ A VOICE ASSISTANT RESOLVES BY NAME, so a name that is not unique is a
     coin flip — and nothing in Home Assistant warns you.

     The Hub allows a zone and a light to share a name, and this integration
     faithfully creates an entity for each, so the duplicates are OFTEN OUR OWN:
     measured on the dev instance, "Cristalliera", "Lotus" and "Vitrine" each
     exist as both a zone and an individual light, and "Toilet" is FOUR entities
     (an ArtiLED room, an ArtiLED light and two Hue bulbs).

     Compared across the whole instance, not just our entities — the assistant
     does not care which integration a name came from, and the Hue bulb next to
     our room is exactly the collision that misroutes a sentence.

     Names are compared as HA composes them (friendly_name), not as the Hub
     spells them: friendly_name is what the assistant is actually given. */
  _clashes() {
    const seen = new Map();
    const states = (this._hass && this._hass.states) || {};
    Object.keys(states).forEach((id) => {
      if (!VOICE_DOMAINS.has(id.split(".")[0])) return;
      const n = String(((states[id].attributes || {}).friendly_name) || "")
        .trim().toLowerCase();
      if (!n) return;
      if (!seen.has(n)) seen.set(n, []);
      seen.get(n).push(id);
    });
    return seen;
  }

  _display_name(it) {
    const st = ((this._hass || {}).states || {})[it.entity];
    return String(((st || {}).attributes || {}).friendly_name || it.name || "");
  }

  _rows(items) {
    const clashes = this._clashes();
    return items.map((it) => {
      const shown = this._display_name(it);
      const others = (clashes.get(shown.trim().toLowerCase()) || [])
        .filter((id) => id !== it.entity);
      /* Only a warning, never a block: two lights may legitimately share a name
         in different rooms, and the user may simply not use voice for them. The
         alias field directly below is the fix, which is why the warning sits
         between the name and the pills rather than in a dialog. */
      const warn = others.length ? `
        <div class="clash" title="${others.join(", ")}">
          <ha-icon icon="mdi:alert-outline"></ha-icon>
          <span>Also called this: ${others.length === 1
            ? others[0]
            : others.length + " other entities"}. Voice may pick the wrong one —
            give this one an alias below.</span>
        </div>` : "";
      return `
      <div class="item" data-e="${it.entity}">
        <div class="name">${it.name}</div>
        ${warn}
        <div class="row">
          ${ASSISTANTS.map(([key, label, icon]) => `
            <button class="pill" data-a="${key}" data-e="${it.entity}">
              <ha-icon icon="${icon}"></ha-icon>${label}
            </button>`).join("")}
        </div>
        <div class="aliases">
          <input type="text" data-e="${it.entity}"
                 placeholder="${it.suggest ? it.suggest : "also called — comma separated"}">
        </div>
      </div>`;
    }).join("");
  }

  /* One scope's scenes (or modes) as tick-rows.
     ⚠ Built LAZILY, when its <details> is opened. The reference install has 23 scopes with
     ~27 scenes each: rendering every row up front is ~620 rows carrying an
     input each, on a page most people open to change one thing. */
  _scoped_rows(scope, what) {
    const items = what === "scene" ? scope.scenes : scope.modes;
    const chosen = what === "scene" ? scope.chosen_scenes : scope.chosen_modes;
    const by_item = new Map(chosen.map((c) => [voice_item_key(c.item), c]));
    return items.map((item) => {
      const hit = by_item.get(voice_item_key(item));
      /* The suggested name is what someone would SAY. "Cinema" in the Cinema
         would become "Cinema Cinema", so a repeated word collapses. */
      const suggest = scope.name.toLowerCase() === String(item).toLowerCase()
        ? `${scope.name} ${what === "mode" ? "Mode" : "Scene"}`
        : `${scope.name} ${item}`;
      /* A name typed here wins until the reloaded config carries it. */
      const k = typed_key(scope.kind, scope.id, what, item);
      if (VOICE_UI.typed.has(k) && hit && hit.name === VOICE_UI.typed.get(k)) VOICE_UI.typed.delete(k);
      const own = VOICE_UI.typed.has(k) ? VOICE_UI.typed.get(k) : (hit ? String(hit.name) : "");
      const shown = own || suggest;
      return `
        <div class="opt" data-kind="${scope.kind}" data-id="${scope.id}"
             data-item="${String(item).replace(/"/g, "&quot;")}" data-what="${what}">
          <button class="pill tick${hit ? " on" : ""}">
            <ha-icon icon="${hit ? "mdi:check" : "mdi:plus"}"></ha-icon>
          </button>
          <span class="opt__name">${item}</span>
          <input type="text" placeholder="${suggest}"
                 value="${own.replace(/"/g, "&quot;")}">
          <span class="opt__warn" title="">${
            this._name_taken(shown, hit && hit.entity) ? "⚠" : ""}</span>
        </div>${hit && hit.entity ? `
        <div class="aliases">
          <input type="text" data-e="${String(hit.entity).replace(/"/g, "&quot;")}"
                 placeholder="also called — comma separated">
        </div>` : ""}`;
    }).join("");
  }

  /* ⚠ THE SAME NAME CHECK AS THE EXPOSURE TABS, and it matters MORE here: the
     name is typed free-form, and `scene` is in HA's alexa_default_expose, so a
     clashing name reaches Amazon as a second device answering one phrase.
     Ignores the row's own entity, or an already-added scene would flag itself. */
  _name_taken(name, self_entity) {
    const key = String(name || "").trim().toLowerCase();
    if (!key) return false;
    const owners = (this._clashes().get(key) || []).filter((id) => id !== self_entity);
    return owners.length > 0;
  }

  _scoped_panel(what) {
    const scopes = this._config.scoped || [];
    const some = scopes.filter((s) => (what === "scene" ? s.scenes : s.modes).length);
    if (!some.length) return "";
    /* ⚠ SPLIT ROOMS FROM ZONES. Listed in one run they are indistinguishable —
       "Kitchen" and "Kitchen Spots" look like siblings when one is a room and
       the other a zone inside it, and the Hub offers each a DIFFERENT scene
       list. The other tabs already separate them, so this matches. */
    const section = (kind, title) => {
      const rows = some.filter((s) => s.kind === kind);
      if (!rows.length) return "";
      return `<div class="head">${title} (${rows.length})</div>` + rows.map((s) => `
        <details data-kind="${s.kind}" data-id="${s.id}" data-what="${what}">
          <summary>
            <ha-icon icon="${s.icon || KIND_ICON[s.kind] || "mdi:lightbulb"}"></ha-icon>
            <span>${s.name}</span>
          </summary>
          <div class="opts"></div>
        </details>`).join("");
    };
    return section("room", "Rooms") + section("zone", "Zones");
  }

  async _build() {
    this._built = true;
    const c = this._config;
    /* ⚠ Rooms / Zones / Lights only. Scenes and Modes are deliberately absent:
       the only scene and mode ENTITIES are the house-wide ones, which fire
       across every light in the house - exposing those to voice means one
       mis-heard phrase can darken the whole home. The per-scope scenes are not
       entities at all, they are options inside the Scene/Mode dropdowns, so
       there is nothing there to expose either. Michel, 2026-08-17: leave them
       off. */
    const groups = [
      ["rooms", "Rooms", c.rooms || []],
      ["zones", "Zones", c.zones || []],
      ["lights", "Lights", c.lights || []],
    ].filter(([, , items]) => items.length);
    if (!groups.length) return;
    /* Scenes and Modes get their own tabs rather than sitting under Rooms and
       Zones: they are a different job. The first three tabs answer "can voice
       control this light at all"; these two answer "what can I ask it to run" —
       and a scoped scene exists only once someone names it. Michel, 2026-08-17. */
    const scoped = c.scoped || [];
    const n_scenes = scoped.reduce((n, s) => n + (s.chosen_scenes || []).length, 0);
    const n_modes = scoped.reduce((n, s) => n + (s.chosen_modes || []).length, 0);
    const extra = [
      ["scenes", "Scenes", n_scenes, "scene"],
      ["modes", "Modes", n_modes, "mode"],
    ].filter(([, , , what]) => this._scoped_panel(what));

    const tabs = groups.map(([k]) => k).concat(extra.map(([k]) => k));
    this._tab = tabs.includes(VOICE_UI.tab) ? VOICE_UI.tab : groups[0][0];
    this.shadowRoot.innerHTML = `
      <style>${VOICE_STYLE}</style>
      <div class="wrap">
        <div class="tabs" role="tablist">
          ${groups.map(([k, label, items]) =>
            `<button class="tab" role="tab" data-t="${k}">${label} (${items.length})</button>`
          ).join("")}
          ${extra.map(([k, label, n]) =>
            `<button class="tab" role="tab" data-t="${k}">${label} (${n})</button>`
          ).join("")}
        </div>
        ${groups.map(([k, , items]) =>
          `<div class="panel" data-p="${k}">${this._rows(items)}</div>`).join("")}
        ${extra.map(([k, , , what]) =>
          `<div class="panel" data-p="${k}">${this._scoped_panel(what)}
             <p class="note">Only what you add here becomes a voice target. The
               Hub offers hundreds of room-and-scene combinations; an entity
               nobody can name is one nobody will ever say.</p>
           </div>`).join("")}
        <p class="note">A voice assistant can only control what is switched on
          here. "Also called" adds the other names it answers to — the Hub's own
          name always works.</p>
      </div>`;
    this.shadowRoot.querySelectorAll(".tab").forEach((t) =>
      t.addEventListener("click", () => this._select(t.dataset.t)));
    this._select(this._tab);
    await this._load();
    this.shadowRoot.querySelectorAll(".item .pill").forEach((b) =>
      b.addEventListener("click", () => this._toggle(b)));
    this.shadowRoot.querySelectorAll(".item input").forEach((i) => {
      i.addEventListener("change", () => this._save_aliases(i));
      i.addEventListener("blur", () => this._save_aliases(i));
    });
    /* Fill a scope's rows the first time it is opened — see _scoped_rows. */
    this.shadowRoot.querySelectorAll("details").forEach((d) => {
      const key = open_key(d.dataset.kind, d.dataset.id, d.dataset.what);
      d.addEventListener("toggle", () => {
        if (d.open) VOICE_UI.open.add(key); else VOICE_UI.open.delete(key);
        if (d.open) this._fill_scoped(d);
      });
      /* A room left open before the reload opens again, filled now - not left
         to a toggle event that may come later or not at all. */
      if (VOICE_UI.open.has(key)) {
        d.open = true;
        this._fill_scoped(d);
      }
    });
  }

  /* One scope's scene/mode rows, built the first time it is opened. */
  _fill_scoped(d) {
    if (d.dataset.filled) return;
    const scope = (this._config.scoped || []).find(
      (s) => s.kind === d.dataset.kind && String(s.id) === d.dataset.id);
    if (!scope) return;
    d.dataset.filled = "1";
    const box = d.querySelector(".opts");
    box.innerHTML = this._scoped_rows(scope, d.dataset.what);
    box.querySelectorAll(".tick").forEach((b) =>
      b.addEventListener("click", () => this._toggle_scoped(b)));
    box.querySelectorAll(".opt input").forEach((i) => {
      i.addEventListener("change", () => this._rename_scoped(i));
      /* Live, as they type — a clash is worth knowing BEFORE the tick. */
      i.addEventListener("input", () => this._recheck_name(i));
    });
    /* An added scene's (or mode's) aliases - the Rooms tab's "also called"
       field, read from and saved to its registry entry (Michel 2026-10-26, as
       the Control's Activities tab). */
    box.querySelectorAll(".aliases input").forEach((i) => {
      i.addEventListener("change", () => this._save_aliases(i));
      i.addEventListener("blur", () => this._save_aliases(i));
      this._load_aliases(i);
    });
  }

  async _load_aliases(input) {
    try {
      const entry = await this._hass.callWS({
        type: "config/entity_registry/get", entity_id: input.dataset.e,
      });
      this._alias_raw.set(input.dataset.e, (entry || {}).aliases || []);
      if (document.activeElement !== input) input.value = aliases_shown((entry || {}).aliases);
    } catch (e) { /* the field stays empty; nothing is written unless typed */ }
  }

  /* Add or remove one scoped scene/mode. The integration persists the choice
     and reloads, which is what makes the entity appear or vanish. */
  async _toggle_scoped(btn) {
    const row = btn.closest(".opt");
    const on = !btn.classList.contains("on");
    const what = row.dataset.what;
    const input = row.querySelector("input");
    const data = { [row.dataset.kind]: Number(row.dataset.id) };
    data[what] = row.dataset.item;
    if (on) data.name = (input.value || input.placeholder).trim();
    const k = typed_key(row.dataset.kind, row.dataset.id, what, row.dataset.item);
    if (on && input.value.trim()) VOICE_UI.typed.set(k, input.value.trim());
    if (!on) VOICE_UI.typed.delete(k);
    btn.classList.toggle("on", on);
    btn.querySelector("ha-icon").setAttribute("icon", on ? "mdi:check" : "mdi:plus");
    try {
      await this._hass.callService(
        "artiled_hub", `${on ? "add" : "remove"}_voice_${what}`, data);
    } catch (e) {
      btn.classList.toggle("on", !on);   /* put it back; the write failed */
      btn.querySelector("ha-icon").setAttribute("icon", !on ? "mdi:check" : "mdi:plus");
      VOICE_UI.typed.delete(k);          /* nothing was stored, nothing to hold */
    }
  }

  _recheck_name(input) {
    const row = input.closest(".opt");
    const warn = row.querySelector(".opt__warn");
    if (!warn) return;
    const chosen = (this._config.scoped || [])
      .flatMap((s) => (row.dataset.what === "scene" ? s.chosen_scenes : s.chosen_modes))
      .find((c) => c && voice_item_key(c.item) === voice_item_key(row.dataset.item));
    const taken = this._name_taken(input.value || input.placeholder,
                                   chosen && chosen.entity);
    warn.textContent = taken ? "⚠" : "";
    warn.title = taken ? "Another entity already answers to this name" : "";
  }

  /* Renaming an already-added one: add again with the new name. The service
     replaces a matching scope+item rather than duplicating it. */
  async _rename_scoped(input) {
    const row = input.closest(".opt");
    if (!row.querySelector(".tick").classList.contains("on")) return;
    const what = row.dataset.what;
    const data = { [row.dataset.kind]: Number(row.dataset.id),
                   name: (input.value || input.placeholder).trim() };
    data[what] = row.dataset.item;
    const k = typed_key(row.dataset.kind, row.dataset.id, what, row.dataset.item);
    VOICE_UI.typed.set(k, data.name);
    try {
      await this._hass.callService("artiled_hub", `add_voice_${what}`, data);
    } catch (e) {
      VOICE_UI.typed.delete(k);   /* refused: the stored name stands; the field keeps what was typed, to retry */
    }
  }

  _select(which) {
    this._tab = which;
    VOICE_UI.tab = which;
    this.shadowRoot.querySelectorAll(".tab").forEach((t) =>
      t.classList.toggle("on", t.dataset.t === which));
    this.shadowRoot.querySelectorAll(".panel").forEach((p) =>
      p.classList.toggle("on", p.dataset.p === which));
  }

  /* ⚠ ONE registry read per entity, and the registry is the right source twice
     over: homeassistant/expose_entity/list returns the BOOLEAN itself rather
     than the {should_expose} object, AND lists only entities that are ON — so
     an absent entity could equally mean "explicitly off" or "never set". The
     registry entry is unambiguous and carries the aliases in the same reply. */
  async _load() {
    const all = Array.from(this.shadowRoot.querySelectorAll(".item"))
      .map((el) => el.dataset.e);
    await Promise.all(all.map(async (id) => {
      let entry = null;
      try {
        entry = await this._hass.callWS({
          type: "config/entity_registry/get", entity_id: id,
        });
      } catch (e) { return; }
      const options = (entry || {}).options || {};
      ASSISTANTS.forEach(([key]) => {
        const set = options[key];
        /* No explicit setting -> HA's own default, which is NOT the same for
           every assistant: DEFAULT_EXPOSED_ASSISTANT is {"conversation": true},
           so Assist exposes a new light and Alexa/Google do not. Showing all
           three as on was wrong for two of them.
           ⚠ This is a fallback that should almost never be reached — the
           integration writes an explicit setting for everything it creates. It
           also cannot see a user's own "expose new entities" switch, which
           overrides the default; the explicit write is what makes the pills
           truthful. */
        const on = set && typeof set.should_expose === "boolean"
          ? set.should_expose
          : (key === "conversation" && id.startsWith("light."));
        const pill = this.shadowRoot.querySelector(`.pill[data-a="${key}"][data-e="${id}"]`);
        if (pill) pill.classList.toggle("on", !!on);
      });
      const input = this.shadowRoot.querySelector(`input[data-e="${id}"]`);
      /* ⚠ The null in aliases is NOT stray: it is HA 2026.10's computed own
         name. Not shown (the field would render "null"), and put back on save
         (aliases_to_save) - dropping it took the entity's own name away.
         ⚠ An empty field keeps its PLACEHOLDER, which carries the suggested
         "<Name> Lights". A placeholder is not a value: nothing is written until
         the user types and the row saves, so this never edits customer data on
         its own. */
      this._alias_raw.set(id, (entry || {}).aliases || []);
      if (input) input.value = aliases_shown((entry || {}).aliases);
    }));
  }

  async _toggle(pill) {
    const on = !pill.classList.contains("on");
    pill.classList.toggle("on", on);
    try {
      await this._hass.callWS({
        type: "homeassistant/expose_entity",
        assistants: [pill.dataset.a],
        entity_ids: [pill.dataset.e],
        should_expose: on,
      });
    } catch (e) {
      pill.classList.toggle("on", !on);   /* put it back; the write failed */
    }
  }

  async _save_aliases(input) {
    const aliases = aliases_to_save(input.value, this._alias_raw.get(input.dataset.e));
    const key = input.dataset.e + "|" + aliases.join("|");
    if (this._saved === key) return;   /* change AND blur both fire */
    this._saved = key;
    try {
      await this._hass.callWS({
        type: "config/entity_registry/update",
        entity_id: input.dataset.e,
        aliases,
      });
    } catch (e) { /* leave the field as typed so the user can retry */ }
  }
}

/* ------------------------------------------------------------------ *
 * The dashboard strategy.
 * ------------------------------------------------------------------ */

/* Classification comes from the DEVICE IDENTIFIER, not from a model string or
   an entity_id: identifiers are "<ident>_room_15" / "_zone_16" / "_light_8"
   and are the same values __init__.py registers. An entity_id can be renamed
   by the user; this cannot. */
function classify(device) {
  for (const pair of device.identifiers || []) {
    if (pair[0] !== "artiled_hub") continue;
    const m = String(pair[1]).match(/_(room|zone|light)_(\d+)$/);
    if (m) return { kind: m[1], id: Number(m[2]) };
    return { kind: "hub", id: 0 };
  }
  return null;
}

const KIND_ICON = { room: "mdi:sofa", zone: "mdi:vector-rectangle" };
const OVERVIEW_COLUMNS = 3;
/* The Hub's palette is normally [start, end]; cap defensively so a pathological
   array can never build a thousand-stop gradient string. */
const MAX_STOPS = 8;

/* ⚠ Match the run pickers on unique_id, not on entity_id or display name. A
   user may rename either; unique_id is the one thing that cannot change.

   ⚠ This must agree with parse_run_picker() in entity_ids.py — the same
   strings, matched twice in two languages. tests/test_frontend.js runs the JS
   against the SAME cases as tests/test_entity_ids.py so the two cannot drift.
   The turn-on/turn-off pickers end in _on_scene/_off_scene and are excluded by
   the _run_ segment. */
const RUN_PICKER = /_(?:room|zone)_\d+_run_(scene|mode)$/;

function run_picker_suffix(unique_id) {
  const m = RUN_PICKER.exec(String(unique_id || ""));
  return m ? m[1] : null;
}

class ArtiLedDashboardStrategy {
  static async generate(config, hass) {
    const [entities, devices] = await Promise.all([
      hass.callWS({ type: "config/entity_registry/list" }),
      hass.callWS({ type: "config/device_registry/list" }),
    ]);

    const ours = entities.filter((e) => e.platform === "artiled_hub");
    if (!ours.length) {
      return {
        views: [
          {
            title: "ArtiLED",
            cards: [
              {
                type: "markdown",
                content:
                  "No ArtiLED Hub entities found. Add the integration under " +
                  "**Settings → Devices & services**.",
              },
            ],
          },
        ],
      };
    }

    const by_device = new Map();
    ours.forEach((e) => {
      if (!e.device_id) return;
      if (!by_device.has(e.device_id)) by_device.set(e.device_id, []);
      by_device.get(e.device_id).push(e);
    });

    const scopes = { room: [], zone: [], light: [], hub: [] };
    const device_by_id = new Map();
    devices.forEach((d) => {
      if (!by_device.has(d.id)) return;
      const what = classify(d);
      if (!what) return;
      device_by_id.set(d.id, d);
      scopes[what.kind].push({ device: d, ...what });
    });

    /* Hub light id -> its HA light entity, via the device identifier. */
    const light_entity_by_hub_id = new Map();
    const light_page = new Map();
    scopes.light.forEach((l) => {
      const light = (by_device.get(l.device.id) || []).find(
        (e) => e.entity_id.startsWith("light.") && !e.disabled_by
      );
      if (light) {
        light_entity_by_hub_id.set(l.id, light.entity_id);
        /* ⚠ Store the ID, not the path: DASHBOARD_PATH is declared further
           down and referencing it here is a temporal-dead-zone ReferenceError
           that the tests cannot catch, because they load the module without
           ever running generate(). */
        light_page.set(light.entity_id, l.id);
      }
    });

    /* Which lights a scope contains, resolved to entity ids.
       ⚠ Read from the scope's own `member_light_ids` attribute, NOT from
       via_device. A light device's via_device is its ROOM, so via_device can
       never describe a ZONE — a zone would get an empty page and a flat
       single-colour tile. The attribute is set by light.py for rooms and zones
       alike, so both go through one path. */
    const members_of = (device_id, light_entity_id) => {
      const state = hass.states[light_entity_id];
      const ids = (state && state.attributes && state.attributes.member_light_ids) || [];
      return ids.map((id) => light_entity_by_hub_id.get(Number(id))).filter(Boolean);
    };

    const pick = (device_id, domain) =>
      (by_device.get(device_id) || []).find(
        (e) => e.entity_id.startsWith(domain + ".") && !e.disabled_by
      );

    const pick_run = (device_id, suffix) =>
      (by_device.get(device_id) || []).find(
        (e) => !e.disabled_by && run_picker_suffix(e.unique_id) === suffix
      );

    /* Subview links need the dashboard's own url_path, which a strategy is not
       told. Take it from the URL being rendered; `dashboard_path` in the
       strategy config overrides it if a customer ever needs to. */
    const DASHBOARD_PATH =
      (config && config.dashboard_path) ||
      window.location.pathname.split("/").filter(Boolean)[0] ||
      "artiled-app";

    const label = (d) => d.name_by_user || d.name;

    /* The Hub's own web root, taken from an artwork URL the integration already
       absolutised — the browser fetches the wheel and stop glyphs from the same
       place it fetches scene artwork, and nothing here should hard-code a host.

       ⚠ Resolved ONCE from any entity that carries artiled_scenes, not per
       entity. Only rooms and zones have that attribute; asking a LIGHT for it
       returned "" and the colour-variant wheels rendered as broken images on
       every light page. */
    const hub_origin = (() => {
      for (const st of Object.values(hass.states)) {
        const first = ((st.attributes || {}).artiled_scenes || [])[0];
        if (first && first.image) {
          try { return new URL(first.image).origin; } catch (e) { /* keep looking */ }
        }
      }
      return "";
    })();
    const HUB_ORIGIN = () => hub_origin;

    /* One scope's own tile. `navigate` turns the card into the app's
       Pressable — tap the room, land on the room's page. */
    const scope_tile = (entry, opts) => {
      const d = entry.device;
      const light = pick(d.id, "light");
      if (!light) return null;
      const scene = pick_run(d.id, "scene");
      const mode = pick_run(d.id, "mode");
      return {
        type: "custom:artiled-tile-card",
        entity: light.entity_id,
        kind: entry.kind,
        icon: KIND_ICON[entry.kind],
        ...(opts && opts.navigate ? { navigate: opts.navigate } : {}),
        ...(opts && opts.controls && scene ? { scene: scene.entity_id } : {}),
        ...(opts && opts.controls && mode ? { mode: mode.entity_id } : {}),
      };
    };

    const by_name = (a, b) => String(label(a.device)).localeCompare(String(label(b.device)));

    const views = [];
    const sub_path = (entry) => `${entry.kind}-${entry.id}`;

    /* ⚠ The overview lists SCOPES ONLY, as the app's home screen does — not
       every light in the house in one endless scroll. The lights and the
       scene/mode pickers live on the scope's own page, reached by tapping it. */
    const rooms = scopes.room.slice().sort(by_name);
    const zones = scopes.zone.slice().sort(by_name);

    /* ⚠ ONE page with a "Rooms" heading then a "Zones" heading, which is what
       the app's home screen is — app/index.php:
           <h2 class="app-section">Rooms</h2>  ...tiles...
           <h2 class="app-section">Zones</h2>  ...tiles...
       Not two tabs.

       ⚠ ONE card holding both lists (artiled-home-card), full width, since
       0.32.5: the webapp's layouts (Grid by default, Square, List, Rows) put
       2..6 tiles in a row by the width they have, with the webapp's own gaps,
       and a per-browser switch changes them live. A card per tile in HA's
       section grid could do neither. `layout: grid|square|list|rows` in the
       strategy config fixes the layout for this dashboard (no switch). */
    const LAYOUT_FIXED = config && LAYOUTS.includes(config.layout) ? config.layout : null;
    const groups = [];
    for (const [entries, heading] of [
      [rooms, "Rooms"],
      [zones, "Zones"],
    ]) {
      const tiles = entries
        .map((e) => scope_tile(e, { navigate: `/${DASHBOARD_PATH}/${sub_path(e)}` }))
        .filter(Boolean);
      if (tiles.length) groups.push({ heading, tiles });
    }
    if (groups.length) {
      views.push({
        title: "Home",
        path: "home",
        icon: "mdi:home",
        type: "sections",
        max_columns: OVERVIEW_COLUMNS,
        sections: [{
          type: "grid",
          column_span: OVERVIEW_COLUMNS,
          cards: [{
            type: "custom:artiled-home-card",
            groups,
            ...(LAYOUT_FIXED ? { layout: LAYOUT_FIXED } : {}),
            grid_options: { columns: "full" },
          }],
        }],
      });
    }

    /* A page per room and per zone — PORTED FROM app/includes/entity-screen.php:
       the scope's own tile, then the tab strip (Scenes · Modes · Colors ·
       [Zones] · Lights). Not a list of dropdowns, which is what this was until
       Michel compared it to the webapp. */
    const zones_of_room = new Map();
    zones.forEach((z) => {
      const parent = z.device.via_device_id;
      if (!parent) return;
      if (!zones_of_room.has(parent)) zones_of_room.set(parent, []);
      const light = pick(z.device.id, "light");
      if (light) zones_of_room.get(parent).push({ entity: light.entity_id, kind: "zone" });
    });

    for (const entry of rooms.concat(zones)) {
      const tile = scope_tile(entry);
      if (!tile) continue;
      const cards = [tile, {
        type: "custom:artiled-entity-card",
        entity: tile.entity,
        ...(LAYOUT_FIXED ? { layout: LAYOUT_FIXED } : {}),
        scope: { [entry.kind]: entry.id },
        origin: HUB_ORIGIN(),
        stop_image: `${HUB_ORIGIN()}/images/control/stop.png`,
        zones: zones_of_room.get(entry.device.id) || [],
        lights: members_of(entry.device.id, tile.entity).map((entity_id) => ({
          entity: entity_id,
          kind: "light",
          navigate: light_page.has(entity_id)
            ? `/${DASHBOARD_PATH}/light-${light_page.get(entity_id)}` : null,
        })),
      }];
      views.push({
        title: label(entry.device),
        path: sub_path(entry),
        icon: KIND_ICON[entry.kind],
        type: "sections",
        max_columns: 2,
        subview: true,
        back_path: `/${DASHBOARD_PATH}/home`,
        /* No heading card: a subview already shows the scope's name in the
           toolbar next to the back arrow, so one would just say it twice. */
        sections: [{ type: "grid", cards }],
      });
    }

    /* ⚠ A page per LIGHT, and it is NOT the room screen with a different
       entity. app/light/index.php is explicit: "It has NO tab strip:
       light-screen.tsx mounts Controller and then <Colors> directly, so a light
       has only its card and the colour controls. There are no scenes, modes or
       zones on a light." */
    for (const l of scopes.light.sort(by_name)) {
      const light = pick(l.device.id, "light");
      if (!light) continue;
      views.push({
        title: label(l.device),
        path: `light-${l.id}`,
        icon: "mdi:lightbulb",
        type: "sections",
        max_columns: 2,
        subview: true,
        back_path: `/${DASHBOARD_PATH}/home`,
        sections: [{ type: "grid", cards: [
          { type: "custom:artiled-tile-card", entity: light.entity_id, kind: "light" },
          { type: "custom:artiled-colors-card", entity: light.entity_id,
            origin: HUB_ORIGIN(),
            scope: { light: l.id } },
        ] }],
      });
    }

    /* The Voice page — exposure and aliases for every scope in one place.
       ⚠ ADMIN ONLY, and omitted entirely rather than shown disabled: both
       websocket commands behind it (homeassistant/expose_entity and
       config/entity_registry/update) are @require_admin, so a household member
       could only ever look at it. A strategy runs per USER, so simply not
       emitting the view is the whole implementation.

       ⚠ It is a CONFIG page, which is why it earns a tab where the old "Hub"
       tab did not: setting voice up otherwise means visiting all 87 scope pages
       or digging through Settings > Voice assistants > Expose. */
    /* ⚠ The tile keeps the Hub's own name ("Bathroom") because that is what the
       webapp shows and what the Hub calls it. Voice is the different audience:
       Alexa and Google have no concept of an area, so the entity NAME is the
       utterance, and "Alexa, turn on Bathroom" is not what anyone says. The
       natural phrase is offered as a suggested ALIAS instead of renaming the
       entity - which would put "Bathroom Lights" on every tile and undo the
       webapp match. Michel, 2026-08-17. */
    const voice_of = (entry) => {
      const light = pick(entry.device.id, "light");
      if (!light) return null;
      const name = label(entry.device);
      return { entity: light.entity_id, name, suggest: `${name} Lights` };
    };
    /* ⚠ A scope's SCENES AND MODES come from its run-picker's options, not from
       a scene list: the Hub offers a different set per room (40 house-wide, 6
       in the Cinema, 2 in the Bedroom), and the picker already holds exactly
       what that scope supports. "None" is the picker's idle placeholder, not a
       scene, so it is dropped.

       ⚠ ALREADY-CHOSEN ones are found by the artiled_scope/artiled_item
       ATTRIBUTES the scoped entities carry — never by parsing the entity_id,
       which is derived from a user-assigned name and changes when they rename
       it. */
    const scoped_of = (entry) => {
      const what = classify(entry.device);
      if (!what || what.kind === "hub" || what.kind === "light") return null;
      const opts = (suffix) => {
        const sel = pick_run(entry.device.id, suffix);
        const st = sel && hass.states[sel.entity_id];
        return ((st && st.attributes.options) || [])
          .filter((o) => o && o !== "None");
      };
      const chosen_in = (domain) => Object.keys(hass.states)
        .filter((id) => id.startsWith(domain + "."))
        .map((id) => hass.states[id])
        .filter((s) => s.attributes.artiled_scope === `${what.kind}_${what.id}`)
        .map((s) => ({ item: s.attributes.artiled_item,
                       name: s.attributes.friendly_name, entity: s.entity_id }));
      /* ⚠ THE HUB'S OWN ICON, not an mdi guess. Every room and zone carries the
         icon the customer chose in the Hub ("fas fa-couch"), which 0.10.0
         bundled so it renders as artiled:<name>. Hardcoding mdi:sofa for rooms
         is exactly the mistake the tiles used to make — it ignores the
         customer's choice and makes 12 different rooms look identical. */
      const light = pick(entry.device.id, "light");
      const st = light && hass.states[light.entity_id];
      const hub_icon = st && st.attributes.artiled_icon;
      return {
        kind: what.kind, id: what.id, name: label(entry.device),
        icon: hub_icon ? `artiled:${fa_name(hub_icon)}` : KIND_ICON[what.kind],
        scenes: opts("scene"), modes: opts("mode"),
        chosen_scenes: chosen_in("scene"), chosen_modes: chosen_in("switch"),
      };
    };

    if (hass.user && hass.user.is_admin) {
      const voice_lights = scopes.light.slice().sort(by_name)
        .map(voice_of).filter(Boolean);
      const voice_card = {
        type: "custom:artiled-voice-card",
        rooms: rooms.map(voice_of).filter(Boolean),
        zones: zones.map(voice_of).filter(Boolean),
        lights: voice_lights,
        scoped: [...rooms, ...zones].map(scoped_of).filter(Boolean),
      };
      if (voice_card.rooms.length || voice_card.zones.length || voice_lights.length) {
        views.push({
          title: "Voice",
          path: "voice",
          icon: "mdi:microphone-settings",
          type: "sections",
          max_columns: 2,
          sections: [{ type: "grid", cards: [voice_card] }],
        });
      }
    }

    /* ⚠ THERE IS NO "HUB" TAB, deliberately. An earlier version added a "Hub"
       view holding the flow buttons and the firmware sensor, because the
       integration happens to expose them as entities — reasoning from the data
       model rather than from the design. The webapp has no Flows screen: its
       navigation is Home / Magic / Notifications / Settings
       (app/includes/menu.php), and this dashboard is the Home stack.

       The flow buttons and the version sensor still EXIST as entities, so
       automations, scripts and the integration's device page can all use them.
       They simply do not get a tab of their own. Michel, 2026-08-17, on seeing
       it: "Why is that there?"

       ⚠ The house-wide scene entities and mode switches are absent for a
       different and stronger reason: a bare scene id runs across every light in
       the house, which is why the integration hides them by default. Scenes and
       modes belong to a scope, and each scope's page carries its own. */

    return { views };
  }
}

/* ------------------------------------------------------------------ *
 * The ArtiLED logo, as a Home Assistant icon.
 * ------------------------------------------------------------------ */

/* ⚠ MEASURED from app/img/icon-512.png, not drawn by eye. The mark is an arch
 * of uniform thickness with a centre dot; the numbers below are its geometry on
 * that 512px canvas, scaled by 24/512 into the icon viewBox:
 *
 *     arc centre (255.5, 259)   outer r 205   inner r 98   stroke 107
 *     legs to y 459             dot centre (255.5, 322) r 52
 *
 * Rendered back and compared to the original: IoU 0.966, area within 1.8%.
 * The purple measured #7A51A1 — the same --purple the app and webapp use —
 * but the path carries NO colour: an HA icon inherits currentColor, so it
 * follows the sidebar's active/inactive state like every built-in icon.
 *
 * One subpath traces the outer arch and then the inner arch, which makes the
 * hole without depending on fill-rule; the dot is a second subpath and fills
 * under both nonzero and evenodd.
 */
const ARTILED_LOGO_PATH =
  "M2.37,21.52 L2.37,12.14 A9.61,9.61 0 0 1 21.59,12.14 L21.59,21.52 " +
  "L16.57,21.52 L16.57,12.14 A4.59,4.59 0 0 0 7.38,12.14 L7.38,21.52 Z " +
  "M9.54,15.09 a2.44,2.44 0 1 0 4.88,0 a2.44,2.44 0 1 0 -4.88,0 Z";

/* ------------------------------------------------------------------ *
 * The Font Awesome icons the Hub's rooms and zones actually use.
 * ------------------------------------------------------------------ */

/* ⚠ The Hub stores its icons as Font Awesome PRO classes ("fas fa-couch") and
 * Home Assistant ships MDI, so there is no shared name to map.
 *
 * ⚠ These paths are NOT shipped with the integration. They are read from the
 * customer's own Hub at runtime by icons.py and cached in the CONFIG directory,
 * because Font Awesome's Pro licence does not permit distributing standalone
 * copies of Pro icons to non-licensees — which is what a published package
 * containing them would be. Do not reintroduce a bundled icon file.
 *
 * ⚠ Only the icons a Hub actually uses are present — a few dozen, not 3,241 —
 * so this is small. Still loaded LAZILY and at most once: the first icon render
 * triggers the fetch, everything after it is served from the resolved map.
 *
 * An icon the cache does not hold falls back to the ArtiLED mark, which is also
 * what happens before the first fetch completes.
 */
const FA_BASE = "/artiled_hub_icons/fa-icons.json";

/* ⚠ Cache-bust the icon URL. The static handler serves it with max-age of a
 * month, so without a buster a refreshed cache would sit unseen behind the
 * browser's copy — deployed and invisible, the same trap as the module itself.
 * Python appends ?v=<version> to this module's own src; read it back off the
 * script tag rather than duplicating the version here where it would drift.
 *
 * ⚠ The version only changes on upgrade, but this file is now REWRITTEN at
 * runtime whenever the Hub gains an icon we have not fetched. A browser that
 * already holds the file will not see a new icon until the next upgrade or a
 * hard reload; the icon falls back to the ArtiLED mark until then. Acceptable
 * for something cosmetic, and far better than the alternative of shipping the
 * whole Pro set.
 *
 * Deliberately NOT import.meta.url: this file is loaded as a module in the
 * browser, but import.meta is a syntax error anywhere else, which would make
 * the whole module unloadable by the test harness. */
function fa_url() {
  try {
    const tag = document.querySelector('script[src*="artiled-hub.js"]');
    const v = tag && new URL(tag.src, location.href).searchParams.get("v");
    return v ? `${FA_BASE}?v=${encodeURIComponent(v)}` : FA_BASE;
  } catch (e) {
    return FA_BASE;
  }
}

let fa_icons_promise = null;

function fa_icons() {
  if (!fa_icons_promise) {
    fa_icons_promise = fetch(fa_url())
      .then((r) => (r.ok ? r.json() : {}))
      .catch(() => ({}));  /* an icon is cosmetic; never break the dashboard */
  }
  return fa_icons_promise;
}

/* "fas fa-couch" / "fa-solid fa-couch" / "couch" -> "couch". The Hub has stored
   several generations of class string, so take the LAST fa- token rather than
   assuming a position: "fas fa-couch" splits to ["fas","fa-couch"]. */
function fa_name(icon) {
  const parts = String(icon || "").trim().split(/\s+/).filter(Boolean);
  const token = parts.filter((p) => p.startsWith("fa-")).pop() || parts.pop() || "";
  return token.replace(/^fa-/, "");
}

/* Registers the `artiled:` iconset — `artiled:logo` for the mark, and
   `artiled:fa-<name>` for a Hub icon. Usable anywhere HA takes an icon name. */
function register_iconset() {
  window.customIconsets = window.customIconsets || {};
  if (window.customIconsets.artiled) return;
  window.customIconsets.artiled = async (name) => {
    if (name === "logo" || name === "a") {
      return { path: ARTILED_LOGO_PATH, viewBox: "0 0 24 24" };
    }
    const key = fa_name(name.replace(/^fa-/, ""));
    const entry = (await fa_icons())[key];
    /* Unknown icon -> the ArtiLED mark rather than an empty box. */
    if (!entry) return { path: ARTILED_LOGO_PATH, viewBox: "0 0 24 24" };
    return { path: entry[0], viewBox: entry[1] };
  };
}

/* ------------------------------------------------------------------ *
 * Registration.
 * ------------------------------------------------------------------ */

/* ⚠ DO NOT define these at module-evaluation time.
 *
 * This module is ~19 KB and loads far faster than Home Assistant's own
 * multi-megabyte bundle, so a top-level define() lands at about 96ms — BEFORE
 * HA installs scoped-custom-element-registry, which REPLACES
 * window.customElements wholesale. The elements then sit in the native
 * registry, which nothing looks at afterwards.
 *
 * The failure is completely silent: define() succeeds, no exception, nothing in
 * the browser console and nothing in the HA log. The only symptom is the
 * dashboard failing with "Timeout waiting for strategy element
 * ll-strategy-dashboard-artiled-hub to be registered" — which reads like the
 * module never loaded, when in fact it loaded early and registered in the wrong
 * place. Proven by comparing the two registries: our card was present in the
 * one captured at document start and absent from the live one, while ha-card
 * was in both.
 *
 * So: wait for an element only HA itself defines, then register on whatever
 * registry is live at that moment. The polyfill also forwards definitions to
 * the native registry, which is why waiting on the native one still resolves.
 */
const NATIVE_REGISTRY = customElements;
const REGISTRY_WATCH_MS = 30000;
const REGISTRY_POLL_MS = 50;

function define_once(registry, tag, ctor) {
  try {
    if (!registry.get(tag)) registry.define(tag, ctor);
  } catch (e) {
    /* Already defined by a second copy of this module — not a problem. */
  }
}

function define_all(registry) {
  define_once(registry, "artiled-tile-card", ArtiLedTileCard);
  define_once(registry, "artiled-entity-card", ArtiLedEntityCard);
  define_once(registry, "artiled-home-card", ArtiLedHomeCard);
  define_once(registry, "artiled-colors-card", ArtiLedColorsCard);
  define_once(registry, "artiled-voice-card", ArtiLedVoiceCard);
  define_once(registry, "ll-strategy-dashboard-artiled-hub", ArtiLedDashboardStrategy);
}

/* ⚠ Register on BOTH registries rather than betting on which one is live.
 *
 * Waiting for one specific element to appear was not good enough: it assumes
 * the polyfill forwards that element to the native registry, and if it ever
 * does not, registration is delayed by the whole fallback timeout and Home
 * Assistant gives up long before. Defining twice is cheap and has no failure
 * mode — define_once() is guarded both by .get() and by try/catch.
 *
 * The three cases this covers:
 *   swap already happened before we loaded  -> the immediate define IS the live
 *                                              registry, and the watcher never
 *                                              fires (correct)
 *   swap happens after we loaded            -> the watcher re-defines on the
 *                                              new registry within ~50ms
 *   no swap ever (future HA)                -> the immediate define is enough
 */
register_iconset();
define_all(NATIVE_REGISTRY);

const watch_started = Date.now();
const watcher = setInterval(() => {
  if (customElements !== NATIVE_REGISTRY) {
    define_all(customElements);
    clearInterval(watcher);
  } else if (Date.now() - watch_started > REGISTRY_WATCH_MS) {
    clearInterval(watcher);
  }
}, REGISTRY_POLL_MS);

window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "artiled-tile-card")) {
  window.customCards.push({
    type: "artiled-tile-card",
    name: "ArtiLED tile",
    description: "An ArtiLED room, zone or light in the app's own styling",
  });
}
