"""Runtime settings, stored in data/settings.json (never keys)."""

from __future__ import annotations

import json
import threading
from typing import Any

from . import config

MODES = ("live", "offline", "demo")
_lock = threading.Lock()


def _path():
    return config.data_dir() / "settings.json"


def defaults() -> dict[str, Any]:
    secrets = config.load_secrets()
    budget = config.load_tunables()["budget"]
    return {
        "mode": "live" if secrets.serpapi_key else "demo",
        "presentation_mode": False,
        "paraphrase_signal": bool(config.tunable("llm", "paraphrase_signal")),
        "monthly_cap": budget["monthly_cap"],
        "hourly_cap": budget["hourly_cap"],
        "per_analysis_cap": budget["per_analysis_cap"],
    }


def load() -> dict[str, Any]:
    with _lock:
        out = defaults()
        if _path().exists():
            try:
                out.update(json.loads(_path().read_text()))
            except ValueError:
                pass
    apply_caps(out)
    return out


def save(changes: dict[str, Any]) -> dict[str, Any]:
    current = load()
    allowed = set(defaults())
    for k, v in changes.items():
        if k not in allowed:
            raise ValueError(f"Unknown setting {k!r}")
        if k == "mode" and v not in MODES:
            raise ValueError(f"mode must be one of {', '.join(MODES)}")
        if k.endswith("_cap") and (not isinstance(v, int) or v < 0):
            raise ValueError(f"{k} must be a non-negative integer")
        current[k] = v
    with _lock:
        _path().write_text(json.dumps(current, indent=2))
    apply_caps(current)
    return current


def apply_caps(s: dict[str, Any]) -> None:
    """Caps set in the UI override the config file for this process."""
    budget = config.load_tunables()["budget"]
    for k in ("monthly_cap", "hourly_cap", "per_analysis_cap"):
        if isinstance(s.get(k), int):
            budget[k] = s[k]


def public() -> dict[str, Any]:
    s = load()
    secrets = config.load_secrets()
    return {**s, "serpapi_key_set": bool(secrets.serpapi_key), "deepseek_key_set": bool(secrets.deepseek_key)}
