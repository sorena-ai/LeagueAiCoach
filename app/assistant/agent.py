"""
Agent Module

This module provides agent creation for League of Legends coaching.
It uses LangChain's agent pattern (langchain.agents.create_agent) with tool calling
to analyze game statistics and provide strategic advice.
"""

import logging
import time
import warnings
from datetime import datetime

from langchain.agents import create_agent
from langchain_classic.agents import AgentExecutor
from google.api_core.exceptions import ResourceExhausted

from app.config import settings
from app.assistant import prompts
from app.assistant.prompts import build_gaming_guidance_section, build_game_state_report
from app.assistant.tools import CHAMPION_TOOLS
from app.lib.langchain import ensure_llm_config, extract_message_text, get_llm_chat, usage_fields
from app.utils.game_stats import GameStateProcessor
from app.utils.log_context import bind_log_context, elapsed_ms

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

    # Create agent with tools so it can look up champion/role data on demand
    # (e.g. matchups, counters, or details missing from the baked-in context).
    agent = create_agent(
        model=llm,
        tools=CHAMPION_TOOLS,
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
    # Bind the session identity so every line below - and anything the agent
    # logs - says which player and match it belongs to.
    bind_log_context(
        riot_id=session.username,
        match_id=session.match_id,
        champion=session.champion,
        role=session.role,
        provider=settings.coach_provider,
        model=settings.coach_model,
        history_messages=session.message_history.get_message_count(),
        session_age_s=round((datetime.now() - session.created_at).total_seconds()),
    )

    logger.info(
        "Getting coach advice - Riot ID: %s, Match: %s, Champion: %s (%s), history: %d messages",
        session.username,
        session.match_id,
        session.champion,
        session.role,
        session.message_history.get_message_count(),
    )
    logger.info("User question: %s", user_question)
    logger.debug("Raw Game Stats json: %s", game_stats_json)

    try:
        # Run agent with user question
        logger.info("Running agent with provider: %s (model: %s)",
                   settings.coach_provider, settings.coach_model)

        # Parse game stats JSON into MatchState (includes formatted_time as MM:SS)
        match_state = GameStateProcessor.process_to_state(game_stats_json)
        bind_log_context(game_time=match_state.formatted_time)
        logger.info("Game time: %s", match_state.formatted_time)
        
        # Generate formatted report from MatchState
        game_stats_report = build_game_state_report(match_state)
        logger.info("Generated game stats report (%d characters)", len(game_stats_report))

        # Build messages array starting with history (bounded window + summary)
        messages = []

        # Add historical context (bounded window + rolling summary, no game stats)
        messages.extend(session.message_history.get_context_messages())

        # Add current message with game time, transcribed question + game stats report
        current_message_text = f"[{match_state.formatted_time}] {user_question}\n\n{game_stats_report}\n\n[Respond in {language.capitalize()}]"
        
        current_message = {
            "role": "user",
            "content": current_message_text
        }
        messages.append(current_message)

        logger.info("Invoking agent with %d total messages (%d historical + 1 current)",
                   len(messages), len(messages) - 1)

        # Invoke agent with messages format
        invoke_started = time.perf_counter()
        agent_result = session.agent.invoke({"messages": messages})
        invoke_ms = elapsed_ms(invoke_started)

        # Extract text response from agent result
        # The agent returns messages with the last message being the assistant's response
        response_messages = agent_result.get("messages", [])
        if not response_messages:
            raise ValueError("Agent did not return any messages")

        # Get the last message (assistant's response)
        last_message = response_messages[-1]
        advice = extract_message_text(last_message)

        bind_log_context(llm_ms=invoke_ms, advice_chars=len(advice), **usage_fields(last_message))
        logger.info(
            "Agent responded in %.0f ms (%d chars, %d new messages)",
            invoke_ms,
            len(advice),
            len(response_messages) - len(messages),
        )
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
