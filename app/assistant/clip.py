"""Shared record-then-speak path for the coach and knowledge routes."""

import logging
import time
from typing import AsyncGenerator, Awaitable, Callable, Optional

from fastapi import HTTPException, UploadFile
from fastapi.responses import Response, StreamingResponse

from app.config import settings
from app.handlers.audio import validate_and_process_audio
from app.lib.stt import transcribe_audio
from app.lib.tts import text_to_speech_stream
from app.models.language import SupportedLanguage
from app.utils.log_context import bind_log_context, elapsed_ms

logger = logging.getLogger(__name__)


async def _stream_spoken_audio(text: str, request_started: float) -> AsyncGenerator[bytes, None]:
    """Stream TTS audio and log size and latency when the body finishes."""
    tts_started = time.perf_counter()
    audio_bytes = 0
    first_chunk_ms: Optional[float] = None

    try:
        async for chunk in text_to_speech_stream(text):
            if first_chunk_ms is None:
                first_chunk_ms = elapsed_ms(tts_started)
            audio_bytes += len(chunk)
            yield chunk
    except Exception:
        bind_log_context(outcome="tts_failed", audio_out_bytes=audio_bytes)
        logger.exception(
            "TTS streaming failed after %d bytes (%.0f ms into synthesis)",
            audio_bytes,
            elapsed_ms(tts_started),
        )
        raise

    bind_log_context(
        tts_ms=elapsed_ms(tts_started),
        tts_first_chunk_ms=first_chunk_ms,
        audio_out_bytes=audio_bytes,
        total_ms=elapsed_ms(request_started),
    )
    logger.info(
        "Spoken audio delivered - %d bytes, first chunk %.0f ms, synthesis %.0f ms, "
        "request total %.0f ms",
        audio_bytes,
        first_chunk_ms or 0,
        elapsed_ms(tts_started),
        elapsed_ms(request_started),
    )


async def _transcribe_question(audio: UploadFile, language: SupportedLanguage) -> str:
    """Accept the uploaded clip and return the transcribed question."""
    audio_bytes, mime_type = await validate_and_process_audio(
        audio, settings.max_file_size_bytes
    )
    bind_log_context(audio_in_bytes=len(audio_bytes), audio_mime=mime_type)
    logger.info("Audio accepted - %d bytes, mime: %s", len(audio_bytes), mime_type)

    stt_started = time.perf_counter()
    user_question = await transcribe_audio(audio_bytes=audio_bytes, language=language)
    bind_log_context(stt_ms=elapsed_ms(stt_started), question_chars=len(user_question))
    logger.info(
        "Transcribed user question in %.0f ms (%d chars): %s",
        elapsed_ms(stt_started),
        len(user_question),
        user_question,
    )
    return user_question


def _advice_audio(text: str, request_started: float, filename: str) -> StreamingResponse:
    """Stream the spoken answer, or refuse when the agent returned nothing."""
    if not text.strip():
        bind_log_context(outcome="empty")
        logger.error("Agent produced an empty response; refusing to synthesize")
        raise HTTPException(
            status_code=502,
            detail="The assistant returned an empty response. Please try again.",
        )

    return StreamingResponse(
        _stream_spoken_audio(text, request_started),
        media_type="audio/wav",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


async def run_voice_clip(
    *,
    audio: UploadFile,
    language: SupportedLanguage,
    source: str,
    mode: str,
    advise: Callable[[str], Awaitable[str]],
    filename: str,
) -> Response:
    """Transcribe a clip, ask one agent, and stream the spoken reply."""
    request_started = time.perf_counter()
    bind_log_context(
        source=source,
        mode=mode,
        language=language.value,
        upload_filename=audio.filename,
    )
    try:
        logger.info("Voice clip received - mode: %s, language: %s", mode, language.value)
        user_question = await _transcribe_question(audio, language)
        advice_started = time.perf_counter()
        advice = await advise(user_question)
        bind_log_context(advice_ms=elapsed_ms(advice_started), response_chars=len(advice))
        logger.info(
            "Advice ready in %.0f ms (%d chars)",
            elapsed_ms(advice_started),
            len(advice),
        )
        return _advice_audio(advice, request_started, filename)
    except HTTPException:
        raise
    except Exception as exc:
        bind_log_context(outcome="error")
        logger.exception("Voice clip failed after %.0f ms: %s", elapsed_ms(request_started), exc)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(exc)}")
