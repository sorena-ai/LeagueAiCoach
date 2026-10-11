"""Anonymous knowledge chat for the Sensii landing.

POST /api/v1/assistant/ask

No login. Eight questions per IP per hour. Kept out of the coach routes.
"""

import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.assistant.landing.agent import get_landing_advice
from app.assistant.landing.sources import (
    FileLink,
    RepoLink,
    contribute_url,
    file_links,
    repo_links,
)
from app.assistant.session import session_manager
from app.utils.log_context import bind_log_context, get_log_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["landing"])

_PER_HOUR = 8
_QUESTION_CHARS = 500
_hits: dict[str, deque[float]] = defaultdict(deque)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=_QUESTION_CHARS)
    session_id: str | None = None


class AskReply(BaseModel):
    reply: str
    session_id: str
    files: list[FileLink]
    repos: list[RepoLink]
    contribute_url: str | None = None


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
        bind_log_context(outcome="rate_limited")
        logger.info("Landing ask rate limited")
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
        bind_log_context(outcome="invalid")
        raise HTTPException(status_code=400, detail="session_id must be a UUID")


@router.post("/assistant/ask")
async def ask(body: AskBody, request: Request) -> AskReply:
    question = body.question.strip()
    bind_log_context(
        source="landing",
        mode="landing",
        session_new=not body.session_id,
        question_chars=len(question),
    )
    if not question:
        bind_log_context(outcome="empty")
        raise HTTPException(status_code=400, detail="Question is empty")

    _limit(_client_ip(request))
    session_id = _session_id(body.session_id)
    bind_log_context(session_id=session_id)
    session = session_manager.get_or_create_landing_session(session_id)
    answer = await get_landing_advice(session=session, question=question)
    if not answer.reply.strip():
        bind_log_context(outcome="empty")
        raise HTTPException(status_code=502, detail="The coach returned an empty response")
    if get_log_context().get("outcome") == "quota":
        logger.info("Landing ask hit the model quota")
    return AskReply(
        reply=answer.reply,
        session_id=session_id,
        files=file_links(answer.source_paths),
        repos=repo_links(answer.source_paths),
        contribute_url=contribute_url(question, answer.reply, answer.source_paths),
    )
