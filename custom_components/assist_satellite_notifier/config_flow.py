"""Config flow for Assist Satellite Notifier.

One config entry = one Assist satellite. The user step picks the
`assist_satellite` entity (which also becomes the entry's unique ID, so the
same satellite cannot be configured twice) and refuses one that does not
advertise `ANNOUNCE`; everything else has a sensible default and can be
changed later through the options flow, which reuses the same schema minus
the satellite itself.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.assist_satellite import (
    DOMAIN as ASSIST_SATELLITE_DOMAIN,
    AssistSatelliteEntityFeature,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import State, callback
from homeassistant.helpers import selector

from .const import (
    CONF_DENY_DOMAINS,
    CONF_PREANNOUNCE,
    CONF_PREANNOUNCE_MEDIA_ID,
    CONF_PREFIX_TITLE,
    CONF_QUIET_BEHAVIOUR,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_SATELLITE,
    DEFAULT_DENY_DOMAINS,
    DEFAULT_PREANNOUNCE,
    DEFAULT_PREFIX_TITLE,
    DEFAULT_QUIET_BEHAVIOUR,
    DOMAIN,
    QUIET_BEHAVIOURS,
)


def _deny_domains_to_string(domains: list[str]) -> str:
    """Render a list of domains as a comma-separated string."""
    return ", ".join(domains)


def _string_to_deny_domains(value: str) -> list[str]:
    """Parse a comma-separated string into a list of domains.

    Domains are case-folded here so `Lock` and `lock` are one rule; the
    announcer folds again when comparing, so an entry stored before this
    normalisation still behaves.
    """
    return [part.strip().casefold() for part in value.split(",") if part.strip()]


def _supports_announce(state: State) -> bool:
    """Return whether a satellite advertises `ANNOUNCE`.

    `assist_satellite.announce` is registered with
    `[AssistSatelliteEntityFeature.ANNOUNCE]` as its required feature
    (`homeassistant/components/assist_satellite/__init__.py`), so a
    satellite without it can never announce and would fail every call.
    Refuse it in the form, where another one can be picked.

    Permissive when the information is missing: a satellite with no
    `supported_features` attribute at all (never seen, a stub) is accepted
    rather than refused on the strength of an absent attribute.
    """
    features = state.attributes.get(ATTR_SUPPORTED_FEATURES)
    if not isinstance(features, int):
        return True
    return bool(features & AssistSatelliteEntityFeature.ANNOUNCE)


def _options_schema() -> vol.Schema:
    """Build the schema shared by the user step and the options flow."""
    return vol.Schema(
        {
            vol.Required(
                CONF_PREANNOUNCE, default=DEFAULT_PREANNOUNCE
            ): selector.BooleanSelector(),
            vol.Optional(CONF_PREANNOUNCE_MEDIA_ID): selector.TextSelector(),
            vol.Required(
                CONF_PREFIX_TITLE, default=DEFAULT_PREFIX_TITLE
            ): selector.BooleanSelector(),
            vol.Required(
                CONF_DENY_DOMAINS,
                default=_deny_domains_to_string(DEFAULT_DENY_DOMAINS),
            ): selector.TextSelector(),
            vol.Optional(CONF_QUIET_START): selector.TimeSelector(),
            vol.Optional(CONF_QUIET_END): selector.TimeSelector(),
            vol.Required(
                CONF_QUIET_BEHAVIOUR, default=DEFAULT_QUIET_BEHAVIOUR
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=QUIET_BEHAVIOURS,
                    translation_key=CONF_QUIET_BEHAVIOUR,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }
    )


def _parse_options(user_input: dict[str, Any]) -> dict[str, Any]:
    """Turn raw form input into the options dict stored on the entry."""
    return {
        CONF_PREANNOUNCE: user_input.get(CONF_PREANNOUNCE, DEFAULT_PREANNOUNCE),
        CONF_PREANNOUNCE_MEDIA_ID: user_input.get(CONF_PREANNOUNCE_MEDIA_ID) or None,
        CONF_PREFIX_TITLE: user_input.get(CONF_PREFIX_TITLE, DEFAULT_PREFIX_TITLE),
        CONF_DENY_DOMAINS: _string_to_deny_domains(
            user_input.get(CONF_DENY_DOMAINS, "")
        ),
        CONF_QUIET_START: user_input.get(CONF_QUIET_START) or None,
        CONF_QUIET_END: user_input.get(CONF_QUIET_END) or None,
        CONF_QUIET_BEHAVIOUR: user_input.get(
            CONF_QUIET_BEHAVIOUR, DEFAULT_QUIET_BEHAVIOUR
        ),
    }


def _suggested_values(options: dict[str, Any]) -> dict[str, Any]:
    """Render stored options back into form values."""
    suggested: dict[str, Any] = {
        CONF_PREANNOUNCE: options.get(CONF_PREANNOUNCE, DEFAULT_PREANNOUNCE),
        CONF_PREFIX_TITLE: options.get(CONF_PREFIX_TITLE, DEFAULT_PREFIX_TITLE),
        CONF_DENY_DOMAINS: _deny_domains_to_string(
            options.get(CONF_DENY_DOMAINS, DEFAULT_DENY_DOMAINS)
        ),
        CONF_QUIET_BEHAVIOUR: options.get(
            CONF_QUIET_BEHAVIOUR, DEFAULT_QUIET_BEHAVIOUR
        ),
    }
    for key in (CONF_PREANNOUNCE_MEDIA_ID, CONF_QUIET_START, CONF_QUIET_END):
        if value := options.get(key):
            suggested[key] = value
    return suggested


class AssistSatelliteNotifierConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Assist Satellite Notifier."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the single setup step: pick the satellite and its settings."""
        errors: dict[str, str] = {}
        if user_input is not None:
            satellite = user_input[CONF_SATELLITE]
            # Known limitation: the unique ID is the satellite's *entity
            # id*, not its entity registry id. Renaming the entity id
            # therefore orphans the entry instead of following the rename.
            # The registry id would fix that, but the picked entity is not
            # guaranteed to be in the registry at all, so the entity id
            # stays the identity; rename the satellite before configuring
            # it, or delete and re-add the entry afterwards.
            await self.async_set_unique_id(satellite)
            self._abort_if_unique_id_configured()

            state = self.hass.states.get(satellite)
            if state is not None and not _supports_announce(state):
                errors[CONF_SATELLITE] = "satellite_cannot_announce"
            else:
                return self.async_create_entry(
                    title=state.name if state is not None else satellite,
                    data={CONF_SATELLITE: satellite},
                    options=_parse_options(user_input),
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_SATELLITE): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=ASSIST_SATELLITE_DOMAIN)
                ),
            }
        ).extend(_options_schema().schema)
        if user_input is not None:
            # Re-showing the form after an error: keep what was typed.
            schema = self.add_suggested_values_to_schema(schema, user_input)

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> AssistSatelliteNotifierOptionsFlow:
        """Return the options flow for this handler."""
        return AssistSatelliteNotifierOptionsFlow()


class AssistSatelliteNotifierOptionsFlow(OptionsFlow):
    """Handle options: everything but the satellite itself."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the announcing settings for this entry's satellite."""
        if user_input is not None:
            return self.async_create_entry(data=_parse_options(user_input))

        schema = self.add_suggested_values_to_schema(
            _options_schema(), _suggested_values(dict(self.config_entry.options))
        )
        return self.async_show_form(step_id="init", data_schema=schema)
