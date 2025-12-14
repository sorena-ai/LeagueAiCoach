# Sensii API - AI-Powered League of Legends Coach

## 🎥 Demo

[![Watch Sensii in Action](https://img.youtube.com/vi/jBRvdGTnado/maxresdefault.jpg)](https://youtu.be/jBRvdGTnado)

**[Watch the full demo on YouTube](https://youtu.be/jBRvdGTnado)**

---

## About

FastAPI service that ingests an in-game screenshot plus a voice question, runs the coach model, and replies with audio advice. Uses LangChain wrappers with **flexible coach provider** (Gemini or Grok, configurable via `COACH_PROVIDER` and `COACH_MODEL` env vars) for analysis, OpenAI Whisper for transcription, and OpenAI TTS for speech generation.

**Visit us at [sensii.gg](https://sensii.gg)**

## Project layout
- `app/routes`: FastAPI endpoints (`assistant.py`)
- `app/assistant`: Coach logic, prompts, draft agent, TTS
- `app/lib`: Shared LangChain clients (`langchain.py`)
- `app/config.py`: Settings loaded from `.env`
- `data/`: Champion XML inputs

## Setup
```bash
cd sensii
cp .env.example .env   # fill in API keys
```

### Required Environment Variables
- `OPENAI_API_KEY` - For Whisper transcription + TTS
- `COACH_PROVIDER` - Choose your coach provider: `gemini` (default) or `grok`
- `COACH_MODEL` - Model name for the selected provider (e.g., `gemini-flash-lite-latest` or `grok-3`)
- `GOOGLE_API_KEY` - Required if `COACH_PROVIDER=gemini`
- `GROK_API_KEY` - Required if `COACH_PROVIDER=grok`

### Switching Coach Providers

**To use Gemini (default):**
```bash
COACH_PROVIDER=gemini
COACH_MODEL=gemini-flash-lite-latest
```

**To use Grok:**
```bash
COACH_PROVIDER=grok
COACH_MODEL=grok-3
```

Just change `COACH_PROVIDER` and `COACH_MODEL` in `.env` - no code changes needed!

## Run with Docker Compose
```bash
docker-compose up -d --build
# API at http://localhost:8000
```

## Tests
Run the test suite in a clean container build:
```bash
docker-compose run --rm --build sensei-api test
```

## Local development (without Docker)
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

## Useful endpoints
- Health: `GET /api/v1/health`
- Ready: `GET /api/v1/ready`
- Coach: `POST /api/v1/assistant/coach` (audio file, image file, game_stats JSON, optional language)

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

Copyright 2025 Sorena AI

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
