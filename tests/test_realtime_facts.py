"""Live coach: no spoken filler, and facts the player supplies when the client cannot."""

from app.assistant.realtime.instructions import session_instructions, turn_context
from app.assistant.realtime.player_facts import PlayerFacts, apply_player_facts, fact_sheet
from app.assistant.realtime.tools import REMEMBER_PLAYER, realtime_tool_definitions
from app.config import Settings


def test_fact_sheet_marks_only_what_the_client_does_not_know():
    sheet = fact_sheet(
        champion="Ziggs",
        lane="",
        keystone="Unknown Rune",
        said=PlayerFacts(),
    )
    assert "Champion: Ziggs. From the client. Do not ask." in sheet
    assert "Lane: unknown." in sheet
    assert "Keystone: unknown." in sheet


def test_what_the_player_says_is_kept_and_overrides_the_client():
    said, message = apply_player_facts(PlayerFacts(), {"lane": "middle", "keystone": "electrocute"})
    assert said.lane == "mid"
    assert said.keystone == "Electrocute"
    assert message.startswith("Saved lane mid, keystone Electrocute")

    again, _ = apply_player_facts(said, {"champion": "ziggs"})
    assert again.lane == "mid"
    assert again.champion == "Ziggs"

    sheet = fact_sheet(champion="", lane="NONE", keystone="", said=again)
    assert "Champion: Ziggs. The player told you this." in sheet
    assert "Lane: mid. The player told you this." in sheet
    assert "do not ask again." in sheet


def test_a_lane_phrase_keeps_the_role_word():
    said, _ = apply_player_facts(PlayerFacts(), {"lane": "mid lane"})
    assert said.lane == "mid"


def test_an_unrecognized_lane_is_not_stored():
    said, message = apply_player_facts(PlayerFacts(lane="mid"), {"lane": "river"})
    assert said.lane == "mid"
    assert message.startswith("Nothing saved.")
    assert "top, jungle, mid, adc, or support" in message


def test_prompt_bans_filler_and_exposes_remember_player():
    text = session_instructions(champion="", role="")
    assert 'Never say "let me think"' in text
    assert "remember_player" in text
    names = [item["name"] for item in realtime_tool_definitions()]
    assert REMEMBER_PLAYER in names


def test_turn_context_carries_the_fact_sheet_ahead_of_the_report():
    text = turn_context(language="english", game_report="=== GAME STATE REPORT ===", facts="Lane: unknown.")
    assert text.index("Lane: unknown.") < text.index("=== GAME STATE REPORT ===")
    assert "player told you otherwise" in text


def test_live_reasoning_defaults_to_minimal():
    assert Settings.model_fields["realtime_reasoning_effort"].default == "minimal"
