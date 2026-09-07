# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-09-07

**Highlights**

- Initial release: one config entry per `assist_satellite` device, with
  both a legacy `notify.satellite_<name>` service and a modern notify
  entity that announce through that satellite.
- Safety net: calls targeting `alarm_control_panel` or `lock` entities are
  refused by default (`deny_domains`).
- Quiet hours: a configurable time window that refuses announcements or
  skips the pre-announce chime, with a `priority: "critical"` bypass.
- Refusals (deny-list, invalid data, quiet hours, a busy or unavailable
  satellite) raise a clear error instead of failing silently.
- Renaming or removing a config entry keeps its notification service
  name consistent and never collides with another entry's service.

### Added

- Repository scaffold and packaging: installable via HACS, with a
  bundled integration icon.
- Config flow: one entry per `assist_satellite` entity, duplicate
  entries are blocked, and a satellite that can't announce is refused.
  An options flow lets settings be changed after setup, taking effect
  once the entry reloads.
- Each entry provides both a legacy `notify.satellite_<name>` service
  and a modern notify entity, both announcing through the configured
  satellite. Multiple satellites appear as distinguishable devices.
- Each entry keeps a stable, unique service name across restarts,
  reloads and renames of any entry — no collisions, even when two
  entries would otherwise produce the same name.
- `deny_domains` safety net: by default, a call whose
  `data.source_entity` belongs to `alarm_control_panel` or `lock` is
  refused and logged instead of announced.
- Quiet hours: a configurable local-time window, which can wrap past
  midnight, that either refuses announcements or skips the
  pre-announce chime; `data.priority: "critical"` bypasses it.
- Per-call `data` supports `source_entity`, `priority`, `preannounce`
  and `media_id`; any other key is refused instead of being silently
  ignored.
- `priority` accepts only `info`, `normal`, `high` or `critical`,
  matched exactly in lowercase; only `critical` has an effect
  (bypassing quiet hours). Any other value, including case variants
  like `Critical`, is refused.
- Refusals — deny-list, invalid data, quiet hours, a busy or
  unavailable satellite — raise a clear error instead of failing
  silently.
- The notify entity becomes unavailable whenever its satellite does,
  and supports titled notifications.
- Removing, unloading or reloading an entry retracts its
  `notify.satellite_<name>` service; renaming an entry renames the
  service instead.
- Diagnostics are available per entry, with translations in English,
  French, and (machine-translated) Spanish.

[Unreleased]: https://github.com/amiel-35/assist-satellite-notifier/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/amiel-35/assist-satellite-notifier/releases/tag/v0.1.0
