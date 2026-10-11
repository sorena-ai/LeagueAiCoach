"""Turn parsed champion TOML into the XML the models read.

Files stay TOML. This module runs at the handoff, so prompts and tools
never see the raw tables.
"""

from typing import Any, Mapping, Optional
from xml.etree import ElementTree as ET

_MATCHUP_LIMIT = 5


def _dump(element: ET.Element) -> str:
    return ET.tostring(element, encoding="unicode")


def _sub(
    parent: ET.Element,
    tag: str,
    text: Optional[object] = None,
    **attrs: object,
) -> ET.Element:
    clean = {
        key: _num(value) for key, value in attrs.items() if value is not None and value != ""
    }
    element = ET.SubElement(parent, tag, clean)
    if text is not None:
        element.text = str(text)
    return element


def _num(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.2f}".rstrip("0").rstrip(".")
    return str(value)


def _names(items: object) -> str:
    if not isinstance(items, list):
        return ""
    names = []
    for item in items:
        if isinstance(item, Mapping):
            name = item.get("name")
            if name:
                names.append(str(name))
        elif item:
            names.append(str(item))
    return ", ".join(names)


def _meta(record: Mapping[str, Any]) -> Mapping[str, Any]:
    meta = record.get("meta")
    return meta if isinstance(meta, Mapping) else {}


def combo_to_xml(record: Mapping[str, Any]) -> str:
    """Ability combos for one champion."""
    meta = _meta(record)
    root = ET.Element(
        "champion",
        {
            "name": str(meta.get("champion") or ""),
            "slug": str(meta.get("slug") or ""),
        },
    )
    combos = record.get("combos") if isinstance(record.get("combos"), list) else []
    block = _sub(root, "combos", count=len(combos))
    for combo in combos:
        if not isinstance(combo, Mapping):
            continue
        node = _sub(block, "combo")
        if combo.get("difficulty"):
            _sub(node, "difficulty", combo["difficulty"])
        if combo.get("description"):
            _sub(node, "description", combo["description"])
    return _dump(root)


def guide_to_xml(record: Mapping[str, Any]) -> str:
    """Strengths, game plan, and power spikes for one champion and role."""
    meta = _meta(record)
    root = ET.Element(
        "guide",
        {
            "champion": str(meta.get("champion") or ""),
            "slug": str(meta.get("slug") or ""),
            "role": str(meta.get("role") or ""),
        },
    )
    overview = record.get("overview") if isinstance(record.get("overview"), Mapping) else {}
    if overview.get("strengths"):
        _sub(root, "strengths", overview["strengths"])
    if overview.get("weaknesses"):
        _sub(root, "weaknesses", overview["weaknesses"])

    game_plan = record.get("game_plan") if isinstance(record.get("game_plan"), Mapping) else {}
    plan = _sub(root, "gamePlan")
    for phase, tag in (("early", "earlyGame"), ("mid", "midGame"), ("late", "lateGame")):
        section = game_plan.get(phase) if isinstance(game_plan.get(phase), Mapping) else {}
        if not section.get("text"):
            continue
        _sub(plan, tag, section["text"], rating=section.get("rating") or None)

    spikes = record.get("power_spikes") if isinstance(record.get("power_spikes"), Mapping) else {}
    if any(spikes.get(phase) for phase in ("early", "mid", "late")):
        block = _sub(root, "powerSpikes")
        for phase in ("early", "mid", "late"):
            if spikes.get(phase):
                _sub(block, phase, spikes[phase])
    return _dump(root)


def playbook_to_xml(record: Mapping[str, Any]) -> str:
    """One playbook file."""
    meta = _meta(record)
    content = record.get("content") if isinstance(record.get("content"), Mapping) else {}
    root = ET.Element(
        "playbook",
        {
            "id": str(meta.get("id") or ""),
            "role": str(meta.get("role") or ""),
            "phase": str(meta.get("phase") or ""),
        },
    )
    root.text = str(content.get("text") or "")
    return _dump(root)


def build_to_xml(record: Mapping[str, Any]) -> str:
    """Coaching slice of a build: runes, spells, skills, core items.

    The long item-option tables stay out. They are too big for a voice prompt.
    """
    meta = _meta(record)
    summary = record.get("summary") if isinstance(record.get("summary"), Mapping) else {}
    root = ET.Element(
        "build",
        {
            "champion": str(meta.get("champion") or ""),
            "slug": str(meta.get("slug") or ""),
            "role": str(meta.get("role") or ""),
            "patch": str(meta.get("patch") or ""),
        },
    )
    if summary.get("win_rate") is not None:
        _sub(root, "winRate", _num(summary["win_rate"]))
    if summary.get("matches") is not None:
        _sub(root, "matches", summary["matches"])
    if summary.get("pick_rate") is not None:
        _sub(root, "pickRate", _num(summary["pick_rate"]))
    if summary.get("ban_rate") is not None:
        _sub(root, "banRate", _num(summary["ban_rate"]))

    runes = record.get("runes") if isinstance(record.get("runes"), Mapping) else {}
    keystone = runes.get("keystone") if isinstance(runes.get("keystone"), Mapping) else {}
    primary_tree = (
        runes.get("primary_tree") if isinstance(runes.get("primary_tree"), Mapping) else {}
    )
    secondary_tree = (
        runes.get("secondary_tree") if isinstance(runes.get("secondary_tree"), Mapping) else {}
    )
    if keystone.get("name") or runes.get("primary"):
        block = _sub(
            root,
            "runes",
            keystone=keystone.get("name"),
            primary=primary_tree.get("name"),
            secondary=secondary_tree.get("name"),
        )
        for item in runes.get("primary") or []:
            if isinstance(item, Mapping) and item.get("name"):
                _sub(block, "primary", item["name"])
        for item in runes.get("secondary") or []:
            if isinstance(item, Mapping) and item.get("name"):
                _sub(block, "secondary", item["name"])
        shards = runes.get("shards") if isinstance(runes.get("shards"), Mapping) else {}
        shard_names = _names(shards.get("names"))
        if shard_names:
            _sub(block, "shards", shard_names)

    spells = record.get("summoner_spells")
    spells = spells if isinstance(spells, Mapping) else {}
    spell_names = _names(spells.get("spells"))
    if spell_names:
        _sub(root, "summonerSpells", spell_names)

    skills = record.get("skills") if isinstance(record.get("skills"), Mapping) else {}
    priority = skills.get("priority")
    if isinstance(priority, list) and priority:
        _sub(root, "skillOrder", ", ".join(str(skill) for skill in priority))

    items = record.get("items") if isinstance(record.get("items"), Mapping) else {}
    starting = items.get("starting") if isinstance(items.get("starting"), Mapping) else {}
    core = items.get("core") if isinstance(items.get("core"), Mapping) else {}
    starting_names = _names(starting.get("items"))
    core_names = _names(core.get("items"))
    if starting_names:
        _sub(root, "startingItems", starting_names)
    if core_names:
        _sub(root, "coreItems", core_names)
    return _dump(root)


def counters_to_xml(record: Mapping[str, Any], limit: int = _MATCHUP_LIMIT) -> str:
    """Hardest and easiest matchups. Not the full counter table."""
    meta = _meta(record)
    root = ET.Element(
        "counters",
        {
            "champion": str(meta.get("champion") or ""),
            "slug": str(meta.get("slug") or ""),
            "role": str(meta.get("role") or ""),
            "patch": str(meta.get("patch") or ""),
        },
    )
    matchups = record.get("matchups") if isinstance(record.get("matchups"), list) else []
    ranked = [
        row
        for row in matchups
        if isinstance(row, Mapping) and row.get("win_rate") is not None and row.get("opponent")
    ]
    ranked.sort(key=lambda row: float(row["win_rate"]))
    hardest = ranked[:limit]
    seen = {row["opponent"] for row in hardest}
    easiest = [row for row in reversed(ranked) if row["opponent"] not in seen][:limit]

    hard_block = _sub(root, "hardest")
    for row in hardest:
        _sub(
            hard_block,
            "matchup",
            opponent=row["opponent"],
            winRate=row["win_rate"],
            matches=row.get("matches"),
        )
    easy_block = _sub(root, "easiest")
    for row in easiest:
        _sub(
            easy_block,
            "matchup",
            opponent=row["opponent"],
            winRate=row["win_rate"],
            matches=row.get("matches"),
        )
    return _dump(root)
