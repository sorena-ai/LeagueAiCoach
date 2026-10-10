"""In-game coach route. Audio clip plus match stats in, spoken advice out."""

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import ValidationError

from app.assistant.clip import run_voice_clip
from app.assistant.coach.agent import get_coach_advice
from app.assistant.session import session_manager
from app.auth.dependencies import get_current_user
from app.models.game_stats import GameStats
from app.models.language import SupportedLanguage
from app.users.models import User

router = APIRouter(prefix="/api/v1", tags=["coach"])

logger = logging.getLogger(__name__)


def _parse_game_stats(game_stats: str) -> tuple[dict, str]:
    """Validate a required game-stats document. Returns the dict and its JSON."""
    if not game_stats or not game_stats.strip():
        raise HTTPException(status_code=400, detail="game_stats is required")

    try:
        game_stats_dict = json.loads(game_stats)
        validated_stats = GameStats(data=game_stats_dict)
        return game_stats_dict, validated_stats.to_json_string()
    except json.JSONDecodeError:
        logger.warning("Rejected malformed game_stats JSON (%d bytes)", len(game_stats))
        raise HTTPException(status_code=400, detail="Invalid JSON format for game_stats")
    except ValidationError as exc:
        if "too large" in str(exc).lower():
            logger.warning(
                "Rejected oversized game_stats (%d bytes): %s", len(game_stats), exc
            )
            raise HTTPException(status_code=413, detail=str(exc))
        logger.warning("Rejected invalid game_stats: %s", exc)
        raise HTTPException(status_code=400, detail=f"Game stats validation error: {str(exc)}")


@router.post("/assistant/coach")
async def in_game_coaching(
    audio: UploadFile = File(..., description="Audio file with the user's question"),
    game_stats: str = Form(..., description="JSON string of the current match (max 50KB)"),
    language: SupportedLanguage = Form(
        default=SupportedLanguage.ENGLISH,
        description="Language for transcription and response (default: english)",
    ),
    user: User = Depends(get_current_user),
) -> Response:
    """
    Give in-game coaching from a recorded clip and the live match document.

    game_stats is required. A missing or blank value is 400. Invalid JSON is
    400. A document over 50KB is 413. The route does not fall through to the
    knowledge agent.

    Sessions are keyed by Riot ID and the GameStart time, with a 2-hour TTL.
    Starting one drops that user's knowledge session.

    Returns a streamed WAV file.
    """
    game_stats_dict, game_stats_json = _parse_game_stats(game_stats)

    async def advise(user_question: str) -> str:
        session = session_manager.get_or_create_session(
            game_stats_dict=game_stats_dict,
            user_id=str(user.id),
        )
        return await get_coach_advice(
            session=session,
            user_question=user_question,
            game_stats_json=game_stats_json,
            language=language.value,
        )

    return await run_voice_clip(
        audio=audio,
        language=language,
        source="coach",
        mode="in_game",
        advise=advise,
        filename="coach_advice.wav",
    )
