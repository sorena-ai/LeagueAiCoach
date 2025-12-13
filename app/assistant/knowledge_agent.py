"""
Knowledge Agent Module

This module provides agent creation for out-of-game League of Legends knowledge assistance.
Used when the user is not in an active game and wants to ask general questions.
"""

import logging
import warnings

from langchain.agents import create_agent
from langchain_classic.agents import AgentExecutor
from google.api_core.exceptions import ResourceExhausted

from app.config import settings
from app.assistant.knowledge_prompts import build_knowledge_prompt
from app.lib.langchain import ensure_llm_config, get_llm_chat

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
    or game state. It answers general League of Legends questions.

    Language instruction is passed dynamically with each user message.

    Returns:
        AgentExecutor instance configured for knowledge mode.
    """
    llm = get_llm_chat()

    # Build knowledge mode system prompt (no gaming guidance section)
    system_prompt = build_knowledge_prompt()

    # Create agent without tools for text-based knowledge assistance
    agent = create_agent(
        model=llm,
        tools=[],
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
    logger.info("Getting knowledge advice - User ID: %s", session.user_id)
    logger.info("User question: %s", user_question)
    logger.info("Message history count: %d messages", session.message_history.get_message_count())

    try:
        logger.info("Running knowledge agent with provider: %s (model: %s)",
                   settings.coach_provider, settings.coach_model)

        # Build messages array starting with history (text-only)
        messages = []

        # Add historical messages (text-only)
        historical_messages = session.message_history.get_all_messages()
        for msg in historical_messages:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        # Add current message with user question (no game stats in knowledge mode)
        current_message_text = f"Answer in {language.upper()}.\n\nUser Question: {user_question}\n\nAnswer this question about League of Legends accurately. If the question is about a specific champion, answer about that champion. If the provided context does not contain info about this champion, use your own knowledge."
        
        current_message = {
            "role": "user",
            "content": current_message_text
        }
        messages.append(current_message)

        logger.info("Invoking knowledge agent with %d total messages (%d historical + 1 current)",
                   len(messages), len(historical_messages))

        # Invoke agent with messages format
        agent_result = session.agent.invoke({"messages": messages})

        # Extract text response from agent result
        response_messages = agent_result.get("messages", [])
        if not response_messages:
            raise ValueError("Agent did not return any messages")
        
        # Get the last message (assistant's response)
        last_message = response_messages[-1]
        advice = last_message.content if hasattr(last_message, 'content') else str(last_message)

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
