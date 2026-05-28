"""Tests for lector.cli — every CLI command exercised via Typer's CliRunner.

Property-based: voice/speed/lang pass-through tested with hypothesis
strategies to verify the pipeline never drops or mutates metadata.
Example-based: error paths (empty text, missing input, non-macOS
platform guard) are discrete cases best checked by example.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from typer.testing import CliRunner

from lector.cli import app

from .conftest import FakeKokoroEngine

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


# ---------------------------------------------------------------------------
# Helper: patch the heavy I/O boundaries
# ---------------------------------------------------------------------------


def _patch_tts_and_playback(fake_engine):
    """Return a tuple of context managers that replace TTS engine and suppress audio."""
    return (
        patch("lector.tts.get_engine", return_value=fake_engine),
        patch("lector.tts._kokoro", fake_engine),
        patch("lector.cli.run_player"),
    )


# ---------------------------------------------------------------------------
# lector (no args) / --help
# ---------------------------------------------------------------------------


def test_no_args_shows_help() -> None:
    """Invoking lector without arguments shows help text."""
    result = runner.invoke(app, [])
    assert result.exit_code in (0, 2)
    assert "read" in result.output.lower()


def test_help_flag() -> None:
    """--help lists all commands."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for cmd in ("read", "voices", "download"):
        assert cmd in result.output


# ---------------------------------------------------------------------------
# Property: read command preserves voice/speed/lang metadata
# ---------------------------------------------------------------------------


@given(
    voice=st.sampled_from(["af_sky", "af_nicole", "am_adam"]),
    speed=st.sampled_from(["0.5", "1.0", "1.5", "2.0"]),
    lang=st.sampled_from(["en-us", "en-gb"]),
)
@settings(max_examples=20)
def test_read_metadata_passes_through(voice: str, speed: str, lang: str) -> None:
    """Voice, speed, and lang given on the CLI must reach the player object."""
    engine = FakeKokoroEngine()
    p1, p2, p3 = _patch_tts_and_playback(engine)
    with p1, p2, p3 as mock_play:
        result = runner.invoke(
            app, ["read", "--voice", voice, "--speed", speed, "--lang", lang, "Hello world"]
        )

    assert result.exit_code == 0
    player = mock_play.call_args[0][0]
    assert player.voice == voice
    assert player.speed == float(speed)
    assert player.lang == lang


# ---------------------------------------------------------------------------
# lector read — example-based edge cases
# ---------------------------------------------------------------------------


class TestReadEdgeCases:
    """Error and empty-input paths — discrete cases."""

    def test_read_positional_text(self, fake_engine) -> None:
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play:
            result = runner.invoke(app, ["read", "Hello, world!"])
        assert result.exit_code == 0
        mock_play.assert_called_once()

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
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play:
            result = runner.invoke(app, ["read"], input="Hello from pipe")
        assert result.exit_code == 0
        mock_play.assert_called_once()

    def test_read_no_text_shows_error(self) -> None:
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

    def test_multi_sentence_produces_chunks(self, fake_engine) -> None:
        """Verify create_player actually processed the text into chunks."""
        p1, p2, p3 = _patch_tts_and_playback(fake_engine)
        with p1, p2, p3 as mock_play:
            result = runner.invoke(app, ["read", "First sentence. Second sentence. Third."])
        assert result.exit_code == 0
        player = mock_play.call_args[0][0]
        assert player.expected_chunks >= 2


# ---------------------------------------------------------------------------
# lector voices — property: output is sorted
# ---------------------------------------------------------------------------


def test_voices_are_sorted(fake_engine) -> None:
    """Voice list must be lexicographically sorted."""
    with patch("lector.cli.get_engine", return_value=fake_engine):
        result = runner.invoke(app, ["voices"])
    assert result.exit_code == 0
    lines = [line.strip() for line in result.output.strip().splitlines() if line.strip()]
    assert lines == sorted(lines)


def test_voices_lists_all(fake_engine) -> None:
    """All voices from the engine must appear in the output."""
    with patch("lector.cli.get_engine", return_value=fake_engine):
        result = runner.invoke(app, ["voices"])
    assert result.exit_code == 0
    for v in fake_engine.get_voices():
        assert v in result.output


# ---------------------------------------------------------------------------
# lector download
# ---------------------------------------------------------------------------


def test_download_default() -> None:
    """Default download does not force."""
    with patch("lector.cli.download_models") as mock_dl:
        result = runner.invoke(app, ["download"])
    assert result.exit_code == 0
    mock_dl.assert_called_once_with(force=False)
    assert "Models ready" in result.output


def test_download_force() -> None:
    """--force flag is forwarded to download_models."""
    with patch("lector.cli.download_models") as mock_dl:
        result = runner.invoke(app, ["download", "--force"])
    assert result.exit_code == 0
    mock_dl.assert_called_once_with(force=True)


# ---------------------------------------------------------------------------
# lector install-service / uninstall-service — platform guard
# ---------------------------------------------------------------------------


class TestServiceCommands:
    """Platform guard and happy-path for service install/uninstall."""

    def test_install_succeeds_on_macos(self, tmp_path: Path) -> None:
        with (
            patch("lector.cli.platform.system", return_value="Darwin"),
            patch("lector.cli.install_quick_action", return_value=tmp_path / "fake.workflow"),
        ):
            result = runner.invoke(app, ["install-service"])
        assert result.exit_code == 0
        assert "Quick Action installed" in result.output

    @pytest.mark.parametrize("os_name", ["Linux", "Windows"])
    def test_install_rejects_non_macos(self, os_name: str) -> None:
        with patch("lector.cli.platform.system", return_value=os_name):
            result = runner.invoke(app, ["install-service"])
        assert result.exit_code == 1
        assert "only available on macOS" in result.output

    def test_uninstall_removes_existing(self, tmp_path: Path) -> None:
        with (
            patch("lector.cli.platform.system", return_value="Darwin"),
            patch("lector.cli.uninstall_quick_action", return_value=tmp_path / "fake.workflow"),
        ):
            result = runner.invoke(app, ["uninstall-service"])
        assert result.exit_code == 0
        assert "Quick Action removed" in result.output

    def test_uninstall_reports_not_installed(self) -> None:
        with (
            patch("lector.cli.platform.system", return_value="Darwin"),
            patch("lector.cli.uninstall_quick_action", return_value=None),
        ):
            result = runner.invoke(app, ["uninstall-service"])
        assert result.exit_code == 0
        assert "was not installed" in result.output

    def test_uninstall_rejects_on_linux(self) -> None:
        with patch("lector.cli.platform.system", return_value="Linux"):
            result = runner.invoke(app, ["uninstall-service"])
        assert result.exit_code == 1
        assert "only available on macOS" in result.output
