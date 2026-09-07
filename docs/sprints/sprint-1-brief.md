# Sprint 1 brief — Assist Satellite Notifier v0.1.0 (new repository; suite roadmap "S12")

> One coding agent, working directly in the fresh repository
> this repository (already created, empty, remote
> `origin` = `github.com/amiel-35/assist-satellite-notifier`, default branch
> `main`). English everywhere; en/fr/es translations; MIT; no first names, no
> personal infrastructure details anywhere in the repository. Paths from the
> orchestrator: core clone 2026.9.1 at `$HA_CORE_SRC`, venv at `$VENV`,
> reference sibling to copy the structure from: the `cast-notifier` repository
> (read-only). Never touch `.github/workflows` of other repos or any Home
> Assistant instance. Tests first.

## Why

Home Assistant has no `notify` service that speaks. Cast Notifier and
AirPlay Notifier fill that gap for two media-player families by driving
`tts.speak` and managing volume themselves. Assist satellites (ESPHome voice
devices, VoIP, Kiosk Satellite tablets, Wyoming) already have a **native**
announcement primitive — `assist_satellite.announce` — that synthesises with
the satellite's own pipeline TTS, optionally plays a pre-announce sound, and
blocks until playback ends (`homeassistant/components/assist_satellite/`:
`services.yaml`, `entity.py` `async_internal_announce`,
`const.py` `AssistSatelliteEntityFeature.ANNOUNCE`). This integration is the
thin `notify` adapter on top of it, so that a core `alert:` (or Notify
Switchboard) can list a satellite among its notifiers.

## Public contract (frozen at release)

| Item | Value |
|---|---|
| Domain | `assist_satellite_notifier` |
| Integration type | `helper`, `iot_class: calculated`, `config_flow: true`, `dependencies: [assist_satellite]` |
| One config entry | one `assist_satellite.*` entity (unique id = that entity id, same known limitation as Cast Notifier, documented) |
| Legacy service | `notify.satellite_<slugify(entry title)>` with deterministic `_<n>` fallback on collision; `message` required, `title` ignored except when `prefix_title` option is on (then "title. message") |
| Notify entity | one `NotifyEntity` per entry (`message` + `title`), same behaviour |
| Options | `preannounce` (bool, default true — passes `preannounce: true/false` to the service), `preannounce_media_id` (optional media id / URL), `deny_domains` (comma list, default `alarm_control_panel, lock`, checked against `data.source_entity` case-insensitively, list or string), `quiet_start` / `quiet_end` / `quiet_behaviour` (`refuse` \| `skip_preannounce`; inside the window `refuse` raises, `skip_preannounce` announces without the pre-sound; `data.priority: "critical"` bypasses) |
| Per-call `data` | `source_entity`, `priority`, `preannounce` (bool override), `media_id` (announce a media file instead of TTS text; `message` still required by `notify`, ignored then) — anything else refused with a translated `ServiceValidationError` (suite ADR-015: refusals raise) |
| Busy satellite | `SatelliteBusyError` from core → translated `ServiceValidationError` (`satellite_busy`), logged at INFO, nothing retried |
| Unavailable satellite | the notify entity is `unavailable`; a call raises `ServiceValidationError` (`satellite_unavailable`) |

Deliveries block until the satellite reports the announcement finished
(that is what `assist_satellite.announce` does); no volume management at all
(the satellite owns it).

## Repository skeleton (mirror cast-notifier)

`custom_components/assist_satellite_notifier/` (`__init__.py`, `config_flow.py`,
`const.py`, `notify.py`, `diagnostics.py`, `manifest.json` with in-repo brand
`brand/icon.png` (copy the suite's icon style), `strings.json`,
`translations/{en,fr,es}.json`, `icons.json`, `quality_scale.yaml` fully
assessed), `hacs.json`, `README.md` (what/why/install via custom repository +
My Home Assistant buttons/config/options/`data` keys/troubleshooting/removal),
`docs/ARCHITECTURE.md`, `docs/known-issues.md`, `docs/ADR/0001-thin-adapter-over-native-announce.md`,
`CHANGELOG.md`, `CODE_OF_CONDUCT.md`, `SECURITY.md`, `LICENSE` (MIT),
`.github/workflows/` (validate: hassfest + hacs/action without `ignore`;
lint: ruff + mypy; test: pytest with `pytest-homeassistant-custom-component`
pinned like cast-notifier; release on tag), `.github/dependabot.yml`,
`pyproject.toml`/`requirements_dev.txt` identical in spirit to cast-notifier.

## Tests (write first)

Use the core test helpers for a mock satellite (see
`$HA_CORE_SRC/tests/components/assist_satellite/conftest.py`,
`MockAssistSatellite`) to assert: the service and entity exist after setup;
a call invokes `assist_satellite.announce` with the right `message`,
`preannounce`, `preannounce_media_id`; `data.media_id` path; deny-list
refusal (list, upper-case); invalid `data` refusal; quiet hours both
behaviours and the `critical` bypass; busy and unavailable satellites;
service unregistered on entry removal and renamed on title change; options
change takes effect without restart; config flow refuses an entity without
the `ANNOUNCE` feature. Coverage ≥ 95 %.

## Definition of done

All of the above green locally with `$VENV`; ruff / mypy / hassfest / HACS
action green in CI (push to `main` is allowed for the initial scaffold only,
then branches + PRs); `v0.1.0` **not** tagged by you — the orchestrator
tags after review. Report: what was verified, what remains (a real
satellite was never exercised: say so in `known-issues.md`).
