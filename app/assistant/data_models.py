"""
Data models for champion data management.

Loaders keep the parsed TOML. XML is built later, when a prompt or tool
hands the record to a model.
"""

from typing import Any, Dict

TomlRecord = Dict[str, Any]

# champion slug -> parsed combo file
ChampionCombosData = Dict[str, TomlRecord]

# champion slug -> role -> parsed file
ChampionBuildsData = Dict[str, Dict[str, TomlRecord]]
ChampionGuidesData = Dict[str, Dict[str, TomlRecord]]
ChampionCountersData = Dict[str, Dict[str, TomlRecord]]

# playbook id (filename without extension) -> parsed file
PlaybookData = Dict[str, TomlRecord]
