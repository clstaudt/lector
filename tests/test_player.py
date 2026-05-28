"""Tests for lector.player — AudioPlayer with real numpy buffers.

The only mock is ``sounddevice.OutputStream`` (audio hardware).

Property-based: a ``RuleBasedStateMachine`` exercises random sequences
of transport actions and verifies invariants hold after every step.
Contract-based: ``speed_up`` / ``speed_down`` carry ``@deal.ensure``
that speed stays in bounds — verified via the state machine invariants.
Example-based: callback behaviour and stream open/close are kept as
example tests (exact numerical results, hardware boundary).
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from hypothesis import settings
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from lector.player import AudioPlayer

from .conftest import FakeKokoroEngine, generate_fully, make_player

# ---------------------------------------------------------------------------
# Property: speed always stays in bounds (exercises the @deal.ensure contract)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("start_speed", [AudioPlayer.SPEED_MIN, 1.0, AudioPlayer.SPEED_MAX])
def test_speed_up_stays_in_bounds(fake_engine: FakeKokoroEngine, start_speed: float) -> None:
    """speed_up must never exceed SPEED_MAX (contract enforced)."""
    p = make_player(fake_engine, speed=start_speed)
    p.speed_up()
    assert AudioPlayer.SPEED_MIN <= p.speed <= AudioPlayer.SPEED_MAX


@pytest.mark.parametrize("start_speed", [AudioPlayer.SPEED_MIN, 1.0, AudioPlayer.SPEED_MAX])
def test_speed_down_stays_in_bounds(fake_engine: FakeKokoroEngine, start_speed: float) -> None:
    """speed_down must never go below SPEED_MIN (contract enforced)."""
    p = make_player(fake_engine, speed=start_speed)
    p.speed_down()
    assert AudioPlayer.SPEED_MIN <= p.speed <= AudioPlayer.SPEED_MAX


# ---------------------------------------------------------------------------
# Stateful property test: random transport control sequences
# ---------------------------------------------------------------------------


class AudioPlayerStateMachine(RuleBasedStateMachine):
    """Exercise random sequences of transport actions on a pre-generated player.

    Invariants checked after every step:
    - speed is always in [SPEED_MIN, SPEED_MAX]
    - playback_time is never negative
    - buffered_duration is never negative
    - pause is a boolean toggle
    """

    def __init__(self) -> None:
        super().__init__()
        engine = FakeKokoroEngine()
        self.player = make_player(engine, text="Alpha. Bravo. Charlie. Delta. Echo.")
        generate_fully(self.player)

    @rule()
    def toggle_pause(self) -> None:
        """Toggle pause state."""
        self.player.toggle_pause()

    @rule()
    def speed_up(self) -> None:
        """Increase speed."""
        self.player.speed_up()

    @rule()
    def speed_down(self) -> None:
        """Decrease speed."""
        self.player.speed_down()

    @rule()
    def next_chunk(self) -> None:
        """Jump forward one chunk."""
        self.player.next_chunk()

    @rule()
    def prev_chunk(self) -> None:
        """Jump backward one chunk."""
        self.player.prev_chunk()

    @rule()
    def restart(self) -> None:
        """Restart from beginning."""
        self.player.restart()

    # -- invariants (checked after every step) ----------------------------

    @invariant()
    def speed_in_bounds(self) -> None:
        """Speed must stay within [SPEED_MIN, SPEED_MAX]."""
        assert AudioPlayer.SPEED_MIN <= self.player.speed <= AudioPlayer.SPEED_MAX

    @invariant()
    def playback_time_non_negative(self) -> None:
        """Playback time must never go negative."""
        assert self.player.playback_time >= 0

    @invariant()
    def buffered_duration_non_negative(self) -> None:
        """Buffered duration must never go negative."""
        assert self.player.buffered_duration >= 0

    @invariant()
    def chunks_received_consistent(self) -> None:
        """Chunks received must not exceed expected chunks."""
        assert self.player.chunks_received <= self.player.expected_chunks

    @invariant()
    def current_chunk_index_non_negative(self) -> None:
        """Current chunk index must be non-negative."""
        assert self.player.current_chunk_index >= 0


TestTransportSequences = AudioPlayerStateMachine.TestCase
TestTransportSequences.settings = settings(max_examples=50, stateful_step_count=20, deadline=None)


# ---------------------------------------------------------------------------
# Properties: toggle_pause is involutory
# ---------------------------------------------------------------------------


def test_toggle_pause_is_involutory(fake_engine: FakeKokoroEngine) -> None:
    """Toggling pause twice returns to the original state."""
    p = make_player(fake_engine)
    original = p.is_paused
    p.toggle_pause()
    p.toggle_pause()
    assert p.is_paused == original


# ---------------------------------------------------------------------------
# Properties: generation produces valid audio
# ---------------------------------------------------------------------------


def test_generation_produces_all_chunks(fake_engine: FakeKokoroEngine) -> None:
    """After full generation, chunks_received equals expected_chunks."""
    p = make_player(fake_engine)
    generate_fully(p)
    assert p.generation_done
    assert p.chunks_received == p.expected_chunks


def test_buffer_is_float32(fake_engine: FakeKokoroEngine) -> None:
    """Generated audio buffer must be float32."""
    p = make_player(fake_engine)
    generate_fully(p)
    assert p._buffer.dtype == np.float32


def test_chunk_starts_monotonically_increasing(fake_engine: FakeKokoroEngine) -> None:
    """Chunk boundary offsets must be strictly increasing."""
    p = make_player(fake_engine, text="A. B. C.")
    generate_fully(p)
    for i in range(1, len(p._chunk_starts)):
        assert p._chunk_starts[i] > p._chunk_starts[i - 1]


def test_chunk_starts_count_matches_received(fake_engine: FakeKokoroEngine) -> None:
    """Number of chunk boundaries must equal chunks_received."""
    p = make_player(fake_engine, text="A. B. C.")
    generate_fully(p)
    assert len(p._chunk_starts) == p.chunks_received


# ---------------------------------------------------------------------------
# Properties: initial state
# ---------------------------------------------------------------------------


def test_fresh_player_is_idle(fake_engine: FakeKokoroEngine) -> None:
    """A new player has zero position and no flags set."""
    p = make_player(fake_engine)
    assert not p.is_paused
    assert not p.is_stopped
    assert not p.is_finished
    assert p.playback_time == 0.0
    assert p.chunks_received == 0


# ---------------------------------------------------------------------------
# Example: speed change invalidates future chunks (epoch bump)
# ---------------------------------------------------------------------------


def test_speed_change_bumps_gen_epoch(fake_engine: FakeKokoroEngine) -> None:
    """After speed change, generation epoch must increase (future audio invalidated)."""
    p = make_player(fake_engine)
    generate_fully(p)
    epoch_before = p._gen_epoch
    p.speed_up()
    assert p._gen_epoch > epoch_before


# ---------------------------------------------------------------------------
# Sounddevice callback — example tests (exact numerical behaviour)
# ---------------------------------------------------------------------------


class TestCallback:
    """Test the _callback method with real numpy arrays."""

    def test_callback_fills_output(self, fake_engine: FakeKokoroEngine) -> None:
        """Non-zero audio must be written when data is available."""
        p = make_player(fake_engine, text="Test.")
        generate_fully(p)

        outdata = np.zeros((2048, 1), dtype=np.float32)
        p._callback(outdata, 2048, None, MagicMock())

        assert np.any(outdata != 0)
        assert p._play_pos == 2048

    def test_callback_silence_when_paused(self, fake_engine: FakeKokoroEngine) -> None:
        """Output must be all zeros when paused."""
        p = make_player(fake_engine, text="Test.")
        generate_fully(p)

        p.toggle_pause()
        outdata = np.ones((2048, 1), dtype=np.float32)
        p._callback(outdata, 2048, None, MagicMock())

        assert np.all(outdata == 0)

    def test_callback_silence_when_stopped(self, fake_engine: FakeKokoroEngine) -> None:
        """Output must be all zeros when stopped."""
        p = make_player(fake_engine, text="Test.")
        p.stop()

        outdata = np.ones((256, 1), dtype=np.float32)
        p._callback(outdata, 256, None, MagicMock())
        assert np.all(outdata == 0)

    def test_callback_zero_pads_at_end(self, fake_engine: FakeKokoroEngine) -> None:
        """When less audio remains than frames requested, the tail is zero-padded."""
        p = make_player(fake_engine, text="Test.")
        generate_fully(p)

        total_samples = len(p._buffer)
        p._play_pos = total_samples - 10
        outdata = np.ones((2048, 1), dtype=np.float32)
        p._callback(outdata, 2048, None, MagicMock())

        assert np.all(outdata[10:] == 0)


# ---------------------------------------------------------------------------
# Start / stop — mocked sounddevice (hardware boundary)
# ---------------------------------------------------------------------------


class TestPlayback:
    """Stream open/close are hardware interactions, tested via mock."""

    @patch("lector.player.sd.OutputStream")
    def test_start_opens_stream(self, mock_cls: MagicMock, fake_engine: FakeKokoroEngine) -> None:
        p = make_player(fake_engine)
        p.start()
        mock_cls.assert_called_once()
        mock_cls.return_value.start.assert_called_once()

    @patch("lector.player.sd.OutputStream")
    def test_stop_closes_stream(self, mock_cls: MagicMock, fake_engine: FakeKokoroEngine) -> None:
        p = make_player(fake_engine)
        p.start()
        p.stop()
        mock_cls.return_value.stop.assert_called_once()
        mock_cls.return_value.close.assert_called_once()
        assert p._stream is None

    def test_is_finished_after_full_playback(self, fake_engine: FakeKokoroEngine) -> None:
        """Player reports finished when all audio has been generated and played."""
        p = make_player(fake_engine, text="Done.")
        generate_fully(p)
        p._play_pos = len(p._buffer)
        assert p.is_finished
