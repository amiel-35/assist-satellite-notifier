"""Tests for the announcing policy: data, deny list, quiet hours, refusals."""

from __future__ import annotations

from typing import Any

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError

from custom_components.assist_satellite_notifier.announcer import AnnounceRequest
from custom_components.assist_satellite_notifier.const import (
    CONF_DENY_DOMAINS,
    CONF_PREANNOUNCE,
    CONF_PREANNOUNCE_MEDIA_ID,
    CONF_PREFIX_TITLE,
    CONF_QUIET_BEHAVIOUR,
    CONF_QUIET_END,
    CONF_QUIET_START,
    QUIET_BEHAVIOUR_REFUSE,
    QUIET_BEHAVIOUR_SKIP_PREANNOUNCE,
)
from tests.conftest import SATELLITE, build_entry

NOTIFY_DOMAIN = "notify"
SERVICE = "satellite_living_room"


async def _setup(hass: HomeAssistant, **options: Any) -> None:
    """Set up one entry with the given option overrides."""
    entry = build_entry(**options)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _notify(hass: HomeAssistant, **payload: Any) -> None:
    """Call this entry's legacy notify service."""
    payload.setdefault("message", "the washing machine is done")
    await hass.services.async_call(NOTIFY_DOMAIN, SERVICE, payload, blocking=True)


async def test_a_call_announces_on_the_satellite(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """The message reaches `assist_satellite.announce`, with the chime on."""
    await _setup(hass)

    await _notify(hass, message="dinner is ready")

    assert len(announce_calls) == 1
    assert announce_calls[0].data == {
        "entity_id": SATELLITE,
        "message": "dinner is ready",
        "preannounce": True,
    }


async def test_the_preannounce_option_is_passed_through(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """`preannounce: false` reaches the core action."""
    await _setup(hass, **{CONF_PREANNOUNCE: False})

    await _notify(hass)

    assert announce_calls[0].data["preannounce"] is False
    assert "preannounce_media_id" not in announce_calls[0].data


async def test_a_custom_preannounce_sound_is_passed_through(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """`preannounce_media_id` is only sent when the chime is actually played."""
    await _setup(hass, **{CONF_PREANNOUNCE_MEDIA_ID: "media-source://chime.mp3"})

    await _notify(hass)
    assert announce_calls[0].data["preannounce_media_id"] == (
        "media-source://chime.mp3"
    )

    await _notify(hass, data={"preannounce": False})
    assert announce_calls[1].data["preannounce"] is False
    assert "preannounce_media_id" not in announce_calls[1].data


async def test_a_per_call_preannounce_overrides_the_option(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """`data.preannounce` wins over the entry option, both ways."""
    await _setup(hass, **{CONF_PREANNOUNCE: False})

    await _notify(hass, data={"preannounce": True})

    assert announce_calls[0].data["preannounce"] is True


async def test_a_media_id_replaces_the_spoken_text(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """`data.media_id` plays a file; the required `message` is not spoken."""
    await _setup(hass)

    await _notify(hass, message="ignored", data={"media_id": "media-source://door.mp3"})

    assert announce_calls[0].data["media_id"] == "media-source://door.mp3"
    assert "message" not in announce_calls[0].data


async def test_the_title_is_ignored_by_default(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """A spoken message has no title line, so the title is dropped."""
    await _setup(hass)

    await _notify(hass, message="the door is open", title="Front door")

    assert announce_calls[0].data["message"] == "the door is open"


async def test_prefix_title_speaks_the_title_first(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """With `prefix_title` on, the title is spoken ahead of the message."""
    await _setup(hass, **{CONF_PREFIX_TITLE: True})

    await _notify(hass, message="the door is open", title="Front door")
    assert announce_calls[0].data["message"] == "Front door. the door is open"

    # An empty title adds nothing, not a stray separator.
    await _notify(hass, message="alone", title="  ")
    assert announce_calls[1].data["message"] == "alone"


@pytest.mark.parametrize(
    "source_entity",
    [
        "alarm_control_panel.home",
        "ALARM_CONTROL_PANEL.Home",
        ["binary_sensor.window", "lock.front_door"],
    ],
)
async def test_the_deny_list_refuses_a_call(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    source_entity: str | list[str],
) -> None:
    """A denied `data.source_entity` is refused, in any accepted shape."""
    await _setup(hass)

    with pytest.raises(ServiceValidationError) as err:
        await _notify(hass, data={"source_entity": source_entity})

    assert err.value.translation_key == "source_entity_denied"
    assert not announce_calls


async def test_the_deny_list_lets_everything_else_through(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """A `source_entity` outside the deny list announces normally."""
    await _setup(hass)

    await _notify(hass, data={"source_entity": "binary_sensor.washing_machine"})

    assert len(announce_calls) == 1


async def test_an_emptied_deny_list_denies_nothing(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """The deny list is a setting, not a hard-coded rule."""
    await _setup(hass, **{CONF_DENY_DOMAINS: []})

    await _notify(hass, data={"source_entity": "lock.front_door"})

    assert len(announce_calls) == 1


@pytest.mark.parametrize(
    "data",
    [
        {"unexpected": "value"},
        {"source_entity": 42},
        {"source_entity": ["binary_sensor.window", 42]},
        {"priority": 3},
        {"preannounce": "yes"},
        {"media_id": ["a", "b"]},
    ],
)
async def test_an_invalid_data_payload_is_refused(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    data: dict[str, Any],
) -> None:
    """A malformed `data` payload fails the call instead of being ignored."""
    await _setup(hass)

    with pytest.raises(ServiceValidationError) as err:
        await _notify(hass, data=data)

    assert err.value.translation_key == "invalid_data"
    assert not announce_calls


async def test_quiet_hours_refuse_a_call(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Inside the window, `refuse` raises and nothing is announced."""
    freezer.move_to("2026-09-07 23:30:00")
    await _setup(
        hass,
        **{
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_REFUSE,
        },
    )

    with pytest.raises(ServiceValidationError) as err:
        await _notify(hass)

    assert err.value.translation_key == "quiet_hours"
    assert not announce_calls


async def test_quiet_hours_can_only_drop_the_chime(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """`skip_preannounce` announces without the pre-announcement sound."""
    freezer.move_to("2026-09-07 23:30:00")
    await _setup(
        hass,
        **{
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_SKIP_PREANNOUNCE,
            CONF_PREANNOUNCE_MEDIA_ID: "media-source://chime.mp3",
        },
    )

    await _notify(hass)

    assert announce_calls[0].data["preannounce"] is False
    assert "preannounce_media_id" not in announce_calls[0].data


async def test_outside_quiet_hours_nothing_changes(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A window that wraps midnight still has a daytime outside."""
    freezer.move_to("2026-09-07 12:00:00")
    await _setup(
        hass,
        **{
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_REFUSE,
        },
    )

    await _notify(hass)

    assert announce_calls[0].data["preannounce"] is True


async def test_a_daytime_quiet_window_does_not_wrap(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A window whose end is after its start applies within the day only."""
    freezer.move_to("2026-09-07 14:30:00")
    await _setup(
        hass,
        **{
            CONF_QUIET_START: "13:00:00",
            CONF_QUIET_END: "16:00:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_REFUSE,
        },
    )

    with pytest.raises(ServiceValidationError):
        await _notify(hass)

    freezer.move_to("2026-09-07 16:30:00")
    await _notify(hass)
    assert len(announce_calls) == 1


async def test_an_empty_quiet_window_is_never_quiet(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Identical bounds mean no quiet hours, not all day."""
    freezer.move_to("2026-09-07 22:00:00")
    await _setup(
        hass,
        **{
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_END: "22:00:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_REFUSE,
        },
    )

    await _notify(hass)

    assert len(announce_calls) == 1


async def test_half_a_quiet_window_is_no_window(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A start without an end cannot silence anything."""
    freezer.move_to("2026-09-07 23:30:00")
    await _setup(
        hass,
        **{
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_REFUSE,
        },
    )

    await _notify(hass)

    assert len(announce_calls) == 1


@pytest.mark.parametrize(
    "behaviour", [QUIET_BEHAVIOUR_REFUSE, QUIET_BEHAVIOUR_SKIP_PREANNOUNCE]
)
async def test_a_critical_priority_bypasses_quiet_hours(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    freezer: FrozenDateTimeFactory,
    behaviour: str,
) -> None:
    """`priority: critical` announces, chime included, whatever the setting."""
    freezer.move_to("2026-09-07 23:30:00")
    await _setup(
        hass,
        **{
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_BEHAVIOUR: behaviour,
        },
    )

    await _notify(hass, data={"priority": "critical"})

    assert announce_calls[0].data["preannounce"] is True


async def test_an_unknown_priority_is_carried_without_effect(
    hass: HomeAssistant,
    announce_calls: list[ServiceCall],
    satellite_state: None,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Only `critical` bypasses quiet hours; other values are just accepted."""
    freezer.move_to("2026-09-07 23:30:00")
    await _setup(
        hass,
        **{
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_REFUSE,
        },
    )

    with pytest.raises(ServiceValidationError):
        await _notify(hass, data={"priority": "high"})

    assert not announce_calls


async def test_an_unavailable_satellite_refuses_the_call(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """A satellite that cannot hear the call fails it rather than dropping it."""
    await _setup(hass)
    hass.states.async_set(SATELLITE, "unavailable")

    with pytest.raises(ServiceValidationError) as err:
        await _notify(hass)

    assert err.value.translation_key == "satellite_unavailable"
    assert not announce_calls


async def test_a_missing_satellite_refuses_the_call(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """A satellite whose entity is gone is treated as unavailable."""
    await _setup(hass)
    hass.states.async_remove(SATELLITE)

    with pytest.raises(ServiceValidationError) as err:
        await _notify(hass)

    assert err.value.translation_key == "satellite_unavailable"


async def test_an_unknown_satellite_state_still_announces(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """`unknown` is a satellite that has not spoken yet, not a broken one."""
    await _setup(hass)
    hass.states.async_set(SATELLITE, "unknown")

    await _notify(hass)

    assert len(announce_calls) == 1


async def test_a_non_mapping_data_payload_is_refused(
    hass: HomeAssistant, announce_calls: list[ServiceCall], satellite_state: None
) -> None:
    """The announcer guards its own input, not just the service schema.

    `notify`'s own schema already requires `data` to be a dict, so this
    can only be reached by a caller that builds an `AnnounceRequest`
    directly -- which the notify entity surface does.
    """
    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError) as err:
        await entry.runtime_data.announcer.async_announce(
            AnnounceRequest(message="hello", data="not a mapping")  # type: ignore[arg-type]
        )

    assert err.value.translation_key == "invalid_data"
    assert not announce_calls
