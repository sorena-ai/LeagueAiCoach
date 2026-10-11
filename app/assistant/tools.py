"""
Champion data lookup tools for the coaching agents.

These tools let an agent fetch champion-specific data (combos, builds, guides,
counters) and role strategy on demand. They power knowledge mode and the landing
chat, where there is no live game stats so the agent must look up whatever
champion the user asks about instead of relying on data baked into the system
prompt.

The getters in ``app.assistant.data`` already return XML. These wrappers add
name slugging, optional role handling, and a clear message when nothing matches.

Each tool returns ``(xml, paths)``. The model sees the same text as before.
The paths travel on ``ToolMessage.artifact`` when the tool is called with a
tool-call id, which is how the landing page cites files. A plain ``invoke``
with only the arguments, as the realtime relay does, still returns the text.
"""

import logging

from langchain.tools import tool

from app.assistant import data

logger = logging.getLogger(__name__)


def _not_found(what: str, champion: str) -> str:
    return f"No {what} data available for champion '{champion}'."


@tool(response_format="content_and_artifact")
def get_champion_combos(champion: str) -> tuple[str, list[str]]:
    """Look up ability combo sequences and trading patterns for a League of Legends champion.

    Args:
        champion: Champion name (e.g. "Aatrox", "Kai'Sa", "Wukong").
    """
    combo = data.get_champion_combo(champion)
    if not combo:
        return _not_found("combo", champion), []
    return combo, data.get_combo_sources(champion)


@tool(response_format="content_and_artifact")
def get_champion_guide(champion: str, role: str = "") -> tuple[str, list[str]]:
    """Look up the guide for a champion: strengths, weaknesses, game plan and power spikes.

    Args:
        champion: Champion name (e.g. "Aatrox").
        role: Optional role filter: top, jungle, mid, adc or support. Leave empty to get every role.
    """
    role = (role or "").strip().lower()
    if role:
        guide = data.get_champion_guide(champion, role)
        if not guide:
            return _not_found(f"guide for role '{role}'", champion), []
        return guide, data.get_guide_sources(champion, role)

    guides = data.get_champion_guides(champion)
    if not guides:
        return _not_found("guide", champion), []
    return "\n".join(guides.values()), data.get_guide_sources(champion)


@tool(response_format="content_and_artifact")
def get_champion_build(champion: str, role: str = "") -> tuple[str, list[str]]:
    """Look up the item and rune build for a champion.

    Args:
        champion: Champion name (e.g. "Aatrox").
        role: Optional role filter: top, jungle, mid, adc or support. Leave empty to get every role.
    """
    role = (role or "").strip().lower()
    if role:
        build = data.get_champion_build(champion, role)
        if not build:
            return _not_found(f"build for role '{role}'", champion), []
        return build, data.get_build_sources(champion, role)

    builds = data.get_champion_builds(champion)
    if not builds:
        return _not_found("build", champion), []
    return "\n".join(builds.values()), data.get_build_sources(champion)


@tool(response_format="content_and_artifact")
def get_champion_counters(champion: str, role: str = "") -> tuple[str, list[str]]:
    """Look up the hardest and easiest matchups for a champion.

    Args:
        champion: Champion name (e.g. "Aatrox").
        role: Optional role filter: top, jungle, mid, adc or support. Leave empty to get every role.
    """
    role = (role or "").strip().lower()
    if role:
        counters = data.get_champion_counter(champion, role)
        if not counters:
            return _not_found(f"counters for role '{role}'", champion), []
        return counters, data.get_counter_sources(champion, role)

    counters_by_role = data.get_champion_counters(champion)
    if not counters_by_role:
        return _not_found("counters", champion), []
    return "\n".join(counters_by_role.values()), data.get_counter_sources(champion)


@tool(response_format="content_and_artifact")
def get_role_playbook(role: str) -> tuple[str, list[str]]:
    """Look up macro strategy (laning phase and early/mid/late game) for a role.

    Args:
        role: Role name: top, jungle, mid, adc or support.
    """
    content = data.get_playbook_content(role)
    if not content:
        return f"No playbook content available for role '{role}'.", []
    return content, data.get_playbook_sources(role)


# Shared toolset wired into agents that fetch champion data on demand.
CHAMPION_TOOLS = [
    get_champion_combos,
    get_champion_guide,
    get_champion_build,
    get_champion_counters,
    get_role_playbook,
]
