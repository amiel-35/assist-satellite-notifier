# Assist Satellite Notifier

A `notify.*` service that **speaks on an Assist satellite**, for Home
Assistant.

[![Validate](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/validate.yml/badge.svg)](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/validate.yml)
[![Lint](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/lint.yml/badge.svg)](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/lint.yml)
[![Test](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/test.yml/badge.svg)](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/test.yml)

## Maintenance mode

Since 7 September 2026 this integration is maintained **at low volume**:
no new features are planned, issues get answered, and the code is kept
working across Home Assistant releases. It is the one adapter of the suite
that still fills a real gap — `assist_satellite` has no `notify` platform,
while any `media_player` can already be a notify target through core's
`notify: - platform: tts` — which is why it stays when the Cast and AirPlay
notifiers were archived. Be aware that it has **never been exercised on a
real satellite**: everything was verified against Home Assistant's test
harness and demo entities. Real-hardware reports are welcome (see the
`help wanted` issues).

## What

One config entry = one `assist_satellite` entity. Each entry gives you two
notify surfaces onto that satellite:

- a legacy service, `notify.satellite_<name>`, which is what
  `alert.notifiers:`, blueprints and "pick a notifier" UIs can list;
- a modern `NotifyEntity`, `notify.<name>`, for `notify.send_message`.

Both call the satellite's own `assist_satellite.announce` action. The
satellite synthesises the text with its own pipeline voice, plays its own
pre-announcement chime, and the call blocks until it has finished
speaking. This integration adds no audio path, no volume management and no
timeout of its own.

## Why

Home Assistant has no `notify` service that speaks. Voice goes through
`assist_satellite.announce` (or `tts.speak`), which are *actions*: a core
`alert:` takes a list of notifier names, and cannot call an action. So a
satellite in the hallway — an ESPHome voice device, a Wyoming satellite, a
VoIP phone, a tablet running a satellite — cannot be one of the channels an
alert escalates through, even though it is the one channel that reaches
someone who is not holding a phone.

This integration is the thin adapter that closes that gap, and nothing
more. It deliberately does **not** re-implement announcing: everything the
speaking involves is core's
[`assist_satellite.announce`](https://www.home-assistant.io/integrations/assist_satellite/).
See [`docs/ADR/0001-thin-adapter-over-native-announce.md`](docs/ADR/0001-thin-adapter-over-native-announce.md)
for why.

## Requirements

- Home Assistant 2026.9.1 or later.
- At least one `assist_satellite` entity that advertises the `ANNOUNCE`
  feature. Satellites that cannot announce are refused by the config flow.

## Install

### Via HACS (custom repository)

1. HACS → three-dot menu → **Custom repositories**.
2. Repository: `https://github.com/amiel-35/assist-satellite-notifier`,
   type **Integration**. Add.
3. Search for **Assist Satellite Notifier**, download it.
4. Restart Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=amiel-35&repository=assist-satellite-notifier&category=integration)

### Manually

Copy `custom_components/assist_satellite_notifier/` into your Home
Assistant `config/custom_components/` directory and restart.

## Configuration

Settings → Devices & services → **Add integration** → *Assist Satellite
Notifier*, then pick the satellite.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=assist_satellite_notifier)

The entry is named after the satellite, and the legacy service takes its
name from the entry title: an entry called *Living room* becomes
`notify.satellite_living_room`. Renaming the entry renames the service (and
breaks automations that used the old name — see *Known limitations*). Two
entries whose titles slugify the same way get `_2`, `_3`, and so on.

The name is resolved once and stored on the entry, so it does not move
under you: an entry that had to fall back to `_2` keeps it, even after the
other entry is deleted and the unsuffixed name is free again.

Add one entry per satellite you want to notify on.

## Options

Settings → Devices & services → Assist Satellite Notifier → **Configure**.
A change takes effect on the next call; no restart.

| Option | Default | What it does |
|---|---|---|
| Play the pre-announcement sound | on | Passes `preannounce` to `assist_satellite.announce`: the satellite's short chime before the message. |
| Custom pre-announcement sound | empty | A media ID or URL played instead of the satellite's default chime. Only sent when the chime is played at all. |
| Speak the title before the message | off | When a call passes a `title`, speak it as `"title. message"`. Off by default: a spoken message has no title line. |
| Never announce about these domains | `alarm_control_panel, lock` | Comma-separated entity domains. A call whose `data.source_entity` is in one of them is refused. Case-insensitive. See [SECURITY.md](SECURITY.md) — it is a safety net, not a boundary. |
| Quiet hours start / end | empty | A window during which announcements are held back. Empty (or half-filled) means no quiet hours; a window whose end is before its start wraps around midnight; identical bounds mean no window at all. |
| During quiet hours | Refuse the announcement | `Refuse the announcement` fails the call; `Announce, but without the chime` speaks the message with no pre-announcement sound. |

## `data` keys

Only the legacy `notify.satellite_<name>` service carries a `data`
payload; `NotifyEntity` has none.

| Key | Type | What it does |
|---|---|---|
| `source_entity` | entity ID, or a list of them | The entity the message is *about*. Used only to enforce the deny list; never spoken, never forwarded. |
| `priority` | `info`, `normal`, `high` or `critical` | `critical` bypasses quiet hours entirely, chime included. The other three are accepted and do nothing. The vocabulary is exact and lowercase: `Critical` and `urgent` are refused, not ignored. See [ADR 0004](docs/ADR/0004-priority-vocabulary.md). |
| `preannounce` | boolean | Per-call override of the *Play the pre-announcement sound* option. |
| `media_id` | string | Play this media file instead of speaking. `message` is still required by `notify`, but is not spoken. |

**Anything else is refused**, with a translated error, rather than being
silently ignored: a typo in an automation should be visible the first time
it runs.

```yaml
# An alert that escalates to a satellite
alert:
  water_leak:
    name: Water leak
    entity_id: binary_sensor.water_leak
    state: "on"
    repeat: 5
    notifiers:
      - mobile_app_phone
      - satellite_living_room

# An automation call with a payload
actions:
  - action: notify.satellite_living_room
    data:
      message: The washing machine is done
      data:
        source_entity: binary_sensor.washing_machine
        priority: critical
```

## Troubleshooting

**"the satellite is busy"** — the satellite was already announcing or in a
conversation. Nothing is queued and nothing is retried: a message that
arrives three minutes late is worse than one that fails loudly. Core raises
`SatelliteBusyError`; this integration turns it into a refusal and logs it
at INFO.

**"the satellite is unavailable"** — the satellite entity is
`unavailable`, so the notify entity is too. Check the satellite's own
integration first.

**Nothing is spoken, and there is no error** — check that the call really
reached the right service. Under core `alert:`, notifiers are called
without waiting for them, so a refusal shows up in the log rather than in
the alert's trace; see [`docs/known-issues.md`](docs/known-issues.md).

**The call takes a long time** — that is by design. The call blocks until
the satellite reports the announcement has finished playing, because
`assist_satellite.announce` does. A long message is a long call.

**The service name changed** — renaming the config entry renames
`notify.satellite_<name>`. Rename it back, or update the automations.

**Enable debug logging:**

```yaml
logger:
  logs:
    custom_components.assist_satellite_notifier: debug
```

## Removal

Settings → Devices & services → Assist Satellite Notifier → three-dot menu
→ **Delete**. The `notify.satellite_<name>` service and the notify entity
go with the entry — this integration retracts the legacy service itself,
because Home Assistant does not do it for a config entry. Then remove the
integration from HACS (or delete
`custom_components/assist_satellite_notifier/`) and restart.

## Known limitations

- **A satellite renamed at the entity-ID level orphans its entry.** The
  entry's unique ID is the satellite's entity ID, not its registry ID.
  Rename the satellite before configuring it, or delete and re-add the
  entry afterwards.
- **Renaming the entry renames the service.** Automations referring to the
  old `notify.satellite_<name>` break. That is the price of a readable
  name; the alternative would be an opaque, entry-ID-based service name.
  Renaming onto a name another entry already owns falls back to `_2`
  rather than taking it.
- **`deny_domains` only applies to the legacy service.** `NotifyEntity`
  has no `data` payload, so it cannot declare a `source_entity` to filter
  on.
- **No queueing.** One announcement at a time, per the satellite's own
  behaviour.
- **No real satellite hardware was exercised** in this release's tests —
  see [`docs/known-issues.md`](docs/known-issues.md).

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — the contract, and every
  core API it relies on.
- [`docs/known-issues.md`](docs/known-issues.md) — what is known to be
  rough, and what was not tested.
- [`docs/ADR/`](docs/ADR/README.md) — the decisions and why.

Translations: `en` and `fr` are written by hand; **`es` is machine
translated** and has not been reviewed by a Spanish speaker — corrections
are welcome.

## License

[MIT](LICENSE).
