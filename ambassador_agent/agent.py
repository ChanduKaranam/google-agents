import logging

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from .a2ui import build_greeting, to_genai_parts

logger = logging.getLogger(__name__)

INSTRUCTION = """You are the Campus Ambassador agent for Sethu at SVEC Tirupati.

You work with ONE ambassador: Sneha Reddy, who looks after EEE Sem 3, Sec B.
You only ever know her section. There is no search, no other cohort.

Answer briefly and plainly. Never invent an activation count, a rank, or a
student. Never claim to have sent a message: you draft, she sends from her own
WhatsApp."""

DEFAULT_CHIPS = [
    "Who should I message?",
    "Where do I stand?",
    "How is my rank calculated?",
    "What unlocks next?",
]


def render_surface(callback_context: CallbackContext) -> types.Content | None:
    """Draw a card alongside the model's own reply.

    Returning Content from an after-agent callback ADDS an event, so the text
    answer survives next to the widget. A renderer bug must never cost the user
    their answer, so the whole thing is guarded.
    """
    try:
        messages = build_greeting(
            "Ask me anything about your section, or pick a suggestion below.",
            DEFAULT_CHIPS,
        )
        return types.Content(role="model", parts=to_genai_parts(messages))
    except Exception:  # noqa: BLE001 - a broken widget must not break the answer
        logger.warning("Could not render A2UI surface", exc_info=True)
        return None


root_agent = Agent(
    model="gemini-2.5-flash",
    name="ambassador_agent",
    description="Campus Ambassador cockpit for one section.",
    instruction=INSTRUCTION,
    after_agent_callback=render_surface,
)
