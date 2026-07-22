"""Identity guard.

Gemini Enterprise sends the end user's email as `user_id` (verified 2026-07-22
against the live app). If that field is ever absent, the Agent Engine template
silently falls back to `default-user-id` (`vertexai/agent_engines/templates/
adk.py:102`), and every student's sessions, artifacts and Memory Bank scope
collapse into one shared bucket — no error, no warning, just one student
reading another's applications.

Refusing the turn converts that silent data leak into a loud failure.
"""

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

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
