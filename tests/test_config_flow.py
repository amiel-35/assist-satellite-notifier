"""Tests for the Assist Satellite Notifier config and options flows."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import ATTR_SUPPORTED_FEATURES
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.assist_satellite_notifier.const import (
    CONF_DENY_DOMAINS,
    CONF_PREANNOUNCE,
    CONF_PREANNOUNCE_MEDIA_ID,
    CONF_PREFIX_TITLE,
    CONF_QUIET_BEHAVIOUR,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_SATELLITE,
    DOMAIN,
    QUIET_BEHAVIOUR_SKIP_PREANNOUNCE,
)
from tests.conftest import FEATURE_ANNOUNCE, SATELLITE, build_entry

USER_INPUT: dict[str, Any] = {
    CONF_SATELLITE: SATELLITE,
    CONF_PREANNOUNCE: True,
    CONF_PREFIX_TITLE: False,
    CONF_DENY_DOMAINS: "alarm_control_panel, Lock",
    CONF_QUIET_BEHAVIOUR: "refuse",
}


@pytest.fixture(autouse=True)
def skip_setup() -> Generator[None]:
    """Keep the flow tests about the flow, not about loading an entry."""
    with patch(
        "custom_components.assist_satellite_notifier.async_setup_entry",
        return_value=True,
    ):
        yield


async def test_the_user_step_creates_an_entry(
    hass: HomeAssistant, satellite_state: None
) -> None:
    """A satellite that can announce is accepted, options and all."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            **USER_INPUT,
            CONF_PREANNOUNCE_MEDIA_ID: "media-source://chime.mp3",
            CONF_QUIET_START: "22:00:00",
            CONF_QUIET_END: "07:00:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_SKIP_PREANNOUNCE,
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_SATELLITE: SATELLITE}
    assert result["options"] == {
        CONF_PREANNOUNCE: True,
        CONF_PREANNOUNCE_MEDIA_ID: "media-source://chime.mp3",
        CONF_PREFIX_TITLE: False,
        # Case-folded and split on the way in, so `Lock` and `lock` are
        # one rule.
        CONF_DENY_DOMAINS: ["alarm_control_panel", "lock"],
        CONF_QUIET_START: "22:00:00",
        CONF_QUIET_END: "07:00:00",
        CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_SKIP_PREANNOUNCE,
    }


async def test_the_entry_is_titled_after_the_satellite(
    hass: HomeAssistant, hass_storage: dict[str, Any]
) -> None:
    """The entry title comes from the satellite's friendly name."""
    hass.states.async_set(
        SATELLITE,
        "idle",
        {ATTR_SUPPORTED_FEATURES: FEATURE_ANNOUNCE, "friendly_name": "Living room"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["title"] == "Living room"


async def test_a_satellite_without_a_state_is_accepted(
    hass: HomeAssistant,
) -> None:
    """An absent `supported_features` is not proof a satellite cannot speak."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == SATELLITE


async def test_a_satellite_that_cannot_announce_is_refused(
    hass: HomeAssistant,
) -> None:
    """A satellite without ANNOUNCE would fail every call, so it is refused."""
    hass.states.async_set(SATELLITE, "idle", {ATTR_SUPPORTED_FEATURES: 0})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_SATELLITE: "satellite_cannot_announce"}

    # The form comes back with what was typed, and another satellite works.
    hass.states.async_set(
        "assist_satellite.kitchen", "idle", {ATTR_SUPPORTED_FEATURES: FEATURE_ANNOUNCE}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**USER_INPUT, CONF_SATELLITE: "assist_satellite.kitchen"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_the_same_satellite_cannot_be_configured_twice(
    hass: HomeAssistant, satellite_state: None
) -> None:
    """One entry per satellite: the entity ID is the unique ID."""
    build_entry().add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_the_options_flow_updates_the_entry(
    hass: HomeAssistant, satellite_state: None
) -> None:
    """Options are editable after the fact, satellite excluded."""
    entry = build_entry()
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PREANNOUNCE: False,
            CONF_PREFIX_TITLE: True,
            CONF_DENY_DOMAINS: "lock",
            CONF_QUIET_START: "23:00:00",
            CONF_QUIET_END: "06:30:00",
            CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_SKIP_PREANNOUNCE,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_PREANNOUNCE: False,
        CONF_PREANNOUNCE_MEDIA_ID: None,
        CONF_PREFIX_TITLE: True,
        CONF_DENY_DOMAINS: ["lock"],
        CONF_QUIET_START: "23:00:00",
        CONF_QUIET_END: "06:30:00",
        CONF_QUIET_BEHAVIOUR: QUIET_BEHAVIOUR_SKIP_PREANNOUNCE,
    }


async def test_the_options_form_shows_the_current_settings(
    hass: HomeAssistant, satellite_state: None
) -> None:
    """Re-opening the options prefills what the entry currently holds."""
    entry = build_entry(
        **{
            CONF_DENY_DOMAINS: ["lock"],
            CONF_QUIET_START: "23:00:00",
            CONF_PREANNOUNCE_MEDIA_ID: "media-source://chime.mp3",
        }
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)

    suggested = {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if key.description and "suggested_value" in key.description
    }
    assert suggested[CONF_DENY_DOMAINS] == "lock"
    assert suggested[CONF_QUIET_START] == "23:00:00"
    assert suggested[CONF_PREANNOUNCE_MEDIA_ID] == "media-source://chime.mp3"


async def test_a_satellite_with_no_feature_attribute_is_accepted(
    hass: HomeAssistant,
) -> None:
    """A missing `supported_features` is not proof of anything either way."""
    hass.states.async_set(SATELLITE, "idle")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
