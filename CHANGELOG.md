# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-09-07

### Added

- Repository scaffold: `custom_components/assist_satellite_notifier`, CI
  (hassfest, HACS validation, lint, tests, release), HACS metadata, and
  the integration icon bundled in-repo.
- Config flow (one entry per `assist_satellite` entity, duplicates
  aborted, a satellite without the `ANNOUNCE` feature refused with
  `satellite_cannot_announce`) and an options flow. Changing an option
  reloads the entry and takes effect on the next call.
- Legacy `notify.satellite_<name>` service and a modern `NotifyEntity`,
  both announcing through the core `assist_satellite.announce` action on
  the configured satellite, sharing one `SatelliteAnnouncer`. One service
  device per entry, so several satellites are distinguishable in the UI.
- The service name is resolved once and stored on the config entry, with
  a deterministic `_<n>` fallback when two entry titles slugify to the
  same name. An entry keeps its service across restarts, reloads and
  renames of the other entries: a fallback to `_2` is never promoted to
  the unsuffixed name, and renaming an entry onto a name another entry
  already owns falls back instead of colliding. A stored name its entry
  no longer wants — one left behind by a rename that landed while the
  entry was disabled — is free for another entry to take, and is not
  taken back if that entry is later renamed onto it again. A name owned
  by something else is reported as an error, and only a service this
  integration registered is ever retracted.
  ([ADR 0003](docs/ADR/0003-service-name-persisted-on-the-entry.md))
- `deny_domains` safety net (`alarm_control_panel`, `lock` by default,
  case-insensitive, single entity or list): a call whose
  `data.source_entity` belongs to a denied domain is refused and logged
  instead of announced. Documented as an opt-in net that only applies when
  `data.source_entity` is present, not as a guarantee.
- Quiet hours: a local-time window, wrapping around midnight, with two
  behaviours — `refuse` fails the call, `skip_preannounce` announces
  without the chime — and a `data.priority: "critical"` bypass.
- Per-call `data` keys `source_entity`, `priority`, `preannounce` and
  `media_id`, validated up front. Anything else is refused with a
  translated error rather than silently ignored. `priority` is a closed
  vocabulary — `info`, `normal`, `high`, `critical` — matched exactly
  and in lowercase; only `critical` acts, the other three are accepted
  and carried without effect. Anything else, `Critical` and `urgent`
  included, is refused as `invalid_data`, so a misspelling of the one
  value that bypasses quiet hours cannot pass unnoticed.
  ([ADR 0004](docs/ADR/0004-priority-vocabulary.md))
- Refusals raise instead of failing silently: a deny-list hit, an invalid
  `data` payload, quiet hours, a busy satellite (`SatelliteBusyError` from
  core) and an unavailable satellite all reach the caller as translated
  `ServiceValidationError`s. ([ADR 0002](docs/ADR/0002-refusals-raise-service-validation-error.md))
- The notify entity follows its satellite's availability, and is
  `unavailable` whenever the satellite is. It advertises
  `NotifyEntityFeature.TITLE`, the feature core gates the `title` field
  on.
- Removing, unloading or reloading an entry retracts its
  `notify.satellite_<name>` service; Home Assistant core never does this
  for a legacy notify service. Renaming the entry renames the service.
- `MINOR_VERSION` and a no-op `async_migrate_entry`, so the first schema
  change can ship as a migration.
- Local ADRs for this repository's own rules, with an index: the thin
  adapter ([0001](docs/ADR/0001-thin-adapter-over-native-announce.md)),
  refusals raise
  ([0002](docs/ADR/0002-refusals-raise-service-validation-error.md)), the
  persisted service name
  ([0003](docs/ADR/0003-service-name-persisted-on-the-entry.md)) and the
  priority vocabulary ([0004](docs/ADR/0004-priority-vocabulary.md)).
- Diagnostics (resilient to an entry that is not loaded), translations
  (`en`, `fr`; `es` machine translated), a fully assessed
  `quality_scale.yaml`, and tests covering the entry lifecycle, the config
  and options flows, the announcing policy, both notify surfaces,
  diagnostics, translation key parity, and one end-to-end pass against a
  real `assist_satellite` entity.

[0.1.0]: https://github.com/amiel-35/assist-satellite-notifier/releases/tag/v0.1.0
