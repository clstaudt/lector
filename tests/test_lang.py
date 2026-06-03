"""Tests for lector.lang — language detection and voice mapping."""

from __future__ import annotations

from unittest.mock import patch

from lector.lang import (
    ALL_LANG_CODES,
    DEFAULT_VOICES,
    GERMAN_LANG_CODES,
    ISO_TO_KOKORO,
    LANG_NAMES,
    STANDARD_LANG_CODES,
    default_voice_for_lang,
    detect_language,
    is_german,
    lang_for_voice,
)


class TestMappingConsistency:
    def test_every_kokoro_code_has_a_default_voice(self) -> None:
        all_codes = STANDARD_LANG_CODES | GERMAN_LANG_CODES
        for code in all_codes:
            assert code in DEFAULT_VOICES, f"No default voice for {code}"

    def test_every_kokoro_code_has_a_name(self) -> None:
        all_codes = STANDARD_LANG_CODES | GERMAN_LANG_CODES
        for code in all_codes:
            assert code in LANG_NAMES, f"No human name for {code}"

    def test_all_lang_codes_starts_with_auto(self) -> None:
        assert ALL_LANG_CODES[0] == "auto"

    def test_all_lang_codes_contains_every_named_lang(self) -> None:
        for code in LANG_NAMES:
            assert code in ALL_LANG_CODES

    def test_iso_to_kokoro_maps_known_languages(self) -> None:
        assert ISO_TO_KOKORO["en"] == "en-us"
        assert ISO_TO_KOKORO["de"] == "de"
        assert ISO_TO_KOKORO["fr"] == "fr-fr"

    def test_german_is_not_in_standard_codes(self) -> None:
        assert "de" not in STANDARD_LANG_CODES

    def test_german_is_in_german_codes(self) -> None:
        assert "de" in GERMAN_LANG_CODES


class TestDetectLanguage:
    def test_english_text(self) -> None:
        result = detect_language(
            "This is a fairly long English sentence used for language detection testing."
        )
        assert result == "en-us"

    def test_german_text(self) -> None:
        result = detect_language(
            "Dies ist ein langer deutscher Satz, der für die Spracherkennung verwendet wird."
        )
        assert result == "de"

    def test_french_text(self) -> None:
        result = detect_language(
            "Ceci est une longue phrase française utilisée pour tester la détection de la langue."
        )
        assert result == "fr-fr"

    def test_spanish_text(self) -> None:
        result = detect_language(
            "Esta es una oración larga en español utilizada para probar la detección del idioma."
        )
        assert result == "es"

    def test_unsupported_language_falls_back_to_english(self) -> None:
        with patch("lector.lang.detect", return_value=[{"lang": "ko", "score": 0.99}]):
            assert detect_language("한국어 텍스트") == "en-us"

    def test_empty_results_falls_back_to_english(self) -> None:
        with patch("lector.lang.detect", return_value=[]):
            assert detect_language("???") == "en-us"


class TestDefaultVoiceForLang:
    def test_english_default(self) -> None:
        assert default_voice_for_lang("en-us") == "af_sky"

    def test_german_default(self) -> None:
        assert default_voice_for_lang("de") == "martin"

    def test_unknown_lang_falls_back(self) -> None:
        assert default_voice_for_lang("xx-unknown") == "af_sky"


class TestIsGerman:
    def test_de_is_german(self) -> None:
        assert is_german("de") is True

    def test_en_is_not_german(self) -> None:
        assert is_german("en-us") is False


class TestLangForVoice:
    def test_american_english_prefix(self) -> None:
        assert lang_for_voice("af_sky") == "en-us"

    def test_british_english_prefix(self) -> None:
        assert lang_for_voice("bf_emma") == "en-gb"

    def test_german_martin_voice(self) -> None:
        assert lang_for_voice("martin") == "de"

    def test_french_prefix(self) -> None:
        assert lang_for_voice("ff_siwis") == "fr-fr"

    def test_unknown_prefix(self) -> None:
        assert lang_for_voice("xx_unknown") is None

    def test_empty_string(self) -> None:
        assert lang_for_voice("") is None
