import socket

import pytest

from . import conftest


@pytest.mark.parametrize("host", ["serpapi.com", "api.deepseek.com"])
def test_guard_blocks_external_hosts(host):
    with pytest.raises(conftest.NetworkBlocked):
        socket.getaddrinfo(host, 443)
    conftest.BLOCKED.remove(host)  # this test tripped the guard on purpose


def test_guard_blocks_raw_connect():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        with pytest.raises(conftest.NetworkBlocked):
            s.connect(("203.0.113.5", 443))
    finally:
        s.close()
    conftest.BLOCKED.remove("203.0.113.5")


def test_real_serpapi_client_is_blocked():
    import serpapi

    client = serpapi.Client(api_key="fakekey-not-real-bbbbbbbbbbbbbbbb", timeout=1)
    with pytest.raises(Exception):  # noqa: B017 - any failure is fine as long as it's the guard
        client.search({"engine": "google_maps_reviews", "data_id": "0x1:0x2"})
    assert "serpapi.com" in conftest.BLOCKED
    conftest.BLOCKED.remove("serpapi.com")
