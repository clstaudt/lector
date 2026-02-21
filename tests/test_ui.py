"""Tests for lector.ui — mode selection, terminal helpers, and save-defaults flow.

Mocking strategy:
- ``_run_interactive`` / ``_run_headless`` → no-op (would play audio and
  require a real terminal).
- ``sys.stdin.isatty`` / ``sys.stderr.isatty`` → controlled per-test to
  exercise the interactive-vs-headless decision in ``run_player``.
- ``save_config`` → intercepted to prevent filesystem writes.
- ``_read_key`` → simulated key sequences for save-defaults tests.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lector.ui import _handle_save_defaults, run_player

# ---------------------------------------------------------------------------
# run_player mode selection
# ---------------------------------------------------------------------------


class TestRunPlayerModeSelection:
    """Verify that ``run_player`` dispatches to the correct backend."""

    @staticmethod
    def _fake_player() -> MagicMock:
        """Return a lightweight stand-in for ``AudioPlayer``."""
        return MagicMock()

    def test_interactive_when_both_ttys(self) -> None:
        """Interactive mode requires both stdin and stderr to be TTYs."""
        player = self._fake_player()
        with (
            patch("lector.ui.sys") as mock_sys,
            patch("lector.ui._run_interactive") as mock_interactive,
            patch("lector.ui._run_headless") as mock_headless,
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr.isatty.return_value = True

            run_player(player)

        mock_interactive.assert_called_once_with(player)
        mock_headless.assert_not_called()

    def test_headless_when_stdin_is_pipe(self) -> None:
        """Piped stdin (e.g. ``pbpaste | lector read``) must use headless mode.

        This is the regression scenario: stderr is still a TTY (the user
        has a terminal), but stdin is a pipe so cbreak mode cannot be set.
        """
        player = self._fake_player()
        with (
            patch("lector.ui.sys") as mock_sys,
            patch("lector.ui._run_interactive") as mock_interactive,
            patch("lector.ui._run_headless") as mock_headless,
        ):
            mock_sys.stdin.isatty.return_value = False
            mock_sys.stderr.isatty.return_value = True

            run_player(player)

        mock_headless.assert_called_once_with(player)
        mock_interactive.assert_not_called()

    def test_headless_when_stderr_is_not_tty(self) -> None:
        """Non-TTY stderr (e.g. Automator Quick Action) → headless."""
        player = self._fake_player()
        with (
            patch("lector.ui.sys") as mock_sys,
            patch("lector.ui._run_interactive") as mock_interactive,
            patch("lector.ui._run_headless") as mock_headless,
        ):
            mock_sys.stdin.isatty.return_value = True
            mock_sys.stderr.isatty.return_value = False

            run_player(player)

        mock_headless.assert_called_once_with(player)
        mock_interactive.assert_not_called()

    def test_headless_when_neither_is_tty(self) -> None:
        """Neither stdin nor stderr is a TTY → headless."""
        player = self._fake_player()
        with (
            patch("lector.ui.sys") as mock_sys,
            patch("lector.ui._run_interactive") as mock_interactive,
            patch("lector.ui._run_headless") as mock_headless,
        ):
            mock_sys.stdin.isatty.return_value = False
            mock_sys.stderr.isatty.return_value = False

            run_player(player)

        mock_headless.assert_called_once_with(player)
        mock_interactive.assert_not_called()


# ---------------------------------------------------------------------------
# Save-defaults flow (s → y/n)
# ---------------------------------------------------------------------------


class TestSaveDefaults:
    """Verify the interactive save-defaults prompt triggered by the 's' key."""

    @staticmethod
    def _fake_player(voice: str = "af_sky", speed: float = 1.0) -> MagicMock:
        """Return a lightweight stand-in for ``AudioPlayer``."""
        player = MagicMock()
        player.voice = voice
        player.speed = speed
        return player

    def test_confirm_saves_config(self) -> None:
        """Pressing 'y' after 's' calls save_config with player values."""
        player = self._fake_player(voice="af_nicole", speed=1.3)
        live = MagicMock()

        with (
            patch("lector.ui.save_config") as mock_save,
            patch("lector.ui._read_key", return_value="y"),
            patch("lector.ui._build_display"),
        ):
            _handle_save_defaults(player, live)

        mock_save.assert_called_once_with(voice="af_nicole", speed=1.3)

    def test_cancel_does_not_save(self) -> None:
        """Pressing 'n' after 's' does not call save_config."""
        player = self._fake_player()
        live = MagicMock()

        with (
            patch("lector.ui.save_config") as mock_save,
            patch("lector.ui._read_key", return_value="n"),
            patch("lector.ui._build_display"),
        ):
            _handle_save_defaults(player, live)

        mock_save.assert_not_called()

    def test_any_key_cancels(self) -> None:
        """Any key other than 'y' cancels the save."""
        player = self._fake_player()
        live = MagicMock()

        with (
            patch("lector.ui.save_config") as mock_save,
            patch("lector.ui._read_key", return_value="x"),
            patch("lector.ui._build_display"),
        ):
            _handle_save_defaults(player, live)

        mock_save.assert_not_called()

    def test_flash_message_set_on_save(self) -> None:
        """A flash message is set after successful save."""
        player = self._fake_player()
        live = MagicMock()

        with (
            patch("lector.ui.save_config"),
            patch("lector.ui._read_key", return_value="y"),
            patch("lector.ui._set_flash") as mock_flash,
            patch("lector.ui._build_display"),
        ):
            _handle_save_defaults(player, live)

        # First call is the prompt, second is the confirmation
        assert mock_flash.call_count == 2
        assert "Saved" in mock_flash.call_args_list[1][0][0]

    def test_flash_message_set_on_cancel(self) -> None:
        """A flash message is set after cancellation."""
        player = self._fake_player()
        live = MagicMock()

        with (
            patch("lector.ui._read_key", return_value="n"),
            patch("lector.ui._set_flash") as mock_flash,
            patch("lector.ui._build_display"),
        ):
            _handle_save_defaults(player, live)

        assert mock_flash.call_count == 2
        assert "Cancelled" in mock_flash.call_args_list[1][0][0]
