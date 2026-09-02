# -*- coding: utf-8 -*-
"""
placement_agent/a2ui/emit.py
Get an A2UI surface to the client without routing it through the model.

The obvious approach -- return the block from a tool and instruct the model to
reproduce it -- asks an LLM to copy ~900 characters of JSON byte for byte. One
altered character, one code fence, one pretty-print and the renderer finds
nothing. Worse, it fails *silently*: the client scans for the tags, doesn't
find them, and shows the raw text instead.

So the tool queues the block in session state and an `after_agent_callback`
emits it as its own event. Returning Content from that callback appends an
extra event after the agent's output (base_agent.py:560-572) -- the model's
prose and the surface both arrive, and the JSON never passes through a token
sampler.

The key is `temp:`-prefixed so it is never persisted: ADK drops temp state at
the session boundary, which is what stops a stored payload from repainting the
card when a session is resumed.
"""

from typing import Optional

from google.genai import types

# temp: -- render payload, deliberately not durable.
A2UI_QUEUE_KEY = "temp:a2ui_block"


def queue_surface(tool_context, block: str) -> None:
    """Hand a rendered block to the callback that will emit it."""
    tool_context.state[A2UI_QUEUE_KEY] = block


def emit_queued_a2ui(callback_context) -> Optional[types.Content]:
    """after_agent_callback: emit a queued surface, at most once.

    Returns None when nothing is queued -- this runs after every turn, and
    returning Content unconditionally would emit an empty event each time.
    """
    block = callback_context.state.get(A2UI_QUEUE_KEY)
    if not block:
        return None

    # Drain, or the card repaints on every subsequent reply. ADK's State has
    # no __delitem__, so empty it rather than removing the key.
    callback_context.state[A2UI_QUEUE_KEY] = ""
    return types.Content(role="model", parts=[types.Part(text=block)])
