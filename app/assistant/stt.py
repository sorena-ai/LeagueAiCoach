"""
Speech-to-Text (STT) Module

This module provides audio transcription using OpenAI Whisper API.
Optimized for WAV audio format with support for multiple languages.
"""

import io
import logging
from typing import Optional

from openai import OpenAI

from app.config import settings
from app.models.language import get_language_code

logger = logging.getLogger(__name__)


def transcribe_audio(
        audio_bytes: bytes,
        language: Optional[str] = "english",
) -> str:
    """
    Transcribe WAV audio using OpenAI Whisper API with best practices.

    Best practices implemented:
    - Uses gpt-4o-transcribe model (most accurate)
    - Supports language hints for better accuracy
    - Supports context prompts to guide transcription
    - Optimized for WAV format
    - Provides detailed error logging

    Args:
        audio_bytes: Raw audio bytes in WAV format
        language: Optional language

    Returns:
        Transcribed text string

    Raises:
        Exception: If transcription fails

    """
    logger.info(
        "Starting audio transcription - Size: %d bytes, Language: %s",
        len(audio_bytes),
        language
    )

    try:
        # Initialize OpenAI client
        client = OpenAI(api_key=settings.openai_api_key)

        # Create file-like object from bytes (always WAV format)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "audio.wav"

        # Call OpenAI API
        logger.debug("Calling OpenAI Audio API...")
        transcript = client.audio.transcriptions.create(
            file=audio_file,
            model="gpt-4o-transcribe",
            response_format="text",
            language=get_language_code(language) if language else None,
            temperature=0.2,
            prompt="""This is a user's verbal request for an AI League of Legends coaching application. 
            The speech will be a question or request, potentially containing background noise, accents, and gaming slang (e.g., 'gank', 'CS', 'peel', 'flash', champion names, item names, lane names like 'mid', 'top').
            Transcribe the audio verbatim and ONLY in the language spoken.
            Preserve all proper nouns, game terms, and slang as they are spoken, including mixed languages/code-switching.
            Do not translate. Maintain proper punctuation and capitalization.""",
        )

        logger.info(
            "Transcription successful - Length: %d characters",
            len(transcript)
        )
        logger.debug("Transcribed text: %s", transcript[:200])

        return transcript

    except Exception as e:
        logger.error(
            "Audio transcription failed: %s - Size: %d bytes",
            str(e),
            len(audio_bytes),
            exc_info=True
        )
        raise


