"""Tests for lector.cli — every CLI command exercised via Typer's CliRunner.

Mocking strategy:
- ``get_engine`` → ``FakeKokoroEngine`` (needs 300 MB model files)
- ``run_player`` → no-op (would play audio on real hardware)
- ``download_models`` → no-op (would hit the network)
- ``subprocess.run`` → intercepted only where it calls clipboard tools
- ``install/uninstall_quick_action`` → real logic tested separately in
  test_macos_service; here we just prevent actual FS writes to ~/Library.

Everything else (argument parsing, text validation, ``create_player``
pipeline) runs for real.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

from lector.cli import app
from lector.config import DEFAULTS

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper: patch the heavy I/O boundaries
# ---------------------------------------------------------------------------


def _patch_tts_and_playback(fake_engine):
    """Context manager that replaces the TTS engine and suppresses audio."""
    return (
        patch("lector.tts.get_engine", return_value=fake_engine),
        patch("lector.tts._kokoro", fake_engine),  # bypass singleton check
        patch("lector.cli.run_player"),  # suppress audio hardware
    )


# ---------------------------------------------------------------------------
# lector (no args) / --help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
        # Typer/Click returns exit code 0 or 2 for help display
        assert result.exit_code in (0, 2)
        assert "read" in result.output.lower()

    def test_help_flag(self) -> None:
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "read" in result.output
        assert "voices" in result.output
        assert "download" in result.output


# ---------------------------------------------------------------------------
# lector read
# ---------------------------------------------------------------------------


class TestReadCommand:
    """The full pipeline runs: arg parsing → create_player → (mocked) playback."""

    def test_read_positional_text(self, fake_engine, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"  # does not exist → uses DEFAULTS
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, patch("lector.config.CONFIG_PATH", cfg_file):
            result = runner.invoke(app, ["read", "Hello, world!"])

        assert result.exit_code == 0
        mock_play.assert_called_once()
        # The player should get default voice/speed from config (== hardcoded DEFAULTS)
        player = mock_play.call_args[0][0]
        assert player.voice == DEFAULTS["voice"]
        assert player.speed == DEFAULTS["speed"]

    def test_read_custom_voice_and_speed(self, fake_engine) -> None:
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play:
            result = runner.invoke(app, ["read", "--voice", "af_nicole", "--speed", "1.5", "Test"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.voice == "af_nicole"
        assert player.speed == 1.5

    def test_read_custom_lang(self, fake_engine) -> None:
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play:
            result = runner.invoke(app, ["read", "--lang", "en-gb", "Good day"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.lang == "en-gb"

    def test_read_clipboard(self, fake_engine) -> None:
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with (
            p1,
            p2,
            p3 as mock_play,
            patch("lector.cli.read_clipboard", return_value="From clipboard"),
        ):
            result = runner.invoke(app, ["read", "--clipboard"])

        assert result.exit_code == 0
        mock_play.assert_called_once()

    def test_read_from_stdin(self, fake_engine) -> None:
        """Piped input (non-TTY stdin) should be read."""
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play:
            result = runner.invoke(app, ["read"], input="Hello from pipe")

        assert result.exit_code == 0
        mock_play.assert_called_once()

    def test_read_no_text_shows_error(self) -> None:
        """No text + TTY stdin → error."""
        with patch("lector.cli.sys") as mock_sys:
            mock_sys.stdin.isatty.return_value = True
            result = runner.invoke(app, ["read"])

        assert result.exit_code == 1
        assert "No text provided" in result.output

    def test_read_empty_text(self) -> None:
        result = runner.invoke(app, ["read", "   "])
        assert result.exit_code == 0
        assert "Nothing to read" in result.output

    def test_read_empty_clipboard(self) -> None:
        with patch("lector.cli.read_clipboard", return_value=""):
            result = runner.invoke(app, ["read", "--clipboard"])
        assert result.exit_code == 0
        assert "Nothing to read" in result.output

    def test_read_player_gets_phoneme_batches(self, fake_engine) -> None:
        """Verify create_player actually processed the text into chunks."""
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play:
            result = runner.invoke(app, ["read", "First sentence. Second sentence. Third."])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.expected_chunks >= 2


# ---------------------------------------------------------------------------
# lector voices
# ---------------------------------------------------------------------------


class TestVoicesCommand:
    def test_lists_voices(self, fake_engine) -> None:
        with patch("lector.cli.get_engine", return_value=fake_engine):
            result = runner.invoke(app, ["voices"])

        assert result.exit_code == 0
        assert "af_sky" in result.output
        assert "af_nicole" in result.output
        assert "am_adam" in result.output

    def test_voices_are_sorted(self, fake_engine) -> None:
        with patch("lector.cli.get_engine", return_value=fake_engine):
            result = runner.invoke(app, ["voices"])

        lines = [line.strip() for line in result.output.strip().splitlines() if line.strip()]
        assert lines == sorted(lines)


# ---------------------------------------------------------------------------
# lector download
# ---------------------------------------------------------------------------


class TestDownloadCommand:
    def test_download_default(self) -> None:
        with patch("lector.cli.download_models") as mock_dl:
            result = runner.invoke(app, ["download"])

        assert result.exit_code == 0
        mock_dl.assert_called_once_with(force=False)
        assert "Models ready" in result.output

    def test_download_force(self) -> None:
        with patch("lector.cli.download_models") as mock_dl:
            result = runner.invoke(app, ["download", "--force"])

        assert result.exit_code == 0
        mock_dl.assert_called_once_with(force=True)


# ---------------------------------------------------------------------------
# lector install-service
# ---------------------------------------------------------------------------


class TestInstallServiceCommand:
    def test_succeeds_on_macos(self, tmp_path: Path) -> None:
        with (
            patch("lector.cli.platform.system", return_value="Darwin"),
            patch("lector.cli.install_quick_action", return_value=tmp_path / "fake.workflow"),
        ):
            result = runner.invoke(app, ["install-service"])

        assert result.exit_code == 0
        assert "Quick Action installed" in result.output

    def test_rejects_on_linux(self) -> None:
        with patch("lector.cli.platform.system", return_value="Linux"):
            result = runner.invoke(app, ["install-service"])

        assert result.exit_code == 1
        assert "only available on macOS" in result.output

    def test_rejects_on_windows(self) -> None:
        with patch("lector.cli.platform.system", return_value="Windows"):
            result = runner.invoke(app, ["install-service"])

        assert result.exit_code == 1
        assert "only available on macOS" in result.output


# ---------------------------------------------------------------------------
# lector uninstall-service
# ---------------------------------------------------------------------------


class TestUninstallServiceCommand:
    def test_removes_existing(self, tmp_path: Path) -> None:
        with (
            patch("lector.cli.platform.system", return_value="Darwin"),
            patch("lector.cli.uninstall_quick_action", return_value=tmp_path / "fake.workflow"),
        ):
            result = runner.invoke(app, ["uninstall-service"])

        assert result.exit_code == 0
        assert "Quick Action removed" in result.output

    def test_reports_not_installed(self) -> None:
        with (
            patch("lector.cli.platform.system", return_value="Darwin"),
            patch("lector.cli.uninstall_quick_action", return_value=None),
        ):
            result = runner.invoke(app, ["uninstall-service"])

        assert result.exit_code == 0
        assert "was not installed" in result.output

    def test_rejects_on_linux(self) -> None:
        with patch("lector.cli.platform.system", return_value="Linux"):
            result = runner.invoke(app, ["uninstall-service"])

        assert result.exit_code == 1
        assert "only available on macOS" in result.output


# ---------------------------------------------------------------------------
# lector config
# ---------------------------------------------------------------------------


class TestConfigCommand:
    """Verify the ``config`` command for showing and setting preferences."""

    def test_show_defaults_when_no_file(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        with (
            patch("lector.config.CONFIG_PATH", cfg_file),
            patch(
                "lector.cli.load_config",
                wraps=__import__("lector.config", fromlist=["load_config"]).load_config,
            ),
        ):
            result = runner.invoke(app, ["config"])

        assert result.exit_code == 0
        assert str(DEFAULTS["voice"]) in result.output
        assert str(DEFAULTS["speed"]) in result.output

    def test_set_voice(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        with (
            patch("lector.config.CONFIG_PATH", cfg_file),
            patch(
                "lector.cli.save_config",
                wraps=__import__("lector.config", fromlist=["save_config"]).save_config,
            ),
            patch(
                "lector.cli.load_config",
                wraps=__import__("lector.config", fromlist=["load_config"]).load_config,
            ),
        ):
            result = runner.invoke(app, ["config", "--voice", "af_nicole"])

        assert result.exit_code == 0
        assert "Configuration saved" in result.output
        assert "af_nicole" in result.output

    def test_set_speed(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        with (
            patch("lector.config.CONFIG_PATH", cfg_file),
            patch(
                "lector.cli.save_config",
                wraps=__import__("lector.config", fromlist=["save_config"]).save_config,
            ),
            patch(
                "lector.cli.load_config",
                wraps=__import__("lector.config", fromlist=["load_config"]).load_config,
            ),
        ):
            result = runner.invoke(app, ["config", "--speed", "1.3"])

        assert result.exit_code == 0
        assert "Configuration saved" in result.output
        assert "1.3" in result.output

    def test_rejects_invalid_speed(self) -> None:
        result = runner.invoke(app, ["config", "--speed", "5.0"])
        assert result.exit_code == 1
        assert "Speed must be between" in result.output


# ---------------------------------------------------------------------------
# lector read — config-aware defaults
# ---------------------------------------------------------------------------


class TestReadConfigAware:
    """Verify that ``read`` picks up config-file defaults when no CLI flags."""

    def test_uses_config_voice(self, fake_engine, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('voice = "af_nicole"\nspeed = 1.0\n', encoding="utf-8")

        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, patch("lector.config.CONFIG_PATH", cfg_file):
            result = runner.invoke(app, ["read", "Hello"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.voice == "af_nicole"

    def test_cli_flag_overrides_config(self, fake_engine, tmp_path: Path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('voice = "af_nicole"\nspeed = 0.8\n', encoding="utf-8")

        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, patch("lector.config.CONFIG_PATH", cfg_file):
            result = runner.invoke(app, ["read", "--voice", "af_sky", "--speed", "1.5", "Hello"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.voice == "af_sky"
        assert player.speed == 1.5
