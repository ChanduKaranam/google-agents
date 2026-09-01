"""A2A server entry point — this is what Gemini Enterprise talks to.

Gemini Enterprise registers a custom agent one of two ways: an ADK agent hosted
on Agent Runtime (registered by its `reasoningEngines/...` resource path), or an
**A2A agent** identified by an agent card. A raw `adk api_server` endpoint is
neither, so this module wraps the root agent with ADK's `to_a2a()`, which serves
the JSON-RPC endpoint and publishes the agent card at
`/.well-known/agent-card.json`.

Run locally:
    uvicorn clinical_simulator.a2a_app:app --host 0.0.0.0 --port 8080

The advertised URL must be the public service URL, which on Cloud Run is only
known after the first deploy, so it comes from A2A_PUBLIC_URL. `deploy.sh`
sets it automatically on a second pass.
"""

from __future__ import annotations

import json
import os
import tempfile
from urllib.parse import urlparse

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .agent_card import build as build_card

PUBLIC_URL = os.getenv(
    "A2A_PUBLIC_URL", f"http://localhost:{os.getenv('PORT', '8080')}"
).rstrip("/")

_parsed = urlparse(PUBLIC_URL)

# Serve the same curated card that `python -m clinical_simulator.agent_card`
# emits, so what Gemini Enterprise discovers matches what was registered.
# ADK reads a pre-built card from a file path.
_card_file = tempfile.NamedTemporaryFile(
    mode="w", suffix=".json", delete=False, encoding="utf-8"
)
json.dump(build_card(PUBLIC_URL, v1_shape=True), _card_file)
_card_file.close()

app = to_a2a(
    root_agent,
    host=_parsed.hostname or "localhost",
    port=_parsed.port or (443 if _parsed.scheme == "https" else 8080),
    protocol=_parsed.scheme or "http",
    agent_card=_card_file.name,
)
