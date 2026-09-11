"""
Assistant Routes Module

This module provides FastAPI routes for the Sensii League of Legends coaching assistant.

Available Endpoints:
- POST /api/v1/assistant/coach - In-game coaching and knowledge Q&A
- GET /api/v1/assistant/languages - List all supported languages
- GET /api/v1/assistant/suggestions - Get example coaching questions
- GET /api/v1/health - Health check
- GET /api/v1/ready - Readiness check

Language Support:
The module uses the centralized language system (app.models.language) which supports
28+ languages including English, Persian, Spanish, French, German, Italian, Portuguese,
Russian, Japanese, Korean, Chinese, Arabic, and more.

Authentication:
All coaching endpoints require authentication via JWT token (Bearer token).
"""

import json
import logging
import time
from typing import AsyncGenerator, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError

from app.assistant.agent import get_coach_advice
from app.assistant.data import (
    CHAMPION_BUILDS,
    CHAMPION_COMBOS,
    CHAMPION_GUIDES,
    PLAYBOOK,
)
from app.assistant.knowledge_agent import get_knowledge_advice
from app.assistant.models import CoachResponse
from app.assistant.session import session_manager
from app.assistant.stt import transcribe_audio
from app.assistant.tts import text_to_speech, text_to_speech_stream
from app.auth.dependencies import get_current_user
from app.config import settings
from app.handlers.audio import validate_and_process_audio
from app.models.language import SupportedLanguage, get_language_code, get_all_supported_languages
from app.users.models import User
from app.models.game_stats import GameStats
from app.utils.log_context import bind_log_context, elapsed_ms

router = APIRouter(prefix="/api/v1", tags=["assistant"])

logger = logging.getLogger(__name__)


async def _stream_coach_audio(text: str, request_started: float) -> AsyncGenerator[bytes, None]:
    """
    Stream TTS audio, reporting size and latency once the response completes.

    The body iterator runs after the handler returns, so without this a TTS
    failure surfaces only as an ASGI exception group with no request context
    and no indication of how far the response got.
    """
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
        "Coaching audio delivered - %d bytes, first chunk %.0f ms, synthesis %.0f ms, "
        "request total %.0f ms",
        audio_bytes,
        first_chunk_ms or 0,
        elapsed_ms(tts_started),
        elapsed_ms(request_started),
    )


# Start session cleanup background task on module import
@router.on_event("startup")
async def startup_event():
    """Start background tasks on application startup."""
    session_manager.start_cleanup_task()


@router.on_event("shutdown")
async def shutdown_event():
    """Stop background tasks on application shutdown."""
    session_manager.stop_cleanup_task()


@router.post("/assistant/coach")
async def in_game_coaching(
    audio: UploadFile = File(..., description="Audio file with user's question"),
    game_stats: Optional[str] = Form(None, description="JSON string containing current game statistics (optional)"),
    language: SupportedLanguage = Form(
        default=SupportedLanguage.ENGLISH,
        description="Language for transcription and response (default: english)"
    ),
    user: User = Depends(get_current_user),
) -> Response:
    """
    Provide personalized coaching advice via voice assistant with multilingual support.

    This endpoint operates in two intelligent modes:

    ## In-Game Mode (game_stats provided)
    - Analyzes current game state and provides tactical advice
    - Sessions maintained per (username, GameStart event time) with 2-hour TTL
    - Agent has access to champion guides, playbooks, and real-time game data
    - Provides context-aware advice based on your champion, lane, items, and match state

    ## Knowledge Mode (game_stats omitted/null)
    - Answers general League of Legends questions
    - Sessions maintained per user with 2-hour TTL
    - Useful for learning about champions, items, strategies outside of matches
    - Encourages using in-game mode for personalized advice during actual games

    ## Request Parameters
    - **audio**: Audio file with spoken question (supports WAV, MP3, MP4, MPEG, MPGA, M4A, WEBM)
    - **game_stats**: Optional JSON string with game statistics (max 50KB)
    - **language**: Language for transcription and TTS response (default: english)

    ## Language Support
    Supports 28+ languages including:
    - English, Persian (فارسی), Spanish (Español), French (Français)
    - German (Deutsch), Italian (Italiano), Portuguese (Português)
    - Russian (Русский), Japanese (日本語), Korean (한국어)
    - Chinese (中文), Arabic (العربية), Turkish (Türkçe)
    - And 15+ more languages

    Use GET /api/v1/assistant/languages to see the full list.

    ## Response
    - Returns WAV audio file containing the coaching advice in the requested language
    - Audio uses OpenAI's TTS with streaming for low latency

    ## Error Responses
    - **400 Bad Request**: Invalid audio format or game_stats JSON
    - **401 Unauthorized**: Missing or invalid authentication token
    - **413 Payload Too Large**: game_stats JSON exceeds 50KB limit
    - **500 Internal Server Error**: Unexpected processing error

    ## Example Usage
    ```bash
    curl -X POST "https://api.sensii.gg/api/v1/assistant/coach" \\
      -H "Authorization: Bearer YOUR_TOKEN" \\
      -F "audio=@question.wav" \\
      -F "game_stats={...}" \\
      -F "language=english"
    ```
    """
    request_started = time.perf_counter()
    in_game = bool(game_stats and game_stats.strip())
    bind_log_context(
        mode="in_game" if in_game else "knowledge",
        language=language.value,
        upload_filename=audio.filename,
    )

    try:
        logger.info(
            "Coaching request received - mode: %s, language: %s",
            "in_game" if in_game else "knowledge",
            language.value,
        )

        # Validate and process uploaded audio file
        audio_bytes, mime_type = await validate_and_process_audio(
            audio, settings.max_file_size_bytes
        )
        bind_log_context(audio_in_bytes=len(audio_bytes), audio_mime=mime_type)
        logger.info(
            "Audio accepted - %d bytes, mime: %s", len(audio_bytes), mime_type
        )

        # Transcribe audio using OpenAI Whisper
        stt_started = time.perf_counter()
        user_question = transcribe_audio(
            audio_bytes=audio_bytes,
            language=language,
        )
        bind_log_context(
            stt_ms=elapsed_ms(stt_started), question_chars=len(user_question)
        )
        logger.info(
            "Transcribed user question in %.0f ms (%d chars): %s",
            elapsed_ms(stt_started),
            len(user_question),
            user_question,
        )

        advice_started = time.perf_counter()

        # Branch based on whether game_stats is provided
        if not in_game:
            # Knowledge mode - no game stats
            logger.info("Using knowledge mode (no game stats)")

            # Get or create knowledge session
            session = session_manager.get_or_create_knowledge_session(
                user_id=str(user.id),
            )

            # Get knowledge advice with transcribed question
            coach_response: str = get_knowledge_advice(
                session=session,
                user_question=user_question,
                language=language.value,
            )
        else:
            # In-game mode - with game stats
            logger.info(
                "Using in-game mode (%d bytes of game stats)", len(game_stats)
            )

            # Validate game_stats JSON size using Pydantic model
            try:
                game_stats_dict = json.loads(game_stats)
                # Validate size and convert to JSON string
                validated_stats = GameStats(data=game_stats_dict)
                game_stats_json = validated_stats.to_json_string()
            except json.JSONDecodeError:
                logger.warning(
                    "Rejected malformed game_stats JSON (%d bytes)", len(game_stats)
                )
                raise HTTPException(
                    status_code=400,
                    detail="Invalid JSON format for game_stats"
                )
            except ValidationError as e:
                # Check if it's a size validation error
                if "too large" in str(e).lower():
                    logger.warning(
                        "Rejected oversized game_stats (%d bytes): %s",
                        len(game_stats),
                        e,
                    )
                    raise HTTPException(
                        status_code=413,
                        detail=str(e)
                    )
                logger.warning("Rejected invalid game_stats: %s", e)
                raise HTTPException(
                    status_code=400,
                    detail=f"Game stats validation error: {str(e)}"
                )

            # Get or create session (removes any knowledge session for this user)
            session = session_manager.get_or_create_session(
                game_stats_dict=game_stats_dict,
                user_id=str(user.id)
            )

            # Get coaching advice using transcribed question
            coach_response: str = get_coach_advice(
                session=session,
                user_question=user_question,
                game_stats_json=game_stats_json,
                language=language.value,
            )

        bind_log_context(
            advice_ms=elapsed_ms(advice_started),
            response_chars=len(coach_response),
        )
        logger.info(
            "Coach advice ready in %.0f ms (%d chars)",
            elapsed_ms(advice_started),
            len(coach_response),
        )

        if not coach_response.strip():
            # TTS rejects empty input, and the resulting 400 is opaque. Fail
            # here instead, where the cause is obvious.
            logger.error("Coach produced an empty response; refusing to synthesize")
            raise HTTPException(
                status_code=502,
                detail="The coach returned an empty response. Please try again.",
            )

        # Convert text response to speech using OpenAI TTS with streaming
        # Return streaming WAV audio
        return StreamingResponse(
            _stream_coach_audio(coach_response, request_started),
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=coach_advice.wav"
            },
        )

    except HTTPException:
        # Re-raise HTTP exceptions from validators
        raise

    except Exception as e:
        # exc_info carries the traceback to both stdout and Datadog error
        # tracking; the request context says who it happened to and how far in.
        logger.exception(
            "Coach advice failed after %.0f ms: %s", elapsed_ms(request_started), e
        )

        # Catch any other unexpected errors
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}",
        )


@router.get("/health")
async def health_check() -> JSONResponse:
    """
    Health check endpoint for monitoring and load balancers.

    Returns a simple health status indicating the service is running.
    This endpoint always returns 200 OK if the service is operational.

    ## Response Format
    ```json
    {
        "status": "healthy",
        "service": "sensei-lol-coach"
    }
    ```

    ## Use Cases
    - Load balancer health checks
    - Kubernetes liveness probes
    - Basic service availability monitoring

    ## Response Codes
    - **200 OK**: Service is running and healthy
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "sensei-lol-coach",
        },
    )


@router.get("/ready")
async def readiness_check() -> JSONResponse:
    """
    Readiness check endpoint for monitoring and orchestration.

    Verifies that the service has all required resources loaded and is ready
    to serve requests. Checks for the presence of champion data files.

    ## Response Format
    ```json
    {
        "status": "ready",
        "service": "sensei-lol-coach",
        "champions_loaded": 172
    }
    ```

    ## Checks Performed
    1. Champion guide, combo, build, and playbook directories exist
    2. In-memory champion data was loaded

    ## Response Codes
    - **200 OK**: Service is ready to serve requests
    - **503 Service Unavailable**: Missing required resources

    ## Use Cases
    - Kubernetes readiness probes
    - Pre-deployment verification
    - Service dependency monitoring

    ## Error Responses
    - **503**: Required champion data directory not found
    - **503**: No champion guide data loaded
    """
    required_dirs = {
        "combos": settings.champion_combos_dir,
        "builds": settings.champion_builds_dir,
        "guides": settings.champion_guide_dir,
        "playbook": settings.playbook_dir,
    }
    for label, directory in required_dirs.items():
        if not directory.exists():
            raise HTTPException(
                status_code=503,
                detail=f"Champion {label} data directory not found",
            )

    if not CHAMPION_GUIDES:
        raise HTTPException(
            status_code=503,
            detail="No champion guide data loaded",
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "service": "sensei-lol-coach",
            "champions_loaded": len(CHAMPION_GUIDES),
            "combos_loaded": len(CHAMPION_COMBOS),
            "builds_loaded": len(CHAMPION_BUILDS),
            "playbook_files": len(PLAYBOOK),
        },
    )


@router.get("/languages")
async def list_languages() -> JSONResponse:
    """
    List all supported languages for voice transcription and text-to-speech.

    Returns comprehensive information about all 28+ languages supported by the
    Sensii coaching assistant. Languages are powered by OpenAI's Whisper (STT)
    and TTS APIs.

    ## Performance Notes
    - Whisper performs best with major languages (English, Spanish, French, German)
    - Accuracy may vary for less common languages due to training data limitations
    - All languages support both transcription (input) and speech synthesis (output)

    ## Response Format
    ```json
    {
        "languages": [
            {
                "code": "english",
                "name": "English",
                "iso_code": "en"
            },
            {
                "code": "persian",
                "name": "Persian (فارسی)",
                "iso_code": "fa"
            },
            ...
        ],
        "default": "english",
        "count": 28
    }
    ```

    ## Response Fields
    - **code**: Language identifier used in API requests (e.g., "english", "spanish")
    - **name**: Display name with native script if applicable (e.g., "Japanese (日本語)")
    - **iso_code**: ISO-639-1 language code (e.g., "en", "ja")
    - **default**: Default language if none specified
    - **count**: Total number of supported languages

    ## Supported Languages Include
    English, Persian, Spanish, French, German, Italian, Portuguese, Russian,
    Japanese, Korean, Chinese, Arabic, Turkish, Polish, Dutch, Swedish, Danish,
    Norwegian, Finnish, Czech, Greek, Hebrew, Hindi, Thai, Vietnamese,
    Indonesian, Malay, Filipino

    ## Usage
    Use the `code` value when making requests to `/api/v1/assistant/coach`:
    ```bash
    curl -X POST "https://api.sensii.gg/api/v1/assistant/coach" \\
      -F "language=japanese"
    ```
    """
    languages = get_all_supported_languages()
    return JSONResponse(
        status_code=200,
        content={
            "languages": languages,
            "default": "english",
            "count": len(languages),
        },
    )


@router.get("/suggestions")
async def get_suggestions() -> JSONResponse:
    """
    Get suggested coaching questions for users.

    Returns a curated list of example questions that users can ask Sensii
    during gameplay or for general League of Legends knowledge.

    ## Response Format
    ```json
    {
        "suggestions": [
            "What's the best second item for me here?",
            "What should we do after taking mid inhib?",
            "Should I freeze or push the wave right now?",
            "Who should I focus in teamfights?"
        ]
    }
    ```

    ## Use Cases
    - Help new users understand what kinds of questions to ask
    - Provide quick-start examples in UI/UX
    - Demonstrate the range of coaching capabilities

    ## Suggestion Categories
    The suggestions cover various aspects of gameplay:
    - **Itemization**: Build paths and item choices
    - **Macro Strategy**: Objective control and map movements
    - **Wave Management**: Lane control and CS optimization
    - **Teamfighting**: Target selection and positioning

    ## Usage Example
    These suggestions can be displayed in a client application to help users
    get started with voice coaching.
    """
    suggestions = [
        "What's the best second item for me here?",
        "What should we do after taking mid inhib?",
        "Should I freeze or push the wave right now?",
        "Who should I focus in teamfights?",
    ]

    return JSONResponse(
        status_code=200,
        content={
            "suggestions": suggestions,
        },
    )
