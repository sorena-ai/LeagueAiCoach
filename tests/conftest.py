import os

# `app.config.Settings` requires these at import time; tests don't need real keys.
os.environ.setdefault("OPENAI_API_KEY", "test")
os.environ.setdefault("GOOGLE_API_KEY", "test")
os.environ.setdefault("GROK_API_KEY", "test")
