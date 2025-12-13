"""
Session Management Module

Manages coaching sessions with 2-hour TTL and background cleanup.
Supports two session types:
- GameSession: For in-game coaching with game stats
- KnowledgeSession: For out-of-game knowledge questions

Each session is keyed by a (identifier, session_type) combination.
"""
import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, Union

from langchain_classic.agents import AgentExecutor

from app.assistant.agent import create_coach_agent
from app.assistant.messages import MessageHistory
from app.models.game_stats import GameStats

logger = logging.getLogger(__name__)


def _normalize_position_to_role(position: str) -> str:
    """
    Convert game stats position format to internal role format.

    Game stats provide positions as: TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY
    Internal system expects roles as: top, jungle, mid, adc, support

    Args:
        position: Position string from game stats (e.g., "TOP", "MIDDLE", "UTILITY")

    Returns:
        Normalized role string (e.g., "top", "mid", "support")
    """
    position_to_role_map = {
        "TOP": "top",
        "JUNGLE": "jungle",
        "MIDDLE": "mid",
        "BOTTOM": "adc",
        "UTILITY": "support",
    }

    normalized_role = position_to_role_map.get(position.upper())

    if normalized_role is None:
        logger.warning(
            "Unknown position '%s' from game stats. Expected one of: %s",
            position,
            ", ".join(position_to_role_map.keys())
        )
        return "unknown"

    return normalized_role


class BaseSession(ABC):
    """Abstract base class for all session types."""

    def __init__(self, agent: AgentExecutor, ttl_hours: int = 2):
        """
        Initialize base session.

        Args:
            agent: LangChain agent executor for this session
            ttl_hours: Session time-to-live in hours (default: 2)
        """
        self.agent = agent
        self.message_history = MessageHistory()
        self.created_at = datetime.now()
        self.expires_at = self.created_at + timedelta(hours=ttl_hours)

    def is_expired(self) -> bool:
        """Check if session has exceeded TTL."""
        return datetime.now() >= self.expires_at

    @abstractmethod
    def get_session_key(self) -> Tuple[str, str]:
        """Return the unique key tuple for this session."""
        pass

    @abstractmethod
    def __repr__(self) -> str:
        pass


class GameSession(BaseSession):
    """Represents a coaching session for a specific in-game match."""

    def __init__(
        self,
        username: str,
        match_id: str,
        game_start_time: float,
        role: str,
        champion: str,
        agent: AgentExecutor,
    ):
        """
        Initialize a game coaching session.

        Args:
            username: Player's Riot ID (e.g., "AliVampire#S2Q")
            match_id: Unique match identifier from client
            game_start_time: Game time in seconds when session was created
            role: Player's role in normalized format (e.g., "top", "jungle", "mid", "adc", "support")
            champion: Champion name (e.g., "Braum")
            agent: LangChain agent executor for this session
        """
        super().__init__(agent, ttl_hours=2)
        self.username = username
        self.match_id = match_id
        self.game_start_time = game_start_time
        self.role = role
        self.team: Optional[str] = None
        self.champion = champion

    def get_session_key(self) -> Tuple[str, str]:
        """Return the unique key tuple for this game session."""
        return (self.username, self.match_id)

    def get_game_time(self, current_game_time: float) -> float:
        """
        Calculate the elapsed game time since session creation.

        Args:
            current_game_time: Current game time from game_stats (in seconds)

        Returns:
            Elapsed game time in seconds
        """
        return current_game_time - self.game_start_time

    def __repr__(self) -> str:
        return (
            f"GameSession(username={self.username}, match_id={self.match_id}, "
            f"champion={self.champion}, role={self.role}, "
            f"expires_at={self.expires_at.isoformat()})"
        )


class KnowledgeSession(BaseSession):
    """Represents an out-of-game knowledge assistant session."""

    def __init__(self, user_id: str, agent: AgentExecutor):
        """
        Initialize a knowledge session.

        Args:
            user_id: User's unique identifier from auth system
            agent: LangChain agent executor for this session
        """
        super().__init__(agent, ttl_hours=2)
        self.user_id = user_id

    def get_session_key(self) -> Tuple[str, str]:
        """Return the unique key tuple for this knowledge session."""
        return (self.user_id, "knowledge")

    def __repr__(self) -> str:
        return (
            f"KnowledgeSession(user_id={self.user_id}, "
            f"expires_at={self.expires_at.isoformat()})"
        )


# Type alias for backward compatibility
Session = GameSession


class SessionManager:
    """Manages in-memory coaching sessions with automatic cleanup."""

    def __init__(self):
        """Initialize session manager with empty storage."""
        self._sessions: Dict[Tuple[str, str], BaseSession] = {}
        self._cleanup_task: Optional[asyncio.Task] = None

    def _get_key(self, identifier: str, session_type: str) -> Tuple[str, str]:
        """Generate session key from identifier and session type."""
        return (identifier, session_type)

    def get_session(self, identifier: str, session_type: str) -> Optional[BaseSession]:
        """
        Retrieve an existing session.

        Args:
            identifier: User identifier (username for game, user_id for knowledge)
            session_type: Session type identifier (match_id or "knowledge")

        Returns:
            Session if found and not expired, None otherwise
        """
        key = self._get_key(identifier, session_type)
        session = self._sessions.get(key)

        if session and session.is_expired():
            logger.info(f"Session expired: {session}")
            del self._sessions[key]
            return None

        return session

    def _remove_knowledge_session(self, user_id: str) -> None:
        """
        Remove knowledge session for a user if it exists.

        Called when user enters a game to clean up knowledge session.

        Args:
            user_id: User's unique identifier
        """
        key = self._get_key(user_id, "knowledge")
        if key in self._sessions:
            session = self._sessions.pop(key)
            logger.info(f"Removed knowledge session as user entered game: {session}")

    def create_game_session(
        self,
        username: str,
        match_id: str,
        game_start_time: float,
        role: str,
        champion: str,
        agent: AgentExecutor,
    ) -> GameSession:
        """
        Create a new game session.

        Args:
            username: Player's Riot ID
            match_id: Match identifier
            game_start_time: Game time when session is created
            role: Player's role in normalized format
            champion: Champion name
            agent: LangChain agent executor

        Returns:
            Newly created GameSession
        """
        key = self._get_key(username, match_id)

        # Clean up existing session if present
        if key in self._sessions:
            logger.info(f"Replacing existing session for {username} in match {match_id}")

        session = GameSession(
            username=username,
            match_id=match_id,
            game_start_time=game_start_time,
            role=role,
            champion=champion,
            agent=agent,
        )
        self._sessions[key] = session

        logger.info(f"Created new game session: {session}")
        return session

    def create_knowledge_session(
        self,
        user_id: str,
        agent: AgentExecutor,
    ) -> KnowledgeSession:
        """
        Create a new knowledge session.

        Args:
            user_id: User's unique identifier
            agent: LangChain agent executor

        Returns:
            Newly created KnowledgeSession
        """
        key = self._get_key(user_id, "knowledge")

        # Clean up existing session if present
        if key in self._sessions:
            logger.info(f"Replacing existing knowledge session for user {user_id}")

        session = KnowledgeSession(
            user_id=user_id,
            agent=agent,
        )
        self._sessions[key] = session

        logger.info(f"Created new knowledge session: {session}")
        return session

    # Legacy method for backward compatibility
    def create_session(
        self,
        username: str,
        match_id: str,
        game_start_time: float,
        role: str,
        champion: str,
        agent: AgentExecutor,
    ) -> GameSession:
        """Legacy method - use create_game_session instead."""
        return self.create_game_session(
            username=username,
            match_id=match_id,
            game_start_time=game_start_time,
            role=role,
            champion=champion,
            agent=agent,
        )

    def get_or_create_session(
        self,
        game_stats_dict: dict,
        user_id: Optional[str] = None,
    ) -> GameSession:
        """
        Get existing game session or create new one if not found.

        Extracts session data from game_stats and creates agent automatically.
        Uses GameStart event time as the unique session identifier.

        If user_id is provided and a new session is created, any existing
        knowledge session for that user will be removed (user entered game).

        Args:
            game_stats_dict: Parsed game statistics dictionary
            user_id: Optional user ID to remove knowledge session when entering game

        Returns:
            Existing or newly created GameSession
        """

        # Extract session data from game_stats
        active_player = game_stats_dict.get("activePlayer", {})
        events = game_stats_dict.get("events", {})

        username = active_player.get("riotId", "unknown")

        # Extract GameStart event time as unique session identifier
        game_start_time = 0.0
        events_list = events.get("Events", [])
        for event in events_list:
            if event.get("EventName") == "GameStart":
                game_start_time = event.get("EventTime", 0.0)
                break

        # Use GameStart time as match_id (unique identifier for this game session)
        session_match_id = f"game_{game_start_time}"

        # Check if session exists
        session = self.get_session(username, session_match_id)

        if session:
            logger.info(f"Reusing existing session: {session}")
            return session

        # Extract champion, role, and team from active player in allPlayers array
        all_players = game_stats_dict.get("allPlayers", [])
        champion = "unknown"
        raw_position = "UNKNOWN"
        team = None
        for player in all_players:
            if player.get("riotId") == username:
                champion = player.get("championName", "unknown")
                raw_position = player.get("position", "UNKNOWN")
                team = player.get("team", None)
                break

        # Normalize position to internal role format
        # Game stats: TOP/JUNGLE/MIDDLE/BOTTOM/UTILITY → System: top/jungle/mid/adc/support
        role = _normalize_position_to_role(raw_position)


        # Create agent with champion guide and playbook baked into system prompt
        # Game stats and language instruction will be passed fresh with each user message

        # Remove any existing knowledge session for this user (they entered a game)
        if user_id:
            self._remove_knowledge_session(user_id)

        session = self.create_session(
            username=username,
            match_id=session_match_id,
            game_start_time=game_start_time,
            role=role,
            champion=champion,
            agent=create_coach_agent(champion, role),
        )

        # Store team if found
        if team:
            session.team = team

        return session

    def get_or_create_knowledge_session(
        self,
        user_id: str,
    ) -> KnowledgeSession:
        """
        Get existing knowledge session or create new one if not found.

        Used when user is not in an active game and wants to ask
        general League of Legends questions.

        Args:
            user_id: User's unique identifier from auth system

        Returns:
            Existing or newly created KnowledgeSession
        """
        # Import here to avoid circular imports
        from app.assistant.knowledge_agent import create_knowledge_agent

        # Check if knowledge session exists
        session = self.get_session(user_id, "knowledge")

        if session and isinstance(session, KnowledgeSession):
            logger.info(f"Reusing existing knowledge session: {session}")
            return session

        # Create new knowledge session
        session = self.create_knowledge_session(
            user_id=user_id,
            agent=create_knowledge_agent(),
        )

        return session

    async def _cleanup_expired_sessions(self):
        """Background task to remove expired sessions every 20 minutes."""
        while True:
            try:
                await asyncio.sleep(20 * 60)  # 20 minutes

                expired_keys = [
                    key for key, session in self._sessions.items()
                    if session.is_expired()
                ]

                for key in expired_keys:
                    session = self._sessions.pop(key)
                    logger.info(f"Cleaned up expired session: {session}")

                if expired_keys:
                    logger.info(f"Removed {len(expired_keys)} expired session(s)")
                else:
                    logger.debug("No expired sessions to clean up")

            except Exception as e:
                logger.error(f"Error in session cleanup task: {e}", exc_info=True)

    def start_cleanup_task(self):
        """Start the background cleanup task."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_sessions())
            logger.info("Started session cleanup background task (runs every 20 minutes)")

    def stop_cleanup_task(self):
        """Stop the background cleanup task."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            logger.info("Stopped session cleanup background task")

    def get_active_session_count(self) -> int:
        """Get count of non-expired sessions."""
        return sum(1 for session in self._sessions.values() if not session.is_expired())


# Global session manager instance
session_manager = SessionManager()
