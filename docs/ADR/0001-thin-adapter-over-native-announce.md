# ADR 0001 — A thin adapter over the native `announce`, not a second announcer

- Status: accepted
- Date: 2026-09-07

## Context

Home Assistant has no `notify` service that speaks. Two sibling
integrations in this suite fill that gap for media players — they drive
`tts.speak`, manage the player's volume, wait for the announcement to run
its course, and restore the volume afterwards. That is a lot of machinery,
and most of the bugs live in it: knowing when a player has really finished
speaking, not stranding it at announcement volume, not hanging a caller
for thirty seconds on a player that was already playing music.

Assist satellites are different. `assist_satellite.announce`
(`homeassistant/components/assist_satellite/`) already does all of it,
natively and per-device:

- it synthesises the message with the satellite's **own pipeline voice**,
  so a satellite speaks in the voice its owner configured, not in one this
  integration picked;
- it optionally plays a pre-announcement chime, with a documented default
  and an override;
- it interrupts a running pipeline first, and refuses a second concurrent
  announcement with `SatelliteBusyError`;
- `async_internal_announce` **awaits** `async_announce`, whose contract is
  "Should block until the announcement is done playing";
- volume is the satellite's business, not the caller's.

The gap is therefore not "satellites cannot announce". It is that
`assist_satellite.announce` is an **action**, and a core `alert:` takes a
list of *notifier names*. An alert cannot call an action, so a satellite
cannot be one of the channels an alert escalates through.

## Decision

Build the adapter, and only the adapter. This integration exposes two
notify surfaces per satellite and forwards to
`assist_satellite.announce`. It re-implements nothing that core already
does.

Concretely, it will **not**:

- call `tts.speak` itself, or pick a TTS engine, language or voice;
- touch the satellite's volume;
- poll or time out waiting for the announcement to end;
- queue, retry, or serialise announcements.

It **will** own the policy a `notify` caller needs and core has no opinion
about: which `data` keys are accepted, a deny list on what a message is
about, a quiet-hours window with a `critical` bypass, and translated
refusals.

## Consequences

Good:

- The whole speaking path is core's, maintained by core, and improves when
  core improves. A satellite that gains a better announcement path gains
  it here for free.
- Very little to get wrong: no volume state, no timeouts, no
  "is it finished yet?" heuristics.
- Behaviour matches what a user already sees when they call
  `assist_satellite.announce` by hand. There is no second, divergent way
  to make a satellite speak.

Costs, accepted:

- **Deliveries block for the length of the message.** That is core's
  contract and it is not worked around. Callers that cannot wait should
  not await the call.
- **No queueing.** A busy satellite refuses, and this integration refuses
  in turn rather than holding the message. A message that arrives three
  minutes late is worse than one that fails loudly.
- **No per-call voice or language.** They come from the satellite's
  pipeline. A caller that needs a different voice wants `tts.speak`, not
  this.
- The integration is only as good as the satellite's own announce
  implementation, which varies between ESPHome, Wyoming and VoIP devices.

## Alternatives rejected

**Re-implement announcing on top of `tts.speak` and `media_player`**, the
way the media-player siblings do. Rejected: it would replace a native,
per-device, blocking primitive with a heuristic one; it would ignore the
satellite's configured voice; and it would reintroduce every volume and
timing bug those siblings had to fix — for no capability gained.

**Add the notify surface to core `assist_satellite` itself.** Reasonable
in the long run, and this integration is deliberately shaped so that it
could be replaced by such a core feature without users changing anything
but the entry. It is not a reason to leave the gap open today.

**Wrap the action in a template/script notifier.** No config flow, no
options, no translated refusals, no availability tracking, and every user
re-invents the same YAML.
