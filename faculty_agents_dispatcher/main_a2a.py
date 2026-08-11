"""ASGI entrypoint: Champion Faculty served as an A2A agent.

    uvicorn faculty_agents_dispatcher.main_a2a:app --host 0.0.0.0 --port 8080

This exists because Gemini Enterprise renders A2UI only for an agent registered
as `a2aAgentDefinition`. The Agent Engine registration cannot draw cards
whatever the agent emits.

Three things `to_a2a()` would otherwise replace with silent stand-ins are put
back explicitly: the runner (persistent sessions and Memory Bank), the agent
card (whose URL must be the real public host), and the caller's identity.
"""

import logging

from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import (
    A2aAgentExecutorConfig,
    ExecuteInterceptor,
)
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from . import card, identity
from .agent import root_agent
from .runtime import build_runner

# Uvicorn leaves the root logger at WARNING, which drops every logger.info —
# including the one line saying whether an end-user token arrived. Without this
# the identity check below finds nothing and reads as "identity is broken".
logging.basicConfig(level=logging.INFO)

app = to_a2a(
    root_agent,
    agent_card=card.card_from_env(),
    runner=build_runner(),
    agent_executor_factory=lambda runner: A2aAgentExecutor(
        runner=runner,
        config=A2aAgentExecutorConfig(
            execute_interceptors=[
                ExecuteInterceptor(before_agent=identity.install())
            ]
        ),
    ),
)
