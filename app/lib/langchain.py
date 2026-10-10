from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_xai import ChatXAI

from app.config import settings


def ensure_gemini_config() -> None:
    """Validate required Gemini environment variables."""
    if not settings.google_api_key:
        raise RuntimeError("Missing GOOGLE_API_KEY; set it to start the assistant service.")


def ensure_grok_config() -> None:
    """Validate required Grok environment variables."""
    if not settings.grok_api_key:
        raise RuntimeError("Missing GROK_API_KEY; set it to start the assistant service.")


def ensure_openai_config() -> None:
    """Validate required OpenAI environment variables."""
    if not settings.openai_api_key:
        raise RuntimeError("Missing OPENAI_API_KEY; set it to start the assistant service.")


def ensure_anthropic_config() -> None:
    """Validate required Anthropic environment variables."""
    if not settings.anthropic_api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY; set it to start the assistant service.")


def ensure_llm_config(provider: str | None = None) -> None:
    """
    Validate required LLM environment variables based on the configured provider.

    Checks the given provider (default: the COACH_PROVIDER setting) and
    validates the corresponding API key.

    Args:
        provider: Provider to validate; defaults to COACH_PROVIDER

    Raises:
        RuntimeError: If required API keys are missing for the selected provider
    """
    provider = (provider or settings.coach_provider).lower()

    if provider == "gemini":
        ensure_gemini_config()
    elif provider == "grok":
        ensure_grok_config()
    elif provider == "openai":
        ensure_openai_config()
    elif provider == "anthropic":
        ensure_anthropic_config()
    else:
        raise RuntimeError(
            f"Unknown LLM provider: '{provider}'. "
            f"Use one of: gemini, grok, openai, anthropic"
        )


def get_knowledge_agent_llm_settings() -> tuple[str, str]:
    """
    Return the (provider, model) pair the knowledge agent runs on.

    KNOWLEDGE_AGENT_PROVIDER / KNOWLEDGE_AGENT_MODEL override the coach
    settings; when unset, the knowledge agent shares COACH_PROVIDER / COACH_MODEL.
    """
    if settings.knowledge_agent_provider:
        if not settings.knowledge_agent_model:
            raise RuntimeError(
                "KNOWLEDGE_AGENT_PROVIDER is set but KNOWLEDGE_AGENT_MODEL is not."
            )
        return settings.knowledge_agent_provider, settings.knowledge_agent_model
    return settings.coach_provider, settings.coach_model


def get_llm_chat(provider: str | None = None, model: str | None = None):
    """
    Return an LLM chat client.

    Provider and model default to the COACH_PROVIDER / COACH_MODEL settings.
    Supports: gemini, grok, openai, anthropic

    Args:
        provider: LLM provider; defaults to COACH_PROVIDER
        model: Model name for that provider; defaults to COACH_MODEL

    Returns:
        LLM chat client

    Raises:
        ValueError: If unknown provider is specified
        RuntimeError: If required API keys are missing
    """
    provider = (provider or settings.coach_provider).lower()
    model = model or settings.coach_model

    # Create base LLM based on provider
    if provider == "gemini":
        ensure_gemini_config()
        llm = ChatGoogleGenerativeAI(
            model=model,
            temperature=.3,
            google_api_key=settings.google_api_key,
        )
    elif provider == "grok":
        ensure_grok_config()
        llm = ChatXAI(
            model=model,
            xai_api_key=settings.grok_api_key,
            temperature=.3,
        )
    elif provider == "openai":
        ensure_openai_config()
        llm = ChatOpenAI(
            model=model,
            api_key=settings.openai_api_key,
            temperature=.3,
        )
    elif provider == "anthropic":
        ensure_anthropic_config()
        # No temperature: Claude Sonnet 5.5 and newer reject non-default sampling
        # params. Effort controls adaptive thinking instead. max_tokens is set
        # explicitly; the profile default (128K) makes the SDK refuse a
        # non-streaming call.
        llm = ChatAnthropic(
            model=model,
            api_key=settings.anthropic_api_key,
            max_tokens=settings.knowledge_agent_max_tokens,
            effort=settings.knowledge_agent_effort,
        )
    else:
        raise ValueError(
            f"Unknown LLM provider: '{provider}'. "
            f"Supported providers: gemini, grok, openai, anthropic"
        )

    return llm


def extract_message_text(message) -> str:
    """
    Extract plain text from a LangChain message.

    ``AIMessage.content`` is typed ``str | list[str | dict]``: providers return a
    list of content blocks (``{"type": "text", "text": ...}`` alongside reasoning
    or tool blocks) whenever the response carries more than plain text. Passing
    that list on to a caller expecting a string fails downstream, so normalize
    both shapes here.

    Args:
        message: A LangChain message object (or anything with ``content``)

    Returns:
        The message's text content as a plain string
    """
    # langchain-core >= 1.0 exposes ``text`` as a property that joins text blocks.
    # It returns a TextAccessor: a str subclass that is *also* callable, so the
    # deprecated ``message.text()`` method form keeps working. Test for str
    # before callable, otherwise every lookup takes the deprecated path and
    # emits a LangChainDeprecationWarning (and breaks outright in 2.0).
    text = getattr(message, "text", None)
    if isinstance(text, str):
        if text:
            return str(text)
    elif callable(text):  # langchain-core < 1.0 exposed ``text`` only as a method
        called = text()
        if isinstance(called, str) and called:
            return str(called)

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)

    return str(message)


def usage_fields(message) -> dict:
    """
    Pull token counts off a LangChain response message.

    Providers populate ``usage_metadata`` inconsistently, so anything missing is
    simply left out rather than logged as null.

    Args:
        message: A LangChain message object

    Returns:
        A dict of token counts, safe to splat into bind_log_context; empty when
        the provider reported nothing
    """
    usage = getattr(message, "usage_metadata", None)
    if not isinstance(usage, dict):
        return {}

    fields = {
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }
    return {key: value for key, value in fields.items() if value is not None}
