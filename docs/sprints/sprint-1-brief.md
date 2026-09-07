# Sprint 1 scope — Assist Satellite Notifier 0.1.0

What the first release set out to do, and how it was checked. Kept in the
repository so a reader can tell what was in scope from what was simply not
attempted.

## Why

Home Assistant has no `notify` service that speaks. Assist satellites
(ESPHome voice devices, VoIP, Wyoming, tablets running a satellite)
already have a **native** announcement primitive —
`assist_satellite.announce` — which synthesises with the satellite's own
pipeline TTS, optionally plays a pre-announcement sound, and blocks until
playback ends (`homeassistant/components/assist_satellite/`:
`services.yaml`, `entity.py::async_internal_announce`,
`const.py::AssistSatelliteEntityFeature.ANNOUNCE`).

But it is an *action*, and a core `alert:` takes a list of notifier
*names*. This integration is the thin `notify` adapter on top of that
action, so an alert can list a satellite among its notifiers. It
re-implements no part of the announcing itself.

## Public contract (frozen at release)

| Item | Value |
|---|---|
| Domain | `assist_satellite_notifier` |
| Integration type | `helper`, `iot_class: calculated`, `config_flow: true`, `dependencies: [assist_satellite]` |
| One config entry | one `assist_satellite.*` entity (unique id = that entity id, a documented limitation) |
| Legacy service | `notify.satellite_<slugify(entry title)>` with a deterministic `_<n>` fallback on collision, resolved once and stored on the entry; `message` required, `title` ignored except when `prefix_title` is on (then "title. message") |
| Notify entity | one `NotifyEntity` per entry (`message` + `title`), same behaviour |
| Options | `preannounce` (bool, default true), `preannounce_media_id` (optional media id / URL), `prefix_title` (bool), `deny_domains` (comma list, default `alarm_control_panel, lock`, checked against `data.source_entity` case-insensitively, list or string), `quiet_start` / `quiet_end` / `quiet_behaviour` (`refuse` \| `skip_preannounce`; inside the window `refuse` raises, `skip_preannounce` announces without the pre-sound; `data.priority: "critical"` bypasses) |
| Per-call `data` | `source_entity`, `priority`, `preannounce` (bool override), `media_id` (announce a media file instead of TTS text; `message` still required by `notify`, ignored then) — anything else refused with a translated `ServiceValidationError` |
| Busy satellite | `SatelliteBusyError` from core → translated `ServiceValidationError` (`satellite_busy`), logged at INFO, nothing retried |
| Unavailable satellite | the notify entity is `unavailable`; a call to the legacy service raises `ServiceValidationError` (`satellite_unavailable`) |

Deliveries block until the satellite reports the announcement finished
(that is what `assist_satellite.announce` does); no volume management at
all (the satellite owns it).

## Tests (written first)

Using the core test helpers for a mock satellite
(`tests/components/assist_satellite/conftest.py`, `MockAssistSatellite`):

- the service and the entity exist after setup;
- a call invokes `assist_satellite.announce` with the right `message`,
  `preannounce` and `preannounce_media_id`;
- the `data.media_id` path;
- deny-list refusal (single entity, list, upper case);
- invalid `data` refusal;
- quiet hours in both behaviours, the `critical` bypass, a non-UTC
  instance timezone and a DST transition day;
- busy and unavailable satellites;
- the service is unregistered on entry removal, and renamed on a title
  change, including a rename onto a name another entry owns;
- an options change takes effect without a restart;
- the config flow refuses an entity without the `ANNOUNCE` feature.

Coverage target: ≥ 95 % of `custom_components/assist_satellite_notifier`.

## Definition of done

`ruff`, `mypy --strict`, `hassfest` and the HACS action green in CI; the
test suite green against the pinned toolchain; `docs/known-issues.md`
stating plainly that no real satellite hardware was ever exercised.
