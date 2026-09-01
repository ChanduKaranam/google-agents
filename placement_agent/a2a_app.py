# -*- coding: utf-8 -*-
"""
placement_agent/a2a_app.py
A2A transport for the existing Placement Assistant.

Gemini Enterprise renders A2UI only for agents registered as A2A agents, and
Agent Engine does not speak A2A -- it serves the reasoningEngines API. So this
module publishes the SAME `root_agent` over the A2A protocol as an ASGI app
that can run on Cloud Run. It is a second front door, not a second agent:
`AGENT is placement_agent.agent.root_agent`, asserted in the test suite.

The existing Agent Engine deployment is untouched and keeps serving today's
traffic. If A2A registration fails, deleting this file is the whole rollback.

    uvicorn placement_agent.a2a_app:app --host 0.0.0.0 --port 8080

Configuration is by environment variable; every one of them is optional and
falls back to in-memory services so `adk web` and the tests keep working:

    A2A_BASE_URL           public https origin, e.g. https://x-uc.a.run.app
    GOOGLE_CLOUD_PROJECT   project for the managed session store
    GOOGLE_CLOUD_LOCATION  region, defaults to us-central1
    AGENT_ENGINE_ID        reasoning engine id whose session store to share
    ARTIFACT_BUCKET        GCS bucket for uploaded resumes
"""

import os

from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

from .agent import root_agent as AGENT

# The A2A JSON-RPC endpoint, relative to the public origin.
RPC_PATH = "/a2a"


def rpc_url(base_url: str) -> str:
    """The URL the agent card advertises.

    `to_a2a` composes `{protocol}://{host}:{port}/` unconditionally, so behind
    Cloud Run it would advertise `https://host:8080/` -- the container port,
    not the public one. The origin is passed in whole instead.
    """
    return base_url.rstrip("/") + RPC_PATH


def build_runner(
    project: str = "",
    location: str = "",
    agent_engine_id: str = "",
    artifact_bucket: str = "",
) -> Runner:
    """A runner with services that survive a container restart.

    `to_a2a`'s built-in runner uses InMemorySessionService and
    InMemoryArtifactService (agent_to_a2a.py:158-161). Those are fine for a
    local demo and wrong here: in-memory session state would put interview
    progress back into per-container memory, and an in-memory artifact service
    cannot serve a resume uploaded to a different instance.

    Pointing the session service at the existing AGENT_ENGINE_ID makes both
    front doors -- Agent Engine and this one -- read one managed session store.
    """
    project = project or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
    location = location or os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")
    agent_engine_id = agent_engine_id or os.environ.get("AGENT_ENGINE_ID", "")
    artifact_bucket = artifact_bucket or os.environ.get("ARTIFACT_BUCKET", "")

    if project and agent_engine_id:
        from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

        session_service = VertexAiSessionService(
            project=project, location=location, agent_engine_id=agent_engine_id
        )
    else:
        session_service = InMemorySessionService()

    if artifact_bucket:
        from google.adk.artifacts.gcs_artifact_service import GcsArtifactService

        artifact_service = GcsArtifactService(bucket_name=artifact_bucket)
    else:
        artifact_service = InMemoryArtifactService()

    return Runner(
        app_name=AGENT.name,
        agent=AGENT,
        session_service=session_service,
        artifact_service=artifact_service,
        memory_service=InMemoryMemoryService(),
        credential_service=InMemoryCredentialService(),
    )


async def build_agent_card(base_url: str):
    """The card GE reads at /.well-known/agent-card.json to register us.

    Streaming is turned on explicitly: AgentCardBuilder defaults it off, and
    without it a client waits for the whole turn before rendering anything --
    including any A2UI surface emitted mid-turn.
    """
    from a2a.types import AgentCapabilities
    from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder

    builder = AgentCardBuilder(
        agent=AGENT,
        rpc_url=rpc_url(base_url),
        capabilities=AgentCapabilities(streaming=True),
    )
    return await builder.build()


def card_streaming_enabled(card) -> bool:
    """a2a-sdk 0.3.x cards are pydantic, 1.x are protobuf; read either."""
    return bool(getattr(card.capabilities, "streaming", False))


def build_a2a_app(base_url: str = ""):
    """The ASGI app. Import-time cheap: no network until a request arrives."""
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    base_url = base_url or os.environ.get("A2A_BASE_URL", "http://localhost:8080")
    runner = build_runner()

    # `agent_card` is supplied so host/port never compose the advertised URL.
    import asyncio

    card = asyncio.run(build_agent_card(base_url))
    return to_a2a(AGENT, agent_card=card, runner=runner)


app = None  # built by __main__ / uvicorn factory; see run() below.


def run() -> None:
    import uvicorn

    uvicorn.run(
        build_a2a_app(),
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8080")),
    )


if __name__ == "__main__":
    run()
