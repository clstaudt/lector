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

from .config import save_config

if TYPE_CHECKING:
    from .player import AudioPlayer

_PID_FILE = Path.home() / ".lector" / "lector.pid"

_FLASH_DURATION = 2.0  # seconds a flash message stays visible

# Flash message state — module-level so _build_display can read it.
_flash_message: str | None = None
_flash_style: str = "dim"
_flash_time: float = 0.0


def _set_flash(message: str, style: str = "dim") -> None:
    """Set a transient message displayed in the player panel."""
    global _flash_message, _flash_style, _flash_time  # noqa: PLW0603
    _flash_message = message
    _flash_style = style
    _flash_time = time.monotonic()


def _get_flash() -> tuple[str, str] | None:
    """Return the current flash *(message, style)* or *None* if expired."""
    global _flash_message  # noqa: PLW0603
    if _flash_message is None:
        return None
    if time.monotonic() - _flash_time > _FLASH_DURATION:
        _flash_message = None
        return None
    return _flash_message, _flash_style


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

    save_hint = Text.assemble(
        ("s", "bold"),
        " save as default",
    )
    save_hint.justify = "center"

    # -- optional flash message --
    flash = _get_flash()
    if flash:
        flash_text = Text(flash[0], style=flash[1], justify="center")
        body = Group(
            gen_table, play_table, status, meta, flash_text, Text(""), keys_panel, save_hint
        )
    else:
        body = Group(gen_table, play_table, status, meta, Text(""), keys_panel, save_hint)

    return Panel(
        body,
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
    "s": "save_defaults",
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


def _handle_save_defaults(player: AudioPlayer, live: Live) -> None:
    """Prompt for confirmation, then persist current voice and speed."""
    _set_flash("Save current voice & speed as default? (y/n)", "bold yellow")
    live.update(_build_display(player))

    # Wait for y/n answer — playback continues on its own threads.
    while True:
        key = _read_key(timeout=0.08)
        if key == "y":
            try:
                save_config(voice=player.voice, speed=player.speed)
                _set_flash("\u2713 Saved as default", "bold green")
            except ValueError:
                _set_flash("\u2717 Could not save", "bold red")
            break
        if key is not None:
            _set_flash("Cancelled", "dim")
            break
        # Keep display alive while waiting
        live.update(_build_display(player))


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
                if action == "save_defaults":
                    _handle_save_defaults(player, live)
                elif action:
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
