"""TTS engine — Kokoro-ONNX wrapper and model management."""

from __future__ import annotations

import urllib.request
from pathlib import Path

from kokoro_onnx import Kokoro
from rich.progress import BarColumn, DownloadColumn, Progress, TransferSpeedColumn

from .lang import STANDARD_LANG_CODES, default_voice_for_lang, is_german
from .player import AudioPlayer

MODEL_DIR = Path.home() / ".lector" / "models"

# ---------------------------------------------------------------------------
# Model registries
# ---------------------------------------------------------------------------

MODELS: dict[str, str] = {
    "kokoro-v1.0.onnx": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/"
        "download/model-files-v1.0/kokoro-v1.0.onnx"
    ),
    "voices-v1.0.bin": (
        "https://github.com/thewh1teagle/kokoro-onnx/releases/"
        "download/model-files-v1.0/voices-v1.0.bin"
    ),
}

GERMAN_MODELS: dict[str, str] = {
    "kokoro-martin.onnx": (
        "https://huggingface.co/huggingFresse/"
        "Kokoro-82M-ONNX-German-Martin/resolve/main/kokoro-martin.onnx"
    ),
    "voices-martin.npz": (
        "https://huggingface.co/huggingFresse/"
        "Kokoro-82M-ONNX-German-Martin/resolve/main/voices-martin.npz"
    ),
}


# ---------------------------------------------------------------------------
# Model management
# ---------------------------------------------------------------------------


def get_model_paths() -> tuple[Path, Path]:
    """Return ``(model_path, voices_path)`` for the standard v1.0 model."""
    return MODEL_DIR / "kokoro-v1.0.onnx", MODEL_DIR / "voices-v1.0.bin"


def get_german_model_paths() -> tuple[Path, Path]:
    """Return ``(model_path, voices_path)`` for the German Martin model."""
    return MODEL_DIR / "kokoro-martin.onnx", MODEL_DIR / "voices-martin.npz"


def _download_file_set(
    file_map: dict[str, str],
    *,
    force: bool = False,
) -> None:
    """Download a set of files with a Rich progress bar."""
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    with Progress(
        "[progress.description]{task.description}",
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
    ) as progress:
        for name, url in file_map.items():
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
            progress.update(task_id, completed=progress.tasks[task_id].total or 0)


def download_models(force: bool = False) -> None:
    """Download the standard v1.0 model files with a Rich progress bar."""
    _download_file_set(MODELS, force=force)


def download_german_models(force: bool = False) -> None:
    """Download the German Martin model files with a Rich progress bar."""
    _download_file_set(GERMAN_MODELS, force=force)


def ensure_models() -> tuple[Path, Path]:
    """Download the standard models if absent, then return paths."""
    model_path, voices_path = get_model_paths()
    if not model_path.exists() or not voices_path.exists():
        download_models()
    return model_path, voices_path


def ensure_german_models() -> tuple[Path, Path]:
    """Download the German models if absent, then return paths."""
    model_path, voices_path = get_german_model_paths()
    if not model_path.exists() or not voices_path.exists():
        download_german_models()
    return model_path, voices_path


# ---------------------------------------------------------------------------
# Engine singletons
# ---------------------------------------------------------------------------

_kokoro: Kokoro | None = None
_kokoro_de: Kokoro | None = None


def get_engine(lang: str = "en-us") -> Kokoro:
    """Return (or lazily create) the Kokoro engine for *lang*."""
    if is_german(lang):
        return _get_german_engine()
    return _get_standard_engine()


def _get_standard_engine() -> Kokoro:
    """Return the standard v1.0 engine singleton."""
    global _kokoro  # noqa: PLW0603
    if _kokoro is None:
        model_path, voices_path = ensure_models()
        _kokoro = Kokoro(str(model_path), str(voices_path))
    return _kokoro


def _get_german_engine() -> Kokoro:
    """Return the German Martin engine singleton."""
    global _kokoro_de  # noqa: PLW0603
    if _kokoro_de is None:
        model_path, voices_path = ensure_german_models()
        _kokoro_de = Kokoro(str(model_path), str(voices_path))
    return _kokoro_de


# ---------------------------------------------------------------------------
# Voices
# ---------------------------------------------------------------------------


def get_all_voices(lang: str | None = None) -> list[str]:
    """Return sorted voice names, optionally filtered by language code.

    When *lang* is ``None`` every voice from the standard engine is
    returned.  When a German code is given only the German engine's
    voices are returned.
    """
    if lang is not None and is_german(lang):
        engine = get_engine(lang)
        return sorted(engine.get_voices())

    engine = get_engine("en-us")
    voices = engine.get_voices()

    if lang is not None and lang in STANDARD_LANG_CODES:
        prefix = _lang_to_voice_prefix(lang)
        if prefix:
            voices = [v for v in voices if v.startswith(prefix)]

    return sorted(voices)


def _lang_to_voice_prefix(lang: str) -> str:
    """Map a kokoro language code to the voice-name prefix character."""
    prefixes: dict[str, str] = {
        "en-us": "a",
        "en-gb": "b",
        "es": "e",
        "fr-fr": "f",
        "hi": "h",
        "it": "i",
        "ja": "j",
        "pt-br": "p",
        "zh": "z",
    }
    return prefixes.get(lang, "")


# ---------------------------------------------------------------------------
# Player factory
# ---------------------------------------------------------------------------


def create_player(
    text: str,
    voice: str | None = None,
    speed: float = 1.0,
    lang: str = "en-us",
) -> AudioPlayer:
    """Prepare an :class:`AudioPlayer` for the given text.

    Pre-computes phoneme batches so the player can generate audio on
    demand with a known total chunk count.  Picks the right engine
    (standard vs. German) based on *lang*.
    """
    if voice is None:
        voice = default_voice_for_lang(lang)

    engine = get_engine(lang)

    espeak_lang = "de" if is_german(lang) else lang
    phonemes = engine.tokenizer.phonemize(text, espeak_lang)
    batched = engine._split_phonemes(phonemes)  # noqa: SLF001
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
