"""Keep API keys out of every log line and error message (Rule 4).

The ``serpapi`` client sends the key as a URL query parameter, and the
``requests`` exceptions it wraps quote the full URL. So nothing from an HTTP
library is ever shown raw: log records are redacted when they are created,
and errors shown to users go through :func:`safe_error`.
"""

from __future__ import annotations

import logging
import re
import threading
import traceback

PLACEHOLDER = "[REDACTED]"

_lock = threading.Lock()
_secrets: set[str] = set()
_installed = False

# Any api_key-like query parameter, whatever its value, is also masked.
_KEY_PARAM = re.compile(r"((?<![A-Za-z0-9_])(?:api_key|apikey|key)=)[^&\s'\"]+", re.IGNORECASE)
_BEARER = re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE)


def register_secret(value: str | None) -> None:
    if value and len(value) >= 4:
        with _lock:
            _secrets.add(value)


def redact(text: object) -> str:
    out = str(text)
    with _lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        out = out.replace(secret, PLACEHOLDER)
    out = _KEY_PARAM.sub(lambda m: m.group(1) + PLACEHOLDER, out)
    out = _BEARER.sub(lambda m: m.group(1) + PLACEHOLDER, out)
    return out


def safe_error(exc: BaseException) -> str:
    """A user-facing description of an exception. Never the raw HTTP-library message."""
    status = getattr(exc, "status_code", None)
    body_error = getattr(exc, "error", None)
    name = type(exc).__name__
    if status is not None and status != -1:
        detail = f": {redact(body_error)}" if body_error else ""
        return f"{name} (HTTP {status}){detail}"
    module = type(exc).__module__ or ""
    if module.startswith(("requests", "urllib3", "serpapi", "httpx", "openai")):
        return name
    return f"{name}: {redact(exc)}"


def install() -> None:
    """Redact every log record at creation time and silence HTTP debug logging."""
    global _installed
    if _installed:
        return
    base_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = base_factory(*args, **kwargs)
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - a bad format string must not crash logging
            message = str(record.msg)
        record.msg = redact(message)
        record.args = ()
        if record.exc_info:
            record.exc_text = redact("".join(traceback.format_exception(*record.exc_info)))
            record.exc_info = None
        return record

    logging.setLogRecordFactory(factory)
    for name in ("urllib3", "requests", "httpx", "httpcore", "openai"):
        logging.getLogger(name).setLevel(logging.WARNING)
    _installed = True


def scrub_secrets(text: str) -> str:
    """Replace registered secret values only (used on response bodies before storing)."""
    with _lock:
        secrets = sorted(_secrets, key=len, reverse=True)
    for secret in secrets:
        text = text.replace(secret, PLACEHOLDER)
    return text
