"""Audio player — buffer management, sounddevice playback, on-demand TTS generation."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import deal
import numpy as np
import sounddevice as sd

if TYPE_CHECKING:
    from kokoro_onnx import Kokoro

# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------

_valid_speed = deal.chain(
    deal.pre(lambda self: hasattr(self, "speed")),
    deal.ensure(
        lambda self, result=None: self.SPEED_MIN <= self.speed <= self.SPEED_MAX  # noqa: ARG005 — deal requires result param
    ),
)


class AudioPlayer:
    """Manages audio buffer, on-demand TTS generation, and playback.

    A background worker generates chunks just ahead of the playback
    cursor (look-ahead).  When speed changes the worker discards
    pre-generated audio after the current chunk and re-generates at the
    new speed.
    """

    SPEED_STEP = 0.1
    SPEED_MIN = 0.5
    SPEED_MAX = 2.0
    LOOK_AHEAD = 3

    def __init__(
        self,
        sample_rate: int = 24000,
        voice: str = "",
        speed: float = 1.0,
        lang: str = "",
        *,
        engine: Kokoro | None = None,
        voice_style: np.ndarray | None = None,
        phoneme_batches: list[str] | None = None,
    ) -> None:
        """Initialise the player with TTS resources and playback settings."""
        self.sample_rate = sample_rate

        # Metadata (for display)
        self.voice = voice
        self.speed = speed
        self.lang = lang

        # Generation resources
        self._engine = engine
        self._voice_style = voice_style
        self._phoneme_batches: list[str] = phoneme_batches or []
        self._expected_chunks: int = len(self._phoneme_batches)

        # Audio buffer (grows as chunks arrive, kept in memory only)
        self._buffer = np.empty(0, dtype=np.float32)
        self._lock = threading.Lock()

        # Chunk boundary tracking — sample offset where each chunk starts.
        self._chunk_starts: list[int] = []

        # Playback state
        self._play_pos: int = 0
        self._paused = False
        self._stopped = False

        # Generation state
        self._gen_cursor: int = 0
        self._chunks_received: int = 0
        self._generation_done = False
        self._gen_epoch: int = 0
        self._gen_wakeup = threading.Event()
        self._worker_thread: threading.Thread | None = None
        self._generation_error: str | None = None

        self._stream: sd.OutputStream | None = None

    # -- generation ---------------------------------------------------------

    def start_generation(self) -> None:
        """Start the background generation worker thread."""
        t = threading.Thread(target=self._generation_worker, daemon=True)
        self._worker_thread = t
        t.start()

    def _generation_worker(self) -> None:
        try:
            while not self._stopped:
                current = self.current_chunk_index
                cursor = self._gen_cursor

                if cursor >= self._expected_chunks:
                    self._generation_done = True
                    break

                if cursor - current >= self.LOOK_AHEAD:
                    self._gen_wakeup.wait(timeout=0.3)
                    self._gen_wakeup.clear()
                    continue

                epoch = self._gen_epoch
                batch = self._phoneme_batches[cursor]
                audio, _ = self._engine._create_audio(  # noqa: SLF001
                    batch,
                    self._voice_style,
                    self.speed,
                )

                with self._lock:
                    if epoch != self._gen_epoch:
                        continue
                    self._chunk_starts.append(len(self._buffer))
                    self._buffer = np.concatenate([self._buffer, audio])
                    self._chunks_received += 1
                    self._gen_cursor += 1

            if not self._stopped:
                self._generation_done = True
        except Exception as exc:
            self._generation_error = str(exc)
            self._generation_done = True

    # -- transport controls -------------------------------------------------

    def start(self) -> None:
        """Open the audio output stream and begin playback."""
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
            blocksize=2048,
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop playback and generation."""
        self._stopped = True
        self._gen_wakeup.set()
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def toggle_pause(self) -> None:
        """Toggle between paused and playing."""
        self._paused = not self._paused

    def next_chunk(self) -> None:
        """Jump to the start of the next sentence chunk."""
        with self._lock:
            for start in self._chunk_starts:
                if start > self._play_pos:
                    self._play_pos = start
                    break
            else:
                self._play_pos = len(self._buffer)
        self._gen_wakeup.set()

    def prev_chunk(self) -> None:
        """Jump back to current or previous sentence chunk."""
        with self._lock:
            grace = int(0.5 * self.sample_rate)
            for start in reversed(self._chunk_starts):
                if start < self._play_pos - grace:
                    self._play_pos = start
                    return
            self._play_pos = 0

    def restart(self) -> None:
        """Restart playback from the beginning."""
        with self._lock:
            self._play_pos = 0
            self._paused = False

    @_valid_speed
    def speed_up(self) -> None:
        """Increase playback speed by one step."""
        old = self.speed
        self.speed = round(min(self.speed + self.SPEED_STEP, self.SPEED_MAX), 1)
        if self.speed != old:
            self._invalidate_future_chunks()

    @_valid_speed
    def speed_down(self) -> None:
        """Decrease playback speed by one step."""
        old = self.speed
        self.speed = round(max(self.speed - self.SPEED_STEP, self.SPEED_MIN), 1)
        if self.speed != old:
            self._invalidate_future_chunks()

    def _invalidate_future_chunks(self) -> None:
        """Discard generated audio after the current chunk and re-generate."""
        with self._lock:
            current_idx = 0
            for i, start in enumerate(self._chunk_starts):
                if start <= self._play_pos:
                    current_idx = i
                else:
                    break
            keep = current_idx + 1

            if keep < len(self._chunk_starts):
                trunc_at = self._chunk_starts[keep]
                self._buffer = self._buffer[:trunc_at]
                self._chunk_starts = self._chunk_starts[:keep]
                self._chunks_received = keep
                self._gen_cursor = keep
                self._generation_done = False

            self._gen_epoch += 1

        self._gen_wakeup.set()

    # -- queries ------------------------------------------------------------

    @property
    def playback_time(self) -> float:
        """Return current playback position in seconds."""
        result = self._play_pos / self.sample_rate
        assert result >= 0  # internal invariant check
        return result

    @property
    def buffered_duration(self) -> float:
        """Return total duration of buffered audio in seconds."""
        result = len(self._buffer) / self.sample_rate
        assert result >= 0  # internal invariant check
        return result

    @property
    def is_paused(self) -> bool:
        """Return whether playback is paused."""
        return self._paused

    @property
    def is_stopped(self) -> bool:
        """Return whether playback has been stopped."""
        return self._stopped

    @property
    def is_finished(self) -> bool:
        """Return whether all audio has been generated and played."""
        return self._generation_done and self._play_pos >= len(self._buffer)

    @property
    def chunks_received(self) -> int:
        """Return the number of chunks generated so far."""
        return self._chunks_received

    @property
    def expected_chunks(self) -> int:
        """Return the total number of chunks to generate."""
        return self._expected_chunks

    @property
    def generation_done(self) -> bool:
        """Return whether the generation worker has finished."""
        return self._generation_done

    @property
    def generation_error(self) -> str | None:
        """Non-*None* when the generation worker died with an error."""
        return self._generation_error

    @property
    def current_chunk_index(self) -> int:
        """0-based index of the chunk currently playing."""
        with self._lock:
            idx = 0
            for i, start in enumerate(self._chunk_starts):
                if start <= self._play_pos:
                    idx = i
                else:
                    break
            return idx

    @property
    def total_chunks(self) -> int:
        """Return the number of chunk boundaries recorded so far."""
        return len(self._chunk_starts)

    # -- sounddevice callback -----------------------------------------------

    def _callback(
        self,
        outdata: np.ndarray,
        frames: int,
        _time_info: object,
        _status: sd.CallbackFlags,
    ) -> None:
        if self._paused or self._stopped:
            outdata[:] = 0
            return

        wake_gen = False
        with self._lock:
            available = len(self._buffer)
            if self._play_pos >= available:
                outdata[:] = 0
                wake_gen = not self._generation_done
            else:
                to_read = min(frames, available - self._play_pos)
                outdata[:to_read, 0] = self._buffer[self._play_pos : self._play_pos + to_read]
                if to_read < frames:
                    outdata[to_read:] = 0
                self._play_pos += to_read
                # Wake worker when less than ~1 s of audio remains
                if available - self._play_pos < self.sample_rate:
                    wake_gen = not self._generation_done

        if wake_gen:
            self._gen_wakeup.set()
