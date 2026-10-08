"""Anonymous knowledge chat for the Sensii landing.

POST /api/v1/assistant/ask

No login. Eight questions per IP per hour. Kept out of the coach routes.
"""

import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.assistant.knowledge_agent import get_knowledge_advice
from app.assistant.session import session_manager

router = APIRouter(prefix="/api/v1", tags=["landing"])

_PER_HOUR = 8
_QUESTION_CHARS = 500
_hits: dict[str, deque[float]] = defaultdict(deque)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=_QUESTION_CHARS)
    session_id: str | None = None


def _client_ip(request: Request) -> str:
    """Use the proxy's client address, which Traefik appends last."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        parts = [part.strip() for part in forwarded.split(",") if part.strip()]
        if parts:
            return parts[-1]
    return request.client.host if request.client else "unknown"


def _limit(ip: str) -> None:
    now = time.monotonic()
    window = _hits[ip]
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

    _limit(_client_ip(request))
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
