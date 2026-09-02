"""Identity guard and best-effort persistence to Memory Bank.

Both behaviours are proven in production on our other Gemini Enterprise agents,
for the same reasons:

* Gemini Enterprise passes the signed-in user's email as ``user_id``. When
  that field is absent the Agent Engine template silently falls back to a
  single shared ``default-user-id`` — which would collapse every user's
  uploaded images, session state and saved artifacts into one bucket. A medical
  image or health question is sensitive personal data, so a silent cross-user
  leak is exactly what we must not allow. Refusing the turn turns a quiet leak
  into a loud, safe failure.

* Nothing writes to Memory Bank on our behalf. A user who returns to continue a
  case tomorrow only sees earlier context if we persist the session after each
  turn — and a memory write must never be allowed to break the answer the user
  actually came for.
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
                        " identity, so I have no safe way to keep your medical"
                        " images and questions separate from anyone else's."
                        " Please open me from Gemini Enterprise while signed in."
                    )
                )
            ],
        )
    return None


async def remember_session(callback_context: CallbackContext) -> None:
    """Persist this conversation to Memory Bank so follow-ups survive."""
    try:
        await callback_context.add_session_to_memory()
    except Exception:  # noqa: BLE001 - memory is best-effort, the answer is not
        logger.warning("Could not persist session to memory", exc_info=True)
    return None
