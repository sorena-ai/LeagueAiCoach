"""
Agent Module

This module provides agent creation for League of Legends coaching.
It uses LangChain's agent pattern (langchain.agents.create_agent) with tool calling
to analyze game statistics and provide strategic advice.
"""

import logging
import warnings

from langchain.agents import create_agent
from langchain_classic.agents import AgentExecutor
from google.api_core.exceptions import ResourceExhausted

from app.config import settings
from app.assistant import prompts
from app.assistant.prompts import build_gaming_guidance_section, build_game_state_report
from app.lib.langchain import ensure_llm_config, get_llm_chat
from app.utils.game_stats import GameStateProcessor

ensure_llm_config()

logger = logging.getLogger(__name__)
# Silence pydantic v1-style __fields__ deprecation warnings from upstream libs
warnings.filterwarnings(
    "ignore",
    message=".*__fields__.*PydanticDeprecatedSince20.*",
)


def create_coach_agent(champion: str, role: str) -> AgentExecutor:
    """
    Create a new coaching agent with static context.

    System prompt has two major sections:
    1. BASE PROMPT: How the agent should behave (personality, tone, scope, response format)
    2. GAMING GUIDANCE: All game data (champion info, playbook with all phases, guide, combos, builds)

    Game stats and language instruction are passed dynamically with each user message.

    Args:
        champion: Champion name
        role: Player's position

    Returns:
        AgentExecutor instance.
    """
    llm = get_llm_chat()

    # Build system prompt with two major sections
    base_prompt = prompts.build_coach_prompt()
    gaming_guidance = build_gaming_guidance_section(champion, role)

    # Construct complete system prompt (order: base + gaming guidance)
    system_prompt = f"{base_prompt}\n\n{gaming_guidance}"

    # Create agent without tools for text-based coaching
    agent = create_agent(
        model=llm,
        tools=[],
        system_prompt=system_prompt,
    )

    return agent


def get_coach_advice(
    session,
    user_question: str,
    game_stats_json: str,
    language: str = "english",
) -> str:
    """
    Get coaching advice using the provided session.

    Args:
        session: Session object containing agent and message history
        user_question: User's transcribed question text
        game_stats_json: Fresh game statistics JSON
        language: Language for the response (default: "english")

    Returns:
        Coaching advice as plain text string

    Raises:
        Exception: If API call fails or processing error occurs
    """
    logger.info("Getting coach advice - Username: %s, Match: %s", session.username, session.match_id)
    logger.info("User question: %s", user_question)
    logger.info("Message history count: %d messages", session.message_history.get_message_count())
    logger.info("Raw Game Stats json: %s", game_stats_json)

    try:
        # Run agent with user question
        logger.info("Running agent with provider: %s (model: %s)",
                   settings.coach_provider, settings.coach_model)

        # Parse game stats JSON into MatchState (includes formatted_time as MM:SS)
        match_state = GameStateProcessor.process_to_state(game_stats_json)
        logger.info("Game time: %s", match_state.formatted_time)
        
        # Generate formatted report from MatchState
        game_stats_report = build_game_state_report(match_state)
        logger.info("Generated game stats report (%d characters)", len(game_stats_report))

        # Build messages array starting with history (text-only)
        messages = []

        # Add historical messages (text-only, no game stats)
        historical_messages = session.message_history.get_all_messages()
        for msg in historical_messages:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        # Add current message with game time, transcribed question + game stats report
        current_message_text = f"[{match_state.formatted_time}] {user_question}\n\n{game_stats_report}\n\n[Respond in {language.capitalize()}]"
        
        current_message = {
            "role": "user",
            "content": current_message_text
        }
        messages.append(current_message)

        logger.info("Invoking agent with %d total messages (%d historical + 1 current)",
                   len(messages), len(historical_messages))

        # Invoke agent with messages format
        agent_result = session.agent.invoke({"messages": messages})

        # Extract text response from agent result
        # The agent returns messages with the last message being the assistant's response
        response_messages = agent_result.get("messages", [])
        if not response_messages:
            raise ValueError("Agent did not return any messages")
        
        # Get the last message (assistant's response)
        last_message = response_messages[-1]
        advice = last_message.content if hasattr(last_message, 'content') else str(last_message)

        logger.info("Agent response: %s", advice[:200])

        # Add user question and assistant response to message history
        session.message_history.add_user_message(f"[{match_state.formatted_time}] {user_question}")
        session.message_history.add_assistant_message(advice)

        logger.info("Added messages to history. New count: %d messages",
                   session.message_history.get_message_count())

        return advice

    except ResourceExhausted as e:
        logger.error("Coach LLM API quota exceeded (%s): %s", settings.coach_provider, str(e))
        return "I'm sorry, but I've reached my usage limit. Please try again in a few minutes."

    except Exception as e:
        logger.error("Error in get_coach_advice: %s", str(e), exc_info=True)
        raise
