"""Test isolation: a temporary data directory, no real keys, and a hard network guard.

Any attempt to reach a non-local host (serpapi.com, api.deepseek.com, anything)
raises immediately AND fails the whole run, even if the test swallows the error.
"""

from __future__ import annotations

import socket

import pytest

from reviewring import config

_LOCAL = {"localhost", "127.0.0.1", "::1", "0.0.0.0", ""}
BLOCKED: list[str] = []


class NetworkBlocked(RuntimeError):
    pass


def _host_of(address) -> str:
    if isinstance(address, tuple) and address:
        return str(address[0])
    return ""  # unix sockets


def _guard(host: str) -> None:
    if host not in _LOCAL:
        BLOCKED.append(host)
        raise NetworkBlocked(f"Tests must not reach the network (tried {host})")


_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _getaddrinfo(host, *args, **kwargs):
    _guard(str(host or ""))
    return _real_getaddrinfo(host, *args, **kwargs)


def _connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _guard(_host_of(address))
    return _real_connect(self, address)


def _connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6):
        _guard(_host_of(address))
    return _real_connect_ex(self, address)


def pytest_configure(config):  # noqa: ARG001
    socket.getaddrinfo = _getaddrinfo
    socket.socket.connect = _connect
    socket.socket.connect_ex = _connect_ex


def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    if BLOCKED:
        print(f"\nNETWORK GUARD: tests tried to reach {sorted(set(BLOCKED))}; failing the run.")
        session.exitstatus = 1


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("REVIEWRING_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("REVIEWRING_NO_DOTENV", "1")
    monkeypatch.delenv("SERPAPI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    config.load_tunables.cache_clear()
    yield tmp_path
    config.load_tunables.cache_clear()
