"""Central Gemini model factory (blueprint §10: runtime model = Gemini).

The API key lives only in `.env` (gitignored; `.env.example` documents it) and is
read from the environment — never hardcoded (§8 secrets hygiene). Constructing a
model does not require the key; the key is needed only when an agent actually runs,
so graphs import and construct without it.
"""

from __future__ import annotations

import os

from google.adk.models import Gemini
from google.genai import types

# Load .env if present so GOOGLE_API_KEY / GOOGLE_GENAI_USE_VERTEXAI are available
# for local runs. Best-effort: absence of python-dotenv or the file is fine.
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - optional convenience only
    pass

DEFAULT_MODEL = os.environ.get("BY_HEART_MODEL", "gemini-flash-latest")


def gemini(model: str = DEFAULT_MODEL) -> Gemini:
    """A Gemini model wrapper with a small retry budget."""
    return Gemini(model=model, retry_options=types.HttpRetryOptions(attempts=3))
