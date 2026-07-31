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

from .a2ui import build_a2ui_messages, to_genai_parts

logger = logging.getLogger(__name__)

# Agent Engine's silent fallback (`vertexai/agent_engines/templates/adk.py:102`).
# It is the SAME string for every caller, so accepting it puts every student's
# sessions, artifacts and memories in one shared bucket. That is the leak this
# guard exists to prevent, and it stays refused.
_DEFAULT_USER_ID = "default-user-id"

# ADK's A2A server synthesises this when no authenticated caller is present
# (`google/adk/a2a/converters/request_converter.py:66-77`).
#
# Measured against a live Gemini Enterprise call, 2026-07-28: GE forwards NO
# end-user identity to an A2A agent. Not an email header, not message metadata,
# not an authenticated principal -- the only credential on the request is
# `x-serverless-authorization`, the Discovery Engine service agent, which is
# identical for every student. So this sentinel is the only identity available.
#
# Accepting it is safe because `context_id` is a per-conversation UUID: it
# FRAGMENTS the scope into one private bucket per conversation rather than
# collapsing it into one shared bucket. The cost is memory, not privacy -- a
# returning student starts fresh, because their next conversation is a new id.
# Refusing it instead simply took the agent offline for everyone.
_A2A_CONVERSATION_PREFIX = "A2A_USER_"


def _is_real_user(user_id: str | None) -> bool:
    """True when this id isolates one student from another."""
    if not user_id or user_id == _DEFAULT_USER_ID:
        return False
    # A bare prefix carries no context id, so it scopes to nothing.
    if user_id == _A2A_CONVERSATION_PREFIX:
        return False
    return True


def require_real_user(callback_context: CallbackContext) -> types.Content | None:
    """Block the turn unless the caller's id isolates them from other students."""
    if _is_real_user(callback_context.user_id):
        return None
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

    return _render_a2ui(callback_context)


def _render_a2ui(callback_context: CallbackContext) -> types.Content | None:
    """Draw the tracked-application board, when there is one to draw.

    Returning None leaves the model's own answer untouched, which is the right
    outcome for every turn that has no structured state behind it -- most of
    them. A widget is an addition to the conversation, never a replacement for
    being able to answer.

    Like the memory write above, this must never cost the student their turn: a
    renderer bug is worth losing the widget over, not the reply.
    """
    try:
        messages = build_a2ui_messages(getattr(callback_context, "state", None))
        if not messages:
            return None
        return types.Content(role="model", parts=to_genai_parts(messages))
    except Exception:  # noqa: BLE001 - a broken widget must not break the answer
        logger.warning("Could not render A2UI surface", exc_info=True)
        return None
