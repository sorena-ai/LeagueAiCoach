from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Dict, Optional


class SessionStatus(str, Enum):
    PENDING = "pending"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class SessionData:
    session_id: str
    created_at: datetime
    expires_at: datetime
    status: SessionStatus = SessionStatus.PENDING
    state: Optional[str] = None
    code_verifier: Optional[str] = None
    session_token: Optional[str] = None
    refresh_token: Optional[str] = None
    user_id: Optional[str] = None
    error: Optional[str] = None


class SessionStore:
    """In-memory session store protected by an asyncio lock."""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionData] = {}
        self._state_index: Dict[str, str] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, ttl_seconds: int, session_id: str) -> SessionData:
        async with self._lock:
            self._purge_expired_locked()
            now = datetime.now(timezone.utc)
            data = SessionData(
                session_id=session_id,
                created_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            self._sessions[session_id] = data
            return data

    async def attach_pkce(self, session_id: str, state: str, code_verifier: str) -> SessionData:
        async with self._lock:
            self._purge_expired_locked()
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError("Session not found")
            session.state = state
            session.code_verifier = code_verifier
            self._state_index[state] = session_id
            return session

    async def get_by_id(self, session_id: str) -> Optional[SessionData]:
        async with self._lock:
            self._purge_expired_locked()
            return self._sessions.get(session_id)

    async def get_by_state(self, state: str) -> Optional[SessionData]:
        async with self._lock:
            self._purge_expired_locked()
            session_id = self._state_index.get(state)
            if session_id is None:
                return None
            return self._sessions.get(session_id)

    async def mark_complete(self, session_id: str, token: str, refresh_token: str, user_id: str) -> SessionData:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError("Session not found")
            session.status = SessionStatus.COMPLETE
            session.session_token = token
            session.refresh_token = refresh_token
            session.user_id = user_id
            session.error = None
            return session

    async def mark_failed(self, session_id: str, error: str) -> SessionData:
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                raise KeyError("Session not found")
            session.status = SessionStatus.FAILED
            session.error = error
            return session

    def _purge_expired_locked(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [sid for sid, data in self._sessions.items() if data.expires_at < now]
        for sid in expired:
            self._sessions.pop(sid, None)
        for state, sid in list(self._state_index.items()):
            if sid not in self._sessions:
                self._state_index.pop(state, None)


session_store = SessionStore()
