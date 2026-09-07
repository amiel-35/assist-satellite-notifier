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

## `notify.send_message` on an unavailable satellite announces nothing, and does not fail

`homeassistant/helpers/service.py::entity_service_call` drops unavailable
entities from a service call without raising. No error is raised, but it
is not silent either: core then logs a WARNING through
`homeassistant/helpers/target.py::SelectedEntities.log_missing` —
`Referenced entities notify.<name> are missing or not currently
available`. What the caller sees is a success for a message nobody heard.

The legacy `notify.satellite_<name>` service is not entity-based. It
reaches the announcer and raises `satellite_unavailable`, so the failure
lands in the caller's trace. Core `alert:` uses that path (it calls
notifiers by service name), and so should any automation where a silent
success would matter.

The entity is deliberately left `unavailable` rather than kept available
so it could refuse loudly: an entity that misreports its own state to
improve its error messages lies to everything else that reads that state.
The asymmetry is the price, and it is documented rather than papered
over.

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

Renaming an entry onto a name another entry already owns is safe but
surprising: the renamed entry falls back to `_2` (`satellite_kitchen_2`)
rather than taking the name, because the entry that registered
`satellite_kitchen` keeps it. The fallback is stored on the entry and does
not change again on its own.

## A refusal because the satellite is busy still costs a TTS synthesis

Core checks `_is_announcing` **after** resolving the announcement media,
not before: `AssistSatelliteEntity.async_internal_announce`
(`homeassistant/components/assist_satellite/entity.py`) calls
`_resolve_announcement_media_id` and only then raises `SatelliteBusyError`.
So a message refused for a busy satellite has already been synthesised —
billed, on a cloud TTS engine, and latency spent, on any engine. Nothing
this integration can do about it from the outside; it is worth knowing
before wiring an automation that retries on `satellite_busy`.

## `deny_domains` never applies to the notify entity

`NotifyEntityFeature` exposes no `data` payload, so the entity surface has
no way to declare what a message is about. The deny list is only reachable
through the legacy service. See [SECURITY.md](../SECURITY.md): it is an
opt-in safety net, not a security boundary.

## Quiet hours use local time, with no date awareness

The window is compared against the Home Assistant instance's local time of
day. There is no weekday, holiday or calendar awareness, and a DST change
shifts the window with the clock.
