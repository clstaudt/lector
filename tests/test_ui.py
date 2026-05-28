"""Tests for lector.ui — mode selection, time formatting, and key mapping.

Contract-based: ``deal.cases`` auto-tests ``_fmt_time`` contracts
(non-negative input, colon in output).
Property-based: ``_fmt_time`` round-trip and format properties checked
with hypothesis.  Mode selection exhaustively parametrized over the
boolean TTY matrix.
Example-based: key-action mapping completeness (discrete finite set).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import deal
import pytest
from hypothesis import given
from hypothesis import strategies as st

from lector.ui import _KEY_ACTIONS, _fmt_time, run_player

# ---------------------------------------------------------------------------
# Contract-driven tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", deal.cases(_fmt_time))
def test_fmt_time_contracts(case: deal.TestCase) -> None:
    """Verify _fmt_time contracts: non-negative input, colon in output."""
    case()


# ---------------------------------------------------------------------------
# Properties: _fmt_time
# ---------------------------------------------------------------------------


@given(seconds=st.floats(min_value=0, max_value=36_000, allow_nan=False))
def test_fmt_time_always_has_colon(seconds: float) -> None:
    """Output always contains a colon separator."""
    assert ":" in _fmt_time(seconds)


@given(seconds=st.floats(min_value=0, max_value=36_000, allow_nan=False))
def test_fmt_time_minutes_seconds_format(seconds: float) -> None:
    """Output is M:SS where SS is always two digits."""
    result = _fmt_time(seconds)
    parts = result.split(":")
    assert len(parts) == 2
    assert len(parts[1]) == 2
    assert parts[1].isdigit()
    assert parts[0].lstrip("-").isdigit()


@given(seconds=st.integers(min_value=0, max_value=36_000))
def test_fmt_time_round_trip(seconds: int) -> None:
    """Parsing the formatted string back yields the original seconds."""
    result = _fmt_time(seconds)
    m_str, s_str = result.split(":")
    reconstructed = int(m_str) * 60 + int(s_str)
    assert reconstructed == seconds


def test_fmt_time_exact_values() -> None:
    """Spot-check known conversions."""
    assert _fmt_time(0) == "0:00"
    assert _fmt_time(59) == "0:59"
    assert _fmt_time(60) == "1:00"
    assert _fmt_time(90) == "1:30"
    assert _fmt_time(3600) == "60:00"


# ---------------------------------------------------------------------------
# Properties: _KEY_ACTIONS mapping
# ---------------------------------------------------------------------------

_VALID_PLAYER_ACTIONS = {
    "toggle_pause",
    "stop",
    "restart",
    "next_chunk",
    "prev_chunk",
    "speed_up",
    "speed_down",
}


def test_all_key_actions_are_valid_player_methods() -> None:
    """Every action in the key map must be a known player method."""
    for action in _KEY_ACTIONS.values():
        assert action in _VALID_PLAYER_ACTIONS


def test_essential_keys_are_mapped() -> None:
    """Space (pause), q (quit), and arrow keys must have bindings."""
    assert "space" in _KEY_ACTIONS
    assert "q" in _KEY_ACTIONS
    assert "right" in _KEY_ACTIONS
    assert "left" in _KEY_ACTIONS


# ---------------------------------------------------------------------------
# run_player mode selection — exhaustive boolean matrix
# ---------------------------------------------------------------------------

_MODE_CASES = [
    (True, True, "interactive"),
    (True, False, "headless"),
    (False, True, "headless"),
    (False, False, "headless"),
]


@pytest.mark.parametrize(("stdin_tty", "stderr_tty", "expected_mode"), _MODE_CASES)
def test_run_player_mode_selection(stdin_tty: bool, stderr_tty: bool, expected_mode: str) -> None:
    """run_player dispatches to interactive only when both stdin and stderr are TTYs."""
    player = MagicMock()
    with (
        patch("lector.ui.sys") as mock_sys,
        patch("lector.ui._run_interactive") as mock_interactive,
        patch("lector.ui._run_headless") as mock_headless,
    ):
        mock_sys.stdin.isatty.return_value = stdin_tty
        mock_sys.stderr.isatty.return_value = stderr_tty
        run_player(player)

    if expected_mode == "interactive":
        mock_interactive.assert_called_once_with(player)
        mock_headless.assert_not_called()
    else:
        mock_headless.assert_called_once_with(player)
        mock_interactive.assert_not_called()
