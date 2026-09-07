# ADR 0002 — A refusal raises, it never fails silently

- Status: accepted
- Date: 2026-09-07

## Context

This integration refuses calls, on purpose and often: a `data` payload it
does not recognise, a `source_entity` in a denied domain, a call inside
quiet hours, a satellite that is mid-sentence, a satellite that is
offline. Each of those is a decision *not* to speak.

There are two ways to report such a decision, and only two:

- return normally and log a line — the caller's automation goes green,
  its trace shows a successful `notify` step, and nobody hears anything;
- raise — the caller's automation goes red, the trace shows the reason,
  and the next step of that automation does not run.

The first is tempting because refusing is *normal* here. A busy
satellite is not a fault. Quiet hours working is quiet hours working.
Raising on a non-fault feels like crying wolf.

It is still wrong, and the reason is the kind of message this
integration carries. An announcement is the channel of last resort: an
`alert:` escalating a water leak, a door left open, a smoke alarm. The
whole value of putting a satellite in `alert.notifiers:` is that
somebody in the room hears it. An automation that believes it spoke, and
did not, has failed in the one way that matters and reports success.

The trace is also the only place a user ever looks. There is no delivery
receipt for a spoken message; a log line in `home-assistant.log` is not
somewhere anybody goes to find out why the house stayed quiet last
night.

## Decision

**Every refusal raises a translated `ServiceValidationError`.** Nothing
is swallowed, nothing is downgraded to a log line alone.

Concretely:

| Refusal | Exception | `translation_key` |
|---|---|---|
| Unknown `data` key, wrong type, priority outside the vocabulary | `InvalidAnnouncementData` | `invalid_data` |
| `data.source_entity` in a denied domain | `AnnouncementRefused` | `source_entity_denied` |
| Inside quiet hours, behaviour `refuse` | `AnnouncementRefused` | `quiet_hours` |
| Core raised `SatelliteBusyError` | `AnnouncementRefused` | `satellite_busy` |
| Satellite `unavailable` | `AnnouncementRefused` | `satellite_unavailable` |

Both exception classes subclass `ServiceValidationError`, and every one
carries `translation_domain`, `translation_key` and placeholders, so the
reason reaches the user in their own language rather than as an English
string baked into a stack trace. Anything this integration did not
anticipate keeps reaching the caller as a `HomeAssistantError`, which is
core's own contract for an action that failed.

A refusal is also logged, at a level that says how normal it is:

- **INFO** — a busy satellite, and quiet hours. Expected operation; a
  house with quiet hours configured will produce these nightly.
- **WARNING** — a deny-list hit, and a malformed `data` payload.
  Something is misconfigured and a human should look.

The log level is about *the logbook*; it says nothing about whether the
call raised. Every row above raises, INFO ones included.

## Consequences

Good:

- A caller cannot believe it spoke when it did not. The automation trace
  carries the reason, in the user's language, at the step that refused.
- The reason is available where people debug: the trace, not a log file.
- `alert:` retries behave: a failed notifier is a failed delivery, and
  the alert's own `repeat:` keeps its meaning.

Costs, accepted:

- **Quiet hours make automations go red every night.** That is the
  visible cost, and it is the intended one: an automation that fires at
  03:00 and must not fail should not be routing to a satellite in the
  first place, or should route to a satellite whose quiet-hours
  behaviour is `skip_preannounce`.
- **A busy satellite fails a call an eventual retry would have
  delivered.** Deliberate — see ADR 0001: nothing is queued, because a
  message that arrives three minutes late is worse than one that fails
  loudly.
- Callers that genuinely do not care must say so, with
  `continue_on_error: true` on the step.

## Alternatives rejected

**Log and return.** The failure mode this integration exists to prevent
— nobody heard it, and nothing said so — becomes its default behaviour.

**Raise for faults, log for policy** (busy and quiet hours would return
normally). Rejected: the split is invisible from the caller's side. An
automation cannot tell "spoke" from "deliberately did not speak", which
is exactly the distinction it needs to decide whether to escalate to a
phone.

**Return a value the caller can inspect.** Legacy `notify` services
return nothing, and `NotifyEntity.async_send_message` returns `None`.
There is no channel for it without inventing one core does not have.

## See also

The notify suite these integrations belong to states the same rule as
its ADR-015. This repository does not depend on that document, and this
ADR is the authority here.
