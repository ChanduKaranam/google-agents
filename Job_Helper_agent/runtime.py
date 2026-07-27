"""The runner that keeps a student's data alive across turns and visits.

`to_a2a()` will happily build its own runner, but that default uses
`InMemorySessionService` and `InMemoryMemoryService`
(`google/adk/a2a/utils/agent_to_a2a.py:157-165`). On Cloud Run, which runs
several instances and recycles them freely, that means a student's tracked
applications can vanish between two turns of one conversation, and nothing is
ever written to Memory Bank. Neither failure raises -- the board just comes
back empty.

Sessions and memory stay backed by the existing Agent Engine instance. Only
request serving moves to Cloud Run.
"""

import os

from google.adk.artifacts.gcs_artifact_service import GcsArtifactService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.vertex_ai_memory_bank_service import VertexAiMemoryBankService
from google.adk.runners import Runner
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

from .agent import root_agent

REQUIRED_ENV = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "AGENT_ENGINE_ID")

APP_NAME = "job_helper_agent"


def _require_env() -> tuple[str, str, str]:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Refusing to start without persistent session and memory storage."
            f" Missing environment: {', '.join(missing)}."
        )
    return tuple(os.environ[name] for name in REQUIRED_ENV)


def build_runner() -> Runner:
    """Build a Runner whose state survives an instance restart."""
    project, location, agent_engine_id = _require_env()

    # Artifacts hold uploaded resumes. A bucket is optional -- without one the
    # agent still works within a single turn, so this degrades rather than
    # blocks. GOOGLE_CLOUD_STORAGE_BUCKET turns on cross-turn resume storage.
    bucket = os.environ.get("GOOGLE_CLOUD_STORAGE_BUCKET")
    artifact_service = (
        GcsArtifactService(bucket_name=bucket) if bucket else InMemoryArtifactService()
    )

    return Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=VertexAiSessionService(
            project=project, location=location, agent_engine_id=agent_engine_id
        ),
        memory_service=VertexAiMemoryBankService(
            project=project, location=location, agent_engine_id=agent_engine_id
        ),
        artifact_service=artifact_service,
    )
