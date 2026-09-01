"""Runtime configuration, read from the environment (see .env.example)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


# Conversation model: fast, cheap, many turns per encounter.
MODEL = os.getenv("CS_MODEL", "gemini-2.5-flash")
# Evaluation model: one call per encounter, worth the extra reasoning.
EVAL_MODEL = os.getenv("CS_EVAL_MODEL", "gemini-2.5-pro")

# Practice Mode (research doc, section 13): the diagnosis is never volunteered.
PRACTICE_MODE = _flag("CS_PRACTICE_MODE", True)

MAX_HINT_LEVEL = 3
