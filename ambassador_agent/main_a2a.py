import logging
import os

from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import (A2aAgentExecutorConfig,
                                            ExecuteInterceptor)
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from . import identity, sethu
from .agent import root_agent
from .card import load_agent_card, require_public_host
from .runtime import build_runner

# Uvicorn leaves the root logger at WARNING, so every logger.info in this
# package was silently dropped -- including the one line that says whether
# Gemini Enterprise forwarded an end-user token, which is the only way to
# verify the OAuth wiring from outside. Without this the runbook's log check
# finds nothing and reads as "identity is broken".
logging.basicConfig(level=logging.INFO)
logging.getLogger("ambassador_agent").setLevel(logging.INFO)

PUBLIC_HOST = require_public_host(
    os.environ.get("PUBLIC_HOST"), os.environ.get("K_SERVICE")
)
PROTOCOL = os.environ.get("PROTOCOL", "https")


def _executor(runner) -> A2aAgentExecutor:
    """Bind the caller's Google token to the turn before the agent runs.

    `to_a2a` builds its own executor with a default config, which drops the
    inbound headers -- so every request would look anonymous and the agent
    would serve one hardcoded ambassador to the whole college.
    """
    return A2aAgentExecutor(
        runner=runner,
        config=A2aAgentExecutorConfig(
            execute_interceptors=[
                ExecuteInterceptor(before_agent=identity.install(sethu))
            ]
        ),
    )


app = to_a2a(
    root_agent,
    agent_card=load_agent_card(PUBLIC_HOST, PROTOCOL),
    runner=build_runner(),
    agent_executor_factory=_executor,
)
