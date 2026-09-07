# Known issues

## No real satellite has ever been exercised

**This is the most important limitation of the 0.1.0 release.** Everything
below the `assist_satellite.announce` action is untested against real
hardware: no ESPHome voice device, no Wyoming satellite, no VoIP endpoint,
no tablet running a satellite has ever spoken a message sent by this
integration.

What *is* covered by the test suite:

- the payload this integration builds is accepted by the real
  `assist_satellite.announce` schema, and reaches a real
  `AssistSatelliteEntity.async_announce` with the expected message and
  pre-announcement media (`tests/test_satellite.py`);
- a real satellite that is already announcing raises `SatelliteBusyError`,
  and that comes back out as a translated refusal.

What is **not** covered:

- audio actually being heard;
- how long a real satellite takes to report an announcement finished, and
  therefore how long a caller really blocks;
- how a specific satellite implementation behaves when it is asked to play
  a `media_id` it cannot fetch;
- pipeline TTS resolution, which is stubbed in the tests
  (`AssistSatelliteEntity._resolve_announcement_media_id`) because it
  needs a real pipeline and a real TTS engine.

Treat timing and audio behaviour as unverified until someone reports back
from a real installation.

## A refusal under core `alert:` is logged, not traced

Core's `alert` calls its notifiers without waiting for them, so a refusal
raised here does not fail the alert — it appears in the log (twice: once
from this integration, once from the unawaited task). An alert that "did
not speak" is diagnosed from the log, not from the alert's own state.

## `notify.send_message` on an unavailable satellite is a silent no-op

`homeassistant/helpers/service.py::entity_service_call` filters
unavailable entities out of a service call without raising. So calling the
`NotifyEntity` while the satellite is unavailable does nothing at all, and
reports nothing. The legacy `notify.satellite_<name>` service is not
entity-based and does raise `satellite_unavailable`. Use it where a silent
failure would matter.

## A satellite renamed at the entity-ID level orphans its entry

The entry's unique ID is the satellite's entity ID, not its entity
registry ID. Renaming `assist_satellite.living_room` to something else
leaves the entry pointing at an entity that no longer exists — and lets
the new ID be configured again as a second entry. The registry ID would
follow the rename, but the picked entity is not guaranteed to be in the
registry at all. Rename first, configure second; or delete and re-add.

## Renaming the config entry renames the service

`notify.satellite_<name>` follows the entry title. That keeps the name
readable and predictable, at the cost of breaking automations that used
the previous name. There is no alias and no redirect.

## `deny_domains` never applies to the notify entity

`NotifyEntityFeature` exposes no `data` payload, so the entity surface has
no way to declare what a message is about. The deny list is only reachable
through the legacy service. See [SECURITY.md](../SECURITY.md): it is an
opt-in safety net, not a security boundary.

## Quiet hours use local time, with no date awareness

The window is compared against the Home Assistant instance's local time of
day. There is no weekday, holiday or calendar awareness, and a DST change
shifts the window with the clock.
