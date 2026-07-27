"""Cloud Run entrypoint. Serves the agent over A2A for Gemini Enterprise.

`to_a2a` is passed an explicit runner. Letting it build its own would silently
swap persistent sessions and Memory Bank for in-memory stand-ins -- see
`runtime.py` for why that loses student data.
"""

import os

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .card import load_agent_card
from .runtime import build_runner

PORT = int(os.environ.get("PORT", 8080))
# Cloud Run terminates TLS and routes by hostname, so the card must advertise
# the public https origin -- not the container's internal http listener.
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost:8080")
PROTOCOL = os.environ.get("PUBLIC_PROTOCOL", "https")

app = to_a2a(
    root_agent,
    agent_card=load_agent_card(PUBLIC_HOST, PROTOCOL),
    runner=build_runner(),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
