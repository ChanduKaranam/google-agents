import logging

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from .a2ui import build_greeting, to_genai_parts
from .actions import (chips_for, chips_for_action, intent_for,
                      parse_user_action, route, route_question)
from .surfaces import chips_surface

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


def _incoming_text(callback_context: CallbackContext) -> str:
    """Join the user turn's text and inline-data parts into one string.

    The A2UI click payload arrives as `inline_data` (`part_converter.py`'s
    conversion of a DataPart to a tagged blob), not `part.text` — GE also sends
    a companion text part reading "User action triggered.", which is a
    transcript placeholder and never something to route on. Both joins guard
    against `content` being None: a turn with no content raises AttributeError
    on `.parts`, which the caller's try/except would otherwise swallow the
    consequences of, so the routing is skipped instead of silently misfiring.
    """
    content = callback_context.user_content
    raw = "".join(part.text or "" for part in (content.parts or [])) \
        if content else ""
    raw += "".join(
        (part.inline_data.data or b"").decode("utf-8", "replace")
        for part in (content.parts or []) if part.inline_data) \
        if content else ""
    return raw


def _with_chips(messages: list[dict], labels: list[str]) -> list[dict]:
    """Attach follow-up chips only to a turn that actually drew a card.

    Chips are a way onward FROM a surface. In the prototype they live in the
    chat chrome and there is exactly one row; here every turn's row persists in
    the transcript, so appending them to plain sentences too -- a send
    confirmation, "nobody left to chase" -- stacks a wall of identical buttons
    down the conversation. Reported from the live demo.
    """
    if not messages:
        return messages
    return messages + chips_surface(labels)


def handle_click(callback_context: CallbackContext) -> types.Content | None:
    """Short-circuit a button press: the router already knows the answer.

    Runs as a before-agent callback so a click skips the model entirely — a
    model asked to re-derive a routed answer will sometimes answer the
    question instead of performing the action. A routing bug must never cost
    the user their turn, so this returns None (falls through to the model) on
    any failure instead of raising or answering with an error.
    """
    try:
        incoming = _incoming_text(callback_context)
        action = parse_user_action(incoming)
        state = callback_context.state
        if action is None:
            # A typed question that matches a known intent is answered from the
            # router too, not by the model. Measured live: asked "who should I
            # message?", the model replied "Sneha Reddy, for EEE Sem 3, Sec B."
            # while the router says "6 students have ignored two campaigns — a
            # broadcast won't move them…" -- the prototype's own copy. The demo
            # is judged on that wording, so it must not vary turn to turn.
            intent = intent_for(incoming)
            if intent == "unknown":
                return None       # off-script: let the model answer freely
            reply, messages = route_question(state, incoming)
            messages = _with_chips(messages, chips_for(intent))
        else:
            reply, messages = route(state, action)
            messages = _with_chips(messages, chips_for_action(action))
        parts = []
        if reply:
            parts.append(types.Part(text=reply))
        parts.extend(to_genai_parts(messages))
        return types.Content(role="model", parts=parts)
    except Exception:  # noqa: BLE001 - never cost the user their turn
        logger.warning("Could not handle A2UI action", exc_info=True)
        return None


def render_surface(callback_context: CallbackContext) -> types.Content | None:
    """Welcome her once, then get out of the way.

    Only off-script turns reach here — `handle_click` (before-agent) already
    answered anything that matched an intent or carried a click, and
    short-circuited the run before the model.

    The welcome card is drawn on the FIRST such turn only. Repeating it after
    every off-script reply stacked an identical row of buttons down the
    transcript, which is what the chips looked like in the live demo: the
    prototype has one chip row in its chrome, not one per message.

    A renderer bug must never cost the user their answer, so this is guarded.
    """
    try:
        question = _incoming_text(callback_context)
        if intent_for(question) != "unknown":
            return None      # handle_click already answered this turn in full
        state = callback_context.state
        if state.get("greeted"):
            return None      # she has seen the options; the model's words stand
        state["greeted"] = True
        messages = build_greeting(
            "Ask me anything about your section, or pick a suggestion"
            " below.", DEFAULT_CHIPS,
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
    before_agent_callback=handle_click,
    after_agent_callback=render_surface,
)
