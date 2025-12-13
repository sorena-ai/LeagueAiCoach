import os
import time
import json
from pathlib import Path

import pytest

from app.assistant.agent import get_coach_advice
from app.assistant.knowledge_agent import get_knowledge_advice
from app.assistant.session import session_manager
from app.assistant.stt import transcribe_audio
from app.assistant.tts import text_to_speech_stream
from app.config import settings
from app.models.language import get_language_code

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "coach_advice"


@pytest.mark.skipif(
    not os.getenv("GOOGLE_API_KEY") or not os.getenv("OPENAI_API_KEY"),
    reason="GOOGLE_API_KEY or OPENAI_API_KEY not set; skipping live coach integration test",
)
@pytest.mark.asyncio
async def test_coach_advice_smoke_streaming():
    # Print test configuration
    print(f"\n{'='*60}")
    print(f"Running STREAMING test with:")
    print(f"  Coach Provider: {settings.coach_provider}")
    print(f"  Coach Model: {settings.coach_model}")
    print(f"{'='*60}\n")

    audio_file = "input_audio.wav"
    language = "english"
    audio_bytes = (FIXTURE_DIR / audio_file).read_bytes()
    mime_type = "audio/wav"  # Known from fixture file extension
    game_stats_json_text = (FIXTURE_DIR / "allgamedata.json").read_text()
    game_stats_dict = json.loads(game_stats_json_text)

    print(f"Audio input - MIME type: {mime_type}, Size: {len(audio_bytes)} bytes")

    # STT transcription
    stt_start = time.perf_counter()
    user_question = transcribe_audio(
        audio_bytes=audio_bytes,
        language=language,
    )
    stt_duration = time.perf_counter() - stt_start
    print(f"Transcribed question: {user_question}")

    # Step 1: Get or create session and get coaching advice
    coach_start = time.perf_counter()
    session = session_manager.get_or_create_session(
        game_stats_dict=game_stats_dict,
    )
    # Agent has champion guide in system prompt
    # Game stats and language instruction are passed fresh with each request in the user message
    # Message history is managed automatically by get_coach_advice
    response = get_coach_advice(
        session=session,
        user_question=user_question,
        game_stats_json=game_stats_json_text,
        language=language,
    )
    coach_duration = time.perf_counter() - coach_start

    print(f"coach_advice response: {response}")

    # Step 2: Convert response to speech with STREAMING TTS
    tts_start = time.perf_counter()

    # Use advice directly for TTS (same as in route)
    tts_text = response

    # Collect audio chunks with streaming and log timing
    chunks = []
    chunk_count = 0
    first_chunk_time = None  # Ensure variable is always defined before use

    print(f"\n🎵 Starting TTS streaming...")

    async for chunk in text_to_speech_stream(tts_text):
        chunk_arrival_time = time.perf_counter()

        if first_chunk_time is None:
            first_chunk_time = chunk_arrival_time

        chunks.append(chunk)
        chunk_count += 1

    # Reassemble audio
    audio_response = b''.join(chunks)

    print(f"\n{'='*60}")
    print(f"Total duration with streaming: {coach_duration + stt_duration + (first_chunk_time - tts_start):.2f}s")
    print(f"  Coach: {coach_duration:.2f}s")
    print(f"  TTS (streaming): {first_chunk_time - tts_start:.2f}s")
    print(f"  STT: {stt_duration:.2f}s")
    print(f"Provider used: {settings.coach_provider} ({settings.coach_model})")
    print(f"{'='*60}\n")

    # Assertions
    assert isinstance(response, str)
    assert response
    assert audio_response
    assert len(audio_response) > 0
    assert chunk_count > 0, "Should receive at least one chunk"

    # Verify it's a valid WAV file
    assert audio_response[:4] == b'RIFF', "Audio should be a valid WAV file"
    assert audio_response[8:12] == b'WAVE', "Audio should be a valid WAV file"

    print("✓ Streaming smoke test passed: Full flow works with streaming TTS")


@pytest.mark.skipif(
    not os.getenv("GOOGLE_API_KEY") or not os.getenv("OPENAI_API_KEY"),
    reason="GOOGLE_API_KEY or OPENAI_API_KEY not set; skipping live coach integration test",
)
@pytest.mark.parametrize("audio_file, language", [("input_audio.wav", "english")])
@pytest.mark.asyncio
async def test_coach_advice_with_build_tool_call(audio_file, language):
    # Print test configuration
    print(f"\n{'='*60}")
    print(f"Running BUILD TOOL CALL test with:")
    print(f"  Coach Provider: {settings.coach_provider}")
    print(f"  Coach Model: {settings.coach_model}")
    print(f"{'='*60}\n")

    # Load test fixtures from build_tool_test directory
    build_test_dir = FIXTURE_DIR / "build_tool_test"
    audio_bytes = (build_test_dir / audio_file).read_bytes()
    mime_type = "audio/wav"  # Known from fixture file extension
    game_stats_json_text = (build_test_dir / "allgamedata.json").read_text()
    game_stats_dict = json.loads(game_stats_json_text)

    print(f"Audio input - MIME type: {mime_type}, Size: {len(audio_bytes)} bytes")

    # STT transcription
    stt_start = time.perf_counter()
    user_question = transcribe_audio(
        audio_bytes=audio_bytes,
        language=language,
    )
    stt_duration = time.perf_counter() - stt_start
    print(f"Transcribed question: {user_question}")

    # Step 1: Get or create session and get coaching advice
    coach_start = time.perf_counter()
    session = session_manager.get_or_create_session(
        game_stats_dict=game_stats_dict,
    )
    # Agent has champion guide in system prompt
    # Game stats and language instruction are passed fresh with each request in the user message
    # Message history is managed automatically by get_coach_advice
    response = get_coach_advice(
        session=session,
        user_question=user_question,
        game_stats_json=game_stats_json_text,
        language=language,
    )
    coach_duration = time.perf_counter() - coach_start

    print(f"coach_advice response: {response}")

    # Step 2: Convert response to speech with STREAMING TTS
    tts_start = time.perf_counter()

    # Use advice directly for TTS (same as in route)
    tts_text = response

    # Collect audio chunks with streaming and log timing
    chunks = []
    chunk_count = 0
    first_chunk_time = None  # Ensure variable is always defined before use

    print(f"\n🎵 Starting TTS streaming...")

    async for chunk in text_to_speech_stream(tts_text):
        chunk_arrival_time = time.perf_counter()

        if first_chunk_time is None:
            first_chunk_time = chunk_arrival_time

        chunks.append(chunk)
        chunk_count += 1

    # Reassemble audio
    audio_response = b''.join(chunks)

    print(f"\n{'=' * 60}")
    print(f"Total duration with streaming: {coach_duration + stt_duration + (first_chunk_time - tts_start):.2f}s")
    print(f"  Coach: {coach_duration:.2f}s")
    print(f"  TTS (streaming): {first_chunk_time - tts_start:.2f}s")
    print(f"  STT: {stt_duration:.2f}s")
    print(f"Provider used: {settings.coach_provider} ({settings.coach_model})")
    print(f"{'=' * 60}\n")

    # Assertions
    assert isinstance(response, str)
    assert response
    assert audio_response
    assert len(audio_response) > 0
    assert chunk_count > 0, "Should receive at least one chunk"

    # Verify it's a valid WAV file
    assert audio_response[:4] == b'RIFF', "Audio should be a valid WAV file"
    assert audio_response[8:12] == b'WAVE', "Audio should be a valid WAV file"

    print("✓ Build tool call test passed: Full flow works with build-related query")


@pytest.mark.skipif(
    not os.getenv("GOOGLE_API_KEY") or not os.getenv("OPENAI_API_KEY"),
    reason="GOOGLE_API_KEY or OPENAI_API_KEY not set; skipping live coach integration test",
)
@pytest.mark.parametrize("audio_file, language", [("input_audio_persian.wav", "persian")])
@pytest.mark.asyncio
async def test_knowledge_mode_out_of_game(audio_file, language):
    """
    Test knowledge mode when user is not in a game (no game_stats).

    This tests the out-of-game knowledge assistant that answers
    general League of Legends questions without live game context.
    """
    # Print test configuration
    print(f"\n{'='*60}")
    print(f"Running KNOWLEDGE MODE (out-of-game) test with:")
    print(f"  Coach Provider: {settings.coach_provider}")
    print(f"  Coach Model: {settings.coach_model}")
    print(f"  Language: {language}")
    print(f"{'='*60}\n")

    # Use existing audio fixture for the question
    # The audio content doesn't matter much - knowledge agent will transcribe and answer
    audio_bytes = (FIXTURE_DIR / "knowledge_test" / audio_file).read_bytes()
    mime_type = "audio/wav"
    user_id = "test_user_123"  # Simulated user ID

    print(f"Audio input - MIME type: {mime_type}, Size: {len(audio_bytes)} bytes")
    print(f"User ID: {user_id}")
    print(f"Mode: Knowledge (no game stats)")

    # STT transcription
    stt_start = time.perf_counter()
    language_code = get_language_code(language)
    user_question = transcribe_audio(
        audio_bytes=audio_bytes,
        language=language,
    )
    stt_duration = time.perf_counter() - stt_start
    print(f"Transcribed question: {user_question}")

    # Step 1: Get or create knowledge session and get advice
    knowledge_start = time.perf_counter()
    session = session_manager.get_or_create_knowledge_session(
        user_id=user_id,
    )

    print(f"Session created: {session}")

    response = get_knowledge_advice(
        session=session,
        user_question=user_question,
        language=language,
    )
    knowledge_duration = time.perf_counter() - knowledge_start

    print(f"knowledge_advice response: {response}")

    # Step 2: Convert response to speech with STREAMING TTS
    tts_start = time.perf_counter()

    # Use advice directly for TTS
    tts_text = response

    # Collect audio chunks with streaming and log timing
    chunks = []
    chunk_count = 0
    first_chunk_time = None  # Ensure variable is always defined before use

    print(f"\n🎵 Starting TTS streaming...")

    async for chunk in text_to_speech_stream(tts_text):
        chunk_arrival_time = time.perf_counter()

        if first_chunk_time is None:
            first_chunk_time = chunk_arrival_time

        chunks.append(chunk)
        chunk_count += 1

    # Reassemble audio
    audio_response = b''.join(chunks)

    print(f"\n{'='*60}")
    print(f"Total duration with streaming: {knowledge_duration + stt_duration + (first_chunk_time - tts_start):.2f}s")
    print(f"  Knowledge Agent: {knowledge_duration:.2f}s")
    print(f"  TTS (streaming): {first_chunk_time - tts_start:.2f}s")
    print(f"  STT: {stt_duration:.2f}s")
    print(f"Provider used: {settings.coach_provider} ({settings.coach_model})")
    print(f"{'='*60}\n")

    # Assertions
    assert isinstance(response, str)
    assert user_question, "Should have transcribed the user's question"
    assert response, "Should have provided advice"
    assert audio_response
    assert len(audio_response) > 0
    assert chunk_count > 0, "Should receive at least one chunk"

    # Verify it's a valid WAV file
    assert audio_response[:4] == b'RIFF', "Audio should be a valid WAV file"
    assert audio_response[8:12] == b'WAVE', "Audio should be a valid WAV file"

    # Test session reuse - same user should get the same session
    session2 = session_manager.get_or_create_knowledge_session(
        user_id=user_id,
    )
    assert session is session2, "Should reuse existing knowledge session for same user"

    print("✓ Knowledge mode test passed: Out-of-game flow works correctly")
