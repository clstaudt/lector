"""TTS engine — Kokoro-ONNX wrapper and model management."""

from __future__ import annotations

import urllib.request
from pathlib import Path

from kokoro_onnx import Kokoro
from rich.progress import BarColumn, DownloadColumn, Progress, TransferSpeedColumn

from .player import AudioPlayer

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
# Player factory
# ---------------------------------------------------------------------------


def create_player(
    text: str,
    voice: str = "af_sky",
    speed: float = 1.0,
    lang: str = "en-us",
) -> AudioPlayer:
    """Prepare an :class:`AudioPlayer` for the given text.

    Pre-computes phoneme batches so the player can generate audio on
    demand with a known total chunk count.
    """
    engine = get_engine()
    phonemes = engine.tokenizer.phonemize(text, lang)
    batched = engine._split_phonemes(phonemes)
    voice_style = engine.get_voice_style(voice)
    return AudioPlayer(
        sample_rate=24_000,
        voice=voice,
        speed=speed,
        lang=lang,
        engine=engine,
        voice_style=voice_style,
        phoneme_batches=batched,
    )
