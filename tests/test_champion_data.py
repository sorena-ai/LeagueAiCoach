from app.assistant.champion_ids import normalize_champion_slug
from app.assistant.data import get_champion_combo, get_champion_guide


def test_normalize_champion_slug_compacts_display_names():
    assert normalize_champion_slug("Miss Fortune") == "missfortune"
    assert normalize_champion_slug("Kai'Sa") == "kaisa"
    assert normalize_champion_slug("Jarvan IV") == "jarvaniv"
    assert normalize_champion_slug("Dr. Mundo") == "drmundo"
    assert normalize_champion_slug("Wukong") == "monkeyking"
    assert normalize_champion_slug("Nunu & Willump") == "nunu"
    assert normalize_champion_slug("Renata Glasc") == "renata"
    assert normalize_champion_slug("aatrox") == "aatrox"


def test_get_champion_combo_accepts_live_client_names():
    assert get_champion_combo("Miss Fortune").startswith("<?xml")
    assert get_champion_combo("Wukong").startswith("<?xml")
    assert get_champion_combo("unknown-champion") == ""


def test_get_champion_guide_accepts_live_client_names():
    assert "<champion>missfortune</champion>" in get_champion_guide(
        "Miss Fortune", "adc"
    )
    assert "<champion>monkeyking</champion>" in get_champion_guide("Wukong", "jungle")
