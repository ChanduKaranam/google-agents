"""Cloud Run entrypoint. Serves the agent over A2A for Gemini Enterprise.

Two things here are load-bearing and look redundant:

`to_a2a` is passed an explicit runner. Letting it build its own would silently
swap persistent sessions and Memory Bank for in-memory stand-ins -- see
`runtime.py` for why that loses student data.

The agent card is built here rather than handed over as a file path. When
`to_a2a` receives a card it uses it verbatim and never fills anything in
(`agent_to_a2a.py:203-205`) -- its `host`/`port`/`protocol` arguments only feed
the builder that runs when no card is supplied. So the `url` Gemini Enterprise
calls back on has to be injected before the card is passed, or the agent
advertises no endpoint at all.
"""

import json
import os
import pathlib

import uvicorn
from a2a.types import AgentCard
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .runtime import build_runner

PORT = int(os.environ.get("PORT", 8080))
# Cloud Run terminates TLS and routes by hostname, so the card must advertise
# the public https origin -- not the container's internal http listener.
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost:8080")
PROTOCOL = os.environ.get("PUBLIC_PROTOCOL", "https")

CARD_PATH = pathlib.Path(__file__).parent / "agent_card.json"


def load_agent_card(public_host: str, protocol: str) -> AgentCard:
    """Load the static card and resolve its url for this deployment."""
    raw = json.loads(CARD_PATH.read_text())
    raw["url"] = f"{protocol}://{public_host}/"
    return AgentCard(**raw)


app = to_a2a(
    root_agent,
    agent_card=load_agent_card(PUBLIC_HOST, PROTOCOL),
    runner=build_runner(),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
