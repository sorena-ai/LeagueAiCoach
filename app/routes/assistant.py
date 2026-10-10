"""
Shared assistant routes: health, readiness, languages, and suggestions.

The spoken agents live in routes/coach.py and routes/knowledge.py.
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.assistant.data import (
    CHAMPION_BUILDS,
    CHAMPION_COMBOS,
    CHAMPION_GUIDES,
    PLAYBOOK,
)
from app.assistant.session import session_manager
from app.config import settings
from app.models.language import get_all_supported_languages

router = APIRouter(prefix="/api/v1", tags=["assistant"])


@router.on_event("startup")
async def startup_event():
    """Start background tasks on application startup."""
    session_manager.start_cleanup_task()


@router.on_event("shutdown")
async def shutdown_event():
    """Stop background tasks on application shutdown."""
    session_manager.stop_cleanup_task()


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
    Use the `code` value on `/api/v1/assistant/knowledge` and `/api/v1/assistant/coach`:
    ```bash
    curl -X POST "https://api.sensii.gg/api/v1/assistant/knowledge" \\
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
