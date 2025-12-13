"""
Data models for champion data management.

This module defines constants and type aliases for champion data structures.
"""

from typing import Dict

# Type aliases for champion data structures

# Champion combos: flat dictionary mapping champion name to XML content
ChampionCombosData = Dict[str, str]

# Champion builds: nested dictionary mapping champion name -> role -> XML content
# Example: {"aatrox": {"jungle": "<xml>...</xml>", "mid": "<xml>...</xml>", ...}}
ChampionBuildsData = Dict[str, Dict[str, str]]

# Champion guides: nested dictionary mapping champion name -> role -> XML content
# Example: {"aatrox": {"jungle": "<xml>...</xml>", "mid": "<xml>...</xml>", ...}}
ChampionGuidesData = Dict[str, Dict[str, str]]

# Playbook: flat dictionary mapping filename (without extension) to text content
# Example: {"0.0-general": "...", "1.1-jungle": "...", "2.1.1-jungle-early-game": "..."}
PlaybookData = Dict[str, str]
