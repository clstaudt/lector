"""Tests for lector.player — AudioPlayer with real numpy buffers.

The only mock is ``sounddevice.OutputStream`` (audio hardware).
All buffer management, threading, transport controls, and state
transitions run against real numpy arrays.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from lector.player import AudioPlayer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_player(fake_engine, text: str = "First. Second. Third.", **kw) -> AudioPlayer:
    """Build a real AudioPlayer wired to the fake engine."""
    phonemes = fake_engine.tokenizer.phonemize(text, "en-us")
    batches = fake_engine._split_phonemes(phonemes)
    style = fake_engine.get_voice_style("af_sky")
    defaults = {
        "sample_rate": 24_000,
        "voice": "af_sky",
        "speed": 1.0,
        "lang": "en-us",
        "engine": fake_engine,
        "voice_style": style,
        "phoneme_batches": batches,
    }
    defaults.update(kw)
    return AudioPlayer(**defaults)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestInitialState:
    def test_not_paused(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        assert not p.is_paused

    def test_not_stopped(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        assert not p.is_stopped

    def test_not_finished(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        assert not p.is_finished

    def test_playback_time_zero(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        assert p.playback_time == 0.0

    def test_expected_chunks(self, fake_engine) -> None:
        p = _make_player(fake_engine, text="One. Two. Three.")
        assert p.expected_chunks >= 3

    def test_no_chunks_received_yet(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        assert p.chunks_received == 0


# ---------------------------------------------------------------------------
# Generation (real threading, fake engine)
# ---------------------------------------------------------------------------


class TestGeneration:
    def test_generation_produces_audio(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        p.start_generation()

        # Wait for generation to finish
        deadline = time.monotonic() + 5.0
        while not p.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

        assert p.generation_done
        assert p.chunks_received == p.expected_chunks
        assert p.buffered_duration > 0

    def test_buffer_is_float32(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        p.start_generation()

        deadline = time.monotonic() + 5.0
        while not p.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

        assert p._buffer.dtype == np.float32

    def test_chunk_starts_tracked(self, fake_engine) -> None:
        p = _make_player(fake_engine, text="A. B. C.")
        p.start_generation()

        deadline = time.monotonic() + 5.0
        while not p.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

        assert len(p._chunk_starts) == p.chunks_received
        # Chunk starts should be monotonically increasing
        for i in range(1, len(p._chunk_starts)):
            assert p._chunk_starts[i] > p._chunk_starts[i - 1]


# ---------------------------------------------------------------------------
# Transport controls (real buffer manipulation)
# ---------------------------------------------------------------------------


class TestTransportControls:
    """Test pause, stop, restart, chunk navigation with real audio data."""

    @pytest.fixture(autouse=True)
    def _player_with_audio(self, fake_engine) -> None:
        """Pre-generate audio so transport tests don't wait."""
        self.player = _make_player(fake_engine, text="Chunk one. Chunk two. Chunk three.")
        self.player.start_generation()
        deadline = time.monotonic() + 5.0
        while not self.player.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

    def test_toggle_pause(self) -> None:
        assert not self.player.is_paused
        self.player.toggle_pause()
        assert self.player.is_paused
        self.player.toggle_pause()
        assert not self.player.is_paused

    def test_stop(self) -> None:
        self.player.stop()
        assert self.player.is_stopped

    def test_restart_resets_position(self) -> None:
        # Advance play position
        self.player._play_pos = 1000
        assert self.player.playback_time > 0
        self.player.restart()
        assert self.player.playback_time == 0.0
        assert not self.player.is_paused

    def test_next_chunk_advances(self) -> None:
        assert self.player._play_pos == 0
        self.player.next_chunk()
        assert self.player._play_pos > 0

    def test_prev_chunk_from_middle(self) -> None:
        # Jump to the last chunk
        if len(self.player._chunk_starts) >= 2:
            self.player._play_pos = self.player._chunk_starts[-1] + 100
            self.player.prev_chunk()
            assert self.player._play_pos < self.player._chunk_starts[-1] + 100

    def test_prev_chunk_at_start_stays_at_zero(self) -> None:
        self.player._play_pos = 0
        self.player.prev_chunk()
        assert self.player._play_pos == 0


# ---------------------------------------------------------------------------
# Speed controls
# ---------------------------------------------------------------------------


class TestSpeedControls:
    def test_speed_up(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        initial = p.speed
        p.speed_up()
        assert p.speed == round(initial + AudioPlayer.SPEED_STEP, 1)

    def test_speed_down(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        initial = p.speed
        p.speed_down()
        assert p.speed == round(initial - AudioPlayer.SPEED_STEP, 1)

    def test_speed_clamped_at_max(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        p.speed = AudioPlayer.SPEED_MAX
        p.speed_up()
        assert p.speed == AudioPlayer.SPEED_MAX

    def test_speed_clamped_at_min(self, fake_engine) -> None:
        p = _make_player(fake_engine)
        p.speed = AudioPlayer.SPEED_MIN
        p.speed_down()
        assert p.speed == AudioPlayer.SPEED_MIN

    def test_speed_change_invalidates_future_chunks(self, fake_engine) -> None:
        """After speed change, generation should restart from current position."""
        p = _make_player(fake_engine)
        p.start_generation()

        deadline = time.monotonic() + 5.0
        while not p.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

        original_epoch = p._gen_epoch

        p.speed_up()

        assert p._gen_epoch > original_epoch


# ---------------------------------------------------------------------------
# Sounddevice callback (real buffer, mocked stream)
# ---------------------------------------------------------------------------


class TestCallback:
    """Test the _callback method with real numpy arrays."""

    def test_callback_fills_output(self, fake_engine) -> None:
        p = _make_player(fake_engine, text="Test.")
        p.start_generation()

        deadline = time.monotonic() + 5.0
        while not p.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

        outdata = np.zeros((2048, 1), dtype=np.float32)
        p._callback(outdata, 2048, None, MagicMock())

        # Should have written non-zero audio data
        assert np.any(outdata != 0)
        assert p._play_pos == 2048

    def test_callback_silence_when_paused(self, fake_engine) -> None:
        p = _make_player(fake_engine, text="Test.")
        p.start_generation()

        deadline = time.monotonic() + 5.0
        while not p.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

        p.toggle_pause()
        outdata = np.ones((2048, 1), dtype=np.float32)
        p._callback(outdata, 2048, None, MagicMock())

        assert np.all(outdata == 0)

    def test_callback_silence_when_stopped(self, fake_engine) -> None:
        p = _make_player(fake_engine, text="Test.")
        p.stop()

        outdata = np.ones((256, 1), dtype=np.float32)
        p._callback(outdata, 256, None, MagicMock())
        assert np.all(outdata == 0)

    def test_callback_zero_pads_end_of_buffer(self, fake_engine) -> None:
        p = _make_player(fake_engine, text="Test.")
        p.start_generation()

        deadline = time.monotonic() + 5.0
        while not p.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

        # Request way more frames than available
        total_samples = len(p._buffer)
        p._play_pos = total_samples - 10
        outdata = np.ones((2048, 1), dtype=np.float32)
        p._callback(outdata, 2048, None, MagicMock())

        # Last portion should be zero-padded
        assert np.all(outdata[10:] == 0)


# ---------------------------------------------------------------------------
# Start / stop with mocked sounddevice (hardware boundary)
# ---------------------------------------------------------------------------


class TestPlayback:
    @patch("lector.player.sd.OutputStream")
    def test_start_opens_stream(self, mock_stream_cls, fake_engine) -> None:
        p = _make_player(fake_engine)
        p.start()

        mock_stream_cls.assert_called_once()
        mock_stream_cls.return_value.start.assert_called_once()

    @patch("lector.player.sd.OutputStream")
    def test_stop_closes_stream(self, mock_stream_cls, fake_engine) -> None:
        p = _make_player(fake_engine)
        p.start()
        p.stop()

        mock_stream_cls.return_value.stop.assert_called_once()
        mock_stream_cls.return_value.close.assert_called_once()
        assert p._stream is None

    def test_is_finished_after_full_playback(self, fake_engine) -> None:
        p = _make_player(fake_engine, text="Done.")
        p.start_generation()

        deadline = time.monotonic() + 5.0
        while not p.generation_done and time.monotonic() < deadline:
            time.sleep(0.05)

        p._play_pos = len(p._buffer)
        assert p.is_finished
