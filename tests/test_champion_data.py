from pathlib import Path
from xml.etree import ElementTree as ET

from app.assistant.champion_ids import normalize_champion_slug
from app.assistant.coach.prompts import build_coach_prompt, build_gaming_guidance_section
from app.assistant.data import (
    CHAMPION_BUILDS,
    CHAMPION_COMBOS,
    CHAMPION_COUNTERS,
    CHAMPION_GUIDES,
    PLAYBOOK,
    get_build_sources,
    get_champion_build,
    get_champion_combo,
    get_champion_counter,
    get_champion_guide,
    get_playbook_content,
    get_playbook_sources,
)
from app.config import settings
from app.assistant.knowledge.prompts import build_knowledge_prompt
from app.assistant.toml_xml import combo_to_xml


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
    miss_fortune = ET.fromstring(get_champion_combo("Miss Fortune"))
    assert miss_fortune.tag == "champion"
    assert miss_fortune.get("slug") == "missfortune"
    assert miss_fortune.find("combos") is not None

    wukong = ET.fromstring(get_champion_combo("Wukong"))
    assert wukong.get("slug") == "monkeyking"
    assert get_champion_combo("unknown-champion") == ""


def test_get_champion_guide_accepts_live_client_names():
    guide = ET.fromstring(get_champion_guide("Miss Fortune", "adc"))
    assert guide.get("slug") == "missfortune"
    assert guide.get("role") == "adc"
    assert guide.findtext("strengths")

    wukong = ET.fromstring(get_champion_guide("Wukong", "jungle"))
    assert wukong.get("slug") == "monkeyking"


def test_guide_omits_rating_when_the_source_has_none():
    guide = ET.fromstring(get_champion_guide("Nautilus", "top"))
    early = guide.find("gamePlan/earlyGame")
    assert early is not None
    assert "rating" not in early.attrib
    assert early.text.startswith("Nautilus has an incredibly strong level 2")


def test_build_xml_is_the_short_slice():
    build = ET.fromstring(get_champion_build("Aatrox", "top"))
    assert build.get("patch") == "26.20"
    assert build.findtext("winRate")
    assert "Eclipse" in build.findtext("coreItems")
    assert build.find("items") is None
    assert get_champion_build("Kayn", "jungle") == ""


def test_counters_xml_is_five_hardest_and_five_easiest():
    counters = ET.fromstring(get_champion_counter("Aatrox", "top"))
    hardest = counters.findall("hardest/matchup")
    easiest = counters.findall("easiest/matchup")
    assert len(hardest) == 5
    assert len(easiest) == 5
    hard_rates = [float(row.get("winRate")) for row in hardest]
    easy_rates = [float(row.get("winRate")) for row in easiest]
    assert hard_rates == sorted(hard_rates)
    assert easy_rates == sorted(easy_rates, reverse=True)
    assert hard_rates[-1] < easy_rates[-1]
    assert get_champion_counter("unknown-champion", "top") == ""


def test_playbook_xml_keeps_role_file_ids():
    content = get_playbook_content("top")
    assert '<playbook id="0.0-general"' in content
    assert '<playbook id="2.0.0-top-laning"' in content
    assert '<playbook id="2.0.1-top-early-game"' in content
    assert "Top Laner" in content
    assert get_playbook_content("aram") == ""


def test_combo_xml_escapes_text():
    xml = combo_to_xml(
        {
            "meta": {"champion": "Aatrox", "slug": "aatrox"},
            "combos": [{"difficulty": "Easy", "description": "Q & W <flash>"}],
        }
    )
    parsed = ET.fromstring(xml)
    assert parsed.findtext("combos/combo/description") == "Q & W <flash>"


def test_every_stored_data_file_exists():
    entries = [*CHAMPION_COMBOS.values(), *PLAYBOOK.values()]
    for by_role in (CHAMPION_BUILDS, CHAMPION_GUIDES, CHAMPION_COUNTERS):
        for roles in by_role.values():
            entries.extend(roles.values())

    assert entries
    for entry in entries:
        assert "\\" not in entry.path
        assert (settings.data_dir / entry.path).is_file()


def test_build_sources_for_aatrox_top():
    assert get_build_sources("Aatrox", "top") == [
        "champion-builds/aatrox/aatrox-build-top.toml"
    ]


def test_playbook_sources_match_content_ids():
    content = get_playbook_content("top")
    ids = [
        node.get("id")
        for node in ET.fromstring(f"<root>{content}</root>").findall("playbook")
    ]
    sources = get_playbook_sources("top")
    assert [Path(path).stem for path in sources] == ids
    assert "0.0-general" in ids


def test_xml_is_the_last_block_of_both_prompts():
    coach = build_coach_prompt() + build_gaming_guidance_section("Aatrox", "top")
    assert coach.rfind("<build ") > coach.rfind("## Tools")
    assert coach.rfind("<build ") > coach.rfind("<combos")

    knowledge = build_knowledge_prompt()
    assert knowledge.rfind("<playbook ") > knowledge.rfind("Remember:")
    assert knowledge.rfind("Remember:") > knowledge.rfind("## Tools")
