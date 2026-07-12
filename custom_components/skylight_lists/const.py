"""Constants for Skylight Lists."""

from datetime import timedelta

DOMAIN = "skylight_lists"
CONF_FRAME_ID = "frame_id"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_SYNC_TARGET_ENTITY = "sync_target_entity"
DEFAULT_SCAN_INTERVAL = timedelta(minutes=5)
API_BASE_URL = "https://app.ourskylight.com"
API_VERSION = "2026-05-01"
OAUTH_CLIENT_ID = "skylight-mobile"
OAUTH_REDIRECT_URI = "skylight-family://welcome"
