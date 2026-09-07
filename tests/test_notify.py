"""Tests for the two notify surfaces: the legacy service and the entity."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.components.assist_satellite import (
    DOMAIN as ASSIST_SATELLITE_DOMAIN,
    SatelliteBusyError,
)
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.assist_satellite_notifier.notify import (
    SatelliteNotificationService,
    async_get_service,
)
from tests.conftest import SATELLITE, build_entry

NOTIFY_DOMAIN = "notify"
SERVICE = "satellite_living_room"
NOTIFY_ENTITY = "notify.living_room"


async def _setup(hass: HomeAssistant, **options: Any) -> Any:
    """Set up one entry and return it."""
    entry = build_entry(**options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _replace_announce(hass: HomeAssistant, error: Exception) -> None:
    """Make `assist_satellite.announce` fail with `error`."""

    async def _fail(call: ServiceCall) -> None:
        raise error

    hass.services.async_remove(ASSIST_SATELLITE_DOMAIN, "announce")
    hass.services.async_register(ASSIST_SATELLITE_DOMAIN, "announce", _fail)


async def test_the_notify_entity_announces(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """`notify.send_message` reaches the same announcer as the service."""
    await _setup(hass)

    await hass.services.async_call(
        NOTIFY_DOMAIN,
        "send_message",
        {"entity_id": NOTIFY_ENTITY, "message": "the tumble dryer is done"},
        blocking=True,
    )

    assert len(announce_calls) == 1
    assert announce_calls[0].data["message"] == "the tumble dryer is done"


async def test_the_notify_entity_can_prefix_its_title(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """The entity surface passes its `title` through the same rule."""
    await _setup(hass, prefix_title=True)

    await hass.services.async_call(
        NOTIFY_DOMAIN,
        "send_message",
        {"entity_id": NOTIFY_ENTITY, "message": "is open", "title": "The gate"},
        blocking=True,
    )

    assert announce_calls[0].data["message"] == "The gate. is open"


async def test_the_notify_entity_follows_the_satellite(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """An entity whose satellite is unavailable is unavailable too."""
    await _setup(hass)
    assert hass.states.get(NOTIFY_ENTITY).state != STATE_UNAVAILABLE

    hass.states.async_set(SATELLITE, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert hass.states.get(NOTIFY_ENTITY).state == STATE_UNAVAILABLE

    hass.states.async_set(SATELLITE, "idle")
    await hass.async_block_till_done()
    assert hass.states.get(NOTIFY_ENTITY).state != STATE_UNAVAILABLE


async def test_a_busy_satellite_refuses_the_call(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """`SatelliteBusyError` becomes a translated refusal, and nothing retries."""
    await _setup(hass)
    _replace_announce(hass, SatelliteBusyError())

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            NOTIFY_DOMAIN, SERVICE, {"message": "hello"}, blocking=True
        )

    assert err.value.translation_key == "satellite_busy"


async def test_an_unexpected_failure_reaches_the_caller(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """Anything the core action raises is reported, never swallowed."""
    await _setup(hass)
    _replace_announce(hass, ValueError("boom"))

    with pytest.raises(HomeAssistantError, match="could not announce"):
        await hass.services.async_call(
            NOTIFY_DOMAIN, SERVICE, {"message": "hello"}, blocking=True
        )


async def test_a_core_error_is_passed_through_untouched(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """A `HomeAssistantError` from core is already caller-facing."""
    await _setup(hass)
    _replace_announce(hass, HomeAssistantError("TTS engine not found"))

    with pytest.raises(HomeAssistantError, match="TTS engine not found"):
        await hass.services.async_call(
            NOTIFY_DOMAIN, SERVICE, {"message": "hello"}, blocking=True
        )


async def test_the_platform_refuses_a_yaml_setup(
    hass: HomeAssistant, announce_calls: list[ServiceCall]
) -> None:
    """Without a discovery payload there is no entry to announce for."""
    assert await async_get_service(hass, {}, None) is None
    assert await async_get_service(hass, {}, {}) is None


async def test_the_platform_refuses_an_unknown_entry(
    hass: HomeAssistant, announce_calls: list[ServiceCall]
) -> None:
    """A discovery payload naming an entry that is gone creates nothing."""
    assert await async_get_service(hass, {}, {"entry_id": "does-not-exist"}) is None


async def test_the_platform_refuses_an_unloaded_entry(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """A discovery still in flight when the entry unloads registers nothing.

    The discovery runs in a task core owns, so it can complete after the
    unload callback has already looked for a service that did not exist
    yet; registering then would leave a service nothing can retract.
    """
    entry = await _setup(hass)
    runtime_data = entry.runtime_data
    runtime_data.unloaded = True

    assert await async_get_service(hass, {}, {"entry_id": entry.entry_id}) is None

    # The same guard on the other side of the race: an instance that was
    # already handed out does not register its service either.
    service = SatelliteNotificationService(hass, runtime_data)
    await service.async_setup(hass, "satellite_late", "satellite_late")
    await service.async_register_services()
    assert not hass.services.has_service(NOTIFY_DOMAIN, "satellite_late")


async def test_the_platform_refuses_an_entry_without_runtime_data(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """An entry that never finished setting up has no announcer to use."""
    entry = build_entry()
    entry.add_to_hass(hass)

    assert await async_get_service(hass, {}, {"entry_id": entry.entry_id}) is None
