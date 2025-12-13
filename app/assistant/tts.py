
from typing import AsyncGenerator

from openai import AsyncOpenAI

from app.config import settings


async def text_to_speech_stream(text: str) -> AsyncGenerator[bytes, None]:
    """
    Convert text to speech using OpenAI TTS API with async streaming.

    Uses OpenAI's with_streaming_response.create() for efficient async streaming.
    This is the recommended approach for async frameworks like FastAPI.

    Args:
        text: Text to convert to speech

    Yields:
        Audio chunks as bytes
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Use with_streaming_response for direct HTTP response streaming
    async with client.audio.speech.with_streaming_response.create(
        model=settings.openai_tts_model,
        voice=settings.openai_tts_voice,
        input=text,
        speed=settings.openai_tts_speed,
        response_format="wav",
    ) as response:
        # Stream the raw bytes from the HTTP response
        async for chunk in response.iter_bytes():
            yield chunk


def text_to_speech(text: str) -> bytes:
    """
    Synchronous version for backward compatibility.
    Collects all chunks from the async streaming generator.
    """
    import asyncio

    async def collect_chunks():
        chunks = []
        async for chunk in text_to_speech_stream(text):
            chunks.append(chunk)
        return b''.join(chunks)

    return asyncio.run(collect_chunks())


