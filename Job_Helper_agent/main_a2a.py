"""Cloud Run entrypoint. Serves the agent over A2A for Gemini Enterprise.

`to_a2a` is passed an explicit runner. Letting it build its own would silently
swap persistent sessions and Memory Bank for in-memory stand-ins -- see
`runtime.py` for why that loses student data.

It is also passed an explicit agent executor, so the request converter can lift
the end user's identity out of the request headers -- see `identity.py` for why
the stock converter would otherwise get every turn refused.
"""

import os

import uvicorn
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .card import load_agent_card, require_public_host
from .identity import build_request_converter
from .runtime import build_runner

PORT = int(os.environ.get("PORT", 8080))
# Cloud Run terminates TLS and routes by hostname, so the card must advertise
# the public https origin -- not the container's internal http listener.
PUBLIC_HOST = require_public_host(
    os.environ.get("PUBLIC_HOST"), os.environ.get("K_SERVICE")
)
PROTOCOL = os.environ.get("PUBLIC_PROTOCOL", "https")

app = to_a2a(
    root_agent,
    agent_card=load_agent_card(PUBLIC_HOST, PROTOCOL),
    runner=build_runner(),
    agent_executor_factory=lambda runner: A2aAgentExecutor(
        runner=runner,
        config=A2aAgentExecutorConfig(request_converter=build_request_converter()),
    ),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
