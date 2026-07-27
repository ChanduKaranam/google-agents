"""Cloud Run entrypoint. Serves the agent over A2A for Gemini Enterprise.

`to_a2a` is passed an explicit runner. Letting it build its own would silently
swap persistent sessions and Memory Bank for in-memory stand-ins -- see
`runtime.py` for why that loses student data.
"""

import os
import pathlib

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .runtime import build_runner

PORT = int(os.environ.get("PORT", 8080))
# Cloud Run terminates TLS and gives the public https URL; the agent card must
# advertise that URL, not the container's http listener.
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost")
PROTOCOL = os.environ.get("PUBLIC_PROTOCOL", "https")

AGENT_CARD = pathlib.Path(__file__).parent / "agent_card.json"

app = to_a2a(
    root_agent,
    host=PUBLIC_HOST,
    port=PORT,
    protocol=PROTOCOL,
    agent_card=str(AGENT_CARD),
    runner=build_runner(),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
