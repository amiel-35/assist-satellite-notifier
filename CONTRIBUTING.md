# Contributing

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements_dev.txt
```

## Before opening a pull request

```bash
ruff check . && ruff format --check .
mypy custom_components/assist_satellite_notifier
pytest
```

`hassfest` runs in CI; to run it locally you need a checkout of
`home-assistant/core` at the pinned version:

```bash
python -m script.hassfest --integration-path <path to this repo>/custom_components/assist_satellite_notifier
```

## House rules

- **Tests first.** Coverage must stay at or above 95%.
- **Every core API you rely on gets its path** in
  `home-assistant/core` written down, in the PR description and in
  `docs/ARCHITECTURE.md`. A behaviour nobody can point at is a guess.
- **Refusals raise.** Nothing that failed to be announced may answer the
  caller with a success.
- `strings.json` and `translations/en|fr|es.json` must have identical
  keys, and translated messages must use identical placeholders. There is
  a test for this.
- Update `CHANGELOG.md` under `Unreleased`.
- Comments explain *why*, not *what*. Prefer a paragraph that saves the
  next reader an hour in the core source over a line that restates the
  code.
