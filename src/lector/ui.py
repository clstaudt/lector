"""Interactive terminal UI — Rich display and keyboard controls."""

from __future__ import annotations

import atexit
import os
import select
import signal
import sys
import termios
import time
import tty
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

if TYPE_CHECKING:
    from .player import AudioPlayer

_PID_FILE = Path.home() / ".lector" / "lector.pid"


# ---------------------------------------------------------------------------
# PID file — allows a second invocation to stop a running instance
# ---------------------------------------------------------------------------


def _kill_existing() -> bool:
    """If another lector process is playing, kill it and return True."""
    try:
        pid = int(_PID_FILE.read_text().strip())
    except (FileNotFoundError, ValueError):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        _PID_FILE.unlink(missing_ok=True)
        return True
    except ProcessLookupError:
        _PID_FILE.unlink(missing_ok=True)
        return False


def _write_pid() -> None:
    """Write current PID so a future invocation can stop us."""
    _PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: _PID_FILE.unlink(missing_ok=True))


# ---------------------------------------------------------------------------
# Terminal helpers
# ---------------------------------------------------------------------------


class _CbreakTerminal:
    """Context manager: cbreak mode for single-key reads.

    Unlike raw mode, cbreak preserves output processing so Rich's
    cursor-movement escapes work correctly.
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
        rlist2, _, _ = select.select([fd], [], [], 0.05)
        if rlist2:
            ch2 = os.read(fd, 1)
            if ch2 == b"[":
                ch3 = os.read(fd, 1)
                return {
                    b"C": "right",
                    b"D": "left",
                    b"A": "up",
                    b"B": "down",
                }.get(ch3)
        return None

    if ch == b" ":
        return "space"
    if ch in (b"\x03", b"\x04"):
        return "quit"
    return ch.decode("utf-8", errors="ignore")


# ---------------------------------------------------------------------------
# Rich display
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

    if player.generation_error:
        pct_err = (received / expected * 100) if expected else 0
        gen_bar = ProgressBar(
            total=100,
            completed=pct_err,
            complete_style="red",
        )
        gen_label = f"[red]\u2717[/red] {received} / {expected} chunks"
    elif player.generation_done:
        gen_bar = ProgressBar(total=100, completed=100, complete_style="green")
        gen_label = f"[green]✓[/green] {received} chunks"
    elif expected > 0:
        pct_gen = received / expected * 100
        gen_bar = ProgressBar(
            total=100,
            completed=min(pct_gen, 100),
            complete_style="magenta",
        )
        gen_label = f"{received} / {expected} chunks"
    else:
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

    play_bar = ProgressBar(
        total=100,
        completed=min(pct, 100),
        complete_style=bar_style,
    )
    time_label = f"{_fmt_time(current)} / {_fmt_time(total_dur)}"
    play_table.add_row("Playback", play_bar, time_label)

    # -- status + chunk --
    chunk_idx = player.current_chunk_index + 1
    total = player.total_chunks
    ellipsis = "" if player.generation_done else "…"

    if player.is_finished and player.generation_error:
        status = Text(
            f"✗ Finished ({received}/{expected} chunks — generation error)",
            style="red",
            justify="center",
        )
    elif player.is_finished:
        status = Text("✓ Done", style="green", justify="center")
    elif player.is_paused:
        status = Text(
            f"⏸  Paused  ·  chunk {chunk_idx} / {total}{ellipsis}",
            style="yellow",
            justify="center",
        )
    elif player.playback_time >= player.buffered_duration and not player.generation_done:
        status = Text("⏳ Buffering…", style="dim", justify="center")
    else:
        status = Text(
            f"▶  Playing  ·  chunk {chunk_idx} / {total}{ellipsis}",
            style="blue",
            justify="center",
        )

    # -- metadata (centered) --
    meta = Text.assemble(
        ("voice ", "dim"),
        (player.voice, "bold cyan"),
        ("   speed ", "dim"),
        (f"{player.speed:.1f}\u00d7", "bold cyan"),
        ("   lang ", "dim"),
        (player.lang, "bold cyan"),
    )
    meta.justify = "center"

    # -- key hints (gray box) --
    keys = Text.assemble(
        ("␣", "bold"),
        " pause  ",
        ("q", "bold"),
        " quit  ",
        ("r", "bold"),
        " restart  ",
        ("← h", "bold"),
        " prev  ",
        ("→ l", "bold"),
        " next  ",
        ("+", "bold"),
        " faster  ",
        ("-", "bold"),
        " slower",
    )
    keys.justify = "center"
    keys_panel = Panel(keys, border_style="bright_black", padding=(0, 1))

    return Panel(
        Group(gen_table, play_table, status, meta, Text(""), keys_panel),
        title="[bold]Lector[/bold]",
        border_style="blue",
        padding=(0, 1),
    )


# ---------------------------------------------------------------------------
# Key → action dispatch
# ---------------------------------------------------------------------------

_KEY_ACTIONS: dict[str, str] = {
    "space": "toggle_pause",
    "q": "stop",
    "quit": "stop",
    "r": "restart",
    "right": "next_chunk",
    "l": "next_chunk",
    "left": "prev_chunk",
    "h": "prev_chunk",
    "+": "speed_up",
    "=": "speed_up",
    "up": "speed_up",
    "-": "speed_down",
    "_": "speed_down",
    "down": "speed_down",
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _run_headless(player: AudioPlayer) -> None:
    """Play audio without interactive UI (no TTY required).

    Used when lector is invoked from Automator, a pipe, or any
    context without a controlling terminal.

    Toggle behaviour: if another lector process is already playing,
    stop it and exit instead of starting a new one.
    """
    if _kill_existing():
        return

    _write_pid()
    player.start_generation()

    deadline = time.monotonic() + 10.0
    while player.chunks_received == 0 and time.monotonic() < deadline:
        time.sleep(0.1)

    player.start()

    try:
        while not player.is_finished:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass
    finally:
        player.stop()


def _run_interactive(player: AudioPlayer) -> None:
    """Run the full interactive player with Rich UI and keyboard controls."""
    player.start_generation()

    deadline = time.monotonic() + 5.0
    while player.chunks_received == 0 and time.monotonic() < deadline:
        time.sleep(0.1)

    player.start()
    console = Console(stderr=True)

    try:
        with (
            _CbreakTerminal(),
            Live(
                _build_display(player),
                console=console,
                refresh_per_second=10,
                transient=True,
            ) as live,
        ):
            while True:
                key = _read_key(timeout=0.08)

                action = _KEY_ACTIONS.get(key) if key else None
                if action == "stop":
                    player.stop()
                    break
                if action:
                    getattr(player, action)()

                live.update(_build_display(player))

                if player.is_finished:
                    live.update(_build_display(player))
                    time.sleep(0.5)
                    break
    except KeyboardInterrupt:
        pass
    finally:
        player.stop()


def run_player(player: AudioPlayer) -> None:
    """Run the player, choosing interactive or headless mode automatically.

    Interactive mode (Rich UI + keyboard controls) is used when **both**
    stdin and stderr are TTYs.  When stdin is a pipe (e.g.
    ``pbpaste | lector read``), cbreak mode cannot be set and keyboard
    input is unavailable, so we fall back to headless playback.
    """
    if sys.stdin.isatty() and sys.stderr.isatty():
        _run_interactive(player)
    else:
        _run_headless(player)
