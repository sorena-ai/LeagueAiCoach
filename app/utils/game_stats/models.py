"""
Data models for League of Legends game state representation
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class Ability:
    """Represents a champion ability with key and level"""
    key: str
    level: int


@dataclass
class CombatStats:
    """Combat statistics for a player"""
    hp_current: int
    hp_max: int
    resource_current: int
    resource_max: int
    resource_type: str
    ad: int
    ap: int
    armor: int
    mr: int


@dataclass
class PlayerScore:
    """Player's KDA and CS statistics"""
    k: int  # Kills
    d: int  # Deaths
    a: int  # Assists
    cs: int  # Creep Score
    vis: float  # Vision Score


@dataclass
class Player:
    """Represents a player in the game"""
    summoner_name: str
    champion_name: str
    team_id: str
    role: str
    level: int
    is_dead: bool
    respawn_timer: float
    items: List[str]
    spells: List[str]
    keystone: str
    scores: PlayerScore
    combat_stats: Optional[CombatStats] = None
    abilities: List[Ability] = field(default_factory=list)
    current_gold: float = 0.0


@dataclass
class LaneState:
    """Represents the state of a lane (structures)"""
    name: str
    turrets_lost: List[str] = field(default_factory=list)
    inhib_lost: bool = False


@dataclass
class ObjectiveStat:
    """Statistics for objectives (dragons, barons, etc.)"""
    count: int = 0
    timers: List[str] = field(default_factory=list)  # e.g. ["15:30 (Chemtech)", "22:10 (Baron)"]


@dataclass
class Team:
    """Represents a team with players and objectives"""
    team_id: str
    players: List[Player] = field(default_factory=list)
    lanes: Dict[str, LaneState] = field(default_factory=dict)
    total_kills: int = 0
    # Objectives
    dragons: ObjectiveStat = field(default_factory=ObjectiveStat)
    barons: ObjectiveStat = field(default_factory=ObjectiveStat)
    heralds: ObjectiveStat = field(default_factory=ObjectiveStat)
    grubs: ObjectiveStat = field(default_factory=ObjectiveStat)


@dataclass
class GameEventLog:
    """Represents a game event for the battle log"""
    time_ago: int
    raw_time: float
    message: str


@dataclass
class MatchState:
    """Complete game state representation"""
    game_time: float
    formatted_time: str = ""
    active_player: Optional[Player] = None
    allies: Optional[Team] = None
    enemies: Optional[Team] = None
    event_log: List[GameEventLog] = field(default_factory=list)

