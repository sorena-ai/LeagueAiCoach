"""Temporary local server for the Sensii landing knowledge chat.

This is a dev-only stand-in. It is not mounted in the production app.
It imports the real knowledge agent and OpenAI speech, then exposes the two
routes the landing hero calls:

    POST /api/v1/assistant/ask     { question, session_id? } -> { reply, session_id }
    POST /api/v1/assistant/speak   { text } -> audio/wav

Run from the LeagueAiCoach repo:

    .venv/bin/python scripts/landing_ask_dev.py

Listens on http://127.0.0.1:8010
"""

from __future__ import annotations

import os
import re
import sys
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ENV = ROOT.parent / "service-catalog-mcp" / ".env"
HOST = "127.0.0.1"
PORT = 8010
MAX_QUESTION_CHARS = 500
MAX_SPEAK_CHARS = 2000
ASKS_PER_HOUR = 8

PLACEHOLDER_PREFIXES = ("your_", "replace-me", "changeme")


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _usable(value: str | None) -> bool:
    if not value:
        return False
    lowered = value.strip().lower()
    return not any(lowered.startswith(prefix) for prefix in PLACEHOLDER_PREFIXES)


def _fill(name: str, *candidates: str | None) -> None:
    if _usable(os.environ.get(name)):
        return
    for candidate in candidates:
        if _usable(candidate):
            os.environ[name] = candidate.strip()
            return


def bootstrap_env() -> None:
    """Load coach keys before app settings are imported.

    LeagueAiCoach/.env wins when it holds a real value. Otherwise the script
    borrows OPENAI_API_KEY and GEMINI_API_KEY from service-catalog-mcp/.env.
    GROK_API_KEY is required by Settings even when the coach provider is Gemini,
    so a dummy value is set only when no real key is present.
    """
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))

    coach = _parse_env_file(ROOT / ".env")
    catalog = _parse_env_file(CATALOG_ENV)

    _fill("OPENAI_API_KEY", coach.get("OPENAI_API_KEY"), catalog.get("OPENAI_API_KEY"))
    _fill(
        "GOOGLE_API_KEY",
        coach.get("GOOGLE_API_KEY"),
        catalog.get("GOOGLE_API_KEY"),
        catalog.get("GEMINI_API_KEY"),
    )
    _fill("GROK_API_KEY", coach.get("GROK_API_KEY"), catalog.get("GROK_API_KEY"))
    _fill("COACH_PROVIDER", coach.get("COACH_PROVIDER"), os.environ.get("COACH_PROVIDER"), "gemini")
    _fill(
        "COACH_MODEL",
        coach.get("COACH_MODEL"),
        os.environ.get("COACH_MODEL"),
        "gemini-flash-lite-latest",
    )

    if not _usable(os.environ.get("GROK_API_KEY")):
        os.environ["GROK_API_KEY"] = "unused-local-dev"

    missing = [
        name
        for name in ("OPENAI_API_KEY", "GOOGLE_API_KEY")
        if not _usable(os.environ.get(name))
    ]
    if missing:
        raise SystemExit(
            "Missing API keys for the local ask server: "
            + ", ".join(missing)
            + ". Add them to LeagueAiCoach/.env."
        )

    print(
        "landing ask dev provider="
        + os.environ["COACH_PROVIDER"]
        + " model="
        + os.environ["COACH_MODEL"],
        flush=True,
    )


bootstrap_env()

from app.assistant.knowledge_agent import get_knowledge_advice  # noqa: E402
from app.assistant.session import session_manager  # noqa: E402
from app.assistant.tts import text_to_speech_stream  # noqa: E402

_LAUNCH_PITCH = re.compile(
    r"\s*(?:open up league|launch league|start a match|i['’]m here for league knowledge)\b[\s\S]*$",
    re.IGNORECASE,
)


def _without_launch_pitch(text: str) -> str:
    cleaned = _LAUNCH_PITCH.sub("", text).strip()
    return cleaned or text


app = FastAPI(title="Sensii landing ask (local)", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

_asks: dict[str, deque[float]] = defaultdict(deque)


class AskBody(BaseModel):
    question: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    session_id: str | None = None


class SpeakBody(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_SPEAK_CHARS)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limit_asks(ip: str) -> None:
    now = time.monotonic()
    window = _asks[ip]
    while window and now - window[0] > 3600:
        window.popleft()
    if len(window) >= ASKS_PER_HOUR:
        raise HTTPException(
            status_code=429,
            detail="You've used the free questions for this hour. Try again later.",
        )
    window.append(now)


def _session_id(raw: str | None) -> str:
    if raw:
        try:
            return str(uuid.UUID(raw))
        except ValueError:
            raise HTTPException(status_code=400, detail="session_id must be a UUID")
    return str(uuid.uuid4())


@app.on_event("startup")
async def _startup() -> None:
    session_manager.start_cleanup_task()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "landing-ask-dev"}


@app.post("/api/v1/assistant/ask")
async def ask(body: AskBody, request: Request) -> dict[str, str]:
    question = body.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(status_code=400, detail="Question is too long")

    _limit_asks(_client_ip(request))
    session_id = _session_id(body.session_id)
    session = session_manager.get_or_create_knowledge_session(
        user_id=session_id,
        end_with_launch_reminder=False,
    )
    reply = await get_knowledge_advice(
        session=session,
        user_question=question,
        language="english",
    )
    reply = _without_launch_pitch(reply)
    if not reply.strip():
        raise HTTPException(status_code=502, detail="The coach returned an empty response")
    return {"reply": reply, "session_id": session_id}


@app.post("/api/v1/assistant/speak")
async def speak(body: SpeakBody) -> StreamingResponse:
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to speak")

    async def chunks():
        async for chunk in text_to_speech_stream(text):
            yield chunk

    return StreamingResponse(chunks(), media_type="audio/wav")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
