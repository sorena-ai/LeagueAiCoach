"""Temporary local server for the Sensii landing knowledge chat.

Dev-only. It loads local keys, then mounts the same landing router the API uses:

    POST /api/v1/assistant/ask     { question, session_id? } -> { reply, session_id }

Run from the LeagueAiCoach repo:

    .venv/bin/python scripts/landing_ask_dev.py

Listens on http://127.0.0.1:8010
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

ROOT = Path(__file__).resolve().parents[1]
CATALOG_ENV = ROOT.parent / "service-catalog-mcp" / ".env"
HOST = "127.0.0.1"
PORT = 8010

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

from app.assistant.session import session_manager  # noqa: E402
from app.routes.landing_ask import router as landing_ask_router  # noqa: E402

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
app.include_router(landing_ask_router)


@app.on_event("startup")
async def _startup() -> None:
    session_manager.start_cleanup_task()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "landing-ask-dev"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
