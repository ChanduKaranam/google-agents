"""The Runner that keeps sessions and memory alive off Agent Engine.

`to_a2a()` builds its own runner from `InMemorySessionService` and
`InMemoryMemoryService`. On Cloud Run — several instances, recycled freely —
that means a professor's state can vanish between two turns and nothing is ever
written to Memory Bank. Neither failure raises, so the agent looks healthy and
forgets people.

The reasoning engine is not retired by this migration: it becomes the session
and memory store. That is also why `app_name` must be the engine id.
"""

import os

from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.memory import VertexAiMemoryBankService
from google.adk.runners import Runner
from google.adk.sessions import VertexAiSessionService

from .agent import root_agent

REQUIRED_ENV = ('GOOGLE_CLOUD_PROJECT', 'GOOGLE_CLOUD_LOCATION', 'AGENT_ENGINE_ID')


def build_runner() -> Runner:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            'Refusing to start without persistent session and memory storage.'
            f' Missing environment: {", ".join(missing)}.'
        )

    project = os.environ['GOOGLE_CLOUD_PROJECT']
    location = os.environ['GOOGLE_CLOUD_LOCATION']
    engine_id = os.environ['AGENT_ENGINE_ID']
    bucket = os.environ.get('GOOGLE_CLOUD_STORAGE_BUCKET')

    return Runner(
        # `app_name` is the Memory Bank retrieval SCOPE, not a label. Agent
        # Engine defaulted it to the engine id, so every memory already written
        # lives under that numeric id. Any other value queries an empty scope
        # and silently returns nothing.
        app_name=engine_id,
        agent=root_agent,
        session_service=VertexAiSessionService(
            project=project, location=location, agent_engine_id=engine_id
        ),
        memory_service=VertexAiMemoryBankService(
            project=project, location=location, agent_engine_id=engine_id
        ),
        artifact_service=(
            GcsArtifactService(bucket_name=bucket)
            if bucket
            else InMemoryArtifactService()
        ),
        credential_service=InMemoryCredentialService(),
    )
