"""
Knowledge Agent Module

This module provides agent creation for out-of-game League of Legends knowledge assistance.
Used when the user is not in an active game and wants to ask general questions.
"""

import logging
import time
import warnings
from datetime import datetime

from langchain.agents import create_agent
from langchain_classic.agents import AgentExecutor
from google.api_core.exceptions import ResourceExhausted

from app.config import settings
from app.assistant.knowledge_prompts import build_knowledge_prompt
from app.assistant.tools import CHAMPION_TOOLS
from app.lib.langchain import ensure_llm_config, extract_message_text, get_llm_chat, usage_fields
from app.utils.log_context import bind_log_context, elapsed_ms

ensure_llm_config()

logger = logging.getLogger(__name__)
# Silence pydantic v1-style __fields__ deprecation warnings from upstream libs
warnings.filterwarnings(
    "ignore",
    message=".*__fields__.*PydanticDeprecatedSince20.*",
)


def create_knowledge_agent() -> AgentExecutor:
    """
    Create a new knowledge agent for out-of-game assistance.

    Unlike the coach agent, this agent doesn't have champion-specific context
    or game state baked into the system prompt. Instead it is given tools to
    look up champion data (combos, builds, guides) and role strategy on
    demand, so it can answer about whatever champion the user asks.

    Language instruction is passed dynamically with each user message.

    Returns:
        AgentExecutor instance configured for knowledge mode.
    """
    llm = get_llm_chat()

    # Build knowledge mode system prompt (no gaming guidance section)
    system_prompt = build_knowledge_prompt()

    # Create agent with tools that fetch champion/role data on demand.
    agent = create_agent(
        model=llm,
        tools=CHAMPION_TOOLS,
        system_prompt=system_prompt,
    )

    return agent


def get_knowledge_advice(
    session,
    user_question: str,
    language: str = "english",
) -> str:
    """
    Get knowledge advice using the provided session (no game stats).

    Args:
        session: KnowledgeSession object containing agent and message history
        user_question: User's transcribed question text
        language: Language for the response (default: "english")

    Returns:
        Knowledge advice as plain text string

    Raises:
        Exception: If API call fails or processing error occurs
    """
    bind_log_context(
        provider=settings.coach_provider,
        model=settings.coach_model,
        history_messages=session.message_history.get_message_count(),
        session_age_s=round((datetime.now() - session.created_at).total_seconds()),
    )

    logger.info(
        "Getting knowledge advice - User ID: %s, history: %d messages",
        session.user_id,
        session.message_history.get_message_count(),
    )
    logger.info("User question: %s", user_question)

    try:
        logger.info("Running knowledge agent with provider: %s (model: %s)",
                   settings.coach_provider, settings.coach_model)

        # Build messages array starting with history (bounded window + summary)
        messages = []

        # Add historical context (bounded window + rolling summary, text-only)
        messages.extend(session.message_history.get_context_messages())

        # Add current message with user question (no game stats in knowledge mode)
        current_message_text = f"Answer in {language.upper()}.\n\nUser Question: {user_question}\n\nAnswer this question about League of Legends accurately. If the question is about a specific champion, answer about that champion. If the provided context does not contain info about this champion, use your own knowledge."
        
        current_message = {
            "role": "user",
            "content": current_message_text
        }
        messages.append(current_message)

        logger.info("Invoking knowledge agent with %d total messages (%d historical + 1 current)",
                   len(messages), len(messages) - 1)

        # Invoke agent with messages format
        invoke_started = time.perf_counter()
        agent_result = session.agent.invoke({"messages": messages})
        invoke_ms = elapsed_ms(invoke_started)

        # Extract text response from agent result
        response_messages = agent_result.get("messages", [])
        if not response_messages:
            raise ValueError("Agent did not return any messages")

        # Get the last message (assistant's response)
        last_message = response_messages[-1]
        advice = extract_message_text(last_message)

        bind_log_context(llm_ms=invoke_ms, advice_chars=len(advice), **usage_fields(last_message))
        logger.info(
            "Knowledge agent responded in %.0f ms (%d chars)", invoke_ms, len(advice)
        )
        logger.info("Knowledge agent response: %s", advice[:200])

        # Add user question and assistant response to message history
        session.message_history.add_user_message(user_question)
        session.message_history.add_assistant_message(advice)

        logger.info("Added messages to history. New count: %d messages",
                   session.message_history.get_message_count())

        return advice

    except ResourceExhausted as e:
        logger.error("Knowledge LLM API quota exceeded (%s): %s", settings.coach_provider, str(e))
        return "I'm sorry, but I've reached my usage limit. Please try again in a few minutes."

    except Exception as e:
        logger.error("Error in get_knowledge_advice: %s", str(e), exc_info=True)
        raise
