"""The Assist Satellite Notifier integration.

Home Assistant has no `notify` service that speaks. Assist satellites do
have a native announcement primitive -- `assist_satellite.announce` -- but
it is an action of its own, so `alert:`, blueprints and anything that takes
a list of notifiers cannot reach it. This integration is the thin adapter
that closes that gap.

Scaffold only at this point: an entry sets up and unloads, and nothing
announces yet. The notify surfaces land in 0.1.0.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Assist Satellite Notifier from a config entry."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return True
