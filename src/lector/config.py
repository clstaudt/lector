"""Persistent user configuration — load and save preferred defaults."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

CONFIG_PATH = Path.home() / ".lector" / "config.toml"

DEFAULTS: dict[str, object] = {
    "voice": "af_sky",
    "speed": 1.0,
}

SPEED_MIN = 0.5
SPEED_MAX = 2.0


def load_config() -> dict[str, object]:
    """Load user config from disk, merged over hardcoded defaults.

    Return *DEFAULTS* if the file is missing or malformed.  On parse
    errors a warning is printed to stderr.
    """
    cfg: dict[str, object] = dict(DEFAULTS)
    if not CONFIG_PATH.is_file():
        return cfg

    try:
        with CONFIG_PATH.open("rb") as fh:
            user = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        print(f"Warning: ignoring malformed {CONFIG_PATH}: {exc}", file=sys.stderr)
        return cfg

    if "voice" in user and isinstance(user["voice"], str):
        cfg["voice"] = user["voice"]
    if "speed" in user and isinstance(user["speed"], int | float):
        cfg["speed"] = float(user["speed"])

    return cfg


def save_config(*, voice: str | None = None, speed: float | None = None) -> None:
    """Persist preferred voice and/or speed to *CONFIG_PATH*.

    Merge the given values into the existing config so that setting one
    key does not erase the other.  Raise ``ValueError`` if *speed* is
    outside the allowed range.
    """
    if speed is not None and not (SPEED_MIN <= speed <= SPEED_MAX):
        msg = f"Speed must be between {SPEED_MIN} and {SPEED_MAX}, got {speed}"
        raise ValueError(msg)

    cfg = load_config()

    if voice is not None:
        cfg["voice"] = voice
    if speed is not None:
        cfg["speed"] = speed

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        f'voice = "{cfg["voice"]}"\nspeed = {cfg["speed"]}\n',
        encoding="utf-8",
    )
