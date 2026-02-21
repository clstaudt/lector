"""Tests for lector.config — persistent user configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from lector.config import DEFAULTS, load_config, save_config

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


class TestLoadConfig:
    """Verify config loading, merging, and graceful error handling."""

    def test_returns_defaults_when_no_file(self, tmp_path: Path) -> None:
        """Missing config file → fall back to hardcoded defaults."""
        with patch("lector.config.CONFIG_PATH", tmp_path / "missing.toml"):
            cfg = load_config()

        assert cfg == DEFAULTS

    def test_merges_partial_config_voice_only(self, tmp_path: Path) -> None:
        """Config with only ``voice`` → speed comes from defaults."""
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('voice = "af_nicole"\n', encoding="utf-8")

        with patch("lector.config.CONFIG_PATH", cfg_file):
            cfg = load_config()

        assert cfg["voice"] == "af_nicole"
        assert cfg["speed"] == DEFAULTS["speed"]

    def test_merges_partial_config_speed_only(self, tmp_path: Path) -> None:
        """Config with only ``speed`` → voice comes from defaults."""
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("speed = 1.3\n", encoding="utf-8")

        with patch("lector.config.CONFIG_PATH", cfg_file):
            cfg = load_config()

        assert cfg["voice"] == DEFAULTS["voice"]
        assert cfg["speed"] == 1.3

    def test_full_config_override(self, tmp_path: Path) -> None:
        """Both keys present → both overridden."""
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('voice = "am_adam"\nspeed = 0.8\n', encoding="utf-8")

        with patch("lector.config.CONFIG_PATH", cfg_file):
            cfg = load_config()

        assert cfg["voice"] == "am_adam"
        assert cfg["speed"] == 0.8

    def test_ignores_malformed_toml(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Malformed TOML → defaults returned, warning printed."""
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("not valid toml {{{\n", encoding="utf-8")

        with patch("lector.config.CONFIG_PATH", cfg_file):
            cfg = load_config()

        assert cfg == DEFAULTS
        captured = capsys.readouterr()
        assert "Warning" in captured.err

    def test_ignores_wrong_type_for_voice(self, tmp_path: Path) -> None:
        """Non-string ``voice`` is ignored."""
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("voice = 42\nspeed = 1.1\n", encoding="utf-8")

        with patch("lector.config.CONFIG_PATH", cfg_file):
            cfg = load_config()

        assert cfg["voice"] == DEFAULTS["voice"]
        assert cfg["speed"] == 1.1

    def test_ignores_wrong_type_for_speed(self, tmp_path: Path) -> None:
        """Non-numeric ``speed`` is ignored."""
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('voice = "af_sky"\nspeed = "fast"\n', encoding="utf-8")

        with patch("lector.config.CONFIG_PATH", cfg_file):
            cfg = load_config()

        assert cfg["voice"] == "af_sky"
        assert cfg["speed"] == DEFAULTS["speed"]


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


class TestSaveConfig:
    """Verify config persistence, merging, and validation."""

    def test_creates_file_and_parent(self, tmp_path: Path) -> None:
        """Save creates the config file (and parent directories)."""
        cfg_file = tmp_path / "sub" / "config.toml"

        with patch("lector.config.CONFIG_PATH", cfg_file):
            save_config(voice="af_nicole", speed=0.9)

        assert cfg_file.exists()
        content = cfg_file.read_text(encoding="utf-8")
        assert 'voice = "af_nicole"' in content
        assert "speed = 0.9" in content

    def test_merges_without_erasing(self, tmp_path: Path) -> None:
        """Setting voice alone preserves existing speed."""
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('voice = "af_sky"\nspeed = 1.5\n', encoding="utf-8")

        with patch("lector.config.CONFIG_PATH", cfg_file):
            save_config(voice="af_nicole")

        content = cfg_file.read_text(encoding="utf-8")
        assert 'voice = "af_nicole"' in content
        assert "speed = 1.5" in content

    def test_merges_speed_preserves_voice(self, tmp_path: Path) -> None:
        """Setting speed alone preserves existing voice."""
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('voice = "am_adam"\nspeed = 1.0\n', encoding="utf-8")

        with patch("lector.config.CONFIG_PATH", cfg_file):
            save_config(speed=0.7)

        content = cfg_file.read_text(encoding="utf-8")
        assert 'voice = "am_adam"' in content
        assert "speed = 0.7" in content

    def test_rejects_speed_too_low(self) -> None:
        """Speed below minimum raises ValueError."""
        with pytest.raises(ValueError, match="Speed must be between"):
            save_config(speed=0.1)

    def test_rejects_speed_too_high(self) -> None:
        """Speed above maximum raises ValueError."""
        with pytest.raises(ValueError, match="Speed must be between"):
            save_config(speed=3.0)

    def test_accepts_boundary_speeds(self, tmp_path: Path) -> None:
        """Min and max boundary values are accepted."""
        cfg_file = tmp_path / "config.toml"

        with patch("lector.config.CONFIG_PATH", cfg_file):
            save_config(speed=0.5)
            content = cfg_file.read_text(encoding="utf-8")
            assert "speed = 0.5" in content

            save_config(speed=2.0)
            content = cfg_file.read_text(encoding="utf-8")
            assert "speed = 2.0" in content
