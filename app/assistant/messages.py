"""
Message History Module

Manages conversation history for coaching sessions with a bounded window and
an optional rolling summary.

Users keep the app open and talk to it for long stretches, so history must not
grow without bound. This class keeps:

- a sliding window of the most recent raw messages (bounded by count and chars)
- an optional running summary that older evicted messages are folded into

The summary is opt-in: pass ``summarize=None`` to simply drop evicted messages
(no LLM call). Agents pass ``default_summarize`` to preserve long-horizon
continuity in a compact form.
"""

import logging
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# A summarizer folds newly-evicted messages into the running summary and
# returns the updated summary string.
SummaryFn = Callable[[str, List[Dict[str, str]]], str]

_llm = None


def _get_summary_llm():
    global _llm
    if _llm is None:
        from app.lib.langchain import get_llm_chat

        _llm = get_llm_chat()
    return _llm


def default_summarize(existing: str, new_messages: List[Dict[str, str]]) -> str:
    """Fold evicted messages into a compact running summary using the coach LLM."""
    transcript = "\n".join(f"{m['role']}: {m['content']}" for m in new_messages)
    prompt = (
        "Summarize this League of Legends coaching conversation into a few "
        "concise lines capturing what the user asked and the advice given. "
        "Keep key facts (champion, role, decisions). Return only the updated summary.\n\n"
        f"Existing summary:\n{existing or '(none)'}\n\n"
        f"New messages:\n{transcript}\n\n"
        "Updated summary:"
    )

    from app.lib.langchain import extract_message_text

    response = _get_summary_llm().invoke(prompt)
    return extract_message_text(response).strip()


class MessageHistory:
    """Bounded conversation history with an optional rolling summary."""

    def __init__(
        self,
        max_messages: int = 12,
        max_chars: int = 12000,
        summarize: Optional[SummaryFn] = None,
        summarize_batch_size: int = 6,
    ):
        """
        Initialize bounded message history.

        Args:
            max_messages: Maximum number of raw messages kept in the window.
            max_chars: Approximate character budget for the raw window.
            summarize: Callable folding evicted messages into a summary.
                If None, evicted messages are dropped without summarization.
            summarize_batch_size: Minimum evicted messages before a summarize call.
        """
        self._messages: List[Dict[str, str]] = []
        self._pending: List[Dict[str, str]] = []
        self._summary: str = ""
        self.max_messages = max_messages
        self.max_chars = max_chars
        self.summarize_batch_size = summarize_batch_size
        self._summarize = summarize

    def add_user_message(self, content: str) -> None:
        """Add a user message to history."""
        self._append("user", content)

    def add_assistant_message(self, content: str) -> None:
        """Add an assistant message to history."""
        self._append("assistant", content)

    def _append(self, role: str, content: str) -> None:
        self._messages.append({"role": role, "content": content})
        self._trim()

    def _trim(self) -> None:
        """Evict oldest messages past the count/char budgets into pending."""
        while len(self._messages) > self.max_messages:
            self._pending.append(self._messages.pop(0))

        while (
            len(self._messages) > 2
            and sum(len(m["content"]) for m in self._messages) > self.max_chars
        ):
            self._pending.append(self._messages.pop(0))

        if len(self._pending) >= self.summarize_batch_size:
            self._fold_pending()

    def _fold_pending(self) -> None:
        """Fold accumulated evicted messages into the running summary."""
        if not self._pending:
            return
        batch = self._pending
        self._pending = []
        if self._summarize is None:
            return
        try:
            self._summary = self._summarize(self._summary, batch)
        except Exception:
            logger.exception(
                "Failed to summarize %d evicted messages; dropping them", len(batch)
            )
            self._summary = ""

    def get_context_messages(self) -> List[Dict[str, str]]:
        """
        Return the bounded context to send to the LLM.

        Includes the running summary (if any) followed by the recent raw
        messages, each as a ``{"role", "content"}`` dict.
        """
        messages: List[Dict[str, str]] = []
        if self._summary:
            messages.append(
                {
                    "role": "user",
                    "content": f"[Earlier conversation summary]\n{self._summary}",
                }
            )
        messages.extend(self._messages)
        return messages

    def get_all_messages(self) -> List[Dict[str, str]]:
        """Get the raw window messages (no summary)."""
        return self._messages.copy()

    def get_message_count(self) -> int:
        """Get the number of raw messages in the window."""
        return len(self._messages)

    def clear(self) -> None:
        """Clear all messages, pending evictions, and the summary."""
        self._messages.clear()
        self._pending.clear()
        self._summary = ""

    def __repr__(self) -> str:
        return (
            f"MessageHistory(message_count={len(self._messages)}, "
            f"summary_chars={len(self._summary)}, pending={len(self._pending)})"
        )
