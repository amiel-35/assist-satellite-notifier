# Architecture

## The contract

| Item | Value |
|---|---|
| Domain | `assist_satellite_notifier` |
| Integration type | `helper`, `iot_class: calculated`, `config_flow: true`, `dependencies: ["assist_satellite"]` |
| One config entry | one `assist_satellite` entity; unique ID = that entity ID |
| Legacy service | `notify.satellite_<slugify(entry title)>`, with a deterministic `_<n>` fallback on collision |
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
- `homeassistant/helpers/service.py` — `entity_service_call`, which
  **skips unavailable entities silently**. See "Availability" below.

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

## Refusals raise — ADR-015 of the suite

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

There is an asymmetry worth knowing: core's `entity_service_call` filters
unavailable entities out of a service call **silently**, so
`notify.send_message` on an unavailable entity is a no-op, not an error.
The legacy `notify.satellite_<name>` service is not entity-based and does
reach the announcer, which raises `satellite_unavailable`. Use the legacy
service when you want the failure to be visible.

## Service naming, and why it survives a reload

`notify/legacy.py` slugifies the discovery payload's `CONF_NAME`, so the
name is chosen here, from the entry title. Collisions are resolved by this
entry's **rank among the entries wanting the same base name**, in
config-entry order — not by "which name is free right now". Two "Kitchen"
entries are therefore `satellite_kitchen` and `satellite_kitchen_2` across
restarts and reloads, in any load order; reloading the second one does not
promote it to the unsuffixed name.

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
