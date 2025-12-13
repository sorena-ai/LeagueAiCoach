"""
Message History Module

Manages lightweight conversation history without game stats.
Stores user transcripts and AI responses in memory within sessions.
"""
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


class MessageHistory:
    """Manages conversation history for a coaching session."""

    def __init__(self):
        """Initialize empty message history."""
        self._messages: List[Dict[str, str]] = []

    def add_user_message(self, content: str) -> None:
        """
        Add a user message to history.

        Args:
            content: User's question transcript (text only, no game stats)
        """
        self._messages.append({"role": "user", "content": content})
        logger.debug(f"Added user message to history. Total messages: {len(self._messages)}")

    def add_assistant_message(self, content: str) -> None:
        """
        Add an assistant message to history.

        Args:
            content: Assistant's response text
        """
        self._messages.append({"role": "assistant", "content": content})
        logger.debug(f"Added assistant message to history. Total messages: {len(self._messages)}")

    def get_all_messages(self) -> List[Dict[str, str]]:
        """
        Get all messages in history.

        Returns:
            List of message dicts with 'role' and 'content' keys
        """
        return self._messages.copy()

    def get_message_count(self) -> int:
        """Get the total number of messages in history."""
        return len(self._messages)

    def clear(self) -> None:
        """Clear all messages from history."""
        self._messages.clear()
        logger.debug("Cleared message history")

    def __repr__(self) -> str:
        return f"MessageHistory(message_count={len(self._messages)})"
