"""Ensure translation files stay in sync with strings.json."""

from __future__ import annotations

import json
import re
import string
from pathlib import Path
from typing import Any

LANGUAGES = ("en", "fr", "es")

# hassfest rejects a placeholder wrapped in single quotes, because the
# frontend's own quoting turns it into literal text.
RE_PLACEHOLDER_IN_SINGLE_QUOTES = re.compile(r"'{\w+}'")

INTEGRATION_DIR = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "assist_satellite_notifier"
)

# Every `translation_key` the announcer can raise.
RAISED_EXCEPTION_KEYS = {
    "source_entity_denied",
    "invalid_data",
    "quiet_hours",
    "satellite_busy",
    "satellite_unavailable",
}


def _flatten_items(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Return every dotted key path in a nested mapping, with its value."""
    items: dict[str, str] = {}
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            items |= _flatten_items(value, path)
        else:
            items[path] = value
    return items


def _flatten_keys(data: dict[str, Any], prefix: str = "") -> set[str]:
    """Return every dotted key path in a nested translation mapping."""
    return set(_flatten_items(data, prefix))


def _placeholders(value: str) -> set[str]:
    """Return the `{name}` placeholders used in a translation value."""
    return {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(value)
        if field_name
    }


def _load(name: str) -> dict[str, Any]:
    path = (
        INTEGRATION_DIR / "strings.json"
        if name == "strings"
        else INTEGRATION_DIR / "translations" / f"{name}.json"
    )
    result: dict[str, Any] = json.loads(path.read_text())
    return result


def test_translations_match_strings_reference() -> None:
    """en, fr and es must expose exactly the same keys as strings.json."""
    reference_keys = _flatten_keys(_load("strings"))
    assert reference_keys, "strings.json should not be empty"

    for language in LANGUAGES:
        translation_keys = _flatten_keys(_load(language))
        assert translation_keys == reference_keys, (
            f"translations/{language}.json is missing "
            f"{reference_keys - translation_keys} and has extra "
            f"{translation_keys - reference_keys}"
        )


def test_exception_keys_cover_what_the_code_raises() -> None:
    """`strings.json` declares every `translation_key` the announcer raises."""
    assert set(_load("strings")["exceptions"]) == RAISED_EXCEPTION_KEYS


def test_the_quiet_behaviour_selector_is_translated() -> None:
    """Both quiet-hours behaviours have a label in every language."""
    for name in ("strings", *LANGUAGES):
        options = _load(name)["selector"]["quiet_behaviour"]["options"]
        assert set(options) == {"refuse", "skip_preannounce"}


def test_the_notify_entity_has_no_translated_name() -> None:
    """The entity takes its device's name; a translated one would collide.

    `_attr_translation_key` is set only so icons.json can hang an icon off
    it, and `homeassistant/helpers/entity.py::Entity._name_internal`
    returns `_attr_name` before it ever looks a translated name up -- but
    only as long as no `entity.notify.satellite.name` key exists.
    """
    for name in ("strings", *LANGUAGES):
        assert "entity" not in _load(name)


def test_exception_placeholders_are_identical_across_languages() -> None:
    """A translated message must use exactly the placeholders it is given.

    A `{satellite}` that only exists in one language silently renders the
    raw key in the others (`async_get_exception_message` suppresses the
    `KeyError`), so drift here is invisible at runtime.
    """
    reference = {
        key: _placeholders(value["message"])
        for key, value in _load("strings")["exceptions"].items()
    }

    for language in LANGUAGES:
        for key, value in _load(language)["exceptions"].items():
            assert _placeholders(value["message"]) == reference[key], (
                f"translations/{language}.json: exceptions.{key} uses "
                f"different placeholders than strings.json"
            )


def test_no_placeholder_is_wrapped_in_single_quotes() -> None:
    """hassfest refuses a placeholder inside single quotes; so do we."""
    for name in ("strings", *LANGUAGES):
        for key, value in _flatten_items(_load(name)).items():
            assert not RE_PLACEHOLDER_IN_SINGLE_QUOTES.search(value), (
                f"{name}: {key} wraps a placeholder in single quotes"
            )


def test_the_icon_translation_key_exists() -> None:
    """icons.json points at the translation key the entity actually sets."""
    icons = json.loads((INTEGRATION_DIR / "icons.json").read_text())
    assert icons["entity"]["notify"]["satellite"]["default"].startswith("mdi:")
