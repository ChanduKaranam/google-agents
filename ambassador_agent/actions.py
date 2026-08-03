"""Parse and route A2UI button clicks.

An inbound A2A DataPart carrying no ADK metadata is converted to an inline_data
blob wrapped in <a2a_datapart_json> tags (`part_converter.py:176-183`), so the
click arrives inside the user turn rather than on a separate channel. Parsing it
here keeps routing deterministic: the model never has to guess which button was
pressed.
"""

import json
import re

from . import data, sethu, surfaces

_TAGGED = re.compile(r"<a2a_datapart_json>(.*?)</a2a_datapart_json>", re.S)


def parse_user_action(content: str) -> dict | None:
    """Return the userAction payload, or None when this is ordinary text."""
    if not content:
        return None
    for match in _TAGGED.finditer(content):
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            continue
        data = payload.get("data") or payload
        action = data.get("userAction")
        if action and action.get("name"):
            return action
    return None


# Keyword sets lifted from the prototype's own reply() so the demo answers the
# same questions with the same surfaces.
_INTENTS = [
    # Demo affordance, checked first so "simulate 100%" cannot be swallowed by
    # a later keyword. The prototype put this control in its own chrome; a GE
    # agent has no chrome, so typing is the only place it can live.
    ("simulate", ("simulate", "jump to", "pretend")),
    ("stragglers", ("nudge", "message", "who should")),
    ("leaderboard", ("rank", "leader")),
    ("rewards", ("reward", "badge", "credential", "unlock", "next")),
    ("roster", ("cohort", "list", "roster", "who is")),
    ("cohort", ("how many", "progress", "pace", "left", "stand")),
]

_CHIPS = {
    "stragglers": ["Where do I stand?", "What unlocks next?", "Show my cohort"],
    "leaderboard": ["Who should I message?", "What unlocks next?"],
    "rewards": ["Who should I message?", "Where do I stand?"],
}
_DEFAULT_CHIPS = [
    "Who should I message?",
    "Where do I stand?",
    "How is my rank calculated?",
    "What unlocks next?",
]

# Maps a button's action name to the surface it just drew, so the chip row
# that follows matches what's on screen rather than always the default four.
_ACTION_SURFACE = {
    "show_stragglers": "stragglers",
    "show_leaderboard": "leaderboard",
    "show_rewards": "rewards",
    "show_roster": "roster",
    "simulate_phase": "cohort",
    # The detail card is a step inside the chase-the-stragglers flow, so it
    # keeps that flow's chips rather than the generic four.
    "open_student": "stragglers",
}

UNKNOWN_REPLY = (
    'I only know your section. Try "who should I message?", "where do I'
    ' stand?", "how is my rank calculated?" or "what unlocks next?"')


def intent_for(question: str) -> str:
    lowered = (question or "").lower()
    for name, keywords in _INTENTS:
        if any(keyword in lowered for keyword in keywords):
            return name
    return "unknown"


def chips_for(surface_name: str) -> list[str]:
    return list(_CHIPS.get(surface_name, _DEFAULT_CHIPS))


def chips_for_action(action: dict) -> list[str]:
    name = action.get("name")
    if name == "ask":
        surface_name = intent_for((action.get("context") or {}).get("question", ""))
    else:
        surface_name = _ACTION_SURFACE.get(name, "")
    return chips_for(surface_name)


def _stragglers_reply(state) -> tuple[str, list[dict]]:
    pending = data.get_stragglers(state)
    if not pending:
        stats = data.get_cohort(state)["stats"]
        if stats["activated"] >= stats["total"]:
            return (f"Nobody left to chase — all {stats['total']} are"
                    " activated."), []
        return ("Nobody is waiting on you. Everyone still pending is inside"
                " Sethu’s campaign cycle; they escalate to you only after"
                " ignoring two."), []
    count = len(pending)
    verb = "student has" if count == 1 else "students have"
    return (f"{count} {verb} gone quiet on the campaigns — a broadcast won’t"
            " move them. I’ve drafted one message each, in the angle that"
            " converts best this week.",
            surfaces.straggler_list(state))


# Kept identical to tools.UNAVAILABLE so she gets one voice whichever path
# answered her.
from .tools import UNAVAILABLE  # noqa: E402


def route(state, action: dict) -> tuple[str, list[dict]]:
    """Handle one button press. Returns (prose reply, A2UI messages)."""
    try:
        return _route(state, action)
    except sethu.SethuError:
        return UNAVAILABLE, []


def route_question(state, question: str) -> tuple[str, list[dict]]:
    try:
        return _route_question(state, question)
    except sethu.SethuError:
        return UNAVAILABLE, []


def _route(state, action: dict) -> tuple[str, list[dict]]:
    name = action.get("name")
    context = action.get("context") or {}
    student_id = context.get("student_id")

    if name == "show_stragglers":
        return _stragglers_reply(state)

    if name == "open_student":
        return "", surfaces.student_detail(state, student_id)

    if name == "open_edit":
        return "", surfaces.edit_form(state, student_id)

    if name == "set_angle":
        angle = context.get("angle", "examPanic")
        angles = dict(state.get("angles", {}) or {})
        angles[student_id] = angle
        state["angles"] = angles
        drafts = dict(state.get("drafts", {}) or {})
        drafts[student_id] = data.draft_for(state, student_id, angle)
        state["drafts"] = drafts
        return "", surfaces.edit_form(state, student_id)

    if name == "send_whatsapp":
        entry = data.student(state, student_id)
        if entry is None:
            # A card can outlive its student: they activate, or drop off the
            # paged straggler list, and the button she taps is now stale.
            # Crashing here costs her the whole turn.
            return ("That student is no longer on your list — they may have"
                    " activated since this card was drawn. Ask me who needs a"
                    " message and I'll pull a fresh list."), []
        first = entry["name"].split(" ")[0]
        message = context.get("message") or data.draft_for(
            state, student_id, (state.get("angles", {}) or {}).get(
                student_id, "examPanic"))
        link = data.wa_link(state, student_id)
        body = f"{message}\n{link}"
        deeplink = data.whatsapp_deeplink(state, student_id, body)
        data.mark_sent(state, student_id)
        # The link goes in prose, not the card: A2UI v0.8 Text excludes links
        # and Button dispatches an action rather than navigating. This wa.me
        # url is what actually keeps the promise that Sethu pre-fills and she
        # sends -- without it she would retype the message herself.
        return (f"Opened WhatsApp with the message for {first}. Once that"
                " sign-in lands, the activation is credited to you — usually"
                f" within the hour.\n\nTap to send it:\n{deeplink}\n\n"
                f"{body}"), []

    if name == "show_leaderboard":
        return "", surfaces.leaderboard(state)

    if name == "show_rewards":
        return "", surfaces.rewards(state)

    if name == "show_roster":
        return "", surfaces.roster(state)

    if name == "simulate_phase":
        data.set_phase(state, context.get("phase", "live"))
        return "", surfaces.cohort_summary(state)

    if name == "ask":
        question = context.get("question", "")
        reply, messages = _route_question(state, question)
        # Echo what she picked. Gemini Enterprise renders its own placeholder
        # for a click -- the literal string "User action triggered." -- and
        # nothing an agent sends can change that bubble. Without this the
        # transcript reads as a question nobody asked, and with several chips
        # on screen there is no record of WHICH one she pressed.
        if question:
            reply = f"**{question}**\n\n{reply}" if reply else f"**{question}**"
        return reply, messages

    return UNKNOWN_REPLY, []


# Spoken forms -> phase. Longest match wins so "100" beats "0".
_PHASE_WORDS = (
    ("complete", "complete"), ("100", "complete"), ("full house", "complete"),
    ("target", "target"), ("75", "target"),
    ("live", "live"), ("start", "live"), ("reset", "live"),
)


def phase_from(question: str) -> str | None:
    lowered = (question or "").lower()
    for word, phase in _PHASE_WORDS:
        if word in lowered:
            return phase
    return None


def _route_question(state, question: str) -> tuple[str, list[dict]]:
    intent = intent_for(question)
    if intent == "simulate":
        phase = phase_from(question)
        if phase is None:
            return ('Which one? Say "simulate live", "simulate 75%" or'
                    ' "simulate 100%".'), []
        data.set_phase(state, phase)
        return (f"Demo: showing the section at the {phase} state."
                f" {data.milestone_line(state)}"), surfaces.cohort_summary(state)
    if intent == "stragglers":
        return _stragglers_reply(state)
    if intent == "leaderboard":
        cohort = data.get_cohort(state)
        stats = cohort["stats"]
        board = data.get_leaderboard(state)
        return (f"{board['basisNote']}. {cohort['label']} is at"
                f" {stats['activated']} of {stats['total']} ({stats['pct']}%),"
                f" ranked #{board['myRank']} of {board['total']}."
                f" {data.milestone_line(state)}",
                surfaces.leaderboard(state))
    if intent == "rewards":
        return data.milestone_line(state), surfaces.rewards(state)
    if intent == "roster":
        cohort = data.get_cohort(state)
        stats = cohort["stats"]
        return (f"{cohort['label']} — {data.plural(stats['total'], 'student')}"
                f" from the college roster, {stats['activated']} activated.",
                surfaces.roster(state))
    if intent == "cohort":
        return "", surfaces.cohort_summary(state)
    return UNKNOWN_REPLY, []
