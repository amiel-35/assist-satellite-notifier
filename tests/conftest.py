"""Fixtures shared by the Assist Satellite Notifier test suite."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

import pytest
from homeassistant.components.assist_satellite import DOMAIN as ASSIST_SATELLITE_DOMAIN
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.assist_satellite_notifier.const import (
    CONF_DENY_DOMAINS,
    CONF_PREANNOUNCE,
    CONF_PREANNOUNCE_MEDIA_ID,
    CONF_PREFIX_TITLE,
    CONF_QUIET_BEHAVIOUR,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_SATELLITE,
    DEFAULT_QUIET_BEHAVIOUR,
    DOMAIN,
)

pytest_plugins = "pytest_homeassistant_custom_component"

SATELLITE = "assist_satellite.living_room"
# `AssistSatelliteEntityFeature.ANNOUNCE`, the feature the core `announce`
# action requires of its target.
FEATURE_ANNOUNCE = 1


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> Generator[None]:
    """Make custom_components discoverable in every test."""
    yield


@pytest.fixture(autouse=True)
async def base_components(hass: HomeAssistant) -> None:
    """Set up what the `assist_satellite` dependency chain needs.

    `conversation`, two levels down that chain, reads
    `homeassistant.exposed_entities` while it starts, so the
    `homeassistant` component has to be up first or every setup in the
    suite fails on an unrelated `KeyError`.

    The timezone is pinned to UTC here too: the harness otherwise runs in
    US/Pacific, and the quiet-hours tests freeze time in UTC.
    """
    await hass.config.async_set_time_zone("UTC")
    assert await async_setup_component(hass, "homeassistant", {})


def build_entry(
    *, title: str = "Living room", satellite: str = SATELLITE, **options: Any
) -> MockConfigEntry:
    """Build a config entry with this integration's default options."""
    entry_options: dict[str, Any] = {
        CONF_PREANNOUNCE: True,
        CONF_PREANNOUNCE_MEDIA_ID: None,
        CONF_PREFIX_TITLE: False,
        CONF_DENY_DOMAINS: ["alarm_control_panel", "lock"],
        CONF_QUIET_START: None,
        CONF_QUIET_END: None,
        CONF_QUIET_BEHAVIOUR: DEFAULT_QUIET_BEHAVIOUR,
    }
    entry_options.update(options)
    return MockConfigEntry(
        domain=DOMAIN,
        title=title,
        unique_id=satellite,
        data={CONF_SATELLITE: satellite},
        options=entry_options,
    )


@pytest.fixture
async def announce_calls(hass: HomeAssistant) -> list[ServiceCall]:
    """Set up `assist_satellite` and capture calls to its `announce` action.

    The component is set up first, then its `announce` action is replaced:
    this integration declares `assist_satellite` as a dependency, so
    setting up a config entry would otherwise register the real action on
    top of the mock.
    """
    assert await async_setup_component(hass, ASSIST_SATELLITE_DOMAIN, {})
    return async_mock_service(hass, ASSIST_SATELLITE_DOMAIN, "announce")


@pytest.fixture
def satellite_state(hass: HomeAssistant) -> None:
    """Publish an idle satellite that advertises `ANNOUNCE`."""
    hass.states.async_set(
        SATELLITE, "idle", {ATTR_SUPPORTED_FEATURES: FEATURE_ANNOUNCE}
    )
