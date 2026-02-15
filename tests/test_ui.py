"""Tests for lector.ui — mode selection and terminal helpers.

Mocking strategy:
- ``_run_interactive`` / ``_run_headless`` → no-op (would play audio and
  require a real terminal).
- ``sys.stdin.isatty`` / ``sys.stderr.isatty`` → controlled per-test to
  exercise the interactive-vs-headless decision in ``run_player``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from lector.ui import run_player

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
