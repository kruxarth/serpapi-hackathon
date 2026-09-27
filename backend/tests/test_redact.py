import logging

from reviewring import redact

from .fakes import FAKE_KEY, http_error, timeout_error


def test_logged_exception_with_key_is_redacted(caplog):
    redact.install()
    redact.register_secret(FAKE_KEY)
    log = logging.getLogger("reviewring.test")
    err = http_error(500)
    assert FAKE_KEY in str(err)  # the premise: the raw message leaks the key
    with caplog.at_level(logging.INFO):
        log.error("request failed: %s", err)
        try:
            raise err
        except Exception:
            log.exception("with traceback")
    assert FAKE_KEY not in caplog.text
    assert redact.PLACEHOLDER in caplog.text


def test_unregistered_key_in_url_still_masked():
    text = "GET https://serpapi.com/search?engine=x&api_key=abcdef123456&hl=en"
    out = redact.redact(text)
    assert "abcdef123456" not in out and "hl=en" in out
    assert redact.redact("request_key=abc") == "request_key=abc"


def test_safe_error_never_shows_raw_http_message():
    redact.register_secret(FAKE_KEY)
    assert FAKE_KEY not in redact.safe_error(http_error(401, "Invalid API key."))
    assert "HTTP 401" in redact.safe_error(http_error(401, "Invalid API key."))
    assert redact.safe_error(timeout_error()) == "TimeoutError"


def test_http_debug_logging_off():
    redact.install()
    assert logging.getLogger("urllib3").getEffectiveLevel() >= logging.WARNING
