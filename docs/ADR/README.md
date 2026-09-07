# Architecture decision records

One file per decision that would otherwise be re-argued from scratch, or
re-broken by somebody who did not know why it was made. Each records the
context at the time, the decision, the consequences accepted with it, and
the alternatives turned down.

They are numbered in the order they were written and are never rewritten
in place: a decision that no longer holds gets a new record that
supersedes it, and the old one keeps its status line so the reasoning
stays readable.

| # | Decision | Status |
|---|---|---|
| [0001](0001-thin-adapter-over-native-announce.md) | A thin adapter over the native `announce`, not a second announcer | accepted |
| [0002](0002-refusals-raise-service-validation-error.md) | A refusal raises, it never fails silently | accepted |
| [0003](0003-service-name-persisted-on-the-entry.md) | The legacy service name is resolved once and persisted on the entry | accepted |
| [0004](0004-priority-vocabulary.md) | `data.priority` is a closed, exact, lowercase vocabulary | accepted |

These are this repository's own records. The notify suite these
integrations belong to keeps its own, cross-cutting set; where the two
overlap, the record here is the one that governs this code.

See also [`../ARCHITECTURE.md`](../ARCHITECTURE.md) for how the pieces
fit together, and [`../known-issues.md`](../known-issues.md) for the
sharp edges that are known and not yet decided about.
