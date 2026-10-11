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
- Your first spoken word is the answer, or one short question when a fact is missing. Nothing before it.
- Do not say you are thinking, checking, or looking something up. Never say "let me think", "let me check", "one moment", "hold on", or "so I can keep this accurate", including while a tool call is in flight. Say nothing until the tool result is back, then speak only the answer.
- Direct answer: 1-2 short sentences, about 20 words. The action first, then the one reason from their game or the data. Then stop.
- Combo or spell order: say the key sequence only.
- They asked why, or they are dead: at most 2 short sentences.
- Do not recap the game report, the playbook, or your instructions.
- After a tool result: 1-2 short sentences. Do not explain the lookup.
- If the audio is unclear, ask them to repeat it in a few words. Do not guess the question.
"""

# The client often has no lane (position NONE) and sometimes no keystone.
# Asking is allowed only for a fact the turn context marks unknown.
_MISSING_FACTS = """# Missing facts
The turn context lists the player's champion, lane, and keystone. Trust a fact the player already told you over the client.
- Champion unknown: ask which champion they are playing before champion-specific advice.
- Keystone unknown, and this answer depends on their rune: ask which keystone they took.
- Lane unknown, and this answer depends on role (build, matchup, or macro): ask which lane. If it does not, do not ask.
Ask only the one fact that blocks this answer. Do not guess a champion, rune, or lane.
When they tell you, call remember_player with only what they just said, then answer the question they asked. Do not ask for a fact you already have, and do not mention that you stored it.
"""


def session_instructions(*, champion: str | None, role: str | None) -> str:
    """Stable in-game session prompt. Not repeated on response.create."""
    base = build_coach_prompt()
    if champion and role and champion != "unknown" and role != "unknown":
        body = f"{base}\n\n{build_gaming_guidance_section(champion, role)}"
    else:
        body = base
    return f"{_VERBOSITY}\n\n{_MISSING_FACTS}\n\n{body}"


def turn_context(*, language: str, game_report: str, facts: str) -> str:
    """Fresh in-game context for one spoken question. Not a system prompt."""
    language_rule = (
        f"Reply only in {language}. Do not switch language because of accent, "
        "a name, or a single foreign word."
    )
    situation = (
        "Use this game state as the truth for this reply, except where the facts "
        "above say the player told you otherwise. Do not recite it back.\n\n"
        f"{game_report}"
    )
    return (
        "Context for this answer only. This is not the player speaking. "
        "Do not read it aloud. Answer only what they just said.\n\n"
        f"{language_rule}\n\n{facts}\n\n{situation}"
    )
