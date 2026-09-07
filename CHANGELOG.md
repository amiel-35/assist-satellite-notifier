# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed

- **Breaking for callers that sent an unrecognised `data.priority`.**
  The key is now a closed vocabulary — `info`, `normal`, `high`,
  `critical` — matched exactly and in lowercase. Only `critical` acts,
  as before; the other three are accepted and carried without effect.
  Anything else, `Critical` and `urgent` included, is refused as
  `invalid_data` instead of being accepted and silently ignored, so a
  misspelling of the one value that bypasses quiet hours cannot pass
  unnoticed. ([ADR 0004](docs/ADR/0004-priority-vocabulary.md))

### Fixed

- A service name stored on an entry that has since been renamed is no
  longer held in reserve. Renaming an entry while it was disabled left
  its old name reserved forever, so a new entry with that title fell
  back to `_2` while the plain name was free. Such a name now counts as
  free, and the renamed entry resolves afresh the next time it loads.

### Documentation

- Local ADRs for this repository's own rules, with an index: refusals
  raise ([0002](docs/ADR/0002-refusals-raise-service-validation-error.md)),
  the persisted service name
  ([0003](docs/ADR/0003-service-name-persisted-on-the-entry.md)) and the
  priority vocabulary ([0004](docs/ADR/0004-priority-vocabulary.md)).
  The places that used to cite an ADR of the wider notify suite, which
  is not readable from here, now cite ADR 0002.

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
  already owns falls back instead of colliding. A name owned by something
  else is reported as an error, and only a service this integration
  registered is ever retracted.
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
  translated error rather than silently ignored.
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
- Diagnostics (resilient to an entry that is not loaded), translations
  (`en`, `fr`; `es` machine translated), a fully assessed
  `quality_scale.yaml`, and tests covering the entry lifecycle, the config
  and options flows, the announcing policy, both notify surfaces,
  diagnostics, translation key parity, and one end-to-end pass against a
  real `assist_satellite` entity.

[Unreleased]: https://github.com/amiel-35/assist-satellite-notifier/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/amiel-35/assist-satellite-notifier/releases/tag/v0.1.0
