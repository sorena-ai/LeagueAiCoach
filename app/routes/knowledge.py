"""Out-of-game knowledge route. Audio clip in, spoken answer out."""

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile

from app.assistant.clip import run_voice_clip
from app.assistant.knowledge.agent import get_knowledge_advice
from app.assistant.session import session_manager
from app.auth.dependencies import get_current_user
from app.models.language import SupportedLanguage
from app.users.models import User

router = APIRouter(prefix="/api/v1", tags=["knowledge"])


@router.post("/assistant/knowledge")
async def knowledge_answer(
    audio: UploadFile = File(..., description="Audio file with the user's question"),
    language: SupportedLanguage = Form(
        default=SupportedLanguage.ENGLISH,
        description="Language for transcription and response (default: english)",
    ),
    user: User = Depends(get_current_user),
) -> Response:
    """
    Answer a League of Legends question from a recorded clip.

    Used when the player is not in a match. There is no game_stats field.
    The session is per user and lasts 2 hours.

    Returns a streamed WAV file. 400 is a bad audio file, 401 is a bad token,
    502 is an empty answer.
    """

    async def advise(user_question: str) -> str:
        session = session_manager.get_or_create_knowledge_session(user_id=str(user.id))
        return await get_knowledge_advice(
            session=session,
            user_question=user_question,
            language=language.value,
        )

    return await run_voice_clip(
        audio=audio,
        language=language,
        source="knowledge",
        mode="knowledge",
        advise=advise,
        filename="knowledge_advice.wav",
    )
