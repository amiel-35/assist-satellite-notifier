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

import re
from dataclasses import dataclass, field
from itertools import count

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
    CONF_SERVICE_NAME,
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
    # Set by `SatelliteNotificationService.async_register_services` only
    # when it really registered `notify.<service_name>`. It can decline --
    # another entry, or another integration, already owns that name --
    # and unload must then leave that service alone instead of retracting
    # somebody else's.
    legacy_service_registered: bool = field(default=False)
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


def _is_derived_from(service_name: str, base: str) -> bool:
    """Return whether `service_name` is `base` or one of its `_<n>` fallbacks."""
    if service_name == base:
        return True
    return re.fullmatch(rf"{re.escape(base)}_\d+", service_name) is not None


def _owned_name(entry: ConfigEntry) -> str | None:
    """Return the service name an entry still owns, or None.

    A stored name only counts while it still derives from the entry's
    current title. A rename that lands while the entry is not loaded -- a
    disabled entry, one that failed to set up -- leaves behind a name the
    entry will never register again, and holding it in reserve would make
    it unusable for every other entry for as long as that one exists. An
    entry in that state is treated exactly like one that has stored
    nothing: it resolves afresh the next time it loads.
    """
    stored = entry.data.get(CONF_SERVICE_NAME)
    if isinstance(stored, str) and _is_derived_from(stored, _service_slug(entry)):
        return stored
    return None


def _first_free(base: str, taken: set[str]) -> str:
    """Return `base`, or the first `base_<n>` nobody has claimed."""
    if base not in taken:
        return base
    return next(
        candidate for n in count(2) if (candidate := f"{base}_{n}") not in taken
    )


def _resolve_service_name(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """Return the `notify.satellite_<name>` service name this entry owns.

    The name comes from the entry title, which is what the user sees and
    renames: `notify/legacy.py::async_setup_legacy.async_setup_platform`
    slugifies whatever is passed as `CONF_NAME` in the discovery payload
    into the final service name.

    Two satellites can legitimately carry the same name (two "Kitchen" in
    two different Home Assistant areas), and the second one must still get
    a service, so a collision falls back to `_<n>`. That resolution is
    done **once** and persisted in `entry.data[CONF_SERVICE_NAME]`; it is
    redone only when the title changes to something the stored name no
    longer derives from, or when another entry has taken that name in the
    meantime. Resolving it afresh on every load would be wrong
    twice over: an entry that fell back to `_2` would be promoted to the
    unsuffixed name as soon as it happened to load first, and a rename
    onto a name another entry already owns would hand this entry a name
    core refuses to register a second time
    (`BaseNotificationService.async_register_services` returns early when
    the service exists), leaving it silently serviceless.

    Entries carrying no name of their own -- every entry upgrading from
    an earlier build, both entries of a fresh pair, and any entry whose
    stored name its title no longer derives from -- are resolved in
    config-entry order, so two of them starting together cannot claim the
    same name.

    A stored name is honoured only while no other entry owns it. It can
    have been given away in the meantime: a name its entry stopped
    wanting is free for a newcomer to take (`_owned_name`), and renaming
    that entry back to its old title makes the stored name derive from
    the title once more. Honouring it then would have both entries hold
    the same name -- and core's early return would leave whichever
    registers second with no service at all.
    """
    base = _service_slug(entry)
    entries = hass.config_entries.async_entries(DOMAIN)
    taken = {
        name
        for other in entries
        if other.entry_id != entry.entry_id and (name := _owned_name(other)) is not None
    }
    if (stored := _owned_name(entry)) is not None and stored not in taken:
        return stored

    for other in entries:
        if other.entry_id == entry.entry_id:
            break
        # Only an entry sharing this base can reserve a fallback of it,
        # and one that stored nothing has never loaded. Unreachable in
        # practice -- setting an entry up resolves and persists in the
        # same event-loop turn -- but it keeps the answer independent of
        # who asks first.
        if _owned_name(other) is not None or _service_slug(other) != base:
            continue
        taken.add(_first_free(base, taken))
    return _first_free(base, taken)


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
    service_name = _resolve_service_name(hass, entry)
    runtime_data = AssistSatelliteNotifierRuntimeData(
        announcer=announcer, service_name=service_name
    )
    entry.runtime_data = runtime_data

    # Persist the resolved name so it is never recomputed for an unchanged
    # title. This runs before the update listener is added on purpose: a
    # real change here fires the entry's listeners, and reloading the
    # entry that is currently setting up would be a loop. An unchanged
    # value is a no-op -- `ConfigEntries._async_update_entry` returns
    # False without firing anything when nothing differs.
    if entry.data.get(CONF_SERVICE_NAME) != service_name:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_SERVICE_NAME: service_name}
        )

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

        Only a service this entry actually registered is retracted.
        Ownership cannot be inferred from the name: another entry -- or
        another integration entirely -- may hold it, in which case
        `SatelliteNotificationService.async_register_services` declined
        and left `legacy_service_registered` False. Retracting by name
        regardless would delete a live service belonging to someone else.
        """
        runtime_data.unloaded = True
        if runtime_data.legacy_service_registered and hass.services.has_service(
            NOTIFY_DOMAIN, service_name
        ):
            hass.services.async_remove(NOTIFY_DOMAIN, service_name)
        runtime_data.legacy_service_registered = False
        # The instance is dropped from `notify.legacy`'s registry either
        # way: core appends it there after `async_register_services`
        # returns, whether or not that call registered anything
        # (`notify/legacy.py::async_setup_legacy.async_setup_platform`).
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
    #
    # The last argument is the `hass_config` that `async_load_platform`
    # passes on to `notify`'s own setup, and an empty one is enough here:
    # this integration is config-entry only, so there is no YAML section
    # to hand over, and `notify` is a dependency of the platform being
    # loaded, so it is set up already -- the config would only matter if
    # this discovery were what first brought `notify` up.
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

    `CONF_SERVICE_NAME` is not a schema change: an entry that predates it
    is valid, and `async_setup_entry` fills the key in on the next load
    (`_resolve_service_name`). Doing it there rather than here keeps the
    resolution in the one place that can see what the other entries own.
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
