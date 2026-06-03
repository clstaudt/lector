"""Language detection and voice mapping for multilingual TTS."""

from __future__ import annotations

from fast_langdetect import detect

# Maximum number of characters to sample for language detection.
_DETECT_SAMPLE_LENGTH = 500

# ---------------------------------------------------------------------------
# ISO 639-1 → kokoro language code
# ---------------------------------------------------------------------------

ISO_TO_KOKORO: dict[str, str] = {
    "en": "en-us",
    "es": "es",
    "fr": "fr-fr",
    "hi": "hi",
    "it": "it",
    "ja": "ja",
    "pt": "pt-br",
    "zh": "zh",
    "de": "de",
}

# Kokoro codes that require a separate German model rather than the standard
# v1.0 checkpoint.
GERMAN_LANG_CODES: frozenset[str] = frozenset({"de"})

# All kokoro language codes the standard v1.0 model can handle.
STANDARD_LANG_CODES: frozenset[str] = frozenset(
    {"en-us", "en-gb", "es", "fr-fr", "hi", "it", "ja", "pt-br", "zh"}
)

# ---------------------------------------------------------------------------
# Default voice per kokoro language code
# ---------------------------------------------------------------------------

DEFAULT_VOICES: dict[str, str] = {
    "en-us": "af_sky",
    "en-gb": "bf_emma",
    "es": "ef_dora",
    "fr-fr": "ff_siwis",
    "hi": "hf_alpha",
    "it": "if_sara",
    "ja": "jf_alpha",
    "pt-br": "pf_dora",
    "zh": "zf_xiaobei",
    "de": "martin",
}

# Human-readable language names keyed by kokoro code.
LANG_NAMES: dict[str, str] = {
    "en-us": "English (US)",
    "en-gb": "English (GB)",
    "es": "Spanish",
    "fr-fr": "French",
    "hi": "Hindi",
    "it": "Italian",
    "ja": "Japanese",
    "pt-br": "Portuguese (BR)",
    "zh": "Chinese (Mandarin)",
    "de": "German",
}

# All language codes accepted by ``--lang`` (auto + explicit codes).
ALL_LANG_CODES: tuple[str, ...] = ("auto", *sorted(LANG_NAMES))

# Voice prefix → language code (first char of voice name).
_VOICE_PREFIX_TO_LANG: dict[str, str] = {
    "a": "en-us",
    "b": "en-gb",
    "e": "es",
    "f": "fr-fr",
    "h": "hi",
    "i": "it",
    "j": "ja",
    "p": "pt-br",
    "z": "zh",
}


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def detect_language(text: str) -> str:
    """Detect the dominant language of *text* and return a kokoro language code.

    Samples up to :data:`_DETECT_SAMPLE_LENGTH` characters, runs
    ``fast_langdetect.detect``, and maps the ISO 639-1 result to a
    kokoro code.  Falls back to ``"en-us"`` for unrecognised languages.
    """
    sample = text[:_DETECT_SAMPLE_LENGTH].replace("\n", " ")
    results = detect(sample, model="auto", k=1)
    if not results:
        return "en-us"
    iso_code = results[0]["lang"]
    return ISO_TO_KOKORO.get(iso_code, "en-us")


def default_voice_for_lang(lang: str) -> str:
    """Return a sensible default voice for the given kokoro language code."""
    return DEFAULT_VOICES.get(lang, "af_sky")


def is_german(lang: str) -> bool:
    """Return whether *lang* requires the German model."""
    return lang in GERMAN_LANG_CODES


def lang_for_voice(voice: str) -> str | None:
    """Infer the kokoro language code from a voice name prefix.

    Returns *None* when the prefix is not recognised.
    """
    if not voice:
        return None
    if voice == "martin":
        return "de"
    return _VOICE_PREFIX_TO_LANG.get(voice[0])
