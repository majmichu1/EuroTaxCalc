"""
Internationalization (i18n) system for EuroTaxCalc.

Usage:
    from src.i18n import t, set_language

    set_language("en")
    label = t("nav.calculator")  # → "Calculator"
"""

from __future__ import annotations

_current_lang: str = "pl"
_strings: dict[str, dict[str, str]] = {}


def _load_strings():
    global _strings
    from src.i18n import pl, en
    _strings = {
        "pl": pl.STRINGS,
        "en": en.STRINGS,
    }


def set_language(lang: str) -> None:
    """Set the active language. Falls back to 'en' if lang not available."""
    global _current_lang
    if not _strings:
        _load_strings()
    _current_lang = lang if lang in _strings else "en"


def get_language() -> str:
    return _current_lang


def t(key: str, **kwargs) -> str:
    """
    Get translated string for key.
    Falls back: current lang → English → key itself.

    Optional kwargs are formatted into the string, e.g.:
        t("calc.tax_rate", rate="19%")  →  "Tax rate: 19%"
    """
    if not _strings:
        _load_strings()

    text = (
        _strings.get(_current_lang, {}).get(key)
        or _strings.get("en", {}).get(key)
        or key
    )

    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, ValueError):
            pass

    return text
