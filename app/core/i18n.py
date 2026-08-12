"""
Internationalization (i18n) Utility

Provides translation support (English / Japanese) using python-i18n.
The active language is stored in a ContextVar set per-request by LocaleMiddleware.
"""

from contextvars import ContextVar
from pathlib import Path
from typing import Any
import i18n

SUPPORTED_LANGUAGES = {"en", "ja"}
DEFAULT_LANGUAGE = "en"

_current_language: ContextVar[str] = ContextVar("current_language", default=DEFAULT_LANGUAGE)

_LOCALES_DIR = Path(__file__).parent.parent / "locales"

i18n.set("load_path", [str(_LOCALES_DIR)])
i18n.set("filename_format", "{locale}.{format}")
i18n.set("file_format", "json")
i18n.set("fallback", DEFAULT_LANGUAGE)
i18n.set("error_on_missing_translation", False)


def set_language(language: str) -> None:
    """Set the current request language."""
    lang = language.lower()
    if lang not in SUPPORTED_LANGUAGES:
        lang = DEFAULT_LANGUAGE
    _current_language.set(lang)


def get_language() -> str:
    """Get the current request language code."""
    return _current_language.get()


def translate(key: str, **kwargs: Any) -> str:
    """Translate a dot-separated key for the current request language."""
    lang = _current_language.get()
    return i18n.t(key, locale=lang, **kwargs)
