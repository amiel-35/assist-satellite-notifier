"""Notify platform for Assist Satellite Notifier.

Exposes the same `SatelliteAnnouncer` on the two surfaces `alert.notifiers:`
and modern automations expect:

- `async_get_service` registers the legacy `notify.satellite_<name>`
  service (see __init__.py, which discovers this platform with the service
  name already resolved);
- `async_setup_entry` registers a `NotifyEntity` for the same config entry.

Both build an `AnnounceRequest` and hand it to the shared announcer.
Nothing is swallowed: refusals raise a translated
`ServiceValidationError` instead of failing silently. A deny-list
refusal, a malformed `data` payload, quiet hours, a busy satellite and an
unavailable satellite all reach the caller that way; anything else
reaches it as a `HomeAssistantError`. (This is ADR-015 of the notify
suite these integrations belong to:
https://github.com/amiel-35/notify-switchboard/blob/main/docs/ADR/0015-refusals-raise-service-validation-error.md)
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.components.notify.const import (
    ATTR_DATA,
    ATTR_TITLE,
    DOMAIN as NOTIFY_DOMAIN,
)
from homeassistant.components.notify.legacy import BaseNotificationService
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import AssistSatelliteNotifierConfigEntry, AssistSatelliteNotifierRuntimeData
from .announcer import AnnounceRequest, SatelliteAnnouncer
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _async_announce(
    announcer: SatelliteAnnouncer, request: AnnounceRequest
) -> None:
    """Announce a request, raising anything that stopped it from being heard.

    Every failure is raised to the caller. Swallowing a refusal would
    answer an automation with a silent success for a message nobody ever
    heard.
    """
    try:
        await announcer.async_announce(request)
    except HomeAssistantError:
        # Already a clear, caller-facing error: one of this integration's
        # translated `ServiceValidationError`s, or a failure raised by
        # `assist_satellite.announce` itself. Let it through untouched.
        raise
    except Exception as err:
        raise HomeAssistantError(
            "Assist Satellite Notifier could not announce on "
            f"{announcer.config.satellite}: {err}"
        ) from err


async def async_get_service(
    hass: HomeAssistant,
    config: ConfigType,
    discovery_info: DiscoveryInfoType | None = None,
) -> BaseNotificationService | None:
    """Set up the legacy `notify.satellite_<name>` service.

    `discovery_info` is populated by __init__.py's `async_setup_entry` with
    the `entry_id` of the config entry it was discovered for.
    """
    if discovery_info is None or "entry_id" not in discovery_info:
        _LOGGER.error("Assist Satellite Notifier can only be set up through the UI")
        return None

    entry = hass.config_entries.async_get_entry(discovery_info["entry_id"])
    if entry is None or not hasattr(entry, "runtime_data"):
        _LOGGER.error("Assist Satellite Notifier config entry is not loaded")
        return None

    runtime_data: AssistSatelliteNotifierRuntimeData = entry.runtime_data
    if runtime_data.unloaded:
        # The entry unloaded while this discovery was still in flight.
        # Registering now would put back the service the unload callback
        # just retracted, bound to a dead announcer.
        _LOGGER.debug(
            "Assist Satellite Notifier entry unloaded before discovery completed"
        )
        return None

    service = SatelliteNotificationService(hass, runtime_data)
    # Remembered so unloading the entry can drop this instance from
    # `notify.legacy`'s registry along with the service itself; core never
    # does that for a config entry (see __init__.py).
    runtime_data.legacy_service = service
    return service


class SatelliteNotificationService(BaseNotificationService):
    """Legacy notify service that announces through the shared announcer."""

    def __init__(
        self, hass: HomeAssistant, runtime_data: AssistSatelliteNotifierRuntimeData
    ) -> None:
        """Initialize the service."""
        self.hass = hass
        self._runtime_data = runtime_data
        self._announcer = runtime_data.announcer

    async def async_register_services(self) -> None:
        """Register the service, unless it cannot or must not be created.

        Two things can stop it.

        The entry may have unloaded already: this platform is set up from
        a task Home Assistant owns -- the discovery dispatcher runs its
        listener as a task of its own
        (`helpers/dispatcher.py::async_dispatcher_send_internal`) -- so an
        entry can unload between `async_get_service` returning this
        instance and this method being reached. The unload callback in
        __init__.py has then already looked for a service that did not
        exist yet, and registering now would leave a
        `notify.satellite_<name>` bound to a dead announcer with nothing
        left to retract it.

        Or the name may be somebody else's. `super()` returns early and
        silently when `notify.<name>` already exists
        (`notify/legacy.py`, `BaseNotificationService`), which would leave
        this entry looking set up while owning no service and pointing at
        one that announces on another satellite. Service names are
        resolved and persisted per entry (see `_resolve_service_name` in
        __init__.py) so this should not be reachable from this
        integration alone; it still is when another integration has taken
        the name, and it is an error worth seeing rather than a silence.

        `legacy_service_registered` records the answer, because unload
        must retract only a service this instance really created.

        Either way, core appends this instance to
        `hass.data[NOTIFY_SERVICES]` once this returns -- it does that
        after the call, not inside it -- so a declined registration still
        leaves a registry entry behind. That is harmless: the unload
        callback in __init__.py drops the instance from that list
        unconditionally, and only the service removal is gated.
        """
        if self._runtime_data.unloaded:
            _LOGGER.debug(
                "Assist Satellite Notifier entry unloaded before its service registered"
            )
            return
        if self.hass.services.has_service(NOTIFY_DOMAIN, self._service_name):
            _LOGGER.error(
                "Assist Satellite Notifier did not create notify.%s: that service"
                " is already registered by something else; this entry has no"
                " legacy notify service. Rename the entry to free a name of its"
                " own",
                self._service_name,
            )
            return
        await super().async_register_services()
        self._runtime_data.legacy_service_registered = True

    async def async_send_message(self, message: str, **kwargs: Any) -> None:
        """Announce `message` on the configured satellite.

        `target` is ignored: an entry always announces on its one
        satellite. `title` is ignored too, unless the `prefix_title` option
        is on.
        """
        request = AnnounceRequest(
            message=message,
            title=kwargs.get(ATTR_TITLE),
            data=dict(kwargs.get(ATTR_DATA) or {}),
        )
        await _async_announce(self._announcer, request)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AssistSatelliteNotifierConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Assist Satellite Notifier entity for a config entry."""
    async_add_entities([SatelliteNotifyEntity(entry)])


class SatelliteNotifyEntity(NotifyEntity):
    """Modern notify entity that announces through the shared announcer.

    One service device per config entry, named after the entry (i.e. after
    the satellite it announces on), and `_attr_name = None` so the entity
    takes that device's name. Without this, every entry would produce the
    same friendly name and collide on entity id.

    `_attr_translation_key` exists only to hang an icon off in icons.json:
    `strings.json` deliberately declares no name for it, so `_attr_name`
    still wins (`homeassistant/helpers/entity.py::Entity._name_internal`
    returns `_attr_name` before it ever looks a translated name up).

    `NotifyEntityFeature.TITLE` is declared because `title` is consumed
    here (the `prefix_title` option speaks it ahead of the message). Core
    gates the field on that flag --
    `homeassistant/components/notify/__init__.py::NotifyEntity.async_send_message`
    only forwards `title` when the feature is set -- and the UI hides the
    field for an entity that does not advertise it.
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_translation_key = "satellite"
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, entry: AssistSatelliteNotifierConfigEntry) -> None:
        """Initialize the entity."""
        self._attr_unique_id = f"{entry.entry_id}_notify_entity"
        self._announcer: SatelliteAnnouncer = entry.runtime_data.announcer
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Assist Satellite Notifier",
            name=entry.title or self._announcer.config.satellite,
        )

    @property
    def available(self) -> bool:
        """Follow the satellite: an entity that cannot speak is unavailable."""
        return self._announcer.available

    async def async_added_to_hass(self) -> None:
        """Track the satellite so this entity's availability follows it."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._announcer.config.satellite],
                self._async_satellite_changed,
            )
        )

    @callback
    def _async_satellite_changed(self, event: Any) -> None:
        """Re-publish this entity's state when the satellite's changes."""
        del event
        self.async_write_ha_state()

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Announce `message` on the configured satellite.

        Overrides the base class rather than `send_message` so no executor
        job is scheduled: announcing is pure async I/O against Home
        Assistant's own service bus.

        There is no `data` payload on this surface (`NotifyEntityFeature`
        exposes none), so `deny_domains` can only be enforced through the
        legacy service; automations that need it should call
        `notify.satellite_<name>` with `data.source_entity` instead.
        """
        await _async_announce(
            self._announcer, AnnounceRequest(message=message, title=title)
        )
