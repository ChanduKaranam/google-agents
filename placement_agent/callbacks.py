"""Identity guard, and persistence of the conversation to Memory Bank.

Gemini Enterprise sends the end user's email as `user_id` (verified 2026-07-22
against the live app). If that field is ever absent, the Agent Engine template
silently falls back to `default-user-id` (`vertexai/agent_engines/templates/
adk.py:102`), and every student's sessions, artifacts and Memory Bank scope
collapse into one shared bucket — no error, no warning, just one student
reading another's applications.

Refusing the turn converts that silent data leak into a loud failure.
"""

import logging

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

logger = logging.getLogger(__name__)

_DEFAULT_USER_ID = "default-user-id"


def require_real_user(callback_context: CallbackContext) -> types.Content | None:
    """Block the turn unless the caller supplied a real user identity."""
    if callback_context.user_id == _DEFAULT_USER_ID:
        return types.Content(
            role="model",
            parts=[
                types.Part(
                    text=(
                        "I can't continue: this request arrived without a user"
                        " identity, so I have no safe way to keep your data"
                        " separate from anyone else's. Please open me from"
                        " Gemini Enterprise while signed in."
                    )
                )
            ],
        )
    return None


async def remember_session(callback_context: CallbackContext) -> None:
    """Persist this conversation to Memory Bank so it survives the session.

    Nothing in the production path does this for us: Gemini Enterprise calls
    the agent and walks away, and session state dies with the session. Without
    this, a student's application history is gone the moment they close the
    chat. `Context.add_session_to_memory` docstring names an after-agent
    callback as the intended place for it.

    Never let a memory failure break the student's turn -- they came here for
    an answer, and losing it because a write failed is a worse outcome than
    losing the memory.
    """
    try:
        await callback_context.add_session_to_memory()
    except Exception:  # noqa: BLE001 - memory is best-effort, the answer is not
        logger.warning("Could not persist session to memory", exc_info=True)
    return None
