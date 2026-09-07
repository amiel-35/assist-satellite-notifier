"""End-to-end tests against a real `assist_satellite` entity.

Everywhere else the core `assist_satellite.announce` action is mocked, so
those tests prove what this integration sends. This module proves the other
half: that what it sends is accepted by the real action's schema, reaches
the satellite's own `async_announce`, and that the satellite's
`SatelliteBusyError` comes back out as a translated refusal.

Only the media resolution is stubbed
(`AssistSatelliteEntity._resolve_announcement_media_id`), because
synthesising the message would mean a real pipeline and a real TTS engine.
No physical satellite is exercised anywhere -- see docs/known-issues.md.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import Mock, patch

import pytest
from homeassistant.components.assist_satellite import (
    DOMAIN as ASSIST_SATELLITE_DOMAIN,
    AssistSatelliteAnnouncement,
    AssistSatelliteConfiguration,
    AssistSatelliteEntity,
    AssistSatelliteEntityFeature,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    MockModule,
    mock_config_flow,
    mock_integration,
    mock_platform,
    setup_test_component_platform,
)

from custom_components.assist_satellite_notifier.const import (
    CONF_PREANNOUNCE_MEDIA_ID,
)
from tests.conftest import build_entry

SATELLITE_PLATFORM = "test"
SATELLITE = "assist_satellite.living_room"
NOTIFY_DOMAIN = "notify"
SERVICE = "satellite_living_room"


class RecordingSatellite(AssistSatelliteEntity):
    """A satellite that records the announcements it is asked to play."""

    _attr_name = "Living room"
    _attr_unique_id = "recording-satellite"
    _attr_supported_features = AssistSatelliteEntityFeature.ANNOUNCE

    def __init__(self) -> None:
        """Initialize the satellite."""
        self.announcements: list[AssistSatelliteAnnouncement] = []

    async def async_announce(self, announcement: AssistSatelliteAnnouncement) -> None:
        """Record the announcement instead of playing it."""
        self.announcements.append(announcement)

    def on_pipeline_event(self, event: Any) -> None:
        """Nothing here runs a pipeline."""

    def async_get_configuration(self) -> AssistSatelliteConfiguration:
        """Return an empty satellite configuration."""
        return AssistSatelliteConfiguration(
            available_wake_words=[], active_wake_words=[], max_active_wake_words=1
        )

    async def async_set_configuration(
        self, config: AssistSatelliteConfiguration
    ) -> None:
        """Accept a configuration this test never reads back."""


async def _fake_resolve(
    self: AssistSatelliteEntity,
    message: str,
    media_id: str | None,
    preannounce_media_id: str | None = None,
) -> AssistSatelliteAnnouncement:
    """Stand in for the pipeline TTS synthesis the real method performs."""
    resolved = media_id or "http://example.test/tts.mp3"
    return AssistSatelliteAnnouncement(
        message=message,
        media_id=resolved,
        original_media_id=resolved,
        tts_token=None,
        media_id_source="media_id" if media_id else "tts",
        preannounce_media_id=preannounce_media_id,
    )


@pytest.fixture
async def satellite(hass: HomeAssistant) -> RecordingSatellite:
    """Set up a real `assist_satellite` entity through a mock integration."""
    assert await async_setup_component(hass, ASSIST_SATELLITE_DOMAIN, {})

    entity = RecordingSatellite()
    host_entry = MockConfigEntry(domain=SATELLITE_PLATFORM)
    host_entry.add_to_hass(hass)

    async def _setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        await hass.config_entries.async_forward_entry_setups(
            entry, [Platform.ASSIST_SATELLITE]
        )
        return True

    async def _unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
        return await hass.config_entries.async_forward_entry_unload(
            entry, Platform.ASSIST_SATELLITE
        )

    mock_integration(
        hass,
        MockModule(
            SATELLITE_PLATFORM,
            async_setup_entry=_setup_entry,
            async_unload_entry=_unload_entry,
        ),
    )
    setup_test_component_platform(
        hass, ASSIST_SATELLITE_DOMAIN, [entity], from_config_entry=True
    )
    mock_platform(hass, f"{SATELLITE_PLATFORM}.config_flow", Mock())

    with mock_config_flow(SATELLITE_PLATFORM, ConfigFlow):
        assert await hass.config_entries.async_setup(host_entry.entry_id)
        await hass.async_block_till_done()

    assert hass.states.get(SATELLITE) is not None
    return entity


async def _setup_notifier(hass: HomeAssistant, **options: Any) -> None:
    """Set up this integration against the real satellite."""
    entry = build_entry(title="Living room", satellite=SATELLITE, **options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_a_message_reaches_the_real_satellite(
    hass: HomeAssistant, satellite: RecordingSatellite
) -> None:
    """The call passes the core action's schema and lands on the satellite."""
    await _setup_notifier(
        hass, **{CONF_PREANNOUNCE_MEDIA_ID: "http://example.test/chime.mp3"}
    )

    with patch.object(
        AssistSatelliteEntity, "_resolve_announcement_media_id", _fake_resolve
    ):
        await hass.services.async_call(
            NOTIFY_DOMAIN, SERVICE, {"message": "the post has arrived"}, blocking=True
        )

    assert len(satellite.announcements) == 1
    announcement = satellite.announcements[0]
    assert announcement.message == "the post has arrived"
    assert announcement.preannounce_media_id == "http://example.test/chime.mp3"


async def test_the_chime_can_be_dropped_on_a_real_satellite(
    hass: HomeAssistant, satellite: RecordingSatellite
) -> None:
    """`preannounce: false` reaches core, which then plays no chime."""
    await _setup_notifier(
        hass, **{CONF_PREANNOUNCE_MEDIA_ID: "http://example.test/chime.mp3"}
    )

    with patch.object(
        AssistSatelliteEntity, "_resolve_announcement_media_id", _fake_resolve
    ):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            SERVICE,
            {"message": "quietly", "data": {"preannounce": False}},
            blocking=True,
        )

    assert satellite.announcements[0].preannounce_media_id is None


async def test_a_busy_real_satellite_refuses_the_call(
    hass: HomeAssistant, satellite: RecordingSatellite
) -> None:
    """A satellite already announcing raises `SatelliteBusyError` in core."""
    await _setup_notifier(hass)
    # What core sets while an announcement is in flight
    # (`assist_satellite/entity.py::async_internal_announce`).
    satellite._is_announcing = True

    with (
        patch.object(
            AssistSatelliteEntity, "_resolve_announcement_media_id", _fake_resolve
        ),
        pytest.raises(ServiceValidationError) as err,
    ):
        await hass.services.async_call(
            NOTIFY_DOMAIN, SERVICE, {"message": "hello"}, blocking=True
        )

    assert err.value.translation_key == "satellite_busy"
    assert not satellite.announcements
