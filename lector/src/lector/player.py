"""Interactive audio player with Rich UI and keyboard controls."""

from __future__ import annotations

import os
import select
import sys
import termios
import threading
import tty
from typing import TYPE_CHECKING

import numpy as np
import sounddevice as sd
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import Callable


# ---------------------------------------------------------------------------
# Audio player (callback-driven, seekable)
# ---------------------------------------------------------------------------


class AudioPlayer:
    """Manages a growing audio buffer with real-time playback.

    Chunks are appended while a ``sounddevice.OutputStream`` callback
    continuously reads from the buffer.  Supports pause, seek, and
    sentence-level navigation.
    """

    def __init__(self, sample_rate: int = 24000) -> None:
        self.sample_rate = sample_rate

        # Audio buffer (grows as chunks arrive)
        self._buffer = np.empty(0, dtype=np.float32)
        self._lock = threading.Lock()

        # Chunk boundary tracking — each entry is the sample offset where
        # that chunk *starts* in the buffer.  Used for sentence navigation.
        self._chunk_starts: list[int] = []

        # Playback state
        self._play_pos: int = 0  # current sample index
        self._paused = False
        self._stopped = False

        # Generation bookkeeping
        self._chunks_received: int = 0
        self._expected_chunks: int | None = None
        self._generation_done = False

        self._stream: sd.OutputStream | None = None

    # -- chunk ingestion ----------------------------------------------------

    def add_chunk(self, samples: np.ndarray) -> None:
        with self._lock:
            self._chunk_starts.append(len(self._buffer))
            self._buffer = np.concatenate([self._buffer, samples])
            self._chunks_received += 1

    def mark_generation_done(self) -> None:
        self._generation_done = True

    def set_expected_chunks(self, n: int) -> None:
        """Set the expected total number of chunks (for progress display)."""
        self._expected_chunks = n

    @property
    def expected_chunks(self) -> int | None:
        return self._expected_chunks

    # -- transport controls -------------------------------------------------

    def start(self) -> None:
        self._stream = sd.OutputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            callback=self._callback,
            blocksize=2048,
        )
        self._stream.start()

    def stop(self) -> None:
        self._stopped = True
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def toggle_pause(self) -> None:
        self._paused = not self._paused

    def next_chunk(self) -> None:
        """Jump to the start of the next sentence chunk."""
        with self._lock:
            for start in self._chunk_starts:
                if start > self._play_pos:
                    self._play_pos = start
                    return
            # Already past the last chunk start — jump to end
            self._play_pos = len(self._buffer)

    def prev_chunk(self) -> None:
        """Jump to the start of the current or previous sentence chunk.

        If we're within the first 0.5 s of the current chunk, jump to the
        *previous* one.  Otherwise restart the current chunk.
        """
        with self._lock:
            grace = int(0.5 * self.sample_rate)
            for start in reversed(self._chunk_starts):
                if start < self._play_pos - grace:
                    self._play_pos = start
                    return
            self._play_pos = 0

    def restart(self) -> None:
        with self._lock:
            self._play_pos = 0
            self._paused = False

    # -- queries ------------------------------------------------------------

    @property
    def playback_time(self) -> float:
        return self._play_pos / self.sample_rate

    @property
    def buffered_duration(self) -> float:
        return len(self._buffer) / self.sample_rate

    @property
    def is_paused(self) -> bool:
        return self._paused

    @property
    def is_stopped(self) -> bool:
        return self._stopped

    @property
    def is_finished(self) -> bool:
        return self._generation_done and self._play_pos >= len(self._buffer)

    @property
    def chunks_received(self) -> int:
        return self._chunks_received

    @property
    def generation_done(self) -> bool:
        return self._generation_done

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

        with self._lock:
            available = len(self._buffer)
            if self._play_pos >= available:
                outdata[:] = 0
                return

            to_read = min(frames, available - self._play_pos)
            outdata[:to_read, 0] = self._buffer[self._play_pos : self._play_pos + to_read]
            if to_read < frames:
                outdata[to_read:] = 0
            self._play_pos += to_read


# ---------------------------------------------------------------------------
# Non-blocking key reader (macOS / Linux)
# ---------------------------------------------------------------------------


class _CbreakTerminal:
    """Context manager: cbreak mode for single-key reads.

    Unlike raw mode, cbreak preserves output processing so Rich's
    cursor-movement escapes work correctly (no stacking panels).
    """

    def __init__(self) -> None:
        self._fd = sys.stdin.fileno()
        self._old: list | None = None

    def __enter__(self) -> _CbreakTerminal:
        self._old = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        return self

    def __exit__(self, *_: object) -> None:
        if self._old is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old)


def _read_key(timeout: float = 0.05) -> str | None:
    """Read a single keypress (non-blocking).

    Uses ``os.read`` on the raw file descriptor to avoid Python's
    internal IO buffer swallowing escape-sequence bytes.
    """
    fd = sys.stdin.fileno()
    rlist, _, _ = select.select([fd], [], [], timeout)
    if not rlist:
        return None

    ch = os.read(fd, 1)
    if not ch:
        return None

    if ch == b"\x1b":
        # Possible escape sequence — remaining bytes arrive together
        rlist2, _, _ = select.select([fd], [], [], 0.05)
        if rlist2:
            ch2 = os.read(fd, 1)
            if ch2 == b"[":
                ch3 = os.read(fd, 1)
                return {
                    b"C": "right", b"D": "left",
                    b"A": "up", b"B": "down",
                }.get(ch3)
        # Bare Escape key (ignored — use 'q' to quit)
        return None

    if ch == b" ":
        return "space"
    if ch in (b"\x03", b"\x04"):  # Ctrl-C / Ctrl-D
        return "quit"
    return ch.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Rich UI
# ---------------------------------------------------------------------------


def _fmt_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}:{s:02d}"


def _build_display(player: AudioPlayer) -> Panel:
    """Return a Rich renderable snapshot of the current player state."""
    # -- generation row --
    gen_table = Table.grid(padding=(0, 1))
    gen_table.add_column(width=13)
    gen_table.add_column(ratio=1)
    gen_table.add_column(width=20, justify="right")

    expected = player.expected_chunks
    received = player.chunks_received

    if player.generation_done:
        gen_bar = ProgressBar(total=100, completed=100, complete_style="green")
        gen_label = f"[green]✓[/green] {received} chunks"
    elif expected is not None and expected > 0:
        pct_gen = received / expected * 100
        gen_bar = ProgressBar(total=100, completed=min(pct_gen, 100), complete_style="magenta")
        gen_label = f"{received} / {expected} chunks"
    else:
        import time
        pulse = (int(time.time() * 4) % 40) + 30
        gen_bar = ProgressBar(total=100, completed=pulse, pulse=True)
        gen_label = f"{received} chunks…"

    gen_table.add_row("Generating", gen_bar, gen_label)

    # -- playback row --
    play_table = Table.grid(padding=(0, 1))
    play_table.add_column(width=13)
    play_table.add_column(ratio=1)
    play_table.add_column(width=20, justify="right")

    total_dur = player.buffered_duration
    current = player.playback_time
    pct = (current / total_dur * 100) if total_dur > 0 else 0

    if player.is_paused:
        bar_style = "yellow"
    elif player.is_finished:
        bar_style = "green"
    else:
        bar_style = "blue"

    play_bar = ProgressBar(total=100, completed=min(pct, 100), complete_style=bar_style)
    time_label = f"{_fmt_time(current)} / {_fmt_time(total_dur)}"
    play_table.add_row("Playback", play_bar, time_label)

    # -- status --
    if player.is_finished:
        status = Text("  ✓ Done", style="green")
    elif player.is_paused:
        status = Text("  ⏸  Paused", style="yellow")
    elif player.playback_time >= player.buffered_duration and not player.generation_done:
        status = Text("  ⏳ Buffering…", style="dim")
    else:
        status = Text("  ▶  Playing", style="blue")

    # -- chunk indicator --
    ellipsis = "" if player.generation_done else "…"
    chunk_info = Text(
        f"  Sentence {player.current_chunk_index + 1} / "
        f"{player.total_chunks}{ellipsis}",
        style="dim",
    )

    # -- key hints --
    keys = Text.assemble(
        ("  ␣", "bold"), " pause  ",
        ("q", "bold"), " quit  ",
        ("r", "bold"), " restart  ",
        ("← h", "bold"), " prev  ",
        ("→ l", "bold"), " next",
    )
    keys.stylize("dim")

    return Panel(
        Group(gen_table, play_table, status, chunk_info, Text(""), keys),
        title="[bold]Lector[/bold]",
        border_style="blue",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def play_with_ui(
    player: AudioPlayer,
    generate_fn: Callable[[AudioPlayer], None],
) -> None:
    """Run the interactive player UI.

    *generate_fn* is called in a background thread.  It should call
    ``player.add_chunk()`` for each audio chunk and
    ``player.mark_generation_done()`` when finished.
    """
    # Start generation in background
    gen_thread = threading.Thread(target=generate_fn, args=(player,), daemon=True)
    gen_thread.start()

    # Wait briefly for the first chunk so we have *something* to play
    gen_thread.join(timeout=3.0)

    player.start()
    console = Console(stderr=True)

    try:
        with _CbreakTerminal():
            with Live(
                _build_display(player),
                console=console,
                refresh_per_second=10,
                transient=True,
            ) as live:
                while True:
                    key = _read_key(timeout=0.08)

                    if key == "space":
                        player.toggle_pause()
                    elif key in ("q", "quit"):
                        player.stop()
                        break
                    elif key == "r":
                        player.restart()
                    elif key in ("right", "l"):
                        player.next_chunk()
                    elif key in ("left", "h"):
                        player.prev_chunk()

                    live.update(_build_display(player))

                    if player.is_finished:
                        live.update(_build_display(player))
                        import time
                        time.sleep(0.5)
                        break
    except KeyboardInterrupt:
        pass
    finally:
        player.stop()
