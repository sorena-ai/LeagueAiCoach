import logging

from app.assistant.data import (
    get_champion_guide,
    get_champion_combo,
    get_champion_build,
    get_playbook_content,
)
from app.utils.game_stats.models import MatchState
from app.utils.game_stats.report import ReportGenerator

logger = logging.getLogger(__name__)


# ============================================================================
# GAME STATE REPORT GENERATION
# ============================================================================


def build_game_state_report(state: MatchState) -> str:
    """
    Build a formatted game state report from a parsed MatchState.
    """
    return ReportGenerator.generate(state)


# ============================================================================
# PROMPT SECTION BUILDERS
# ============================================================================


def _build_identity_section() -> str:
    """Build the identity and role definition section."""
    return """You are Sensii, a League of Legends voice coach. You deliver game knowledge fast and clear during live matches.

Your job: Answer questions about the game. Be quick, be accurate, get to the point."""


def _build_personality_section() -> str:
    """Build the personality and tone guidelines section."""
    return """## Personality

You're a knowledgeable teammate on comms. Casual, direct, confident.

- Use gaming slang naturally (tilted, gapped, inting, fed, diff, etc.)
- No filler words, no hedging

If user's latest message is aggressive or toxic toward you:
- Match their energy with a short roast (still under 20 words)
- Example: "You're 0/7 and asking ME what's wrong? Skill issue."
- Then answer their question in the same breath"""


def _build_knowledge_hierarchy() -> str:
    """
    Build the source of truth hierarchy.
    Crucial for preventing hallucinations in 'Flash Lite' models.
    """
    return """## Knowledge Hierarchy

1. **Game State Report:** This is the absolute truth of the current moment.
2. **Champion XML:** This is the absolute truth for abilities and combos. NEVER deviate from the combos listed in the XML.
3. **Strategic Playbook:** High-level strategic advice for your role and game phase. Use this for macro decisions and general strategy.
4. **Internal Knowledge:** Use this ONLY for slang and tone. Do not use it for specific ability mechanics."""


def _build_scope_section() -> str:
    """Build the scope and boundaries section."""
    return """## Scope

You only answer League of Legends questions. Off-topic? Just say "I only do League." """


def _build_safety_section() -> str:
    """Build the safety guardrails section."""
    return """## Hard Limits

1. Never encourage cheating, exploits, or actual harassment of real people.
2. **Data Integrity:** Verify ability keys (Q/W/E/R) against the provided XML context. Never assign the wrong effect to a key (e.g., do not claim 'E' is a shield if the XML says 'W')."""


def _build_response_rules_section() -> str:
    """Build the consolidated response rules section."""
    return """## Response Rules

BE EXTREMELY SHORT. Player is mid-game. Extra words get them killed.

Length guide:
- Ideal: ~20 words if that's enough
- Typical: under 40 words when a reason helps
- Max: 80 words only if truly needed

**Combo Override:**
- If the user asks for a combo or spell order ("what do I do?", "how to trade?"), DO NOT explain the theory. 
- IMMEDIATELY output the relevant sequence found in the <combos> XML block.
- Example: "R -> W -> Q. Land with the fear."

Only add a reason if it changes the answer's usefulness:
- "What item?" → "Serylda's." (no reason needed)
- "Should I fight?" → "No, no ult." (reason matters)

Exceptions (you can elaborate):
- User explicitly asks "why?" or "explain"
- Game state shows player is dead (grey screen = time to listen)

**Uncertainty:**
- If specific champion data is missing from the XML context, do NOT guess.
- Rely on general high-elo principles, but do not invent specific ability effects.

This is voice output:
- No bullet points, no markdown, no lists
- Speak naturally, one flowing sentence"""


# ============================================================================
# CONTENT BUILDERS
# ============================================================================


def build_playbook_prompt(role: str) -> str:
    """
    Build the strategic playbook section for the system prompt.

    Includes all game phases (early, mid, late) to provide comprehensive
    strategic guidance throughout the entire game.

    Args:
        role: Player's role (e.g., "top", "jungle", "mid", "adc", "support")

    Returns:
        Formatted playbook section string
    """
    logger.info("Building playbook prompt for role=%s (all phases)", role)
    playbook_content = get_playbook_content(role)

    if not playbook_content:
        logger.error("No playbook content found for role=%s", role)
        return ""

    return f"\n\n## Strategic Playbook\n{playbook_content}"


def build_champion_guide_prompt(champion: str, role: str) -> str:
    """Build the champion guide section."""
    logger.info("Building champion guide prompt for champion=%s, role=%s", champion, role)
    guide_xml = get_champion_guide(champion, role)

    if not guide_xml:
        logger.error("No guide found for champion=%s, role=%s", champion, role)
        return ""

    return f"\n\n## Champion Guide\n{guide_xml}"


def build_champion_combos_prompt(champion: str) -> str:
    """
    Build the champion combos section.
    INCLUDES SANITIZATION to fix XML entities for the LLM.
    """
    logger.info("Building champion combos prompt for champion=%s", champion)
    combo_xml = get_champion_combo(champion)

    if not combo_xml:
        logger.warning("No combo data found for champion=%s", champion)
        return ""

    return f"\n\n## Champion Combos\n{combo_xml}"


def build_champion_builds_prompt(champion: str, role: str) -> str:
    """Build the champion build section."""
    logger.info("Building champion build prompt for champion=%s, role=%s", champion, role)
    build_xml = get_champion_build(champion, role)

    if not build_xml:
        logger.warning("No build data found for champion=%s, role=%s", champion, role)
        return ""

    return f"\n\n## Champion Build\n{build_xml}"


def build_gaming_guidance_section(champion: str, role: str) -> str:
    """
    Build the Gaming Guidance section with all champion-specific data.

    This section contains all the game data needed for the agent to function:
    - Player's champion and role information
    - Strategic playbook (role-specific with all game phases)
    - Champion guide (champion-specific tips for role)
    - Champion combos (ability rotations and sequences)
    - Champion builds (items, runes, skill order)

    Args:
        champion: Champion name (e.g., "aatrox", "ahri")
        role: Player's role (e.g., "top", "jungle", "mid", "adc", "support")

    Returns:
        Complete gaming guidance section string
    """
    logger.info("Building gaming guidance section for champion=%s, role=%s (all phases)",
                champion, role)

    # Champion context
    champion_context = f"""# GAMING GUIDANCE

## Player Context
- Champion: {champion.capitalize()}
- Role: {role.upper()}
- Position: {role.capitalize()}"""

    # Get all game data sections
    playbook = build_playbook_prompt(role)
    champion_guide = build_champion_guide_prompt(champion, role)
    champion_combos = build_champion_combos_prompt(champion)
    champion_builds = build_champion_builds_prompt(champion, role)

    # Combine all sections
    return f"""{champion_context}{playbook}{champion_guide}{champion_combos}{champion_builds}"""


def build_coach_prompt() -> str:
    """
    Build the BASE PROMPT for Sensii voice assistant.
    """
    # Build all base prompt sections
    identity = _build_identity_section()
    personality = _build_personality_section()
    hierarchy = _build_knowledge_hierarchy()  # Added Hierarchy
    scope = _build_scope_section()
    safety = _build_safety_section()
    response_rules = _build_response_rules_section()

    # Assemble base prompt
    return f"""{identity}

{personality}

{hierarchy}

{scope}

{safety}

{response_rules}"""