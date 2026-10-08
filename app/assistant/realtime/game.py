"""Match identity from a live-client payload, without creating a LangChain agent."""

from __future__ import annotations

import logging

from app.assistant.session import _normalize_position_to_role

logger = logging.getLogger(__name__)


def match_identity(game_stats: dict) -> dict[str, str]:
    """
    Pull the fields the coach session is keyed on.

    Returns riot_id, match_id, champion, role. Missing data becomes "unknown".
    """
    active_player = game_stats.get("activePlayer") or {}
    riot_id = active_player.get("riotId") or "unknown"

    game_start = 0.0
    events = (game_stats.get("events") or {}).get("Events") or []
    for event in events:
        if event.get("EventName") == "GameStart":
            game_start = event.get("EventTime") or 0.0
            break

    champion = "unknown"
    raw_position = "UNKNOWN"
    for player in game_stats.get("allPlayers") or []:
        if player.get("riotId") == riot_id:
            champion = player.get("championName") or "unknown"
            raw_position = player.get("position") or "UNKNOWN"
            break

    role = _normalize_position_to_role(raw_position)
    return {
        "riot_id": riot_id,
        "match_id": f"game_{game_start}",
        "champion": champion,
        "role": role,
    }
