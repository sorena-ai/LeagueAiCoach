"""Landing agent for typed questions on sensii.gg.

One shared agent serves every anonymous session. The prompt has nothing
per visitor, and a new page visit should not build another one.
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime
from xml.etree import ElementTree as ET

from anthropic import RateLimitError as AnthropicRateLimitError
from google.api_core.exceptions import ResourceExhausted
from langchain.agents import create_agent

from app.assistant.landing.prompts import build_landing_prompt
from app.assistant.landing.sources import collect_source_paths
from app.assistant.tools import CHAMPION_TOOLS
from app.lib.langchain import (
    ensure_llm_config,
    extract_message_text,
    get_knowledge_agent_llm_settings,
    get_llm_chat,
    usage_fields,
)
from app.lib.langsmith_tracing import langsmith_tracing, trace_config
from app.utils.log_context import bind_log_context, elapsed_ms

LANDING_PROVIDER, LANDING_MODEL = get_knowledge_agent_llm_settings()
ensure_llm_config(LANDING_PROVIDER)

logger = logging.getLogger(__name__)

_REFUSAL = "Sorry, I can't help with that one. Try asking something else about League."
_QUOTA = "I'm sorry, but I've reached my usage limit. Please try again in a few minutes."

_shared_agent = None


@dataclass(frozen=True)
class LandingAnswer:
    """Advice text plus the repo files the tools returned while writing it."""

    reply: str
    source_paths: list[str]


def build_landing_turn(question: str, language: str = "english") -> str:
    """XML for the current visitor turn. ``<`` and ``&`` in the question are escaped."""
    turn = ET.Element("turn")
    language_el = ET.SubElement(turn, "language")
    language_el.text = language
    question_el = ET.SubElement(turn, "question")
    question_el.text = question
    return ET.tostring(turn, encoding="unicode")


def create_landing_agent():
    """Return the landing agent, built once and reused for every session."""
    global _shared_agent
    if _shared_agent is None:
        _shared_agent = create_agent(
            model=get_llm_chat(LANDING_PROVIDER, LANDING_MODEL),
            tools=CHAMPION_TOOLS,
            system_prompt=build_landing_prompt(),
        )
    return _shared_agent


async def get_landing_advice(
    session,
    question: str,
    language: str = "english",
) -> LandingAnswer:
    """Answer one landing question and record which data files the tools read.

    Refusal and quota return the same strings as the knowledge agent, with
    no source paths.
    """
    bind_log_context(
        provider=LANDING_PROVIDER,
        model=LANDING_MODEL,
        history_messages=session.message_history.get_message_count(),
        session_age_s=round((datetime.now() - session.created_at).total_seconds()),
    )

    logger.info(
        "Getting landing advice - session: %s, history: %d messages",
        session.session_id,
        session.message_history.get_message_count(),
    )
    logger.info("Visitor question: %s", question)

    try:
        messages = list(session.message_history.get_context_messages())
        messages.append({"role": "user", "content": build_landing_turn(question, language)})

        invoke_started = time.perf_counter()
        with langsmith_tracing():
            agent_result = await session.agent.ainvoke(
                {"messages": messages},
                config=trace_config(
                    "landing",
                    provider=LANDING_PROVIDER,
                    model=LANDING_MODEL,
                ),
            )
        invoke_ms = elapsed_ms(invoke_started)

        response_messages = agent_result.get("messages", [])
        if not response_messages:
            raise ValueError("Agent did not return any messages")

        last_message = response_messages[-1]
        if last_message.response_metadata.get("stop_reason") == "refusal":
            bind_log_context(
                outcome="refusal",
                llm_ms=invoke_ms,
                source_count=0,
                refusal=last_message.response_metadata.get("stop_details"),
            )
            logger.warning("Landing agent declined the question")
            return LandingAnswer(reply=_REFUSAL, source_paths=[])

        advice = extract_message_text(last_message)
        source_paths = collect_source_paths(response_messages)
        bind_log_context(
            outcome="answered",
            llm_ms=invoke_ms,
            advice_chars=len(advice),
            source_count=len(source_paths),
            sources=source_paths,
            **usage_fields(last_message),
        )
        logger.info(
            "Landing agent responded in %.0f ms (%d chars, %d sources)",
            invoke_ms,
            len(advice),
            len(source_paths),
        )

        await session.message_history.add_user_message(question)
        await session.message_history.add_assistant_message(advice)
        return LandingAnswer(reply=advice, source_paths=source_paths)

    except (ResourceExhausted, AnthropicRateLimitError) as exc:
        bind_log_context(outcome="quota", source_count=0)
        logger.error("Landing LLM API quota exceeded (%s): %s", LANDING_PROVIDER, exc)
        return LandingAnswer(reply=_QUOTA, source_paths=[])

    except Exception as exc:
        logger.error("Error in get_landing_advice: %s", exc, exc_info=True)
        raise
