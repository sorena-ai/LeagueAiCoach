"""Supported languages and example questions."""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.models.language import get_all_supported_languages

router = APIRouter(prefix="/api/v1", tags=["catalog"])


@router.get("/languages")
async def list_languages() -> JSONResponse:
    """
    List all supported languages for voice transcription and text-to-speech.

    Returns the language code, display name, and ISO code. Use the code value
    on `/api/v1/assistant/knowledge` and `/api/v1/assistant/coach`.
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
    """Example questions a player can ask during a match or outside one."""
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
