"""Language support models and utilities."""
from enum import Enum
from typing import Dict, List, Optional


class SupportedLanguage(str, Enum):
    """Languages supported for TTS and LLM responses."""
    ENGLISH = "english"
    PERSIAN = "persian"
    SPANISH = "spanish"
    FRENCH = "french"
    GERMAN = "german"
    ITALIAN = "italian"
    PORTUGUESE = "portuguese"
    RUSSIAN = "russian"
    JAPANESE = "japanese"
    KOREAN = "korean"
    CHINESE = "chinese"
    ARABIC = "arabic"
    TURKISH = "turkish"
    POLISH = "polish"
    DUTCH = "dutch"
    SWEDISH = "swedish"
    DANISH = "danish"
    NORWEGIAN = "norwegian"
    FINNISH = "finnish"
    CZECH = "czech"
    GREEK = "greek"
    HEBREW = "hebrew"
    HINDI = "hindi"
    THAI = "thai"
    VIETNAMESE = "vietnamese"
    INDONESIAN = "indonesian"
    MALAY = "malay"
    FILIPINO = "filipino"

    @classmethod
    def get_display_name(cls, language: str) -> str:
        """
        Get the display name for a language.

        Args:
            language: Language enum value

        Returns:
            Human-readable display name
        """
        display_names = {
            "arabic": "Arabic (العربية)",
            "chinese": "Chinese (中文)",
            "czech": "Czech (Čeština)",
            "danish": "Danish (Dansk)",
            "dutch": "Dutch (Nederlands)",
            "english": "English",
            "filipino": "Filipino",
            "finnish": "Finnish (Suomi)",
            "french": "French (Français)",
            "german": "German (Deutsch)",
            "greek": "Greek (Ελληνικά)",
            "hebrew": "Hebrew (עברית)",
            "hindi": "Hindi (हिन्दी)",
            "indonesian": "Indonesian (Bahasa Indonesia)",
            "italian": "Italian (Italiano)",
            "japanese": "Japanese (日本語)",
            "korean": "Korean (한국어)",
            "malay": "Malay (Bahasa Melayu)",
            "norwegian": "Norwegian (Norsk)",
            "persian": "Persian (فارسی)",
            "polish": "Polish (Polski)",
            "portuguese": "Portuguese (Português)",
            "russian": "Russian (Русский)",
            "spanish": "Spanish (Español)",
            "swedish": "Swedish (Svenska)",
            "thai": "Thai (ไทย)",
            "turkish": "Turkish (Türkçe)",
            "vietnamese": "Vietnamese (Tiếng Việt)",
        }
        return display_names.get(language.lower(), language.capitalize())

    @classmethod
    def get_iso_code(cls, language: str) -> Optional[str]:
        """
        Get ISO-639-1 code for a language (used by Whisper API).

        Args:
            language: Language enum value

        Returns:
            ISO-639-1 code or None if not found
        """
        iso_codes = {
            "english": "en",
            "persian": "fa",
            "spanish": "es",
            "french": "fr",
            "german": "de",
            "italian": "it",
            "portuguese": "pt",
            "russian": "ru",
            "japanese": "ja",
            "korean": "ko",
            "chinese": "zh",
            "arabic": "ar",
            "turkish": "tr",
            "polish": "pl",
            "dutch": "nl",
            "swedish": "sv",
            "danish": "da",
            "norwegian": "no",
            "finnish": "fi",
            "czech": "cs",
            "greek": "el",
            "hebrew": "he",
            "hindi": "hi",
            "thai": "th",
            "vietnamese": "vi",
            "indonesian": "id",
            "malay": "ms",
            "filipino": "fil",
        }
        return iso_codes.get(language.lower())

    @classmethod
    def list_all(cls) -> List[Dict[str, str]]:
        """
        List all supported languages with metadata.

        Returns:
            List of dictionaries containing language information
        """
        return [
            {
                "code": lang.value,
                "name": cls.get_display_name(lang.value),
                "iso_code": cls.get_iso_code(lang.value),
            }
            for lang in cls
        ]


# Convenience functions for external use
def get_language_code(language_name: str) -> Optional[str]:
    """
    Convert language name to ISO-639-1 code for Whisper API.

    Args:
        language_name: Language name (e.g., "english", "persian", "spanish", "french")

    Returns:
        ISO-639-1 code or None if not found

    Example:
        >>> get_language_code("english")
        "en"
        >>> get_language_code("persian")
        "fa"
        >>> get_language_code("spanish")
        "es"
    """
    return SupportedLanguage.get_iso_code(language_name)


def get_all_supported_languages() -> List[Dict[str, str]]:
    """
    Get all supported languages for Whisper API transcription.

    Returns a list of all languages with their codes and display names,
    following Whisper API best practices.

    Whisper supports nearly 100 languages, but performs best with major
    languages like English, Spanish, French, German, etc. Accuracy may
    vary for less common languages due to limited training data.

    Returns:
        List of dictionaries with 'code', 'name', and 'iso_code' keys

    Example:
        >>> languages = get_all_supported_languages()
        >>> languages[0]
        {'code': 'english', 'name': 'English', 'iso_code': 'en'}
    """
    return SupportedLanguage.list_all()


def get_language_display_name(language_code: str) -> str:
    """
    Get display name for a language code.

    Args:
        language_code: Language enum value (e.g., "english", "persian")

    Returns:
        Display name or the code itself if not found

    Example:
        >>> get_language_display_name("english")
        "English"
        >>> get_language_display_name("persian")
        "Persian (فارسی)"
    """
    return SupportedLanguage.get_display_name(language_code)

