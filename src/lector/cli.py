"""Typer CLI for lector."""

from __future__ import annotations

import platform
import sys

import typer
from rich.console import Console
from rich.table import Table

from .lang import (
    ALL_LANG_CODES,
    LANG_NAMES,
    STANDARD_LANG_CODES,
    default_voice_for_lang,
    detect_language,
    lang_for_voice,
)
from .macos_service import install_quick_action, uninstall_quick_action
from .tts import (
    create_player,
    download_german_models,
    download_models,
    get_all_voices,
)
from .ui import run_player
from .utils import read_clipboard, read_stdin

app = typer.Typer(
    name="lector",
    help="Read text aloud using high-quality neural text-to-speech.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Language / voice resolution
# ---------------------------------------------------------------------------

_VOICE_SENTINEL = "__auto__"


def _resolve_lang_and_voice(
    text: str,
    lang: str,
    voice: str,
) -> tuple[str, str]:
    """Return the concrete ``(lang, voice)`` pair to use.

    Handles ``--lang auto`` detection, voice-implies-language inference,
    and default-voice selection.
    """
    voice_explicit = voice != _VOICE_SENTINEL
    lang_auto = lang == "auto"

    if voice_explicit and lang_auto:
        inferred = lang_for_voice(voice)
        lang = inferred if inferred else "en-us"
    elif lang_auto:
        lang = detect_language(text)
        name = LANG_NAMES.get(lang, lang)
        console.print(f"[dim]Detected language:[/dim] [bold]{name}[/bold] ({lang})")

    if not voice_explicit:
        voice = default_voice_for_lang(lang)

    supported = STANDARD_LANG_CODES | frozenset({"de"})
    if lang not in supported:
        name = LANG_NAMES.get(lang, lang)
        console.print(
            f"[yellow]Language {name} ({lang}) is not supported — "
            f"falling back to English.[/yellow]"
        )
        lang = "en-us"
        if not voice_explicit:
            voice = default_voice_for_lang(lang)

    return lang, voice


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@app.command()
def read(
    text: str | None = typer.Argument(None, help="Text to read aloud."),
    clipboard: bool = typer.Option(
        False, "--clipboard", "-c", help="Read text from the system clipboard (pbpaste)."
    ),
    voice: str = typer.Option(
        _VOICE_SENTINEL,
        "--voice",
        "-v",
        help="Voice name (run 'lector voices' to list). Auto-selected when omitted.",
    ),
    speed: float = typer.Option(1.0, "--speed", "-s", help="Speech speed (0.5-2.0)."),
    lang: str = typer.Option(
        "auto",
        "--lang",
        "-l",
        help="Language code, or 'auto' to detect. " + ", ".join(ALL_LANG_CODES),
    ),
) -> None:
    r"""Read text aloud.

    Text can be given as a positional argument, read from the clipboard
    ([bold]--clipboard[/bold]), or piped via stdin.

    \b
    Examples:
        lector read "Hello, world!"
        lector read --clipboard
        lector read --lang de "Guten Morgen, wie geht es Ihnen?"
        cat article.txt | lector read
        lector read --voice af_nicole --speed 0.9 "Good evening."
    """
    if clipboard:
        text = read_clipboard()
    elif text is None:
        if not sys.stdin.isatty():
            text = read_stdin()
        else:
            console.print(
                "[red]No text provided.[/red]  "
                "Pass text as argument, use [bold]--clipboard[/bold], or pipe via stdin."
            )
            raise typer.Exit(1)

    if not text or not text.strip():
        console.print("[yellow]Nothing to read (empty text).[/yellow]")
        raise typer.Exit

    text = text.strip()
    lang, voice = _resolve_lang_and_voice(text, lang, voice)

    player = create_player(text, voice=voice, speed=speed, lang=lang)
    run_player(player)


@app.command()
def voices(
    lang: str | None = typer.Option(None, "--lang", "-l", help="Filter voices by language code."),
) -> None:
    """List available TTS voices, grouped by language."""
    out = Console()

    if lang is not None:
        voice_list = get_all_voices(lang)
        name = LANG_NAMES.get(lang, lang)
        out.print(f"[bold]{name}[/bold]")
        for v in voice_list:
            out.print(f"  {v}")
        return

    table = Table(title="Available Voices", show_lines=False)
    table.add_column("Language", style="bold")
    table.add_column("Code", style="dim")
    table.add_column("Voices")

    for code in sorted(LANG_NAMES):
        name = LANG_NAMES[code]
        try:
            voice_list = get_all_voices(code)
        except Exception:
            voice_list = []
        if voice_list:
            table.add_row(name, code, ", ".join(voice_list))

    out.print(table)


@app.command()
def download(
    force: bool = typer.Option(
        False, "--force", "-f", help="Re-download models even if they already exist."
    ),
    german: bool = typer.Option(False, "--german", help="Download the German (Martin) model."),
) -> None:
    """Download the Kokoro TTS model files (~300 MB)."""
    if german:
        download_german_models(force=force)
    else:
        download_models(force=force)
    console.print("[green]\u2713 Models ready.[/green]")


@app.command(name="install-service")
def install_service() -> None:
    """[macOS] Install a Quick Action for the right-click Services menu.

    Adds "Read with Lector / Stop Reading" to Services.
    """
    if platform.system() != "Darwin":
        console.print("[red]This command is only available on macOS.[/red]")
        raise typer.Exit(1)

    path = install_quick_action()
    console.print("[green]\u2713 Quick Action installed![/green]")
    console.print(
        "  Select text \u2192 right-click \u2192 "
        "[bold]Services \u2192 Read with Lector \u00b7 Stop Reading[/bold]"
    )
    console.print("  Invoke again while playing to stop playback.")
    console.print(f"  [dim]Installed to {path}[/dim]")


@app.command(name="uninstall-service")
def uninstall_service() -> None:
    """[macOS] Remove the Lector Quick Action from the Services menu."""
    if platform.system() != "Darwin":
        console.print("[red]This command is only available on macOS.[/red]")
        raise typer.Exit(1)

    path = uninstall_quick_action()
    if path:
        console.print("[green]\u2713 Quick Action removed.[/green]")
        console.print(f"  [dim]Removed {path}[/dim]")
    else:
        console.print("[yellow]Quick Action was not installed.[/yellow]")
