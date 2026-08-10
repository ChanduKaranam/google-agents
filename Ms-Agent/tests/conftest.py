"""Shared test configuration: .env loading and the live-model gate."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _model_backend_configured() -> bool:
    enterprise = os.getenv("GOOGLE_GENAI_USE_ENTERPRISE") or os.getenv(
        "GOOGLE_GENAI_USE_VERTEXAI"
    )
    if enterprise and enterprise.lower() in ("1", "true", "yes"):
        return bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


@pytest.fixture(scope="session")
def live_model() -> None:
    """Skip cleanly when no model backend is configured."""
    if not _model_backend_configured():
        pytest.skip(
            "No model backend configured (set GOOGLE_CLOUD_PROJECT with "
            "GOOGLE_GENAI_USE_ENTERPRISE=true, or GEMINI_API_KEY)."
        )
