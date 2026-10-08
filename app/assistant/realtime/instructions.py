"""Session and per-turn instructions for the realtime voice model."""

from app.assistant.knowledge_prompts import build_knowledge_prompt
from app.assistant.prompts import build_coach_prompt, build_gaming_guidance_section

_VOICE_RULES = """
## Voice
This is a live voice conversation. Speak the answer. No markdown, no lists.
Skip filler such as "let me check" unless you are about to call a tool.
"""

# response.create replaces the session prompt, so this has to be repeated
# at the end of every reply, after the game report.
_STOP = """
Speak the answer, then stop talking.
In a match: about 20 words, under 40 unless they asked why or they are dead. Never lecture.
Out of a match: one to three sentences, then stop.
"""


def session_instructions(*, in_game: bool, champion: str | None, role: str | None) -> str:
    """Stable prompt for the OpenAI session. Game state is added per turn."""
    if in_game and champion and role and champion != "unknown":
        base = build_coach_prompt()
        guidance = build_gaming_guidance_section(champion, role)
        return f"{base}\n\n{guidance}\n{_VOICE_RULES}"
    return f"{build_knowledge_prompt()}\n{_VOICE_RULES}"


def turn_instructions(
    *,
    language: str,
    game_report: str | None,
    in_game: bool,
    champion: str | None,
    role: str | None,
) -> str:
    """Full prompt for one reply.

    OpenAI uses response.instructions instead of the session prompt, so the
    coach or knowledge prompt has to be included here or the model never sees it.
    """
    base = session_instructions(in_game=in_game, champion=champion, role=role)
    language_rule = (
        f"Reply only in {language}. Do not switch language because of accent, "
        "a name, or a single foreign word."
    )
    if game_report:
        situation = (
            f"{language_rule}\n\n"
            "Use this game state as the truth for this reply. "
            "Do not recite it back unless the player asked.\n\n"
            f"{game_report}"
        )
    else:
        situation = (
            f"{language_rule}\n\n"
            "The player is not in a match. Answer the League of Legends question."
        )
    return f"{base}\n\n{situation}\n{_STOP}"
