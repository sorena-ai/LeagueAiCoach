"""
One Windows client connection relayed to one OpenAI Realtime session.

The client speaks a small JSON/binary protocol. OpenAI events stay on this
server. Transcripts are written to the process log (Datadog when enabled).
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
from typing import Any, Optional

from fastapi import WebSocket
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from app.assistant.messages import MessageHistory
from app.assistant.prompts import build_game_state_report
from app.assistant.realtime.game import match_identity
from app.assistant.realtime.instructions import session_instructions, turn_instructions
from app.assistant.realtime.tools import realtime_tool_definitions, run_tool
from app.config import settings
from app.lib.openai import get_openai_client
from app.models.game_stats import GameStats
from app.models.language import SupportedLanguage, get_language_code
from app.users.models import User
from app.utils.game_stats import GameStateProcessor
from app.utils.log_context import bind_log_context, elapsed_ms

logger = logging.getLogger(__name__)

_active: dict[str, "LiveRelay"] = {}
_active_lock = asyncio.Lock()


def _plain(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_plain(item) for item in value]
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        return _plain(dump())
    return value


def _connect_realtime(model: str):
    client = get_openai_client()
    realtime = getattr(client, "realtime", None)
    if realtime is not None and hasattr(realtime, "connect"):
        return realtime.connect(model=model)
    beta = getattr(client, "beta", None)
    legacy = getattr(beta, "realtime", None) if beta is not None else None
    if legacy is not None and hasattr(legacy, "connect"):
        return legacy.connect(model=model)
    raise RuntimeError(
        "The installed openai package has no Realtime client. "
        "Install openai[realtime]."
    )


class LiveRelay:
    """Bridges one authenticated client socket to OpenAI."""

    def __init__(self, websocket: WebSocket, user: User, language: str):
        self.websocket = websocket
        self.user = user
        self.language = language if language else "english"
        self.history = MessageHistory(
            max_messages=settings.max_history_messages,
            max_chars=settings.max_history_chars,
            summarize=None,
        )
        self._openai_cm: Any = None
        self._conn: Any = None
        self._reader: Optional[asyncio.Task] = None
        self._idle: Optional[asyncio.Task] = None
        self._send_lock = asyncio.Lock()
        self._mode: Optional[str] = None
        self._match_id: Optional[str] = None
        self._champion: Optional[str] = None
        self._role: Optional[str] = None
        self._riot_id: Optional[str] = None
        self._opened_at: float = 0.0
        self._last_activity = time.monotonic()
        self._turn_open = False
        self._bytes_in = 0
        self._commit_at: Optional[float] = None
        self._first_audio_ms: Optional[float] = None
        self._assistant_item_id: Optional[str] = None
        self._assistant_text = ""
        self._user_text: Optional[str] = None
        self._usage: Any = None
        self._tool_names: list[str] = []
        self._game_report: Optional[str] = None
        self._closed = False

    async def run(self) -> None:
        user_id = str(self.user.id)
        async with _active_lock:
            previous = _active.get(user_id)
            if previous is not None and previous is not self:
                await previous.close_replaced()
            _active[user_id] = self

        bind_log_context(
            source="realtime",
            user_id=user_id,
            user_email=self.user.email,
            user_name=self.user.display_name,
            language=self.language,
        )
        self._idle = asyncio.create_task(self._watch_idle())
        try:
            await self._send_json({"type": "ready"})
            while not self._closed:
                message = await self.websocket.receive()
                kind = message.get("type")
                if kind == "websocket.disconnect":
                    break
                self._last_activity = time.monotonic()
                if message.get("bytes"):
                    await self._on_audio(message["bytes"])
                elif message.get("text"):
                    await self._on_text(message["text"])
        except WebSocketDisconnect:
            logger.info("Realtime client disconnected")
        finally:
            async with _active_lock:
                if _active.get(user_id) is self:
                    _active.pop(user_id, None)
            await self._shutdown()

    async def close_replaced(self) -> None:
        self._closed = True
        try:
            await self.websocket.close(code=4000, reason="replaced")
        except Exception:
            logger.debug("Could not close replaced realtime socket", exc_info=True)

    async def _shutdown(self) -> None:
        self._closed = True
        if self._idle is not None:
            self._idle.cancel()
        await self._close_openai()

    async def _watch_idle(self) -> None:
        idle_s = settings.realtime_knowledge_idle_minutes * 60
        try:
            while not self._closed:
                await asyncio.sleep(30)
                if self._turn_open or self._conn is None or self._mode != "knowledge":
                    continue
                if time.monotonic() - self._last_activity >= idle_s:
                    logger.info("Closing idle knowledge realtime session")
                    await self._close_openai()
        except asyncio.CancelledError:
            return

    async def _on_text(self, raw: str) -> None:
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            await self._send_json({"type": "error", "code": "bad_message"})
            return
        kind = event.get("type")
        if kind == "language":
            value = str(event.get("value") or "english")
            self.language = value
            bind_log_context(language=value)
            if self._conn is not None:
                await self._update_transcription_language()
            return
        if kind == "turn.cancel":
            await self._cancel_turn(event.get("played_ms"))
            return
        if kind == "turn.start":
            await self._start_turn(event)
            return
        if kind == "turn.commit":
            await self._commit_turn()
            return
        await self._send_json({"type": "error", "code": "unknown_event"})

    async def _start_turn(self, event: dict) -> None:
        if self._turn_open:
            await self._cancel_turn(event.get("played_ms"))

        game_stats = event.get("game_stats")
        identity: Optional[dict[str, str]] = None
        report: Optional[str] = None
        if isinstance(game_stats, dict) and game_stats:
            try:
                validated = GameStats(data=game_stats)
                stats_json = validated.to_json_string()
                identity = match_identity(game_stats)
                state = GameStateProcessor.process_to_state(stats_json)
                report = build_game_state_report(state)
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                logger.warning("Ignoring game stats for this turn: %s", exc)
                identity = None
                report = None

        in_game = identity is not None
        mode = "in_game" if in_game else "knowledge"
        match_id = identity["match_id"] if identity else None
        if mode != self._mode or match_id != self._match_id:
            self.history.clear()
        self._mode = mode
        self._game_report = report
        if identity:
            self._match_id = identity["match_id"]
            self._champion = identity["champion"]
            self._role = identity["role"]
            self._riot_id = identity["riot_id"]
        else:
            self._match_id = None
            self._champion = None
            self._role = None
            self._riot_id = None

        bind_log_context(
            source="realtime",
            mode="in_game" if in_game else "knowledge",
            champion=self._champion,
            role=self._role,
            match_id=self._match_id,
            riot_id=self._riot_id,
            language=self.language,
        )

        await self._ensure_openai(in_game)
        await self._openai_send({"type": "input_audio_buffer.clear"})

        self._turn_open = True
        self._bytes_in = 0
        self._commit_at = None
        self._first_audio_ms = None
        self._assistant_text = ""
        self._user_text = None
        self._usage = None
        self._tool_names = []
        self._assistant_item_id = None

    async def _on_audio(self, pcm: bytes) -> None:
        if not self._turn_open or self._conn is None or self._commit_at is not None:
            return
        self._bytes_in += len(pcm)
        await self._openai_send(
            {
                "type": "input_audio_buffer.append",
                "audio": base64.b64encode(pcm).decode("ascii"),
            }
        )

    async def _commit_turn(self) -> None:
        if not self._turn_open or self._conn is None:
            await self._send_json({"type": "error", "code": "no_turn"})
            return
        if self._bytes_in <= 0:
            self._turn_open = False
            await self._send_json({"type": "error", "code": "empty_audio"})
            return
        self._commit_at = time.perf_counter()
        await self._openai_send({"type": "input_audio_buffer.commit"})
        await self._openai_send(
            {
                "type": "response.create",
                "response": {
                    "instructions": turn_instructions(
                        language=self.language,
                        game_report=self._game_report,
                    ),
                },
            }
        )

    async def _cancel_turn(self, played_ms: Any) -> None:
        if self._conn is not None:
            await self._openai_send({"type": "response.cancel"})
            if self._assistant_item_id and isinstance(played_ms, (int, float)):
                await self._openai_send(
                    {
                        "type": "conversation.item.truncate",
                        "item_id": self._assistant_item_id,
                        "content_index": 0,
                        "audio_end_ms": int(played_ms),
                    }
                )
            await self._openai_send({"type": "input_audio_buffer.clear"})
            self._assistant_item_id = None
        self._turn_open = False
        self._commit_at = None

    async def _ensure_openai(self, in_game: bool) -> None:
        rotate_s = settings.realtime_rotate_minutes * 60
        expired = (
            self._conn is not None
            and in_game
            and self._opened_at
            and (time.monotonic() - self._opened_at) >= rotate_s
        )
        if self._conn is not None and not expired:
            return
        await self._close_openai()
        instructions = session_instructions(
            in_game=in_game,
            champion=self._champion,
            role=self._role,
        )
        token_limit = (
            settings.realtime_coach_context_tokens
            if in_game
            else settings.realtime_knowledge_context_tokens
        )
        retention = 0.8 if in_game else 0.5
        self._openai_cm = _connect_realtime(settings.openai_realtime_model)
        self._conn = await self._openai_cm.__aenter__()
        self._opened_at = time.monotonic()
        await self._openai_send(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "model": settings.openai_realtime_model,
                    "output_modalities": ["audio"],
                    "instructions": instructions,
                    "tools": realtime_tool_definitions(),
                    "tool_choice": "auto",
                    "reasoning": {"effort": settings.realtime_reasoning_effort},
                    "truncation": {
                        "type": "retention_ratio",
                        "retention_ratio": retention,
                        "token_limits": {"post_instructions": token_limit},
                    },
                    "audio": {
                        "input": {
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "turn_detection": None,
                            "transcription": self._transcription_config(),
                        },
                        "output": {
                            "format": {"type": "audio/pcm", "rate": 24000},
                            "voice": settings.openai_realtime_voice,
                        },
                    },
                },
            }
        )
        await self._seed_history()
        self._reader = asyncio.create_task(self._read_openai())

    def _transcription_config(self) -> dict[str, str]:
        iso = get_language_code(self.language) or SupportedLanguage.get_iso_code(self.language)
        config = {"model": settings.realtime_transcription_model}
        if iso:
            config["language"] = iso
        return config

    async def _update_transcription_language(self) -> None:
        await self._openai_send(
            {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "audio": {"input": {"transcription": self._transcription_config()}},
                },
            }
        )

    async def _seed_history(self) -> None:
        """Put recent text turns into a fresh OpenAI session. Audio is not copied."""
        for message in self.history.get_context_messages()[-8:]:
            role = message.get("role")
            content = message.get("content") or ""
            if role not in ("user", "assistant") or not content:
                continue
            part_type = "input_text" if role == "user" else "output_text"
            await self._openai_send(
                {
                    "type": "conversation.item.create",
                    "item": {
                        "type": "message",
                        "role": role,
                        "content": [{"type": part_type, "text": content[:4000]}],
                    },
                }
            )

    async def _close_openai(self) -> None:
        reader = self._reader
        self._reader = None
        conn = self._conn
        cm = self._openai_cm
        self._conn = None
        self._openai_cm = None
        if reader is not None:
            reader.cancel()
            try:
                await reader
            except (asyncio.CancelledError, Exception):
                pass
        if cm is not None:
            try:
                await cm.__aexit__(None, None, None)
            except Exception:
                logger.debug("OpenAI realtime close failed", exc_info=True)
        elif conn is not None:
            close = getattr(conn, "close", None)
            if close is not None:
                result = close()
                if asyncio.iscoroutine(result):
                    await result

    async def _openai_send(self, event: dict) -> None:
        """Send raw JSON so explicit nulls (turn_detection) are not dropped."""
        if self._conn is None:
            return
        payload = json.dumps(event)
        async with self._send_lock:
            socket = getattr(self._conn, "_connection", None)
            if socket is not None:
                result = socket.send(payload)
            else:
                result = self._conn.send(event)
            if asyncio.iscoroutine(result):
                await result

    async def _read_openai(self) -> None:
        conn = self._conn
        if conn is None:
            return
        try:
            async for raw in conn:
                if self._closed:
                    return
                await self._on_openai(_plain(raw))
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("OpenAI realtime reader stopped")
            await self._send_json({"type": "error", "code": "openai_disconnected"})

    async def _on_openai(self, event: dict) -> None:
        kind = event.get("type")
        if kind == "error":
            logger.error("OpenAI realtime error: %s", event)
            await self._send_json({"type": "error", "code": "openai"})
            return
        if kind in ("response.output_audio.delta", "response.audio.delta"):
            if self._first_audio_ms is None and self._commit_at is not None:
                self._first_audio_ms = elapsed_ms(self._commit_at)
            item_id = event.get("item_id")
            if isinstance(item_id, str):
                self._assistant_item_id = item_id
            delta = event.get("delta")
            if isinstance(delta, str) and delta:
                try:
                    pcm = base64.b64decode(delta)
                except Exception:
                    logger.warning("Bad audio delta from OpenAI")
                    return
                await self.websocket.send_bytes(pcm)
            return
        if kind in (
            "response.output_audio_transcript.delta",
            "response.audio_transcript.delta",
        ):
            delta = event.get("delta")
            if isinstance(delta, str):
                self._assistant_text += delta
            return
        if kind in (
            "response.output_audio_transcript.done",
            "response.audio_transcript.done",
        ):
            transcript = event.get("transcript")
            if isinstance(transcript, str) and transcript:
                self._assistant_text = transcript
            return
        if kind == "conversation.item.input_audio_transcription.completed":
            transcript = event.get("transcript")
            if isinstance(transcript, str):
                self._user_text = transcript
                await self._remember_user(transcript)
                self._log_turn(partial=True)
            return
        if kind == "response.done":
            await self._on_response_done(event)

    async def _on_response_done(self, event: dict) -> None:
        response = event.get("response") or {}
        self._usage = response.get("usage")
        output = response.get("output") or []
        calls = [
            item
            for item in output
            if isinstance(item, dict) and item.get("type") == "function_call"
        ]
        if calls:
            for call in calls:
                name = str(call.get("name") or "")
                self._tool_names.append(name)
                result = await run_tool(name, call.get("arguments") or "{}")
                await self._openai_send(
                    {
                        "type": "conversation.item.create",
                        "item": {
                            "type": "function_call_output",
                            "call_id": call.get("call_id"),
                            "output": result,
                        },
                    }
                )
            await self._openai_send(
                {
                    "type": "response.create",
                    "response": {
                        "instructions": turn_instructions(
                            language=self.language,
                            game_report=self._game_report,
                        ),
                    },
                }
            )
            return

        status = response.get("status") or "completed"
        if self._assistant_text:
            await self.history.add_assistant_message(self._assistant_text)
        self._turn_open = False
        self._log_turn(partial=False, status=str(status))
        await self._send_json({"type": "turn.done", "status": status})

    async def _remember_user(self, transcript: str) -> None:
        # Avoid storing the same question twice if the event is repeated.
        recent = self.history.get_all_messages()
        if recent and recent[-1].get("role") == "user" and recent[-1].get("content") == transcript:
            return
        await self.history.add_user_message(transcript)

    def _log_turn(self, *, partial: bool, status: str = "completed") -> None:
        """Datadog (and stdout) record of what was said. No other store."""
        if not self._user_text and not self._assistant_text and partial:
            return
        total_ms = elapsed_ms(self._commit_at) if self._commit_at else None
        bind_log_context(
            source="realtime",
            outcome="partial" if partial else status,
            mode="in_game" if self._mode == "in_game" else "knowledge",
            language=self.language,
            champion=self._champion,
            role=self._role,
            match_id=self._match_id,
            riot_id=self._riot_id,
            user_transcript=self._user_text,
            assistant_transcript=self._assistant_text,
            interrupted=status == "cancelled",
            tool_calls=",".join(self._tool_names) if self._tool_names else None,
            commit_to_first_audio_ms=self._first_audio_ms,
            turn_total_ms=total_ms,
            realtime_usage=self._usage,
        )
        logger.info(
            "Realtime turn user=%r assistant=%r tools=%s first_audio_ms=%s total_ms=%s",
            self._user_text,
            (self._assistant_text or "")[:500],
            self._tool_names,
            self._first_audio_ms,
            total_ms,
        )

    async def _send_json(self, payload: dict) -> None:
        if self._closed:
            return
        try:
            await self.websocket.send_json(payload)
        except Exception:
            logger.debug("Client socket send failed", exc_info=True)
            self._closed = True
