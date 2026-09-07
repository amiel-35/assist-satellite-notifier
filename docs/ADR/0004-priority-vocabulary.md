# ADR 0004 — `data.priority` is a closed, exact, lowercase vocabulary

- Status: accepted
- Date: 2026-09-07

## Context

The legacy `notify.satellite_<name>` service accepts a `data.priority`
key. Exactly one value does anything: `critical` bypasses the
quiet-hours check entirely, chime included.

The first implementation validated only the *type* — any string was
accepted, and anything that was not `critical` was carried and ignored.
The stated reason was forward compatibility: let a caller keep its own
escalation vocabulary, and this integration will not stand in the way.

That reasoning does not survive contact with the one value that acts.
`Critical`, `CRITICAL` and `urgent` were all accepted, and all did
nothing. A caller that writes any of them has said, as clearly as it
knows how, *"this one matters, wake the house"* — and got silence, at
03:00, with a green automation trace and no log line. The failure is
invisible at exactly the moment it is expensive, and it is a typo away
from every correct call.

"Accept and ignore" is a reasonable default for a key whose values are
inert. It is not reasonable for a key where one value changes behaviour:
there, the space of accepted-and-ignored values is exactly the space of
misspellings of the value that works.

## Decision

`data.priority`, when present, must be one of exactly four strings:

```
info | normal | high | critical
```

Lowercase, matched exactly, no case folding and no aliases. They live in
`const.PRIORITIES`, and `SatelliteAnnouncer._validate` checks membership
after the type check.

Anything else — `Critical`, `CRITICAL`, `urgent`, `""`, a number, a list
— is refused as `invalid_data`, a translated `ServiceValidationError`,
per ADR 0002. The error names the accepted values, so a caller that got
it wrong is told what right looks like.

Only `critical` acts. `info`, `normal` and `high` are accepted and
carried without effect: they exist so a caller with an escalation ladder
can pass it through unchanged, and so that a future version can give
them meaning without breaking callers that already send them.

No case folding, deliberately. Accepting `Critical` as `critical` would
mean the vocabulary is four words *and* their case variants, which is a
larger promise to keep, and it makes the refusal message ("accepted
values are …") a half-truth.

## Consequences

Good:

- A misspelled `critical` is refused at the first call in the automation
  editor, not discovered on the night it mattered.
- The README, the strings and the code agree on one list, in one place.
- Adding meaning to `high` later is additive: callers already sending it
  keep working.

Costs, accepted:

- **Breaking for callers already sending something else.** Anyone
  passing `urgent` or `p1` today gets a red automation on the next call.
  That is the point — those calls were doing nothing — but it is a
  breaking change and is documented as one.
- Callers with a richer ladder must map onto four words, or carry their
  own vocabulary somewhere other than `data.priority`.

## Alternatives rejected

**Keep accepting any string.** The status quo, and the reason for this
ADR: it makes the one value that matters silently typo-able.

**Case-fold before comparing.** Fixes `Critical` and leaves `urgent`
silently inert, so it solves the smaller half of the problem while
enlarging what the vocabulary promises.

**Accept only `critical`, refuse the other three.** Smallest possible
surface, and it forces every caller with a ladder to strip the key
before calling. The three inert values cost nothing and leave room to
grow.

**A boolean `bypass_quiet_hours` instead of a priority word.** Honest
about what it does, and out of step with every other notify platform in
Home Assistant — `data.priority` is the key an automation author already
knows. Rejected on familiarity, not on merit.
