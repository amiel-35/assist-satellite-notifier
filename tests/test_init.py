"""Tests for the Assist Satellite Notifier config entry lifecycle."""

from __future__ import annotations

from homeassistant.core import HomeAssistant, ServiceCall

from custom_components.assist_satellite_notifier import (
    _service_name,
    async_migrate_entry,
)
from custom_components.assist_satellite_notifier.const import (
    CONF_DENY_DOMAINS,
    CONF_PREANNOUNCE,
)
from tests.conftest import SATELLITE, build_entry

NOTIFY_DOMAIN = "notify"


async def test_setup_registers_the_service_and_the_entity(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """Setting up an entry exposes both notify surfaces."""
    entry = build_entry(title="Living room")
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(NOTIFY_DOMAIN, "satellite_living_room")
    assert hass.states.get("notify.living_room") is not None


async def test_service_name_falls_back_deterministically_on_collision(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """Two entries with the same title get `_2`, and keep it."""
    hass.states.async_set("assist_satellite.kitchen", "idle")

    first = build_entry(title="Kitchen")
    first.add_to_hass(hass)
    second = build_entry(title="Kitchen", satellite="assist_satellite.kitchen")
    second.add_to_hass(hass)

    # Setting up the first entry sets the component up, which Home
    # Assistant then applies to every entry of the domain at once.
    assert await hass.config_entries.async_setup(first.entry_id)
    await hass.async_block_till_done()

    assert hass.services.has_service(NOTIFY_DOMAIN, "satellite_kitchen")
    assert hass.services.has_service(NOTIFY_DOMAIN, "satellite_kitchen_2")

    # The suffix follows the entry, not the order in which names were
    # claimed: reloading the first one does not promote the second.
    assert _service_name(hass, first) == "satellite_kitchen"
    assert _service_name(hass, second) == "satellite_kitchen_2"

    await hass.config_entries.async_reload(second.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(NOTIFY_DOMAIN, "satellite_kitchen_2")


async def test_unload_retracts_the_legacy_service(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """Core never retracts a legacy notify service for a config entry."""
    entry = build_entry(title="Living room")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert hass.services.has_service(NOTIFY_DOMAIN, "satellite_living_room")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(NOTIFY_DOMAIN, "satellite_living_room")


async def test_removal_retracts_the_legacy_service(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """Deleting the entry leaves no dangling service behind."""
    entry = build_entry(title="Living room")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()

    assert not hass.services.has_service(NOTIFY_DOMAIN, "satellite_living_room")


async def test_renaming_the_entry_renames_the_service(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """A title change reloads the entry under the new service name."""
    entry = build_entry(title="Living room")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.config_entries.async_update_entry(entry, title="Hallway")
    await hass.async_block_till_done()

    assert not hass.services.has_service(NOTIFY_DOMAIN, "satellite_living_room")
    assert hass.services.has_service(NOTIFY_DOMAIN, "satellite_hallway")


async def test_changing_options_takes_effect_without_a_restart(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """The next call uses the new options, with no restart in between."""
    entry = build_entry(title="Living room")
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        NOTIFY_DOMAIN, "satellite_living_room", {"message": "first"}, blocking=True
    )
    assert announce_calls[-1].data["preannounce"] is True

    hass.config_entries.async_update_entry(
        entry,
        options={**entry.options, CONF_PREANNOUNCE: False, CONF_DENY_DOMAINS: []},
    )
    await hass.async_block_till_done()

    await hass.services.async_call(
        NOTIFY_DOMAIN, "satellite_living_room", {"message": "second"}, blocking=True
    )
    assert announce_calls[-1].data["preannounce"] is False


async def test_the_announcer_targets_the_configured_satellite(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """Runtime data carries the satellite the entry was configured with."""
    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.announcer.config.satellite == SATELLITE
    assert entry.runtime_data.service_name == "satellite_living_room"


async def test_a_titleless_entry_falls_back_to_the_satellite_name(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """An empty title still produces a usable service name."""
    entry = build_entry(title="")
    entry.add_to_hass(hass)

    assert _service_name(hass, entry) == "satellite_assist_satellite_living_room"


async def test_migrate_entry_is_a_no_op(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
) -> None:
    """The entry format has not changed yet, so migration accepts it as is."""
    entry = build_entry()
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry)
