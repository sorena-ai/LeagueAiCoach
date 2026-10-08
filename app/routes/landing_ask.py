"""Anonymous knowledge chat for the Sensii landing.

POST /api/v1/assistant/ask
POST /api/v1/assistant/speak

No login. Eight calls per IP per hour. Kept out of the coach routes.
"""

import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.assistant.knowledge_agent import get_knowledge_advice
from app.assistant.session import session_manager
from app.assistant.tts import text_to_speech_stream

router = APIRouter(prefix="/api/v1", tags=["landing"])

_PER_HOUR = 8
_QUESTION_CHARS = 500
_SPEAK_CHARS = 2000
_hits: dict[str, deque[float]] = defaultdict(deque)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=_QUESTION_CHARS)
    session_id: str | None = None


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=_SPEAK_CHARS)


def _client_ip(request: Request) -> str:
    """Use the proxy's client address, which Traefik appends last."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def _limit(bucket: str, ip: str) -> None:
    now = time.monotonic()
    window = _hits[f"{bucket}:{ip}"]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= _PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="You've used the free questions for this hour. Try again later.",
        )
    window.append(now)


def _session_id(raw: str | None) -> str:
    if not raw:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(raw))
    except ValueError:
        raise HTTPException(status_code=400, detail="session_id must be a UUID")


@router.post("/assistant/ask")
async def ask(body: AskBody, request: Request) -> dict[str, str]:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty")

    _limit("ask", _client_ip(request))
    session_id = _session_id(body.session_id)
    session = session_manager.get_or_create_knowledge_session(user_id=session_id)
    reply = await get_knowledge_advice(
        session=session,
        user_question=question,
        language="english",
    )
    if not reply.strip():
        raise HTTPException(status_code=502, detail="The coach returned an empty response")
    return {"reply": reply, "session_id": session_id}


@router.post("/assistant/speak")
async def speak(body: SpeakBody, request: Request) -> StreamingResponse:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to speak")

    _limit("speak", _client_ip(request))

    async def chunks():
        async for chunk in text_to_speech_stream(text):
            yield chunk

    return StreamingResponse(chunks(), media_type="audio/wav")
