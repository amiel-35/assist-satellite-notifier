"""Config flow for Assist Satellite Notifier.

One config entry = one Assist satellite. Scaffold version: it picks the
satellite and stores it. The feature checks and the options flow land in
0.1.0.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.assist_satellite import (
    DOMAIN as ASSIST_SATELLITE_DOMAIN,
)
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import selector

from .const import CONF_SATELLITE, DOMAIN


class AssistSatelliteNotifierConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Assist Satellite Notifier."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the single setup step: pick the satellite."""
        if user_input is not None:
            satellite = user_input[CONF_SATELLITE]
            await self.async_set_unique_id(satellite)
            self._abort_if_unique_id_configured()
            state = self.hass.states.get(satellite)
            return self.async_create_entry(
                title=state.name if state is not None else satellite,
                data={CONF_SATELLITE: satellite},
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SATELLITE): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain=ASSIST_SATELLITE_DOMAIN)
                    ),
                }
            ),
        )
