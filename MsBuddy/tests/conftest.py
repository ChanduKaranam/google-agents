# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Shared pytest configuration.

Fixes a scaffold gap: `tests/integration/test_agent.py` imports the agent
directly and never calls `load_dotenv()`, so the project `.env` was ignored
and google-genai fell back to API-key mode, failing with "No API key was
provided" even though Vertex AI was configured. `fast_api_app.py` loads it,
but a direct-import test never reaches that module.

Also provides `live_model` — integration tests that call a real model skip
cleanly when the environment is not configured for one, instead of failing
with an authentication error that looks like a code defect.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent

load_dotenv(PROJECT_ROOT / ".env")


def _model_backend_configured() -> bool:
    """True if either a Vertex AI project or an API key is available."""
    enterprise = os.getenv("GOOGLE_GENAI_USE_ENTERPRISE") or os.getenv(
        "GOOGLE_GENAI_USE_VERTEXAI"
    )
    if enterprise and enterprise.lower() in ("1", "true", "yes"):
        return bool(os.getenv("GOOGLE_CLOUD_PROJECT"))
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY"))


@pytest.fixture(scope="session")
def live_model() -> None:
    """Skip a test unless a model backend is actually configured."""
    if not _model_backend_configured():
        pytest.skip(
            "No model backend configured. Set GOOGLE_CLOUD_PROJECT with "
            "GOOGLE_GENAI_USE_ENTERPRISE=true, or set GEMINI_API_KEY."
        )
