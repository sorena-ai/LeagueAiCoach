"""
Champion data management module.

Loads TOML from the data directories into memory at import time.
Getters convert one record to XML at the moment something asks for it.
"""

import logging
import tomllib
from pathlib import Path
from typing import Dict, Optional

from app.assistant.champion_ids import normalize_champion_slug
from app.assistant.data_models import (
    ChampionBuildsData,
    ChampionCombosData,
    ChampionCountersData,
    ChampionGuidesData,
    PlaybookData,
    TomlRecord,
)
from app.assistant.toml_xml import (
    build_to_xml,
    combo_to_xml,
    counters_to_xml,
    guide_to_xml,
    playbook_to_xml,
)
from app.config import settings

logger = logging.getLogger(__name__)


def ensure_champion_combos_exist() -> None:
    """Raise FileNotFoundError if the champion combos directory is missing."""
    directory = settings.champion_combos_dir
    if not directory.exists():
        raise FileNotFoundError(f"Champion combos directory not found: {directory}")


def ensure_champion_builds_exist() -> None:
    """Raise FileNotFoundError if the champion builds directory is missing."""
    directory = settings.champion_builds_dir
    if not directory.exists():
        raise FileNotFoundError(f"Champion builds directory not found: {directory}")


def ensure_champion_guides_exist() -> None:
    """Raise FileNotFoundError if the champion guide directory is missing."""
    directory = settings.champion_guide_dir
    if not directory.exists():
        raise FileNotFoundError(f"Champion guide directory not found: {directory}")


def ensure_champion_counters_exist() -> None:
    """Raise FileNotFoundError if the champion counters directory is missing."""
    directory = settings.champion_counters_dir
    if not directory.exists():
        raise FileNotFoundError(f"Champion counters directory not found: {directory}")


def ensure_playbook_exists() -> None:
    """Raise FileNotFoundError if the playbook directory is missing."""
    directory = settings.playbook_dir
    if not directory.exists():
        raise FileNotFoundError(f"Playbook directory not found: {directory}")


def ensure_all_champion_data_exists() -> None:
    """Validate that every champion data directory exists. Called at startup."""
    logger.info("Validating champion data directories...")
    ensure_champion_combos_exist()
    ensure_champion_builds_exist()
    ensure_champion_guides_exist()
    ensure_champion_counters_exist()
    ensure_playbook_exists()
    logger.info("All champion data directories validated successfully")


def _read_toml(path: Path) -> Optional[TomlRecord]:
    try:
        loaded = tomllib.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to load %s: %s", path, exc)
        return None
    if not isinstance(loaded, dict):
        logger.error("Expected a TOML table in %s", path)
        return None
    return loaded


def _role_from_stem(stem: str) -> Optional[str]:
    """aatrox-build-jungle -> jungle. Needs at least champion-kind-role."""
    parts = stem.split("-")
    if len(parts) < 3:
        return None
    return parts[-1]


def _load_flat(directory: Path) -> Dict[str, TomlRecord]:
    records: Dict[str, TomlRecord] = {}
    for path in directory.glob("*.toml"):
        record = _read_toml(path)
        if record is not None:
            records[path.stem.lower()] = record
    return records


def _load_by_role(directory: Path) -> Dict[str, Dict[str, TomlRecord]]:
    records: Dict[str, Dict[str, TomlRecord]] = {}
    if not directory.exists():
        return records
    for champion_dir in directory.iterdir():
        if not champion_dir.is_dir():
            continue
        roles: Dict[str, TomlRecord] = {}
        for path in champion_dir.glob("*.toml"):
            role = _role_from_stem(path.stem)
            record = _read_toml(path)
            if role and record is not None:
                roles[role] = record
        if roles:
            records[champion_dir.name.lower()] = roles
    return records


def _load_champion_combos(directory: Path) -> ChampionCombosData:
    combos = _load_flat(directory)
    logger.info("Loaded %d champion combo files into memory", len(combos))
    return combos


def _load_champion_builds(directory: Path) -> ChampionBuildsData:
    builds = _load_by_role(directory)
    logger.info("Loaded champion builds for %d champions into memory", len(builds))
    return builds


def _load_champion_guides(directory: Path) -> ChampionGuidesData:
    guides = _load_by_role(directory)
    logger.info("Loaded champion guides for %d champions into memory", len(guides))
    return guides


def _load_champion_counters(directory: Path) -> ChampionCountersData:
    counters = _load_by_role(directory)
    logger.info("Loaded champion counters for %d champions into memory", len(counters))
    return counters


def _load_playbook(directory: Path) -> PlaybookData:
    playbook = _load_flat(directory)
    logger.info("Loaded %d playbook files into memory", len(playbook))
    return playbook


CHAMPION_COMBOS: ChampionCombosData = _load_champion_combos(settings.champion_combos_dir)
CHAMPION_BUILDS: ChampionBuildsData = _load_champion_builds(settings.champion_builds_dir)
CHAMPION_GUIDES: ChampionGuidesData = _load_champion_guides(settings.champion_guide_dir)
CHAMPION_COUNTERS: ChampionCountersData = _load_champion_counters(
    settings.champion_counters_dir
)
PLAYBOOK: PlaybookData = _load_playbook(settings.playbook_dir)

logger.info(
    "Champion data coverage: %d combos, %d build folders, %d guide folders, "
    "%d counter folders, %d playbook files",
    len(CHAMPION_COMBOS),
    len(CHAMPION_BUILDS),
    len(CHAMPION_GUIDES),
    len(CHAMPION_COUNTERS),
    len(PLAYBOOK),
)


def get_champion_combo(champion: str) -> str:
    """XML combos for a champion, or "" if missing."""
    record = CHAMPION_COMBOS.get(normalize_champion_slug(champion))
    return combo_to_xml(record) if record else ""


def get_champion_builds(champion: str) -> Dict[str, str]:
    """role -> build XML. Empty dict if the champion has no builds."""
    records = CHAMPION_BUILDS.get(normalize_champion_slug(champion), {})
    return {role: build_to_xml(record) for role, record in records.items()}


def get_champion_build(champion: str, role: str) -> str:
    """Build XML for one champion and role, or "" if missing."""
    return get_champion_builds(champion).get(role.lower(), "")


def get_champion_guides(champion: str) -> Dict[str, str]:
    """role -> guide XML. Empty dict if the champion has no guides."""
    records = CHAMPION_GUIDES.get(normalize_champion_slug(champion), {})
    return {role: guide_to_xml(record) for role, record in records.items()}


def get_champion_guide(champion: str, role: str) -> str:
    """Guide XML for one champion and role, or "" if missing."""
    return get_champion_guides(champion).get(role.lower(), "")


def get_champion_counters(champion: str) -> Dict[str, str]:
    """role -> counters XML. Empty dict if the champion has no counters."""
    records = CHAMPION_COUNTERS.get(normalize_champion_slug(champion), {})
    return {role: counters_to_xml(record) for role, record in records.items()}


def get_champion_counter(champion: str, role: str) -> str:
    """Counters XML for one champion and role, or "" if missing."""
    return get_champion_counters(champion).get(role.lower(), "")


def _playbook_xml(playbook_id: str) -> str:
    record = PLAYBOOK.get(playbook_id)
    return playbook_to_xml(record) if record else ""


def get_playbook_content(role: str) -> str:
    """
    Playbook XML for one role, all phases.

    Includes general advice, the role overview, the lane or early-clear file,
    and early, mid, and late game.
    """
    role_lower = role.lower()
    role_index_map = {
        "top": 0,
        "jungle": 1,
        "mid": 2,
        "adc": 3,
        "support": 4,
    }
    role_index = role_index_map.get(role_lower)
    if role_index is None:
        logger.warning("Unknown role: %s. Cannot load playbook.", role)
        return ""

    if role_lower == "jungle":
        special_file = f"2.{role_index}.0-{role_lower}-early-clear"
    else:
        special_file = f"2.{role_index}.0-{role_lower}-laning"

    files_to_include = [
        "0.0-general",
        f"1.{role_index}-{role_lower}",
        special_file,
    ]
    for phase_name, phase_index in (("early", 1), ("mid", 2), ("late", 3)):
        files_to_include.append(
            f"2.{role_index}.{phase_index}-{role_lower}-{phase_name}-game"
        )

    content_parts = []
    for filename in files_to_include:
        file_content = _playbook_xml(filename)
        if file_content:
            content_parts.append(file_content)
        else:
            logger.warning("Playbook file not found: %s", filename)

    return "\n".join(content_parts)


def get_all_playbook_content() -> str:
    """Every playbook file as XML, in filename order."""
    parts = []
    for filename in sorted(PLAYBOOK):
        file_content = _playbook_xml(filename)
        if file_content:
            parts.append(file_content)
    return "\n".join(parts)
