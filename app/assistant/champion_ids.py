"""Normalize League client champion names onto on-disk data slugs."""

import re

# Display / LCU names that do not compact to the folder slug.
_CHAMPION_SLUG_ALIASES = {
    "wukong": "monkeyking",
    "nunuwillump": "nunu",
    "nunuandwillump": "nunu",
    "renataglasc": "renata",
}


def normalize_champion_slug(champion: str) -> str:
    """Map a live-client or display name onto the data-directory slug.

    Files are keyed as compacted lowercase ids (missfortune, kaisa, jarvaniv).
    The League client sends display names (Miss Fortune, Kai'Sa, Wukong).
    """
    if not champion:
        return ""
    compact = re.sub(r"[^a-z0-9]", "", champion.lower())
    return _CHAMPION_SLUG_ALIASES.get(compact, compact)
