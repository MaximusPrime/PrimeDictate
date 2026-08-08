"""Strict, file-backed Turkish and English localization catalog."""

import json
from pathlib import Path


_language = "en"
_LOCALE_DIR = Path(__file__).with_name("locales")


def _load_locale(language: str) -> dict[str, str]:
    path = _LOCALE_DIR / f"{language}.json"
    with path.open("r", encoding="utf-8") as locale_file:
        catalog = json.load(locale_file)
    if not isinstance(catalog, dict) or not all(
        isinstance(key, str) and isinstance(value, str) and value.strip()
        for key, value in catalog.items()
    ):
        raise RuntimeError(f"Invalid locale catalog: {path}")
    return catalog


TR = _load_locale("tr")
EN_CATALOG = _load_locale("en")
if set(TR) != set(EN_CATALOG):
    missing_tr = sorted(set(EN_CATALOG) - set(TR))
    missing_en = sorted(set(TR) - set(EN_CATALOG))
    raise RuntimeError(
        f"Locale key mismatch; missing_tr={missing_tr!r}, missing_en={missing_en!r}"
    )

MESSAGES = {
    key: {"tr": TR[key], "en": EN_CATALOG[key]}
    for key in sorted(TR)
}

# Static widget literals are progressively moving to semantic keys. Legacy
# literals already have deterministic legacy.<sha1> keys in the JSON catalogs,
# so runtime translation never relies on a reverse English-to-Turkish map.
EN = {
    TR[key]: EN_CATALOG[key]
    for key in TR
    if key.startswith("legacy.")
}
LEGACY_TEXT_KEYS = {}
for key in TR:
    if not key.startswith("legacy."):
        continue
    LEGACY_TEXT_KEYS[TR[key]] = key
    LEGACY_TEXT_KEYS.setdefault(EN_CATALOG[key], key)


def set_language(language: str):
    global _language
    _language = language if language in {"tr", "en"} else "en"


def get_language() -> str:
    return _language


def translate(key: str, **values) -> str:
    translations = MESSAGES.get(key)
    if translations is None:
        raise KeyError(f"Unknown translation key: {key}")
    text = translations[_language]
    return text.format(**values) if values else text


def legacy_translation_key(text: str):
    """Resolve a static widget literal to its deterministic catalog key."""
    return LEGACY_TEXT_KEYS.get(text)
