"""Facts the player tells the live coach when the client does not have them.

The League client sometimes reports no position, no keystone, or no champion.
The coach asks once, stores the answer on the relay for the rest of the match,
and later turns treat it as known.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping

_MISSING = frozenset({"", "unknown", "unknown rune", "none"})

_LANES = {
    "top": "top",
    "jungle": "jungle",
    "jng": "jungle",
    "jg": "jungle",
    "mid": "mid",
    "middle": "mid",
    "adc": "adc",
    "bot": "adc",
    "bottom": "adc",
    "support": "support",
    "supp": "support",
    "utility": "support",
}


@dataclass(frozen=True)
class PlayerFacts:
    """What the player has said about themselves this match."""

    champion: str = ""
    lane: str = ""
    keystone: str = ""


def known(value: str) -> str:
    """A client value the coach can trust, or empty when the client does not know."""
    text = " ".join((value or "").split())
    if text.lower() in _MISSING:
        return ""
    return text


def fact_sheet(
    *,
    champion: str,
    lane: str,
    keystone: str,
    said: PlayerFacts,
) -> str:
    """Per-turn note of which facts are settled and which are still missing."""
    lines = [
        "Facts for this match. Something the player told you overrides the client for the rest of the match.",
        _line(
            "Champion",
            known(champion),
            said.champion,
            "Ask which champion they are playing before champion-specific advice.",
        ),
        _line(
            "Lane",
            known(lane),
            said.lane,
            "Ask which lane they are playing only when this answer depends on role. Otherwise do not ask.",
        ),
        _line(
            "Keystone",
            known(keystone),
            said.keystone,
            "Ask which keystone they took only when this answer depends on their rune. Otherwise do not ask.",
        ),
    ]
    return "\n".join(lines)


def apply_player_facts(current: PlayerFacts, args: Mapping[str, Any]) -> tuple[PlayerFacts, str]:
    """Merge one remember_player call. Unknown lanes are rejected, other fields kept."""
    champion = _clean_name(args.get("champion"))
    keystone = _clean_name(args.get("keystone") or args.get("rune"))
    lane_raw = args.get("lane") or args.get("role") or ""
    lane, lane_error = _clean_lane(lane_raw)

    saved: list[str] = []
    if champion:
        saved.append(f"champion {champion}")
    if lane:
        saved.append(f"lane {lane}")
    if keystone:
        saved.append(f"keystone {keystone}")
    if not saved:
        detail = f" {lane_error}" if lane_error else ""
        return current, f"Nothing saved.{detail} Ask for the missing fact in a few words."

    updated = PlayerFacts(
        champion=champion or current.champion,
        lane=lane or current.lane,
        keystone=keystone or current.keystone,
    )
    note = f"Saved {', '.join(saved)} for the rest of this match."
    if lane_error:
        note += f" {lane_error}"
    note += " Answer their question now using this. Do not say that you saved it."
    return updated, note


def _line(label: str, client: str, told: str, ask: str) -> str:
    if told:
        return f"- {label}: {told}. The player told you this. Use it, and do not ask again."
    if client:
        return f"- {label}: {client}. From the client. Do not ask."
    return f"- {label}: unknown. {ask}"


def _clean_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = " ".join(value.split())
    if not text or text.lower() in _MISSING or len(text) > 40:
        return ""
    if text.islower():
        return text.title()
    return text


def _clean_lane(value: Any) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        return "", ""
    words = re.findall(r"[a-z]+", value.lower())
    compact = "".join(words)
    if compact in _LANES:
        return _LANES[compact], ""
    for word in words:
        if word in _LANES:
            return _LANES[word], ""
    return "", "Lane must be top, jungle, mid, adc, or support."
