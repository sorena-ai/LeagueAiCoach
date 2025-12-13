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
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError

from app.assistant.agent import get_coach_advice
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

router = APIRouter(prefix="/api/v1", tags=["assistant"])


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
    try:
        logging.info("Coaching request from user %s (game_stats: %s)",
                    user.id, "provided" if game_stats else "not provided")

        # Validate and process uploaded audio file
        audio_bytes, mime_type = await validate_and_process_audio(
            audio, settings.max_file_size_bytes
        )

        # Transcribe audio using OpenAI Whisper
        logging.info("Transcribing audio with Whisper language: %s",
                    language.value, language or "auto-detect")
        
        user_question = transcribe_audio(
            audio_bytes=audio_bytes,
            language=language,
        )
        logging.info("Transcribed user question: %s", user_question)

        # Branch based on whether game_stats is provided
        if game_stats is None or game_stats.strip() == "":
            # Knowledge mode - no game stats
            logging.info("Using knowledge mode (no game stats)")

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
            logging.info("Using in-game mode (with game stats)")

            # Validate game_stats JSON size using Pydantic model
            try:
                game_stats_dict = json.loads(game_stats)
                # Validate size and convert to JSON string
                validated_stats = GameStats(data=game_stats_dict)
                game_stats_json = validated_stats.to_json_string()
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid JSON format for game_stats"
                )
            except ValidationError as e:
                # Check if it's a size validation error
                if "too large" in str(e).lower():
                    raise HTTPException(
                        status_code=413,
                        detail=str(e)
                    )
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

        # Convert text response to speech using OpenAI TTS with streaming
        audio_stream = text_to_speech_stream(coach_response)

        # Return streaming WAV audio
        return StreamingResponse(
            audio_stream,
            media_type="audio/wav",
            headers={
                "Content-Disposition": "attachment; filename=coach_advice.wav"
            },
        )

    except HTTPException:
        # Re-raise HTTP exceptions from validators
        raise

    except Exception as e:
        # Log the full error with traceback for debugging
        import traceback
        logging.error(f"Coach advice error: {str(e)}")
        logging.error(f"Full traceback:\n{traceback.format_exc()}")

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
        "champions_loaded": 168
    }
    ```

    ## Checks Performed
    1. Champions data directory exists
    2. Champion XML files are present and loaded

    ## Response Codes
    - **200 OK**: Service is ready to serve requests
    - **503 Service Unavailable**: Missing required resources

    ## Use Cases
    - Kubernetes readiness probes
    - Pre-deployment verification
    - Service dependency monitoring

    ## Error Responses
    - **503**: Champions data directory not found
    - **503**: No champion data files found
    """
    # Check if required directories exist
    if not settings.champions_dir.exists():
        raise HTTPException(
            status_code=503,
            detail="League of Legends champions data directory not found",
        )

    # Check if there are champion files in the directory
    champion_files = list(settings.champions_dir.glob("*.xml"))
    if not champion_files:
        raise HTTPException(
            status_code=503,
            detail="No champion data files found in champions directory",
        )

    return JSONResponse(
        status_code=200,
        content={
            "status": "ready",
            "service": "sensei-lol-coach",
            "champions_loaded": len(champion_files),
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
