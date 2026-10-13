"""Anonymous endpoints for the Sensii landing.

POST /api/v1/assistant/ask
POST /api/v1/assistant/waitlist

No login. Kept out of the coach routes.
"""

import asyncio
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from app.assistant.landing.agent import get_landing_advice
from app.assistant.landing.sources import (
    FileLink,
    RepoLink,
    contribute_url,
    file_links,
    repo_links,
)
from app.assistant.session import session_manager
from app.assistant.waitlist import WaitlistUnavailable, append_waitlist_row
from app.utils.log_context import bind_log_context, get_log_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["landing"])

_PER_HOUR = 8
_WAITLIST_PER_HOUR = 5
_QUESTION_CHARS = 500
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_hits: dict[str, deque[float]] = defaultdict(deque)
_waitlist_hits: dict[str, deque[float]] = defaultdict(deque)


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
    _limit_window(
        _hits,
        ip,
        _PER_HOUR,
        "You've used the free questions for this hour. Try again later.",
        "Landing ask rate limited",
    )


def _limit_waitlist(ip: str) -> None:
    _limit_window(
        _waitlist_hits,
        ip,
        _WAITLIST_PER_HOUR,
        "Too many signups from this network. Try again later.",
        "Waitlist rate limited",
    )


def _limit_window(hits: dict[str, deque[float]], ip: str, cap: int, detail: str, log_line: str) -> None:
    now = time.monotonic()
    window = hits[ip]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= cap:
        bind_log_context(outcome="rate_limited")
        logger.info(log_line)
        raise HTTPException(status_code=429, detail=detail)
    window.append(now)


def _submitted_at() -> str:
    return datetime.now(timezone.utc).isoformat()


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


class WaitlistBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    platform: str = Field(default="", max_length=32)
    source: str = Field(default="", max_length=64)
    utm_source: str = Field(default="", max_length=200)
    utm_medium: str = Field(default="", max_length=200)
    utm_campaign: str = Field(default="", max_length=200)
    utm_content: str = Field(default="", max_length=200)
    utm_term: str = Field(default="", max_length=200)
    gclid: str = Field(default="", max_length=200)

    @field_validator("email")
    @classmethod
    def _valid_email(cls, value: str) -> str:
        cleaned = value.strip()
        if not _EMAIL.fullmatch(cleaned):
            raise ValueError("invalid email")
        return cleaned

    @field_validator(
        "platform",
        "source",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "gclid",
    )
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()


class WaitlistReply(BaseModel):
    ok: bool = True


@router.post("/assistant/waitlist")
async def waitlist(body: WaitlistBody, request: Request) -> WaitlistReply:
    """Append one Mac or mobile signup to the waitlist sheet."""
    bind_log_context(source="landing", mode="waitlist", platform=body.platform or None)
    _limit_waitlist(_client_ip(request))
    row = [
        body.email,
        _submitted_at(),
        body.platform,
        body.source,
        body.utm_source,
        body.utm_medium,
        body.utm_campaign,
        body.utm_content,
        body.utm_term,
        body.gclid,
    ]
    try:
        await asyncio.to_thread(append_waitlist_row, row)
    except WaitlistUnavailable as exc:
        bind_log_context(outcome="unavailable")
        logger.warning("Waitlist unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Could not save your email. Please try again.",
        )
    logger.info("Waitlist submission saved")
    return WaitlistReply()
