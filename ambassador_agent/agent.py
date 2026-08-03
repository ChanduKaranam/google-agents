import logging

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from . import data, sethu
from .a2ui import build_greeting, button, row, text, to_genai_parts
from .actions import (DEFAULT_CHIPS, chips_for, chips_for_action, intent_for,
                      parse_user_action, route, route_question)
from .surfaces import (chips_surface, cohort_summary, leaderboard, rewards,
                       roster, straggler_list)
from .tools import ALL_TOOLS, UNAVAILABLE

logger = logging.getLogger(__name__)

INSTRUCTION = """You are the Campus Ambassador agent for Sethu.

You work with ONE ambassador, and Sethu's token tells you which — you never
choose. You only ever know that person's own section: there is no search, no
other cohort, and no way to look anyone else up.

Never state the ambassador's name, section, or any number from memory. Every
one of those comes from a tool result, because they are read live from Sethu
and change between turns.

For anything about her section, CALL A TOOL. The tools are how the cards get
drawn — answering from memory leaves her with prose and no card:

- who to message, nudge, chase, follow up, who is stalling  -> show_stragglers
- how far along, how many left, pace, her numbers           -> show_progress
- rank, standing, who is ahead, how ranking works           -> show_leaderboard
- rewards, badges, certificate, what unlocks next           -> show_rewards
- the roster, the class list, who has activated             -> show_roster
- only if she explicitly asks to simulate or jump a state   -> simulate_phase

She will phrase these any way she likes. "Is there anyone I should message?",
"who's falling behind?" and "anyone ignoring me?" all mean show_stragglers.

Every tool returns a `say` field. Open your reply with that sentence, close to
verbatim — it carries the numbers and the wording the product is built on.
Add at most one short sentence of your own.

Never invent an activation count, a rank, or a student. Never claim to have
sent a message: you draft, she sends from her own WhatsApp."""

# Which builder draws each surface a tool can pick.
_SURFACE_BUILDERS = {
    "stragglers": straggler_list,
    "cohort": cohort_summary,
    "leaderboard": leaderboard,
    "rewards": rewards,
    "roster": roster,
}

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
    """Attach follow-up chips to EVERY agent turn, card or not.

    The prototype keeps one chip row in its chrome, always visible. Gemini
    Enterprise gives an agent no chrome, so the only way to keep options in
    front of her is to put a row in each turn.

    They must ride INSIDE the turn's card. Measured in GE 2026-08-03: a turn
    carrying two surfaces renders only the first, so a chip row sent as its own
    surface never appeared -- reported twice as "I don't see the 4 suggestions
    after every message". With no card to attach to (a send confirmation), a
    standalone chip surface is correct, because then it is the first one.
    """
    if not messages:
        return chips_surface(labels)

    update = next((m["surfaceUpdate"] for m in messages if "surfaceUpdate" in m), None)
    root = next((m["beginRendering"]["root"] for m in messages
                 if "beginRendering" in m), None)
    if update is None or root is None:
        return messages + chips_surface(labels)

    prefix = update["surfaceId"]
    components = update["components"]
    by_id = {c["id"]: c for c in components}

    # The root is a Card wrapping a Column, or a Column already. Chips hang off
    # the Column either way -- a Card takes a single child and cannot hold a
    # sibling.
    container = by_id.get(root)
    spec = next(iter(container["component"].values())) if container else None
    if spec and isinstance(spec.get("child"), str):
        container = by_id.get(spec["child"])
        spec = next(iter(container["component"].values())) if container else None
    children = (spec or {}).get("children", {}).get("explicitList")
    if children is None:
        return messages + chips_surface(labels)   # nothing to attach to

    chip_ids = []
    for index, label in enumerate(labels):
        label_id, button_id = f"{prefix}-chip{index}-label", f"{prefix}-chip{index}"
        components.append(text(label_id, label))
        components.append(button(button_id, label_id, "ask", {"question": label}))
        chip_ids.append(button_id)
    components.append(row(f"{prefix}-chiprow", chip_ids))
    children.append(f"{prefix}-chiprow")
    return messages


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
            # message?", the model answered with the ambassador's name alone,
            # while the router names the students who have gone quiet and draws
            # the card. The router's wording is deterministic; the model's is
            # not, and this reply is what the product is judged on.
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

        # The model reached a surface by calling a tool, so it understood a
        # phrasing the keyword list does not cover. Draw what it picked.
        picked = state.get("surface")
        if picked:
            state["surface"] = None
            builder = _SURFACE_BUILDERS.get(picked)
            if builder:
                messages = _with_chips(builder(state), chips_for(picked))
                return types.Content(
                    role="model", parts=to_genai_parts(messages))

        if state.get("greeted"):
            # Off-script turn later in the conversation: the model answered in
            # its own words, but she still gets the options back.
            return types.Content(
                role="model",
                parts=to_genai_parts(chips_surface(DEFAULT_CHIPS)))
        state["greeted"] = True
        # First turn: the prototype's opening, from live numbers, instead of a
        # generic welcome. It cannot fire before she speaks -- Gemini
        # Enterprise gives an agent no "conversation opened" event -- so this
        # rides on whatever she says first.
        messages = build_greeting(
            data.greeting_line(state) + "\n\nAsk me anything about your"
            " section, or pick a suggestion below.", DEFAULT_CHIPS,
        )
        return types.Content(role="model", parts=to_genai_parts(messages))

    except sethu.SethuError as error:
        # Sethu was unreachable, or we do not know who is asking. Swallowing
        # this left her with the model's
        # generic reply and NO card and NO chips -- measured in Gemini
        # Enterprise, and it reads as a dead agent. Say so, and keep the
        # options on screen so she can try again with one tap.
        logger.warning("Cannot draw a surface: %s", type(error).__name__)
        return types.Content(
            role="model",
            parts=to_genai_parts(build_greeting(sethu.message_for(error),
                                                DEFAULT_CHIPS)))
    except Exception:  # noqa: BLE001 - a broken widget must not break the answer
        logger.warning("Could not render A2UI surface", exc_info=True)
        return None


root_agent = Agent(
    model="gemini-2.5-flash",
    name="ambassador_agent",
    description="Campus Ambassador cockpit for one section.",
    instruction=INSTRUCTION,
    tools=ALL_TOOLS,
    before_agent_callback=handle_click,
    after_agent_callback=render_surface,
)
