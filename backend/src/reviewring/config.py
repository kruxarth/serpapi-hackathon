"""Paths, tunables and secrets.

Tunables come from ``config/reviewring.toml`` (committed), optionally overridden
by ``data/config.toml`` (gitignored). Secrets come only from the environment or
the gitignored ``.env`` file and never leave the backend.
"""

from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_FILE = REPO_ROOT / "config" / "reviewring.toml"


def data_dir() -> Path:
    """The gitignored data directory. ``REVIEWRING_DATA_DIR`` overrides it (tests use this)."""
    path = Path(os.environ.get("REVIEWRING_DATA_DIR", REPO_ROOT / "data"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


@lru_cache(maxsize=1)
def load_tunables() -> dict[str, Any]:
    with CONFIG_FILE.open("rb") as f:
        tunables = tomllib.load(f)
    local = data_dir() / "config.toml"
    if local.exists():
        with local.open("rb") as f:
            tunables = _merge(tunables, tomllib.load(f))
    return tunables


def tunable(section: str, key: str) -> Any:
    return load_tunables()[section][key]


@dataclass(frozen=True)
class Secrets:
    serpapi_key: str | None
    deepseek_key: str | None

    def values(self) -> list[str]:
        return [v for v in (self.serpapi_key, self.deepseek_key) if v]


def load_secrets() -> Secrets:
    """Environment variables win over ``.env``. Empty strings count as unset."""
    env_file = REPO_ROOT / ".env"
    use_file = env_file.exists() and not os.environ.get("REVIEWRING_NO_DOTENV")
    file_values = dotenv_values(env_file) if use_file else {}

    def get(name: str) -> str | None:
        value = os.environ.get(name) or file_values.get(name) or ""
        return value.strip() or None

    return Secrets(serpapi_key=get("SERPAPI_API_KEY"), deepseek_key=get("DEEPSEEK_API_KEY"))
