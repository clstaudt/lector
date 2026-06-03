"""Tests for lector.cli — every CLI command exercised via Typer's CliRunner.

Mocking strategy:
- ``get_engine`` → ``FakeKokoroEngine`` (needs 300 MB model files)
- ``run_player`` → no-op (would play audio on real hardware)
- ``download_models`` → no-op (would hit the network)
- ``subprocess.run`` → intercepted only where it calls clipboard tools
- ``install/uninstall_quick_action`` → real logic tested separately in
  test_macos_service; here we just prevent actual FS writes to ~/Library.
- ``detect_language`` → returns "en-us" by default so tests don't hit
  the fast-langdetect model.

Everything else (argument parsing, text validation, ``create_player``
pipeline) runs for real.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

from typer.testing import CliRunner

from lector.cli import app

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()

_DEFAULT_DETECT = patch("lector.cli.detect_language", return_value="en-us")


# ---------------------------------------------------------------------------
# Helper: patch the heavy I/O boundaries
# ---------------------------------------------------------------------------


def _patch_tts_and_playback(fake_engine):
    """Context manager that replaces the TTS engine and suppresses audio."""
    return (
        patch("lector.tts.get_engine", return_value=fake_engine),
        patch("lector.tts._kokoro", fake_engine),
        patch("lector.cli.run_player"),
        _DEFAULT_DETECT,
    )


# ---------------------------------------------------------------------------
# lector (no args) / --help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_no_args_shows_help(self) -> None:
        result = runner.invoke(app, [])
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

    def test_read_positional_text(self, fake_engine) -> None:
        p1, p2, p3, p4 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, p4:
            result = runner.invoke(app, ["read", "Hello, world!"])

        assert result.exit_code == 0
        mock_play.assert_called_once()
        player = mock_play.call_args[0][0]
        assert player.voice == "af_sky"
        assert player.speed == 1.0

    def test_read_custom_voice_and_speed(self, fake_engine) -> None:
        p1, p2, p3, p4 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, p4:
            result = runner.invoke(app, ["read", "--voice", "af_nicole", "--speed", "1.5", "Test"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.voice == "af_nicole"
        assert player.speed == 1.5

    def test_read_custom_lang(self, fake_engine) -> None:
        p1, p2, p3, p4 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, p4:
            result = runner.invoke(app, ["read", "--lang", "en-gb", "Good day"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.lang == "en-gb"

    def test_read_auto_lang_detects_english(self, fake_engine) -> None:
        p1, p2, p3, _ = _patch_tts_and_playback(fake_engine)
        with (
            p1,
            p2,
            p3 as mock_play,
            patch("lector.cli.detect_language", return_value="en-us"),
        ):
            result = runner.invoke(app, ["read", "Hello, world!"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.lang == "en-us"
        assert player.voice == "af_sky"

    def test_read_auto_lang_detects_german(self, fake_engine) -> None:
        p1, p2, p3, _ = _patch_tts_and_playback(fake_engine)
        with (
            p1,
            p2,
            p3 as mock_play,
            patch("lector.cli.detect_language", return_value="de"),
            patch("lector.tts.get_engine", return_value=fake_engine),
        ):
            result = runner.invoke(app, ["read", "Guten Morgen, wie geht es Ihnen?"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.lang == "de"
        assert player.voice == "martin"

    def test_read_voice_implies_language(self, fake_engine) -> None:
        """When --voice is given but --lang is auto, infer lang from voice prefix."""
        p1, p2, p3, p4 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, p4:
            result = runner.invoke(app, ["read", "--voice", "bf_emma", "Good day"])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.lang == "en-gb"
        assert player.voice == "bf_emma"

    def test_read_clipboard(self, fake_engine) -> None:
        p1, p2, p3, p4 = _patch_tts_and_playback(fake_engine)
        with (
            p1,
            p2,
            p3 as mock_play,
            p4,
            patch("lector.cli.read_clipboard", return_value="From clipboard"),
        ):
            result = runner.invoke(app, ["read", "--clipboard"])

        assert result.exit_code == 0
        mock_play.assert_called_once()

    def test_read_from_stdin(self, fake_engine) -> None:
        """Piped input (non-TTY stdin) should be read."""
        p1, p2, p3, p4 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, p4:
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
        p1, p2, p3, p4 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play, p4:
            result = runner.invoke(app, ["read", "First sentence. Second sentence. Third."])

        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.expected_chunks >= 2


# ---------------------------------------------------------------------------
# lector voices
# ---------------------------------------------------------------------------


class TestVoicesCommand:
    def test_lists_voices_table(self, fake_engine) -> None:
        with patch("lector.tts.get_engine", return_value=fake_engine):
            result = runner.invoke(app, ["voices"])

        assert result.exit_code == 0
        assert "Available Voices" in result.output

    def test_voices_filtered_by_lang(self, fake_engine) -> None:
        with patch("lector.tts.get_engine", return_value=fake_engine):
            result = runner.invoke(app, ["voices", "--lang", "en-us"])

        assert result.exit_code == 0
        assert "English (US)" in result.output


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

    def test_download_german(self) -> None:
        with patch("lector.cli.download_german_models") as mock_dl:
            result = runner.invoke(app, ["download", "--german"])

        assert result.exit_code == 0
        mock_dl.assert_called_once_with(force=False)


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
