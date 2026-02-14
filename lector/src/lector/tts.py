"""TTS engine — Kokoro-ONNX with streaming playback."""

from __future__ import annotations

import asyncio
import urllib.request
from pathlib import Path

from kokoro_onnx import Kokoro

MODEL_DIR = Path.home() / ".lector" / "models"

MODELS = {
    "kokoro-v1.0.onnx": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/"
        "download/model-files-v1.0/kokoro-v1.0.onnx"
    ),
    "voices-v1.0.bin": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/"
        "download/model-files-v1.0/voices-v1.0.bin"
    ),
}


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------

def get_model_paths() -> tuple[Path, Path]:
    """Return ``(model_path, voices_path)``."""
    return MODEL_DIR / "kokoro-v1.0.onnx", MODEL_DIR / "voices-v1.0.bin"


def download_models(force: bool = False) -> None:
    """Download model and voice files with a Rich progress bar."""
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        TransferSpeedColumn,
    )

    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        for name, url in MODELS.items():
            dest = MODEL_DIR / name
            if dest.exists() and not force:
                continue

            task_id = progress.add_task(f"Downloading {name}", total=None)

            def _hook(
                block_num: int,
                block_size: int,
                total_size: int,
                _tid: int = task_id,
            ) -> None:
                if total_size > 0:
                    progress.update(
                        _tid,
                        total=total_size,
                        completed=min(block_num * block_size, total_size),
                    )

            urllib.request.urlretrieve(url, dest, reporthook=_hook)
            progress.update(
                task_id, completed=progress.tasks[task_id].total or 0
            )


def ensure_models() -> tuple[Path, Path]:
    """Download models if not already present, then return paths."""
    model_path, voices_path = get_model_paths()
    if not model_path.exists() or not voices_path.exists():
        download_models()
    return model_path, voices_path


# ---------------------------------------------------------------------------
# Engine singleton
# ---------------------------------------------------------------------------

_kokoro: Kokoro | None = None


def get_engine() -> Kokoro:
    """Return (or lazily create) the global Kokoro engine."""
    global _kokoro  # noqa: PLW0603
    if _kokoro is None:
        model_path, voices_path = ensure_models()
        _kokoro = Kokoro(str(model_path), str(voices_path))
    return _kokoro


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

def speak(
    text: str,
    voice: str = "af_heart",
    speed: float = 1.0,
    lang: str = "en-us",
) -> None:
    """Read *text* aloud with an interactive player UI.

    Generation streams in the background while audio plays immediately.
    Supports pause, seek, restart, and quit via keyboard controls.
    """
    from .player import AudioPlayer, play_with_ui

    engine = get_engine()
    player = AudioPlayer(sample_rate=24_000)

    # Pre-compute the expected number of chunks so the UI can show a
    # real progress bar.  Phonemisation + splitting is near-instant.
    phonemes = engine.tokenizer.phonemize(text, lang)
    batched = engine._split_phonemes(phonemes)
    player.set_expected_chunks(len(batched))

    def generate(p: AudioPlayer) -> None:
        async def _stream() -> None:
            stream = engine.create_stream(text, voice=voice, speed=speed, lang=lang)
            async for samples, _sr in stream:
                p.add_chunk(samples)
            p.mark_generation_done()

        asyncio.run(_stream())

    play_with_ui(player, generate)
