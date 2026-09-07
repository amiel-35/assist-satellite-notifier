# Assist Satellite Notifier

A `notify.*` service that **speaks on an Assist satellite**, for Home
Assistant.

[![Validate](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/validate.yml/badge.svg)](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/validate.yml)
[![Lint](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/lint.yml/badge.svg)](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/lint.yml)
[![Test](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/test.yml/badge.svg)](https://github.com/amiel-35/assist-satellite-notifier/actions/workflows/test.yml)

> **Status: scaffold.** The repository, CI and integration metadata are in
> place; the notify surfaces land in 0.1.0. Nothing announces yet.

## What it will do

Home Assistant has no `notify` service that speaks. Voice goes through
`assist_satellite.announce`, which is an *action*: a core `alert:` takes a
list of notifier names and cannot call an action, so a satellite cannot be
one of the channels an alert escalates through.

This integration is the thin adapter that closes that gap — one
`notify.satellite_<name>` service and one `NotifyEntity` per configured
`assist_satellite` entity, both forwarding to the satellite's own native
announcement. It re-implements nothing that core already does: no TTS of
its own, no volume management, no timeouts.

See [`docs/sprints/sprint-1-brief.md`](docs/sprints/sprint-1-brief.md) for
the full contract being built.

## Install

Not yet released. Once 0.1.0 ships: HACS → Custom repositories →
`https://github.com/amiel-35/assist-satellite-notifier`, type
**Integration**.

## License

[MIT](LICENSE).
