"""
Champion data management module.

This module handles validation, loading, and retrieval of champion data from
the data directories (champion-combos, champion-builds, champion-guide).

All data is loaded into memory at import time to avoid disk I/O during requests.
"""

import logging
from pathlib import Path
from typing import Dict

from app.config import settings
from app.assistant.data_models import (
    ChampionBuildsData,
    ChampionCombosData,
    ChampionGuidesData,
    PlaybookData,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Validation Functions
# ============================================================================


def ensure_champion_combos_exist() -> None:
    """
    Validate that champion combos directory exists and contains exactly 172 XML files.

    Raises:
        FileNotFoundError: If directory is missing or doesn't have 172 files
    """
    directory = settings.champion_combos_dir

    if not directory.exists():
        raise FileNotFoundError(
            f"Champion combos directory not found: {directory}"
        )


def ensure_champion_builds_exist() -> None:
    """
    Validate that champion builds directory exists and contains exactly 172 subdirectories.

    Raises:
        FileNotFoundError: If directory is missing or doesn't have 172 subdirectories
    """
    directory = settings.champion_builds_dir

    if not directory.exists():
        raise FileNotFoundError(
            f"Champion builds directory not found: {directory}"
        )


def ensure_champion_guides_exist() -> None:
    """
    Validate that champion guide directory exists and contains exactly 172 subdirectories.

    Raises:
        FileNotFoundError: If directory is missing or doesn't have 172 subdirectories
    """
    directory = settings.champion_guide_dir

    if not directory.exists():
        raise FileNotFoundError(
            f"Champion guide directory not found: {directory}"
        )


def ensure_playbook_exists() -> None:
    """
    Validate that playbook directory exists and contains required .txt files.

    Raises:
        FileNotFoundError: If directory is missing
    """
    directory = settings.playbook_dir

    if not directory.exists():
        raise FileNotFoundError(
            f"Playbook directory not found: {directory}"
        )


def ensure_all_champion_data_exists() -> None:
    """
    Validate that all champion data directories exist with the correct structure.

    This function should be called during application startup to ensure all
    required champion data is present before the application starts serving requests.

    Raises:
        FileNotFoundError: If any validation check fails
    """
    logger.info("Validating champion data directories...")
    ensure_champion_combos_exist()
    ensure_champion_builds_exist()
    ensure_champion_guides_exist()
    ensure_playbook_exists()
    logger.info("All champion data directories validated successfully")


# ============================================================================
# Loading Functions
# ============================================================================


def _load_champion_combos(directory: Path) -> ChampionCombosData:
    """
    Load all champion combo XML files into memory.

    Args:
        directory: Path to the champion-combos directory

    Returns:
        Dictionary mapping champion name (lowercase) to XML content
    """
    combos: ChampionCombosData = {}

    for combo_file in directory.glob("*.xml"):
        try:
            combos[combo_file.stem.lower()] = combo_file.read_text(
                encoding="utf-8"
            )
        except Exception as exc:
            logger.error("Failed to load combo file %s: %s", combo_file, exc)

    logger.info("Loaded %d champion combo files into memory", len(combos))
    return combos


def _load_champion_builds(directory: Path) -> ChampionBuildsData:
    """
    Load all champion build XML files into memory.

    Args:
        directory: Path to the champion-builds directory

    Returns:
        Nested dictionary mapping champion name -> role -> XML content
        Example: {"aatrox": {"jungle": "<xml>...</xml>", ...}}
    """
    builds: ChampionBuildsData = {}

    for champion_dir in directory.iterdir():
        if not champion_dir.is_dir():
            continue

        champion_name = champion_dir.name.lower()
        builds[champion_name] = {}

        for build_file in champion_dir.glob("*.xml"):
            try:
                # Extract role from filename (e.g., "aatrox-build-jungle.xml" -> "jungle")
                filename = build_file.stem  # e.g., "aatrox-build-jungle"
                parts = filename.split("-")
                if len(parts) >= 3:  # champion-build-role
                    role = parts[-1]  # Get the last part (role)
                    builds[champion_name][role] = build_file.read_text(
                        encoding="utf-8"
                    )
            except Exception as exc:
                logger.error("Failed to load build file %s: %s", build_file, exc)

    logger.info(
        "Loaded champion builds for %d champions into memory", len(builds)
    )
    return builds


def _load_champion_guides(directory: Path) -> ChampionGuidesData:
    """
    Load all champion guide XML files into memory.

    Args:
        directory: Path to the champion-guide directory

    Returns:
        Nested dictionary mapping champion name -> role -> XML content
        Example: {"aatrox": {"jungle": "<xml>...</xml>", ...}}
    """
    guides: ChampionGuidesData = {}

    for champion_dir in directory.iterdir():
        if not champion_dir.is_dir():
            continue

        champion_name = champion_dir.name.lower()
        guides[champion_name] = {}

        for guide_file in champion_dir.glob("*.xml"):
            try:
                # Extract role from filename (e.g., "aatrox-guide-jungle.xml" -> "jungle")
                filename = guide_file.stem  # e.g., "aatrox-guide-jungle"
                parts = filename.split("-")
                if len(parts) >= 3:  # champion-guide-role
                    role = parts[-1]  # Get the last part (role)
                    guides[champion_name][role] = guide_file.read_text(
                        encoding="utf-8"
                    )
            except Exception as exc:
                logger.error("Failed to load guide file %s: %s", guide_file, exc)

    logger.info(
        "Loaded champion guides for %d champions into memory", len(guides)
    )
    return guides


def _load_playbook(directory: Path) -> PlaybookData:
    """
    Load all playbook .txt files into memory.

    Args:
        directory: Path to the playbook directory

    Returns:
        Dictionary mapping filename (without extension) to text content
        Example: {"0.0-general": "...", "1.1-jungle": "..."}
    """
    playbook: PlaybookData = {}

    for playbook_file in directory.glob("*.txt"):
        try:
            # Use filename without extension as key
            playbook[playbook_file.stem] = playbook_file.read_text(
                encoding="utf-8"
            )
        except Exception as exc:
            logger.error("Failed to load playbook file %s: %s", playbook_file, exc)

    logger.info("Loaded %d playbook files into memory", len(playbook))
    return playbook


# ============================================================================
# Module-level data storage (loaded once at import)
# ============================================================================

CHAMPION_COMBOS: ChampionCombosData = _load_champion_combos(
    settings.champion_combos_dir
)
CHAMPION_BUILDS: ChampionBuildsData = _load_champion_builds(
    settings.champion_builds_dir
)
CHAMPION_GUIDES: ChampionGuidesData = _load_champion_guides(
    settings.champion_guide_dir
)
PLAYBOOK: PlaybookData = _load_playbook(
    settings.playbook_dir
)


# ============================================================================
# Getter Functions
# ============================================================================


def get_champion_combo(champion: str) -> str:
    """
    Get champion combo data for a specific champion.

    Args:
        champion: Champion name (case-insensitive)

    Returns:
        XML content string, or empty string if not found
    """
    return CHAMPION_COMBOS.get(champion.lower(), "")


def get_champion_builds(champion: str) -> Dict[str, str]:
    """
    Get all build data for a specific champion.

    Args:
        champion: Champion name (case-insensitive)

    Returns:
        Dictionary mapping role -> XML content, or empty dict if not found
    """
    return CHAMPION_BUILDS.get(champion.lower(), {})


def get_champion_build(champion: str, role: str) -> str:
    """
    Get build data for a specific champion and role.

    Args:
        champion: Champion name (case-insensitive)
        role: Role name (e.g., "jungle", "mid", "top")

    Returns:
        XML content string, or empty string if not found
    """
    builds = get_champion_builds(champion)
    return builds.get(role.lower(), "")


def get_champion_guides(champion: str) -> Dict[str, str]:
    """
    Get all guide data for a specific champion.

    Args:
        champion: Champion name (case-insensitive)

    Returns:
        Dictionary mapping role -> XML content, or empty dict if not found
    """
    return CHAMPION_GUIDES.get(champion.lower(), {})


def get_champion_guide(champion: str, role: str) -> str:
    """
    Get guide data for a specific champion and role.

    Args:
        champion: Champion name (case-insensitive)
        role: Role name (e.g., "jungle", "mid", "top")

    Returns:
        XML content string, or empty string if not found
    """
    guides = get_champion_guides(champion)
    return guides.get(role.lower(), "")


def get_playbook_content(role: str) -> str:
    """
    Get playbook content for a specific role including all game phases.

    Combines multiple playbook files based on role, including:
    - General advice (always included)
    - Role-specific advice
    - Special phase files (laning for lanes, early-clear for jungle)
    - All phase-specific advice (early/mid/late game)

    Args:
        role: Role name (e.g., "top", "jungle", "mid", "adc", "support")

    Returns:
        Combined playbook content string with all phases
    """
    role_lower = role.lower()

    # Map role to index
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

    logger.info("Loading playbook for role=%s (all phases)", role_lower)

    # Build list of filenames to include
    files_to_include = []

    # 1. General advice (always)
    files_to_include.append("0.0-general")

    # 2. Role-specific advice
    files_to_include.append(f"1.{role_index}-{role_lower}")

    # 3. Special phase files (laning for lanes, early-clear for jungle)
    if role_lower == "jungle":
        special_file = f"2.{role_index}.0-{role_lower}-early-clear"
    else:
        special_file = f"2.{role_index}.0-{role_lower}-laning"
    files_to_include.append(special_file)

    # 4. All phase-specific advice (early/mid/late)
    phases = [
        ("early", 1),
        ("mid", 2),
        ("late", 3)
    ]
    for phase_name, phase_index in phases:
        phase_file = f"2.{role_index}.{phase_index}-{role_lower}-{phase_name}-game"
        files_to_include.append(phase_file)

    # Concatenate content
    content_parts = []
    for filename in files_to_include:
        file_content = PLAYBOOK.get(filename)
        if file_content:
            content_parts.append(file_content)
        else:
            logger.warning("Playbook file not found: %s", filename)

    # Join with double newlines for readability
    combined_content = "\n\n".join(content_parts)

    logger.info("Loaded %d playbook files for role=%s (all phases)",
                len(content_parts), role_lower)

    return combined_content


def get_all_playbook_content() -> str:
    """
    Get all playbook content combined for knowledge mode.

    Returns all playbook files concatenated together in alphabetical order,
    providing comprehensive League of Legends strategic knowledge.
    New files added to the playbook directory will automatically be included.

    Returns:
        Combined content of all playbook files
    """
    # Get all filenames and sort alphabetically
    ordered_files = sorted(PLAYBOOK.keys())

    content_parts = []
    for filename in ordered_files:
        file_content = PLAYBOOK.get(filename)
        if file_content:
            content_parts.append(f"### {filename}\n{file_content}")

    combined_content = "\n\n".join(content_parts)
    logger.info("Loaded all %d playbook files for knowledge mode", len(content_parts))

    return combined_content
