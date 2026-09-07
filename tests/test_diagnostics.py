"""Tests for the Assist Satellite Notifier diagnostics."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.assist_satellite_notifier.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.conftest import SATELLITE, build_entry


async def test_diagnostics_report_the_resolved_settings(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """A loaded entry reports its options and what they resolved to."""
    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["loaded"] is True
    assert diagnostics["service_name"] == "satellite_living_room"
    assert diagnostics["satellite_available"] is True
    assert diagnostics["announcer_config"]["satellite"] == SATELLITE
    assert diagnostics["announcer_config"]["deny_domains"] == [
        "alarm_control_panel",
        "lock",
    ]


async def test_diagnostics_survive_an_entry_that_is_not_loaded(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """Diagnostics can be downloaded for an entry that never set up."""
    entry = build_entry()
    entry.add_to_hass(hass)

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["loaded"] is False
    assert diagnostics["announcer_config"] is None
    assert diagnostics["service_name"] is None
    assert diagnostics["satellite_available"] is None
    assert diagnostics["data"] == {"satellite": SATELLITE}
