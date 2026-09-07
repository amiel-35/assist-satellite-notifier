# Architecture

## The contract

| Item | Value |
|---|---|
| Domain | `assist_satellite_notifier` |
| Integration type | `helper`, `iot_class: calculated`, `config_flow: true`, `dependencies: ["assist_satellite"]` |
| One config entry | one `assist_satellite` entity; unique ID = that entity ID |
| Legacy service | `notify.satellite_<slugify(entry title)>`, with a deterministic `_<n>` fallback on collision, resolved once and stored on the entry |
| Notify entity | one `NotifyEntity` per entry, same behaviour, no `data` payload |
| Delivery | blocks until the satellite reports the announcement finished |
| Refusals | translated `ServiceValidationError`, raised — never swallowed |

## Modules

```
__init__.py      config entry lifecycle, service naming, the two surfaces
announcer.py     all the policy: data validation, deny list, quiet hours
config_flow.py   user step + options flow
notify.py        the legacy BaseNotificationService and the NotifyEntity
diagnostics.py   what an entry resolved to
```

`announcer.py` holds everything this integration decides. `notify.py`
builds an `AnnounceRequest` from a call and hands it over; both surfaces
share one `SatelliteAnnouncer`, stored on `entry.runtime_data`.

## The core APIs it stands on

Every path below is in `home-assistant/core` 2026.9.1.

- `homeassistant/components/assist_satellite/__init__.py` — registers the
  `announce` action with the schema this integration builds its payload
  for (`message`, `media_id`, `preannounce`, `preannounce_media_id`) and
  the required feature `[AssistSatelliteEntityFeature.ANNOUNCE]`.
- `homeassistant/components/assist_satellite/entity.py` —
  `AssistSatelliteEntity.async_internal_announce`, which resolves the
  media (pipeline TTS when only a message is given), refuses a second
  concurrent announcement, and **awaits `async_announce`**, documented as
  "Should block until the announcement is done playing". That is why a
  delivery here blocks.
- `homeassistant/components/assist_satellite/const.py` —
  `AssistSatelliteEntityFeature.ANNOUNCE`, checked by the config flow.
- `homeassistant/components/assist_satellite/errors.py` —
  `SatelliteBusyError`, translated here into a `satellite_busy` refusal.
- `homeassistant/components/assist_satellite/services.yaml` — the action's
  documented field shapes.
- `homeassistant/components/notify/legacy.py` — `BaseNotificationService`,
  `async_get_service`, and `async_setup_legacy.async_setup_platform`,
  which slugifies the discovery payload's `CONF_NAME` into the final
  service name.
- `homeassistant/components/notify/__init__.py` — `NotifyEntity`.
- `homeassistant/helpers/entity.py` — `Entity._name_internal`, which
  returns `_attr_name` before it looks up a translated name; that is what
  lets the entity carry a `translation_key` for its icon while still
  taking its device's name.
- `homeassistant/components/notify/__init__.py` —
  `NotifyEntity.async_send_message`, which forwards `title` only when the
  entity advertises `NotifyEntityFeature.TITLE`; that is why the entity
  declares it.
- `homeassistant/helpers/service.py` — `entity_service_call`, which drops
  unavailable entities from a call without raising, and
  `homeassistant/helpers/target.py` — `SelectedEntities.log_missing`,
  which then logs a WARNING about them. See "Availability" below.

## What is delegated, and what is owned

Delegated to core, entirely:

- synthesising the message (the satellite's own pipeline voice);
- playing the pre-announcement chime;
- blocking until playback ends;
- refusing a second concurrent announcement;
- volume — the satellite owns it, and nothing here touches it.

Owned here:

- which `data` keys a call may carry, and a refusal for anything else;
- the `deny_domains` net on `data.source_entity`;
- the quiet-hours window, its two behaviours, and the `critical` bypass;
- turning core's `SatelliteBusyError` and an unavailable satellite into
  translated, caller-facing errors;
- the two notify surfaces, their naming, and their lifecycle.

## Order of checks

A call is evaluated in this order, and the first refusal wins:

1. **`data` validation** — unknown keys and wrong types.
2. **Deny list** — every `data.source_entity`, case-folded by domain.
3. **Availability** — the satellite's state.
4. **Quiet hours** — unless `data.priority` is `critical`.

Validation comes first so that a malformed payload is reported as a
malformed payload, and not as whatever the first half-read key happened to
mean.

## Refusals raise

The rule: **a refusal raises a translated `ServiceValidationError`
instead of failing silently.** (It is ADR-015 of the notify suite these
integrations belong to — [`0015-refusals-raise-service-validation-error.md`](https://github.com/amiel-35/notify-switchboard/blob/main/docs/ADR/0015-refusals-raise-service-validation-error.md) —
restated here so this repository is readable on its own.)

Nothing is swallowed. A deny-list refusal, an invalid `data` payload, a
quiet-hours refusal, a busy satellite and an unavailable satellite all
reach the caller as a translated `ServiceValidationError`; anything else
becomes a `HomeAssistantError`. An automation that believes it spoke when
nobody heard anything is worse than a red error in its trace.

Log levels follow how normal the refusal is: a busy satellite and quiet
hours are INFO (expected operation), a deny-list hit and a malformed
payload are WARNING (something is misconfigured).

## Availability

The notify entity follows the satellite: it subscribes to the satellite's
state in `async_added_to_hass` and reports `unavailable` whenever the
satellite is. `unknown` counts as available — a satellite that has not
reported a state since a restart is not a broken one.

There is an asymmetry worth knowing, and it is precise:

- `notify.send_message` on the entity while the satellite is unavailable
  **announces nothing and raises nothing**. Core's `entity_service_call`
  drops unavailable entities from the call
  (`homeassistant/helpers/service.py`), then reports them through
  `SelectedEntities.log_missing` (`homeassistant/helpers/target.py`),
  which logs `Referenced entities … are missing or not currently
  available` at WARNING. So it is not silent — but the caller's trace
  shows a success.
- the legacy `notify.satellite_<name>` service is not entity-based. It
  reaches the announcer, which raises `satellite_unavailable`, and the
  caller's trace shows the failure.

Keeping the entity unavailable is the idiomatic choice, and the reason
the asymmetry exists at all: an entity that misreports itself as
available to make its own errors louder would lie to every other consumer
of its state. Core `alert:` is unaffected either way — it calls notifiers
by service name, and gets the raised refusal.

## Service naming, and why it survives a reload

`notify/legacy.py` slugifies the discovery payload's `CONF_NAME`, so the
name is chosen here, from the entry title. It is resolved **once** and
stored in `entry.data[CONF_SERVICE_NAME]`, and recomputed only when the
title changes to something the stored name no longer derives from. The
collision suffix is chosen against the names the other entries have
stored; entries carrying none yet — every entry upgrading from an earlier
build — resolve in config-entry order, so two of them starting together
cannot claim the same name.

Storing it, rather than deriving it on every load, is what makes two
things true:

- an entry that fell back to `satellite_kitchen_2` keeps that name across
  restarts and reloads, and is never promoted to the unsuffixed name when
  that name becomes free;
- renaming an entry onto a name another entry already owns falls back to
  `_<n>` instead of colliding. That matters because
  `BaseNotificationService.async_register_services` returns early when the
  service exists (`notify/legacy.py`): a colliding entry would end up with
  no service at all, pointing at one that announces on another satellite.

Ownership is tracked, not inferred from the name. The registration records
whether it really created the service (`legacy_service_registered`), an
already-taken name is an ERROR rather than a silence, and unload retracts
only a service this entry created.

## Lifecycle

Home Assistant never retracts a legacy notify service for a config entry:
`notify/legacy.py` only unregisters them from `async_reset_platform`,
which is reached for YAML reloads. So this integration retracts its own,
from an `entry.async_on_unload` callback, and drops its instance from
`notify.legacy`'s registry too.

The legacy platform is discovered from a task tied to the entry
(`entry.async_create_task`), because `ConfigEntry.async_unload` awaits the
entry's own tasks. Even so, the discovery dispatcher runs its listener in a
task core owns, so the discovery can still complete just after an unload:
both `async_get_service` and `async_register_services` check a
`runtime_data.unloaded` flag the unload callback sets synchronously.

An options change **or a title change** fires the entry's update listener,
which reloads the entry. The reload is what makes both take effect on the
legacy service: unloading retracts it, setting up again registers it under
a name recomputed from the current title, against an announcer built from
the current options.
