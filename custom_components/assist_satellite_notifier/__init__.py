"""The Assist Satellite Notifier integration.

Home Assistant has no `notify` service that speaks. Assist satellites do
have a native announcement primitive -- `assist_satellite.announce` -- but
it is an action of its own, so `alert:`, blueprints and anything that takes
a list of notifiers cannot reach it. This integration is the thin adapter
that closes that gap: one `notify.*` per configured satellite, and nothing
else. See docs/ARCHITECTURE.md for the full contract.

This module wires a config entry to the two notify surfaces defined in
notify.py:

- the legacy `notify.satellite_<name>` service, loaded through the
  discovery helper so `alert.notifiers:` can reference it by name;
- a modern `NotifyEntity`, set up as a regular entity platform.

Both share the same `SatelliteAnnouncer` stored on `entry.runtime_data`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from homeassistant.components.notify.const import DOMAIN as NOTIFY_DOMAIN
from homeassistant.components.notify.legacy import (
    NOTIFY_SERVICES,
    BaseNotificationService,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import discovery
from homeassistant.util import slugify

from .announcer import AnnouncerConfig, SatelliteAnnouncer
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
)

PLATFORMS: list[Platform] = [Platform.NOTIFY]

SERVICE_NAME_PREFIX = "satellite"


@dataclass(slots=True)
class AssistSatelliteNotifierRuntimeData:
    """Runtime data stored on the config entry."""

    announcer: SatelliteAnnouncer
    service_name: str
    # Set by notify.py's `async_get_service` once the legacy service has
    # actually been created, so unload knows which instance to retract.
    legacy_service: BaseNotificationService | None = field(default=None)
    # Set by the unload callback. The legacy platform is registered from a
    # dispatcher callback Home Assistant runs in a task of its own
    # (`helpers/discovery.py` -> `async_dispatcher_send_internal`), which
    # nothing here owns: it can still be in flight when the entry unloads,
    # and would then put back a service that was just retracted. See
    # `async_get_service`.
    unloaded: bool = field(default=False)


type AssistSatelliteNotifierConfigEntry = ConfigEntry[
    AssistSatelliteNotifierRuntimeData
]


def _service_slug(entry: ConfigEntry) -> str:
    """Return the base service name an entry would like to own."""
    slug = slugify(entry.title) or slugify(str(entry.data.get(CONF_SATELLITE, "")))
    return f"{SERVICE_NAME_PREFIX}_{slug}"


def _service_name(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Derive `notify.satellite_<name>` for an entry, resolving collisions.

    The name comes from the entry title, which is what the user sees and
    renames, so `notify/legacy.py::async_setup_legacy.async_setup_platform`
    slugifies whatever is passed as `CONF_NAME` in the discovery payload
    into the final service name.

    Two satellites can legitimately carry the same name (two "Kitchen" in
    two different Home Assistant areas), and the second one must still get
    a service. The suffix is derived from this entry's rank among the
    entries that want the same base name, in config-entry order -- not from
    "which name happens to be free right now" -- so an entry keeps the same
    service across restarts whatever order the entries load in, and a
    reload does not silently promote `_2` to the unsuffixed name.
    """
    base = _service_slug(entry)
    siblings = [
        other
        for other in hass.config_entries.async_entries(DOMAIN)
        if _service_slug(other) == base
    ]
    index = next(
        (
            position
            for position, other in enumerate(siblings)
            if other.entry_id == entry.entry_id
        ),
        0,
    )
    return base if index == 0 else f"{base}_{index + 1}"


def _build_announcer_config(
    entry: AssistSatelliteNotifierConfigEntry,
) -> AnnouncerConfig:
    """Build the announcer config from a config entry's data and options."""
    options = entry.options
    return AnnouncerConfig(
        satellite=entry.data[CONF_SATELLITE],
        preannounce=options.get(CONF_PREANNOUNCE, DEFAULT_PREANNOUNCE),
        preannounce_media_id=options.get(CONF_PREANNOUNCE_MEDIA_ID) or None,
        prefix_title=options.get(CONF_PREFIX_TITLE, DEFAULT_PREFIX_TITLE),
        deny_domains=[
            domain.casefold()
            for domain in options.get(CONF_DENY_DOMAINS, DEFAULT_DENY_DOMAINS)
        ],
        quiet_start=options.get(CONF_QUIET_START) or None,
        quiet_end=options.get(CONF_QUIET_END) or None,
        quiet_behaviour=options.get(CONF_QUIET_BEHAVIOUR, DEFAULT_QUIET_BEHAVIOUR),
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: AssistSatelliteNotifierConfigEntry
) -> bool:
    """Set up Assist Satellite Notifier from a config entry."""
    announcer = SatelliteAnnouncer(hass, _build_announcer_config(entry))
    service_name = _service_name(hass, entry)
    runtime_data = AssistSatelliteNotifierRuntimeData(
        announcer=announcer, service_name=service_name
    )
    entry.runtime_data = runtime_data

    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))

    @callback
    def _async_retract_legacy_service() -> None:
        """Remove the legacy `notify.satellite_<name>` service on unload.

        Home Assistant never does this for us: `notify/legacy.py` only
        unregisters legacy services from `async_reset_platform`, which is
        reached from `homeassistant/helpers/reload.py` for YAML reloads --
        never from a config entry unload. Without this, deleting an entry
        leaves a dangling `notify.satellite_<name>` bound to a dead
        announcer, and re-adding or renaming it is a no-op because
        `BaseNotificationService.async_register_services` returns early
        when the service already exists.

        Removal is by name rather than through the service object's own
        `async_unregister_services()`: that method is a coroutine, and an
        `entry.async_on_unload` callback is synchronous, so calling it
        would fire a task nothing waits for -- the entry could be set up
        again before the old service is gone.
        """
        runtime_data.unloaded = True
        if hass.services.has_service(NOTIFY_DOMAIN, service_name):
            hass.services.async_remove(NOTIFY_DOMAIN, service_name)
        services = hass.data.get(NOTIFY_SERVICES, {}).get(DOMAIN)
        instance = runtime_data.legacy_service
        if services is not None and instance is not None and instance in services:
            services.remove(instance)
            if not services:
                del hass.data[NOTIFY_SERVICES][DOMAIN]
        runtime_data.legacy_service = None

    entry.async_on_unload(_async_retract_legacy_service)

    # Legacy `notify.satellite_<name>` service, discovered the way
    # `mobile_app` discovers its own per-device services. Tied to the entry
    # rather than to `hass`: `ConfigEntry.async_unload` awaits the entry's
    # own tasks (`_async_process_on_unload` in `config_entries.py`), so the
    # discovery cannot still be running against an entry that no longer
    # exists.
    entry.async_create_task(
        hass,
        discovery.async_load_platform(
            hass,
            Platform.NOTIFY,
            DOMAIN,
            {CONF_NAME: service_name, "entry_id": entry.entry_id},
            {},
        ),
        name="assist_satellite_notifier legacy notify discovery",
        eager_start=True,
    )

    # Modern `NotifyEntity`.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: AssistSatelliteNotifierConfigEntry
) -> bool:
    """Unload a config entry.

    The legacy service is retracted by the `entry.async_on_unload` callback
    registered in `async_setup_entry`, which Home Assistant runs once this
    returns `True`.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(
    hass: HomeAssistant, entry: AssistSatelliteNotifierConfigEntry
) -> bool:
    """Migrate an old config entry.

    Nothing to do yet: the entry format has not changed since the first
    release (`VERSION` 1, `MINOR_VERSION` 1). This exists so the first
    schema change ships as a migration instead of as a broken entry.
    """
    return True


async def _async_entry_updated(
    hass: HomeAssistant, entry: AssistSatelliteNotifierConfigEntry
) -> None:
    """Reload the entry when its options or its title change.

    The reload is what makes both take effect on the legacy service:
    unloading retracts `notify.satellite_<name>`, so setting up again
    registers it afresh, under a name recomputed from the current title and
    against an announcer built from the current options.
    """
    await hass.config_entries.async_reload(entry.entry_id)
