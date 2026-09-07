"""Constants for the Assist Satellite Notifier integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "assist_satellite_notifier"

# Config entry data keys. The satellite an entry speaks on is its identity
# and is not editable; everything else lives in `entry.options`.
CONF_SATELLITE: Final = "satellite"
# The resolved `notify.satellite_<name>` service name, persisted the first
# time the entry sets up and recomputed only when the entry title changes.
# Stored rather than derived on every load so that two entries can never
# resolve to the same name, and so that an entry that fell back to `_2`
# keeps it once the unsuffixed name is free again.
CONF_SERVICE_NAME: Final = "service_name"

# Config entry option keys.
CONF_PREANNOUNCE: Final = "preannounce"
CONF_PREANNOUNCE_MEDIA_ID: Final = "preannounce_media_id"
CONF_PREFIX_TITLE: Final = "prefix_title"
CONF_DENY_DOMAINS: Final = "deny_domains"
CONF_QUIET_START: Final = "quiet_start"
CONF_QUIET_END: Final = "quiet_end"
CONF_QUIET_BEHAVIOUR: Final = "quiet_behaviour"

# Play the satellite's pre-announcement sound by default, which is what
# `assist_satellite.announce` itself defaults to
# (`homeassistant/components/assist_satellite/__init__.py`, the `announce`
# schema: `vol.Optional("preannounce", default=True)`).
DEFAULT_PREANNOUNCE: Final = True
DEFAULT_PREFIX_TITLE: Final = False
# The safety rule: nothing from these domains is ever spoken out loud, so a
# security event cannot be inferred from what is heard in a room.
DEFAULT_DENY_DOMAINS: Final[list[str]] = ["alarm_control_panel", "lock"]

# What a call that lands inside the quiet-hours window does.
QUIET_BEHAVIOUR_REFUSE: Final = "refuse"
QUIET_BEHAVIOUR_SKIP_PREANNOUNCE: Final = "skip_preannounce"
QUIET_BEHAVIOURS: Final[list[str]] = [
    QUIET_BEHAVIOUR_REFUSE,
    QUIET_BEHAVIOUR_SKIP_PREANNOUNCE,
]
DEFAULT_QUIET_BEHAVIOUR: Final = QUIET_BEHAVIOUR_REFUSE

# `data` payload keys accepted by the legacy `notify.satellite_<name>`
# service. Anything else is refused rather than ignored, so a typo in an
# automation is visible immediately.
ATTR_SOURCE_ENTITY: Final = "source_entity"
ATTR_PRIORITY: Final = "priority"
ATTR_PREANNOUNCE: Final = "preannounce"
ATTR_MEDIA_ID: Final = "media_id"

ALLOWED_DATA_KEYS: Final[frozenset[str]] = frozenset(
    {ATTR_SOURCE_ENTITY, ATTR_PRIORITY, ATTR_PREANNOUNCE, ATTR_MEDIA_ID}
)

# The one `priority` value this integration acts on: it bypasses quiet
# hours. Any other string is accepted and ignored, so that a caller can
# carry its own priority vocabulary through to future versions.
PRIORITY_CRITICAL: Final = "critical"

# The `data.priority` vocabulary. Declared here for the tests that pin it;
# not enforced yet.
PRIORITIES: Final[frozenset[str]] = frozenset(
    {"info", "normal", "high", PRIORITY_CRITICAL}
)
