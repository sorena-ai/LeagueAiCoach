"""Session and per-turn context for the realtime voice model.

OpenAI uses response.instructions instead of the session prompt when that
field is set. The coach prompt and champion data stay on the session.
The live game report is a conversation item for that turn only, same as the
text coach, which put the report on the user message and left the system
prompt stable.
"""

from app.assistant.coach.prompts import build_coach_prompt, build_gaming_guidance_section

# gpt-realtime-2 follows a labeled verbosity block, and it follows the start
# of the prompt. Later sections (playbooks, "elaborate", 1-3 sentences) lose
# when they disagree with this.
_VERBOSITY = """# Verbosity
These rules outrank every later section, including playbooks and the game report.
- Direct answer: 1-2 short sentences, about 20 words. Then stop.
- Combo or spell order: say the key sequence only.
- They asked why, or they are dead: at most 2 short sentences.
- Do not recap the game report, the playbook, or your instructions.
- No preamble on a direct answer. No "let me check" unless you are calling a tool.
- After a tool result: 1-2 short sentences. Do not explain the lookup.
"""


def session_instructions(*, champion: str | None, role: str | None) -> str:
    """Stable in-game session prompt. Not repeated on response.create."""
    base = build_coach_prompt()
    if champion and role and champion != "unknown" and role != "unknown":
        body = f"{base}\n\n{build_gaming_guidance_section(champion, role)}"
    else:
        body = base
    return f"{_VERBOSITY}\n\n{body}"


def turn_context(*, language: str, game_report: str) -> str:
    """Fresh in-game context for one spoken question. Not a system prompt."""
    language_rule = (
        f"Reply only in {language}. Do not switch language because of accent, "
        "a name, or a single foreign word."
    )
    situation = (
        "Use this game state as the truth for this reply. "
        "Do not recite it back.\n\n"
        f"{game_report}"
    )
    return (
        "Context for this answer only. This is not the player speaking. "
        "Do not read it aloud. Answer only what they just said.\n\n"
        f"{language_rule}\n\n{situation}"
    )
