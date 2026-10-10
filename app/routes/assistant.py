"""
Catalog routes: supported languages and example questions.

The spoken agents live in routes/coach.py and routes/knowledge.py.
Health probes live in routes/health.py.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.assistant.session import session_manager
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
