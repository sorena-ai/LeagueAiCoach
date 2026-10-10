"""
WebSocket route for the in-game realtime coach.

Clients use /api/v1/assistant/live only while a match is running.
turn.start must include a valid game_stats object. Out-of-game questions
use POST /api/v1/assistant/knowledge.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket

from app.assistant.realtime.relay import LiveRelay
from app.core.security import decode_session_token
from app.users import repository as user_repository

router = APIRouter(prefix="/api/v1", tags=["realtime"])

logger = logging.getLogger(__name__)


@router.websocket("/assistant/live")
async def assistant_live(websocket: WebSocket) -> None:
    """Authenticated speech relay. Close code 4401 means the JWT was rejected."""
    await websocket.accept()
    authorization = websocket.headers.get("authorization")
    language = websocket.query_params.get("language") or "english"
    if not authorization or not authorization.lower().startswith("bearer "):
        await websocket.close(code=4401)
        return
    token = authorization.split(" ", 1)[1].strip()
    if not token:
        await websocket.close(code=4401)
        return
    try:
        payload = decode_session_token(token)
    except Exception:
        logger.info("Realtime socket rejected: invalid session token")
        await websocket.close(code=4401)
        return
    user_id = payload.get("sub")
    user = await user_repository.get_user_by_id(user_id) if user_id else None
    if user is None:
        await websocket.close(code=4401)
        return

    await LiveRelay(websocket, user, language).run()
