# Copyright (C) 2026 ArtiLED B.V. All Rights Reserved.
"""Constants for the ArtiLED Hub integration."""

DOMAIN = "artiled_hub"

CONF_TOKEN = "token"
CONF_CREATE_DASHBOARD = "create_dashboard"   # #525 — config-flow checkbox, default on

STORAGE_VERSION = 1

DEFAULT_PORT = 80
UPDATE_INTERVAL_SECONDS = 10

# The Hub's white channel takes temperature 0..255. Same mapping the old
# YAML shim used: mired 153 (cold) -> 0, mired 500 (warm) -> 255.
MIRED_MIN = 153
MIRED_MAX = 500

# Every assistant a voice exposure can be set for. The frontend's Voice page
# carries the same three, in the same order.
ASSISTANTS = ("conversation", "cloud.alexa", "cloud.google_assistant")

ON_SCENE_NAME = "on"
OFF_SCENE_NAME = "off"
NO_SCENE = "none"

PLATFORMS = ["light", "scene", "select", "switch", "button", "sensor"]

# The frontend module: the ArtiLED tile card and the dashboard strategy.
# Served from the integration itself so a customer installs nothing extra —
# no HACS, no manual resource, no third-party card.
# ⚠ The whole directory is served, so everything in frontend/ must be intended
# to be publicly readable. Font Awesome paths are NOT in there — see icons.py.
FRONTEND_BASE = "/artiled_hub_frontend"
FRONTEND_DIR = "frontend"
FRONTEND_URL = f"{FRONTEND_BASE}/artiled-hub.js"

# Font Awesome paths read from the customer's own Hub at runtime, cached in the
# CONFIG directory so a HACS upgrade does not discard them. ⚠ Never move this
# into the integration directory: that is what shipped Font Awesome Pro icons
# inside the package, which the Pro licence does not permit once the package is
# published. See icons.py.
ICON_BASE = "/artiled_hub_icons"
ICON_CACHE_DIR = "artiled_hub_icons"
ICON_CACHE_FILE = "fa-icons.json"
ICON_URL = f"{ICON_BASE}/{ICON_CACHE_FILE}"
