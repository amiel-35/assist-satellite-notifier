"""The announcing logic shared by both notify surfaces.

Everything specific to this integration happens here; `notify.py` only
builds an `AnnounceRequest` and hands it over. The actual speaking is
delegated in full to the core `assist_satellite.announce` action
(`homeassistant/components/assist_satellite/__init__.py`), which
synthesises with the satellite's own pipeline TTS, optionally plays a
pre-announcement sound, and blocks until playback is over
(`entity.py::AssistSatelliteEntity.async_internal_announce` awaits
`async_announce`, documented as "Should block until the announcement is
done playing"). This integration therefore owns no audio, no volume and no
timeout of its own.

What it does own is the policy in front of that action:

* which `data` keys a call may carry, and a refusal for anything else;
* the `deny_domains` safety net on `data.source_entity`;
* the `data.priority` vocabulary -- `info`, `normal`, `high`,
  `critical` -- and the quiet-hours window `critical` bypasses;
* turning a busy or unavailable satellite into a caller-facing,
  translated `ServiceValidationError` instead of a stack trace.

A refusal is raised, never swallowed: it reaches the caller as a
translated `ServiceValidationError` instead of failing silently, because
an automation that believes it spoke when it did not is worse than a red
error in its trace. See docs/ADR/0002-refusals-raise-service-validation-error.md,
which also lists which refusal logs at which level.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import time
from typing import Any

from homeassistant.components.assist_satellite import (
    DOMAIN as ASSIST_SATELLITE_DOMAIN,
    SatelliteBusyError,
)
from homeassistant.const import ATTR_ENTITY_ID, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .const import (
    ALLOWED_DATA_KEYS,
    ATTR_MEDIA_ID,
    ATTR_PREANNOUNCE,
    ATTR_PRIORITY,
    ATTR_SOURCE_ENTITY,
    DOMAIN,
    PRIORITIES,
    PRIORITY_CRITICAL,
    QUIET_BEHAVIOUR_REFUSE,
)

_LOGGER = logging.getLogger(__name__)

SERVICE_ANNOUNCE = "announce"

ATTR_MESSAGE = "message"
ATTR_PREANNOUNCE_MEDIA_ID = "preannounce_media_id"


class AnnouncementRefused(ServiceValidationError):
    """A call was refused by this integration's own policy.

    A translated `ServiceValidationError` so the caller sees the reason in
    its own language, in the automation trace, rather than a silent
    success.
    """


class InvalidAnnouncementData(ServiceValidationError):
    """The `data` payload of a call is not something this integration accepts."""


@dataclass(frozen=True, slots=True)
class AnnouncerConfig:
    """The resolved settings of one config entry."""

    satellite: str
    preannounce: bool
    preannounce_media_id: str | None
    prefix_title: bool
    deny_domains: list[str]
    quiet_start: str | None
    quiet_end: str | None
    quiet_behaviour: str


@dataclass(slots=True)
class AnnounceRequest:
    """One call to one of the two notify surfaces."""

    message: str
    title: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AnnouncePayload:
    """The `data` payload of a call, after validation."""

    source_entities: list[str]
    priority: str | None
    preannounce: bool | None
    media_id: str | None


def _as_entity_list(value: Any) -> list[str] | None:
    """Normalise `data.source_entity` into a list of entity IDs.

    Accepts a single entity ID or a list of them, because both shapes turn
    up in the wild: a template that resolves to one entity, and an
    automation that forwards `trigger.entity_id` from a multi-entity
    trigger.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    return None


def _parse_time(value: str | None) -> time | None:
    """Parse an `HH:MM[:SS]` option, returning None when it is not set."""
    if not value:
        return None
    return dt_util.parse_time(value)


def _is_within(now: time, start: time, end: time) -> bool:
    """Return whether `now` falls in the `[start, end)` window.

    The window wraps around midnight when `end` is earlier than `start`,
    which is the normal case for quiet hours (22:00 to 07:00). A window
    whose bounds are equal is empty, not "all day": that is what an
    accidental double entry of the same time should mean.
    """
    if start == end:
        return False
    if start < end:
        return start <= now < end
    return now >= start or now < end


class SatelliteAnnouncer:
    """Announce messages on one Assist satellite, under this entry's policy."""

    def __init__(self, hass: HomeAssistant, config: AnnouncerConfig) -> None:
        """Initialize the announcer."""
        self.hass = hass
        self.config = config

    @property
    def available(self) -> bool:
        """Return whether the satellite could take an announcement right now.

        `unknown` counts as available: a satellite that has been set up but
        has not reported a state yet is not a broken one, and refusing it
        here would make the first announcement after a restart fail for no
        reason.
        """
        state = self.hass.states.get(self.config.satellite)
        return state is not None and state.state != STATE_UNAVAILABLE

    async def async_announce(self, request: AnnounceRequest) -> None:
        """Speak (or play) one message on the configured satellite."""
        payload = self._validate(request.data)
        self._check_deny_list(payload)
        self._check_available()
        preannounce = self._resolve_preannounce(payload)

        service_data: dict[str, Any] = {ATTR_ENTITY_ID: self.config.satellite}
        if payload.media_id is not None:
            # A media file is played as-is; `message` is a `notify`
            # requirement, not something the satellite needs here.
            service_data[ATTR_MEDIA_ID] = payload.media_id
        else:
            service_data[ATTR_MESSAGE] = self._build_message(request)
        service_data[ATTR_PREANNOUNCE] = preannounce
        if preannounce and self.config.preannounce_media_id:
            service_data[ATTR_PREANNOUNCE_MEDIA_ID] = self.config.preannounce_media_id

        try:
            await self.hass.services.async_call(
                ASSIST_SATELLITE_DOMAIN,
                SERVICE_ANNOUNCE,
                service_data,
                blocking=True,
            )
        except SatelliteBusyError as err:
            # Nothing is queued or retried: the satellite is mid-sentence
            # or mid-conversation, and a message that arrives late is
            # worse than one that is refused loudly. INFO, not WARNING --
            # a busy satellite is normal operation, not a fault.
            _LOGGER.info(
                "Assist Satellite Notifier did not announce on %s: the satellite"
                " is busy",
                self.config.satellite,
            )
            raise AnnouncementRefused(
                translation_domain=DOMAIN,
                translation_key="satellite_busy",
                translation_placeholders={"satellite": self.config.satellite},
            ) from err

    def _build_message(self, request: AnnounceRequest) -> str:
        """Return the text to synthesise.

        `title` is ignored unless the `prefix_title` option is on, in which
        case it is spoken ahead of the message. A spoken message has no
        separate title line to render, so joining the two is the only way a
        title can be heard at all.
        """
        title = (request.title or "").strip()
        if self.config.prefix_title and title:
            return f"{title}. {request.message}"
        return request.message

    def _validate(self, data: Any) -> AnnouncePayload:
        """Validate the `data` payload of a call."""
        payload: dict[str, Any] = data or {}
        if not isinstance(payload, dict):
            raise self._invalid_data("data must be a mapping")

        if unknown := sorted(set(payload) - ALLOWED_DATA_KEYS):
            raise self._invalid_data(
                f"unknown keys {', '.join(unknown)}; accepted keys are "
                f"{', '.join(sorted(ALLOWED_DATA_KEYS))}"
            )

        source_entities: list[str] = []
        if (raw_source := payload.get(ATTR_SOURCE_ENTITY)) is not None:
            if (entities := _as_entity_list(raw_source)) is None:
                raise self._invalid_data(
                    "source_entity must be an entity ID or a list of entity IDs"
                )
            source_entities = entities

        priority = payload.get(ATTR_PRIORITY)
        if priority is not None and not isinstance(priority, str):
            raise self._invalid_data("priority must be a string")
        if priority is not None and priority not in PRIORITIES:
            # Exact and lowercase: `Critical` is a typo for `critical`,
            # not a synonym, and accepting it would leave the caller
            # believing it had armed the quiet-hours bypass.
            raise self._invalid_data(
                f"unknown priority {priority!r}; accepted values are "
                f"{', '.join(sorted(PRIORITIES))}"
            )

        preannounce = payload.get(ATTR_PREANNOUNCE)
        if preannounce is not None and not isinstance(preannounce, bool):
            raise self._invalid_data("preannounce must be a boolean")

        media_id = payload.get(ATTR_MEDIA_ID)
        if media_id is not None and not isinstance(media_id, str):
            raise self._invalid_data("media_id must be a string")

        return AnnouncePayload(
            source_entities=source_entities,
            priority=priority,
            preannounce=preannounce,
            media_id=media_id,
        )

    def _invalid_data(self, error: str) -> InvalidAnnouncementData:
        """Build the translated error for a malformed `data` payload."""
        _LOGGER.warning(
            "Assist Satellite Notifier did not announce on %s: invalid data: %s",
            self.config.satellite,
            error,
        )
        return InvalidAnnouncementData(
            translation_domain=DOMAIN,
            translation_key="invalid_data",
            translation_placeholders={
                "satellite": self.config.satellite,
                "error": error,
            },
        )

    def _check_deny_list(self, payload: AnnouncePayload) -> None:
        """Refuse a call about an entity from a denied domain."""
        for entity_id in payload.source_entities:
            entity_domain = entity_id.split(".", 1)[0].casefold()
            if entity_domain in self.config.deny_domains:
                _LOGGER.warning(
                    "Assist Satellite Notifier did not announce a message about"
                    " %s on %s: the %s domain is in this entry's deny list",
                    entity_id,
                    self.config.satellite,
                    entity_domain,
                )
                raise AnnouncementRefused(
                    translation_domain=DOMAIN,
                    translation_key="source_entity_denied",
                    translation_placeholders={
                        "source_entity": entity_id,
                        "satellite": self.config.satellite,
                        "domain": entity_domain,
                    },
                )

    def _check_available(self) -> None:
        """Refuse a call the satellite could not possibly answer."""
        if self.available:
            return
        raise AnnouncementRefused(
            translation_domain=DOMAIN,
            translation_key="satellite_unavailable",
            translation_placeholders={"satellite": self.config.satellite},
        )

    def _resolve_preannounce(self, payload: AnnouncePayload) -> bool:
        """Decide whether the pre-announcement sound is played.

        Order of precedence: the per-call `data.preannounce` override, then
        the entry option. Quiet hours can only take the sound away
        (`skip_preannounce`) or refuse the call outright (`refuse`), and a
        `critical` priority skips the whole quiet-hours check.
        """
        preannounce = (
            payload.preannounce
            if payload.preannounce is not None
            else self.config.preannounce
        )

        if payload.priority == PRIORITY_CRITICAL:
            return preannounce
        if not self._in_quiet_hours():
            return preannounce

        if self.config.quiet_behaviour == QUIET_BEHAVIOUR_REFUSE:
            _LOGGER.info(
                "Assist Satellite Notifier did not announce on %s: quiet hours",
                self.config.satellite,
            )
            raise AnnouncementRefused(
                translation_domain=DOMAIN,
                translation_key="quiet_hours",
                translation_placeholders={
                    "satellite": self.config.satellite,
                    "quiet_start": self.config.quiet_start or "",
                    "quiet_end": self.config.quiet_end or "",
                },
            )
        return False

    def _in_quiet_hours(self) -> bool:
        """Return whether the current local time is inside the quiet window."""
        start = _parse_time(self.config.quiet_start)
        end = _parse_time(self.config.quiet_end)
        if start is None or end is None:
            return False
        return _is_within(dt_util.now().time(), start, end)
