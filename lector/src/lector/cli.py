"""Typer CLI for lector."""

from __future__ import annotations

import sys
from typing import Optional

import typer
from rich.console import Console

app = typer.Typer(
    name="lector",
    help="Read text aloud using high-quality neural text-to-speech.",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
console = Console(stderr=True)


@app.command()
def read(
    text: Optional[str] = typer.Argument(None, help="Text to read aloud."),
    clipboard: bool = typer.Option(
        False, "--clipboard", "-c", help="Read text from the system clipboard (pbpaste)."
    ),
    voice: str = typer.Option(
        "af_heart", "--voice", "-v", help="Voice name (run 'lector voices' to list)."
    ),
    speed: float = typer.Option(1.0, "--speed", "-s", help="Speech speed (0.5–2.0)."),
    lang: str = typer.Option("en-us", "--lang", "-l", help="Language code."),
) -> None:
    """Read text aloud.

    Text can be given as a positional argument, read from the clipboard
    ([bold]--clipboard[/bold]), or piped via stdin.

    \b
    Examples:
        lector read "Hello, world!"
        pbpaste | lector read
        lector read --clipboard
        cat article.txt | lector read --voice af_nicole --speed 0.9
    """
    from .tts import speak
    from .utils import read_clipboard as _clipboard, read_stdin

    if clipboard:
        text = _clipboard()
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
        raise typer.Exit()

    console.print(f"[dim]voice={voice}  speed={speed}  lang={lang}[/dim]")
    speak(text.strip(), voice=voice, speed=speed, lang=lang)


@app.command()
def voices() -> None:
    """List available TTS voices."""
    from .tts import get_engine

    out = Console()  # stdout, not stderr
    engine = get_engine()
    for v in sorted(engine.get_voices()):
        out.print(v)


@app.command()
def download(
    force: bool = typer.Option(
        False, "--force", "-f", help="Re-download models even if they already exist."
    ),
) -> None:
    """Download the Kokoro TTS model files (~300 MB)."""
    from .tts import download_models

    download_models(force=force)
    console.print("[green]✓ Models ready.[/green]")


@app.command(name="install-service")
def install_service() -> None:
    """[macOS] Install a Quick Action so "Read with Lector" appears in the right-click Services menu."""
    import platform

    if platform.system() != "Darwin":
        console.print("[red]This command is only available on macOS.[/red]")
        raise typer.Exit(1)

    from .utils import install_macos_quick_action

    path = install_macos_quick_action()
    console.print("[green]✓ Quick Action installed![/green]")
    console.print(
        "  Select text → right-click → [bold]Services → Read with Lector[/bold]"
    )
    console.print(
        "  (You may need to enable it in System Settings → Keyboard → Keyboard Shortcuts → Services.)"
    )
    console.print(f"  [dim]Installed to {path}[/dim]")
