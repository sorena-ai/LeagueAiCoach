"""
Game state calculator - Processes events and calculates objectives, structures, and battle log
"""

from typing import Optional, List
from .models import MatchState, Team, GameEventLog


class GameCalculator:
    """Calculates game statistics from events and enriches the MatchState"""

    def __init__(self, state: MatchState, raw_events: list):
        """
        Initialize calculator with game state and event data

        Args:
            state: Parsed MatchState from GameParser
            raw_events: List of game events from the API
        """
        self.state = state
        self.events = raw_events
        self.lane_map = {"L0": "Bottom", "L1": "Middle", "L2": "Top"}

        # Mapping Summoner Name to Champion Name for clean logs
        self.sum_to_champ = {}
        # Mapping for name resolution (handles both full names with tags and game names without tags)
        self.name_to_player = {}
        all_p = self.state.allies.players + self.state.enemies.players
        for p in all_p:
            self.sum_to_champ[p.summoner_name] = p.champion_name
            # Store player by full summoner name
            self.name_to_player[p.summoner_name] = p
            # Also store by game name without tag (if applicable)
            if '#' in p.summoner_name:
                game_name = p.summoner_name.split('#')[0]
                self.name_to_player[game_name] = p
            # Store by champion name as well
            self.name_to_player[p.champion_name] = p

    def process(self):
        """Process all calculations and enrich the state"""
        self._calc_scores()
        self._format_time()
        self._process_structures_and_objectives()
        self._process_event_history()

    def _calc_scores(self):
        """Calculate total team kills"""
        self.state.allies.total_kills = sum(p.scores.k for p in self.state.allies.players)
        self.state.enemies.total_kills = sum(p.scores.k for p in self.state.enemies.players)

    def _format_time(self):
        """Format game time as MM:SS"""
        mins = int(self.state.game_time // 60)
        secs = int(self.state.game_time % 60)
        self.state.formatted_time = f"{mins}:{secs:02d}"

    def _format_timestamp(self, seconds: float) -> str:
        """Format a timestamp as MM:SS"""
        m = int(seconds // 60)
        s = int(seconds % 60)
        return f"{m}:{s:02d}"

    def _get_team_for_entity(self, killer_name: str, raw_team_str: str = "") -> Optional[Team]:
        """
        Determines which Team object a killer belongs to.

        Args:
            killer_name: Name of the entity (can be summoner name, game name, or champion name)
            raw_team_str: Raw team string from event (e.g., "TChaos")

        Returns:
            Team object or None if not found
        """
        if not killer_name:
            return None

        # 1. Try using the name_to_player mapping (handles full names, game names without tags, and champion names)
        if killer_name in self.name_to_player:
            player = self.name_to_player[killer_name]
            if player in self.state.allies.players:
                return self.state.allies
            elif player in self.state.enemies.players:
                return self.state.enemies

        # 2. Try by raw string (e.g., TChaos)
        if "Chaos" in raw_team_str:
            return self.state.allies if self.state.allies.team_id == "CHAOS" else self.state.enemies
        if "Order" in raw_team_str:
            return self.state.allies if self.state.allies.team_id == "ORDER" else self.state.enemies

        return None

    def _process_structures_and_objectives(self):
        """Process structure destruction and objective captures"""
        for e in self.events:
            name = e.get('EventName')
            time = e.get('EventTime', 0.0)
            formatted_time = self._format_timestamp(time)

            # --- STRUCTURES ---
            if name == 'TurretKilled':
                token = e.get('TurretKilled', '')
                parts = token.split('_')
                if len(parts) >= 4:
                    team_raw, lane_code, pos = parts[1], parts[2], parts[3]

                    # Target team is who LOST the turret
                    target_team = None
                    if "Chaos" in team_raw:
                        target_team = self.state.allies if self.state.allies.team_id == "CHAOS" else self.state.enemies
                    else:
                        target_team = self.state.allies if self.state.allies.team_id == "ORDER" else self.state.enemies

                    pos_name = "Tier 1"
                    if "P2" in pos:
                        pos_name = "Tier 2"
                    if "P1" in pos:
                        pos_name = "Inhib Turret"
                    if "P4" in pos or "P5" in pos:
                        pos_name = "Nexus Turret"

                    lane_name = self.lane_map.get(lane_code, "Unknown")
                    if lane_name in target_team.lanes:
                        target_team.lanes[lane_name].turrets_lost.append(pos_name)

            elif name == 'InhibKilled':
                token = e.get('InhibKilled', '')
                parts = token.split('_')
                if len(parts) >= 3:
                    team_raw, lane_code = parts[1], parts[2]

                    target_team = None
                    if "Chaos" in team_raw:
                        target_team = self.state.allies if self.state.allies.team_id == "CHAOS" else self.state.enemies
                    else:
                        target_team = self.state.allies if self.state.allies.team_id == "ORDER" else self.state.enemies

                    lane_name = self.lane_map.get(lane_code, "Unknown")
                    if lane_name in target_team.lanes:
                        target_team.lanes[lane_name].inhib_lost = True

            # --- OBJECTIVES ---
            # For objectives, we check the Killer to see who GAINED it
            killer_name = e.get('KillerName')
            killer_team = self._get_team_for_entity(killer_name)

            if killer_team:
                if name == 'DragonKill':
                    d_type = e.get('DragonType', 'Unknown')
                    killer_team.dragons.count += 1
                    killer_team.dragons.timers.append(f"{formatted_time} ({d_type})")
                elif name == 'BaronKill':
                    killer_team.barons.count += 1
                    killer_team.barons.timers.append(f"{formatted_time}")
                elif name == 'HeraldKill':
                    killer_team.heralds.count += 1
                    killer_team.heralds.timers.append(f"{formatted_time}")
                elif name == 'HordeKill':  # Void Grubs
                    killer_team.grubs.count += 1
                    killer_team.grubs.timers.append(f"{formatted_time}")

    def _get_champion_with_team(self, player_name: str) -> str:
        """
        Get champion name with team tag for display

        Args:
            player_name: Name of the player/entity

        Returns:
            Formatted string like 'Lux (ORDER)' or 'Galio (CHAOS)'
        """
        if not player_name:
            return "Minion/Monster"

        # Try to find the player
        if player_name in self.name_to_player:
            player = self.name_to_player[player_name]
            return f"{player.champion_name} ({player.team_id})"

        # Fallback: check if it's already a champion name
        champion_name = self.sum_to_champ.get(player_name, player_name)
        if champion_name and champion_name != player_name:
            # We found a champion name, now find the team
            if player_name in self.name_to_player:
                player = self.name_to_player[player_name]
                return f"{champion_name} ({player.team_id})"
            return champion_name

        return player_name if player_name else "Minion/Monster"

    def _process_event_history(self):
        """Process event history and build battle log"""
        all_logs = []

        for e in self.events:
            ago = int(self.state.game_time - e['EventTime'])
            ev_name = e.get('EventName')

            # Resolve Killer/Victim to Champion Names with Team
            killer_key = e.get('KillerName')
            victim_key = e.get('VictimName')

            killer = self._get_champion_with_team(killer_key)
            victim = self._get_champion_with_team(victim_key)

            msg = ""
            if ev_name == 'ChampionKill':
                msg = f"{killer} killed {victim}"
            elif ev_name == 'TurretKilled':
                msg = f"{killer} destroyed a Turret"
            elif ev_name == 'InhibKilled':
                msg = f"{killer} destroyed an Inhibitor"
            elif ev_name == 'DragonKill':
                d_type = e.get('DragonType', 'Elemental')
                msg = f"{killer} took {d_type} Dragon"
            elif ev_name == 'BaronKill':
                msg = f"{killer} took Baron Nashor"
            elif ev_name == 'HeraldKill':
                msg = f"{killer} took Rift Herald"
            elif ev_name == 'HordeKill':
                msg = f"{killer} took Void Grubs"

            if msg:
                all_logs.append(GameEventLog(ago, e['EventTime'], msg))

        # Sort by most recent (smallest 'ago' / largest 'raw_time')
        # We use raw_time for accurate sorting, then display ago
        all_logs.sort(key=lambda x: x.raw_time, reverse=True)

        # Logic: Get last 60s. If count < 10, fill up to 10 from history.
        recent_window = [l for l in all_logs if l.time_ago <= 60]

        if len(recent_window) >= 10:
            self.state.event_log = recent_window
        else:
            # Take top 10 regardless of time
            self.state.event_log = all_logs[:10]

