"""
Report generator - Formats MatchState into human-readable text report
"""

from .models import MatchState, Team, Player


class ReportGenerator:
    """Generates formatted text reports from MatchState"""

    @staticmethod
    def generate(s: MatchState) -> str:
        """
        Generate a complete game state report

        Args:
            s: MatchState object with all game information

        Returns:
            Formatted multi-line string report
        """

        def render_lanes(t: Team) -> str:
            """Render lane structure status for a team"""
            lines = []
            for name in ["Top", "Middle", "Bottom"]:
                l = t.lanes[name]
                status = []
                if l.turrets_lost:
                    status.append(f"{', '.join(sorted(l.turrets_lost))}")
                if l.inhib_lost:
                    status.append("**INHIBITOR**")

                status_str = "Secure" if not status else "; ".join(status)
                lines.append(f"   - {name}: {status_str}")
            return "\n".join(lines)

        def render_objectives(t: Team) -> str:
            """Render objective control for a team"""
            lines = []
            if t.dragons.count > 0:
                lines.append(f"   - Dragons ({t.dragons.count}): {', '.join(t.dragons.timers)}")
            if t.barons.count > 0:
                lines.append(f"   - Baron ({t.barons.count}): {', '.join(t.barons.timers)}")
            if t.heralds.count > 0:
                lines.append(f"   - Rift Herald ({t.heralds.count}): {', '.join(t.heralds.timers)}")
            if t.grubs.count > 0:
                lines.append(f"   - Void Grubs ({t.grubs.count}): Taken at {', '.join(t.grubs.timers)}")

            if not lines:
                return "   - None"
            return "\n".join(lines)

        def render_player(p: Player) -> str:
            """Render player information"""
            stat = "ALIVE"
            if p.is_dead:
                stat = f"DEAD ({int(p.respawn_timer)}s)"

            return (
                f"[{p.champion_name}] (Lvl {p.level} {p.role}) - {stat}\n"
                f"   Kills: {p.scores.k}, Deaths: {p.scores.d}, Assists: {p.scores.a} | CS: {p.scores.cs} | Vis: {round(p.scores.vis, 1)}\n"
                f"   Items: {', '.join(p.items)}\n"
                f"   Spells: {' '.join(p.spells)} | Rune: {p.keystone}\n"
            )

        # Active Player Block
        ap = s.active_player
        ap_text = "N/A"
        ap_name = "Unknown"
        if ap:
            ap_name = ap.summoner_name
            ap_status = "ALIVE"
            if ap.is_dead:
                ap_status = f"DEAD (Respawn {int(ap.respawn_timer)}s)"

            if ap.combat_stats:
                cs = ap.combat_stats
                abs_str = " ".join([f"{a.key}:{a.level}" for a in ap.abilities])

                ap_text = (
                    f"Champion: {ap.champion_name} (Lvl {ap.level} {ap.role}) - {ap_status}\n"
                    f"Kills: {ap.scores.k}, Deaths: {ap.scores.d}, Assists: {ap.scores.a} | CS: {ap.scores.cs} | Vision Score: {round(ap.scores.vis, 1)}\n"
                    f"Vitals: {cs.hp_current}/{cs.hp_max} HP | {cs.resource_current}/{cs.resource_max} {cs.resource_type}\n"
                    f"Current Gold: {int(ap.current_gold)} Gold\n"
                    f"Combat Stats: AD:{cs.ad} AP:{cs.ap} Armor:{cs.armor} MR:{cs.mr}\n"
                    f"Abilities: {abs_str}\n"
                    f"Items: {', '.join(ap.items)}\n"
                    f"Summoner Spells: {' / '.join(ap.spells)}\n"
                    f"Keystone Rune: {ap.keystone}"
                )
            else:
                ap_text = f"Champion: {ap.champion_name} - {ap_status}\n(Waiting for combat stats update...)"

        evt_text = "\n".join([f"- {e.time_ago}s ago: {e.message}" for e in s.event_log])
        if not evt_text:
            evt_text = "- No events recorded."

        # Filter out active player from ally team list
        ally_team_players = [p for p in s.allies.players if p != s.active_player]

        return f"""=== GAME STATE REPORT ===
SCORE: {s.allies.team_id} {s.allies.total_kills} - {s.enemies.total_kills} {s.enemies.team_id}

=== ACTIVE PLAYER STATUS ({ap_name}) ===
{ap_text}

=== OBJECTIVE CONTROL ===
[{s.allies.team_id} Objectives]:
{render_objectives(s.allies)}

[{s.enemies.team_id} Objectives]:
{render_objectives(s.enemies)}

=== MAP STRUCTURE STATUS ===
ENEMY_TURRETS_DESTROYED (We killed these):
{render_lanes(s.enemies)}

YOUR_TURRETS_DESTROYED (We lost these):
{render_lanes(s.allies)}

=== ALLY TEAM ({s.allies.team_id}) ===
{"".join([render_player(p) for p in ally_team_players])}
=== ENEMY TEAM ({s.enemies.team_id}) ===
{"".join([render_player(p) for p in s.enemies.players])}
=== RECENT BATTLE LOG (Last 10 Events / 60s) ===
{evt_text}
"""

