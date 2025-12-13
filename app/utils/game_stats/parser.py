"""
Game data parser - Converts raw League Client API JSON to structured MatchState
"""

from .models import (
    MatchState, Player, PlayerScore, Team, LaneState,
    CombatStats, Ability
)


class GameParser:
    """Parses raw JSON data from League Client API into structured MatchState"""

    def __init__(self, json_data: dict):
        self.raw = json_data

    def parse(self) -> MatchState:
        """
        Parse JSON data into a MatchState object

        Returns:
            MatchState: Structured game state with players, teams, and basic info
        """
        game_data = self.raw.get('gameData', {})
        g_time = game_data.get('gameTime', 0.0)
        
        # Format game time as MM:SS
        total_seconds = int(g_time)
        minutes = total_seconds // 60
        seconds = total_seconds % 60
        formatted_time = f"{minutes:02d}:{seconds:02d}"
        
        state = MatchState(game_time=g_time, formatted_time=formatted_time)

        ap_data = self.raw.get('activePlayer', {})
        ap_name = ap_data.get('summonerName', 'Unknown')

        players_map = {}
        active_team_id = "ORDER"

        all_players_list = self.raw.get('allPlayers', [])

        for p_raw in all_players_list:
            # Name Resolution
            s_name = p_raw.get('summonerName')
            if not s_name:
                riot_name = p_raw.get('riotIdGameName')
                if riot_name:
                    tag = p_raw.get('riotIdTagLine', '')
                    s_name = f"{riot_name}#{tag}" if tag else riot_name
                else:
                    s_name = p_raw.get('championName', 'Unknown Champion')

            # Items
            raw_items = p_raw.get('items', [])
            items = [i.get('displayName', 'Unknown Item') for i in raw_items if i.get('displayName')]
            if not items:
                items = ["Empty Inventory"]

            # Spells
            spells_raw = p_raw.get('summonerSpells', {})
            spell_one = spells_raw.get('summonerSpellOne', {}).get('displayName', 'Unknown')
            spell_two = spells_raw.get('summonerSpellTwo', {}).get('displayName', 'Unknown')
            spells = [spell_one, spell_two]

            # Runes
            runes_raw = p_raw.get('runes', {})
            keystone = runes_raw.get('keystone', {}).get('displayName', 'Unknown Rune')

            scores_raw = p_raw.get('scores', {})

            player = Player(
                summoner_name=s_name,
                champion_name=p_raw.get('championName', 'Unknown'),
                team_id=p_raw.get('team', 'ORDER'),
                role=p_raw.get('position', 'NONE'),
                level=p_raw.get('level', 1),
                is_dead=p_raw.get('isDead', False),
                respawn_timer=p_raw.get('respawnTimer', 0.0),
                items=items,
                spells=spells,
                keystone=keystone,
                scores=PlayerScore(
                    k=scores_raw.get('kills', 0),
                    d=scores_raw.get('deaths', 0),
                    a=scores_raw.get('assists', 0),
                    cs=scores_raw.get('creepScore', 0),
                    vis=scores_raw.get('wardScore', 0.0)
                )
            )

            players_map[s_name] = player

            if s_name == ap_name or p_raw.get('summonerName') == ap_name:
                active_team_id = p_raw.get('team', 'ORDER')
                state.active_player = player

        # Enrich active player with detailed stats
        if state.active_player:
            state.active_player.current_gold = ap_data.get('currentGold', 0.0)
            c_stats = ap_data.get('championStats', {})
            state.active_player.combat_stats = CombatStats(
                hp_current=int(c_stats.get('currentHealth', 0)),
                hp_max=int(c_stats.get('maxHealth', 1)),
                resource_current=int(c_stats.get('resourceValue', 0)),
                resource_max=int(c_stats.get('resourceMax', 1)),
                resource_type=c_stats.get('resourceType', 'MANA'),
                ad=int(c_stats.get('attackDamage', 0)),
                ap=int(c_stats.get('abilityPower', 0)),
                armor=int(c_stats.get('armor', 0)),
                mr=int(c_stats.get('magicResist', 0))
            )
            ab_raw = ap_data.get('abilities', {})
            ab_list = []
            for key in ['Q', 'W', 'E', 'R']:
                if key in ab_raw:
                    lvl = ab_raw[key].get('abilityLevel', 0)
                    ab_list.append(Ability(key, lvl))
            state.active_player.abilities = ab_list

        # Set up teams
        enemy_id = "CHAOS" if active_team_id == "ORDER" else "ORDER"
        state.allies = Team(team_id=active_team_id)
        state.enemies = Team(team_id=enemy_id)

        # Distribute players to teams
        for p in players_map.values():
            if p.team_id == active_team_id:
                state.allies.players.append(p)
            else:
                state.enemies.players.append(p)

        # Initialize lane states
        for lane_name in ["Top", "Middle", "Bottom"]:
            state.allies.lanes[lane_name] = LaneState(lane_name)
            state.enemies.lanes[lane_name] = LaneState(lane_name)

        return state

