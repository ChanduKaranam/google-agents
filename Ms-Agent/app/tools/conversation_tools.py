"""Conversation tools — deterministic context resolution for short replies."""

from __future__ import annotations

from google.adk.tools import ToolContext

from app.services.context_service import resolve_reference


def interpret_reply(
    reply: str, options: list[dict], tool_context: ToolContext
) -> dict:
    """Resolve a short contextual reply against the values in play.

    Use when the student answers with a reference rather than a value:
    "the current one", "use the new one", "the second option", "same as
    above", "yes", "I don't have it". Pass the candidates the reply could
    refer to, MOST RECENT / CURRENT FIRST.

    Args:
        reply: The student's reply, verbatim.
        options: Ordered candidates, e.g. `[{"label": "current
            conversation", "value": "CSE"}, {"label": "resume", "value":
            "Computer Science and Systems Engineering"}]`.

    Returns:
        `resolution`: selected (with the value), affirmed, negated,
        declined, or unresolved. Act on it directly — never re-ask the
        question the student just answered; an unresolved reply allows
        ONE concrete clarification.
    """
    return {"status": "success", **resolve_reference(reply, options)}
