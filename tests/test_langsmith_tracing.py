from langsmith.anonymizer import create_anonymizer

from app.lib.langsmith_tracing import redact_player_ids, trace_config
from app.utils.game_stats.calculator import GameCalculator


def test_redact_player_ids_replaces_riot_ids_only():
    text = (
        "ACTIVE PLAYER STATUS (AliVampire#S2Q)\n"
        "Hide on bush#KR1 killed Lux (ORDER)\n"
        "K'Sante stayed mid."
    )
    redacted = redact_player_ids(text)
    assert "AliVampire#S2Q" not in redacted
    assert "#KR1" not in redacted
    assert redacted.startswith("ACTIVE PLAYER STATUS (<player>)")
    assert "killed Lux (ORDER)" in redacted
    assert "K'Sante" in redacted
    assert redact_player_ids("Coach Player#EUW on Lux") == "Coach <player> on Lux"
    assert redact_player_ids("(Hide on bush#KR1)") == "(<player>)"


def test_anonymizer_redacts_nested_trace_inputs():
    anonymize = create_anonymizer(redact_player_ids)
    payload = {
        "messages": [
            {"role": "user", "content": "Coach Player#EUW on Lux"},
        ]
    }
    result = anonymize(payload)
    assert result["messages"][0]["content"] == "Coach <player> on Lux"


def test_trace_config_names_the_run_and_skips_empty_tags():
    config = trace_config(
        "coach",
        tags=["Lux", ""],
        champion="Lux",
        role="mid",
        match_id=None,
    )
    assert config["run_name"] == "coach"
    assert config["tags"] == ["coach", "Lux"]
    assert config["metadata"] == {"agent": "coach", "champion": "Lux", "role": "mid"}


def test_unresolved_riot_id_is_not_used_as_a_champion_label():
    calc = GameCalculator.__new__(GameCalculator)
    calc.name_to_player = {}
    calc.sum_to_champ = {}
    assert calc._get_champion_with_team("AliVampire#S2Q") == "Unknown"
    assert calc._get_champion_with_team("") == "Minion/Monster"
