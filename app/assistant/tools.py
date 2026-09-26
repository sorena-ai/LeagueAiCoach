"""
Champion data lookup tools for the coaching agents.

These tools let an agent fetch champion-specific data (combos, builds, guides)
and role strategy on demand. They power knowledge mode, where there is no live
game stats so the agent must look up whatever champion the user asks about
instead of relying on data baked into the system prompt.

The wrappers keep the raw data getters in ``app.assistant.data`` untouched and
only add model-friendly behaviour: name slugging, optional role handling, and
clear "not found" messages instead of silent empty strings.
"""

import logging

from langchain.tools import tool

from app.assistant import data

logger = logging.getLogger(__name__)


def _not_found(what: str, champion: str) -> str:
    return f"No {what} data available for champion '{champion}'."


@tool
def get_champion_combos(champion: str) -> str:
    """Look up ability combo sequences and trading patterns for a League of Legends champion.

    Args:
        champion: Champion name (e.g. "Aatrox", "Kai'Sa", "Wukong").
    """
    combo = data.get_champion_combo(champion)
    if not combo:
        return _not_found("combo", champion)
    return combo


@tool
def get_champion_guide(champion: str, role: str = "") -> str:
    """Look up the guide for a champion: strengths, weaknesses, game plan and power spikes.

    Args:
        champion: Champion name (e.g. "Aatrox").
        role: Optional role filter: top, jungle, mid, adc or support. Leave empty to get every role.
    """
    role = (role or "").strip().lower()
    if role:
        guide = data.get_champion_guide(champion, role)
        if not guide:
            return _not_found(f"guide for role '{role}'", champion)
        return guide

    guides = data.get_champion_guides(champion)
    if not guides:
        return _not_found("guide", champion)
    return "\n\n".join(f"### {r}\n{content}" for r, content in guides.items())


@tool
def get_champion_build(champion: str, role: str = "") -> str:
    """Look up the item and rune build for a champion.

    Args:
        champion: Champion name (e.g. "Aatrox").
        role: Optional role filter: top, jungle, mid, adc or support. Leave empty to get every role.
    """
    role = (role or "").strip().lower()
    if role:
        build = data.get_champion_build(champion, role)
        if not build:
            return _not_found(f"build for role '{role}'", champion)
        return build

    builds = data.get_champion_builds(champion)
    if not builds:
        return _not_found("build", champion)
    return "\n\n".join(f"### {r}\n{content}" for r, content in builds.items())


@tool
def get_role_playbook(role: str) -> str:
    """Look up macro strategy (laning phase and early/mid/late game) for a role.

    Args:
        role: Role name: top, jungle, mid, adc or support.
    """
    content = data.get_playbook_content(role)
    if not content:
        return f"No playbook content available for role '{role}'."
    return content


# Shared toolset wired into agents that fetch champion data on demand.
CHAMPION_TOOLS = [
    get_champion_combos,
    get_champion_guide,
    get_champion_build,
    get_role_playbook,
]
