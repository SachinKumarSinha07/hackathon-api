"""
Locale Middleware

Reads the X-Language / Accept-Language header and stores the resolved language
in the i18n ContextVar so translate() returns the correct language per request.
"""

from starlette.middleware.base import BaseHTTPMiddleware
from app.core.i18n import set_language, SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE


def _resolve_language(raw_value: str) -> str:
    """Resolve a raw header value to a supported two-letter language code."""
    if not raw_value:
        return DEFAULT_LANGUAGE
    primary = raw_value.split(",")[0].strip()
    primary = primary.split(";")[0].strip()
    lang = primary.split("-")[0].strip().lower()
    return lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


class LocaleMiddleware(BaseHTTPMiddleware):
    """Detect the request locale and store it for the request scope."""

    async def dispatch(self, request, call_next):
        raw = (
            request.headers.get("X-Language")
            or request.headers.get("Accept-Language")
            or DEFAULT_LANGUAGE
        )
        set_language(_resolve_language(raw))
        return await call_next(request)
