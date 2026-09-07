"""Diagnostics support for Assist Satellite Notifier.

Nothing this integration stores is a secret: `deny_domains` is a policy
list, the quiet-hours window is a schedule, and the satellite it announces
on is visible everywhere else in Home Assistant. `TO_REDACT` is therefore
empty, but the redaction pass runs anyway so adding a sensitive option
later is a one-line change to that tuple rather than a review of this whole
module.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import AssistSatelliteNotifierConfigEntry

TO_REDACT: tuple[str, ...] = ()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: AssistSatelliteNotifierConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Diagnostics can be downloaded for an entry that failed to set up or is
    disabled, in which case `runtime_data` does not exist; the stored
    data/options are still worth reporting, so that case degrades instead
    of raising.
    """
    diagnostics: dict[str, Any] = {
        "data": dict(entry.data),
        "options": dict(entry.options),
        "loaded": hasattr(entry, "runtime_data"),
    }

    if hasattr(entry, "runtime_data"):
        runtime_data = entry.runtime_data
        diagnostics["announcer_config"] = asdict(runtime_data.announcer.config)
        diagnostics["service_name"] = runtime_data.service_name
        diagnostics["satellite_available"] = runtime_data.announcer.available
    else:
        diagnostics["announcer_config"] = None
        diagnostics["service_name"] = None
        diagnostics["satellite_available"] = None

    return async_redact_data(diagnostics, TO_REDACT)
