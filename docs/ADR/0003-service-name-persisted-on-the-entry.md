# ADR 0003 — The legacy service name is resolved once and persisted on the entry

- Status: accepted
- Date: 2026-09-07

## Context

Each config entry exposes a legacy `notify.satellite_<name>` service, so
that `alert.notifiers:` — which takes service *names*, not entity IDs —
can reach a satellite. The name comes from the entry title:
`notify/legacy.py::async_setup_legacy.async_setup_platform` slugifies
whatever the discovery payload passes as `CONF_NAME`.

Two things make "just derive it from the title on every load" wrong.

**Titles collide.** Two satellites can legitimately be called "Kitchen"
— two Home Assistant areas, a house and a flat — and the second one must
still get a service. So a collision has to fall back to
`satellite_kitchen_2`.

**Core will not overwrite a service that exists.**
`BaseNotificationService.async_register_services` returns early when the
name is already registered:

```python
# homeassistant/components/notify/legacy.py:312
if self.hass.services.has_service(DOMAIN, self._service_name):
    return
```

No exception, no log line, no second registration — the entry that asked
second is simply left with no service at all, pointing at a live
announcer nobody can call. Every naming scheme has to be evaluated
against that early return, because it turns any name collision into a
silent partial failure rather than a loud one.

Deriving the name afresh on every load fails there twice:

- **Promotion.** An entry that fell back to `satellite_kitchen_2` would
  claim `satellite_kitchen` the moment it happened to load first — after
  a restart, or once the other entry was deleted. Every `alert:` and
  script naming `satellite_kitchen_2` breaks, silently, on a reboot
  nobody connected to it.
- **Rename onto a taken name.** Renaming "Hall" to "Kitchen" while
  another entry already owns `satellite_kitchen` hands this entry that
  name, core's early return declines it, and the entry ends up
  serviceless.

## Decision

**Resolve the service name once and store it in
`entry.data["service_name"]`.** Recompute it only when the entry's
current title no longer derives from the stored name.

The rules, in full:

1. An entry keeps a stored name for as long as that name is the entry's
   title slug or one of its `_<n>` fallbacks (`_is_derived_from`). A
   reload, a restart, or another entry appearing or disappearing never
   changes it.
2. A name is recomputed when, and only when, the title changes to
   something the stored name no longer derives from.
3. Resolution counts as **taken** every name another entry still owns —
   that is, another entry's stored name that still derives from *that*
   entry's current title. A stored name whose entry has since been
   renamed is not taken: nothing will ever register it again, and
   reserving it would make it unusable forever.
4. Entries with no name of their own — a fresh pair, an entry upgrading
   from a build that predates the key, an entry renamed while it was
   disabled — are resolved in config-entry order, so two starting
   together cannot claim the same name.
5. The resolved name is written back in `async_setup_entry`, before the
   update listener is added, so persisting it cannot reload the entry
   that is currently setting up. An unchanged value is a no-op:
   `ConfigEntries._async_update_entry` returns `False` without firing
   listeners when nothing differs.

This is not a schema change, so `async_migrate_entry` does not touch it:
an entry that predates the key is valid, and the next setup fills it in
— in the one place that can see what every other entry owns.

## Consequences

Good:

- A service name is stable for the life of the entry. `alert:` and
  scripts that name it keep working across restarts, reloads, and the
  deletion of unrelated entries.
- `_2` is never promoted. The entry that got the suffix keeps it even
  once the unsuffixed name is free.
- A rename onto a name another entry owns falls back to `_<n>` instead
  of hitting core's early return and leaving the entry serviceless.
- Unload retracts only a service this entry actually registered
  (`legacy_service_registered`), so it can never delete a name that
  belongs to another entry or another integration.

Costs, accepted:

- **A `_2` is permanent.** Deleting the entry that holds
  `satellite_kitchen` does not move `satellite_kitchen_2` up. Tidying it
  is a manual rename, or deleting and re-adding the entry.
- **No alias on rename.** Renaming an entry retracts the old service and
  registers the new one; automations naming the old one break at the
  rename, which is at least the moment the user did something.
- The entry carries one more key than its options strictly need, and
  `entry.data` is written on first load after an upgrade.

## Alternatives rejected

**Recompute on every load, ranking entries by creation order.** The
promotion and rename failures above, both silent, both surfacing at a
restart far from the change that caused them.

**Name the service after the entry ID** (`satellite_01H…`). Collision
proof and stable, and unusable: nobody types that into
`alert.notifiers:`, and the whole point of the legacy surface is that it
is named after the room.

**Name it after the satellite entity ID.** Stable, but it makes the
title — the thing the user edits, in the UI, to rename their
integration — cosmetic. It also collides just as readily once two
entries point at satellites whose entity IDs slugify alike.

**Let the collision stand and log it.** That is core's early return, and
it produces exactly the silent serviceless entry this ADR exists to
prevent.
