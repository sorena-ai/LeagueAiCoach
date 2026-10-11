"""
Data models for champion data management.

Loaders keep the parsed TOML. XML is built later, when a prompt or tool
hands the record to a model.
"""

from dataclasses import dataclass
from typing import Any, Dict

TomlRecord = Dict[str, Any]


@dataclass(frozen=True)
class DataFile:
    """One loaded TOML file.

    ``path`` is relative to the data directory and uses POSIX separators,
    for example ``champion-builds/aatrox/aatrox-build-top.toml``.
    """

    path: str
    record: TomlRecord


# champion slug -> combo file
ChampionCombosData = Dict[str, DataFile]

# champion slug -> role -> file
ChampionBuildsData = Dict[str, Dict[str, DataFile]]
ChampionGuidesData = Dict[str, Dict[str, DataFile]]
ChampionCountersData = Dict[str, Dict[str, DataFile]]

# playbook id (filename without extension) -> file
PlaybookData = Dict[str, DataFile]
