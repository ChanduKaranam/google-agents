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

# The starter prompts, shown after EVERY reply.
#
# These used to vary by surface -- the leaderboard reply offered two chips, the
# rewards reply a different two -- which meant the option she wanted was often
# not on screen and she had to scroll back up to the greeting to find it. Asked
# for directly by the ambassador: the same four, every time.
DEFAULT_CHIPS = [
    "Who should I message?",
    "Where do I stand?",
    "Show the leaderboard",
    "What unlocks next?",
]

UNKNOWN_REPLY = (
    'I only know your section. Try "who should I message?", "where do I'
    ' stand?", "show the leaderboard" or "what unlocks next?"')


def chips_for(_surface_name: str = "") -> list[str]:
    """The starter prompts. Takes a surface only so callers need not change."""
    return list(DEFAULT_CHIPS)


def chips_for_action(_action: dict | None = None) -> list[str]:
    return list(DEFAULT_CHIPS)


def intent_for(question: str) -> str:
    lowered = (question or "").lower()
    for name, keywords in _INTENTS:
        if any(keyword in lowered for keyword in keywords):
            return name
    return "unknown"


def _stragglers_reply(state, reset: bool = True) -> tuple[str, list[dict]]:
    if reset:
        state["strag_offset"] = 0      # asking again starts from the top
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
    except sethu.SethuError as error:
        return sethu.message_for(error), []


def route_question(state, question: str) -> tuple[str, list[dict]]:
    try:
        return _route_question(state, question)
    except sethu.SethuError as error:
        return sethu.message_for(error), []


def _route(state, action: dict) -> tuple[str, list[dict]]:
    name = action.get("name")
    context = action.get("context") or {}
    student_id = context.get("student_id")

    if name == "show_stragglers":
        return _stragglers_reply(state)

    if name == "more_stragglers":
        # The offset rides on the button, so tapping the next-page button on a
        # card further up the transcript still does the right thing.
        try:
            state["strag_offset"] = int(context.get("offset"))
        except (TypeError, ValueError):
            state["strag_offset"] = (int(state.get("strag_offset", 0) or 0)
                                     + surfaces.drawn_count(state))
        return "", surfaces.straggler_list(state)

    if name == "open_student":
        return "", surfaces.student_detail(state, student_id)

    if name == "open_edit":
        return "", surfaces.edit_form(state, student_id)

    if name == "set_angle":
        angle = context.get("angle", data.DEFAULT_ANGLE)
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
        if not data.wa_number(entry):
            # `phone` is null when not on file. wa.me with no number opens an
            # empty chat, so say it plainly rather than handing her a dead link.
            return (f"Sethu has no phone number on file for {entry['name']},"
                    " so I can't open WhatsApp for them. Their link still"
                    f" works if you can reach them another way:"
                    f" {data.wa_link(state, student_id)}"), []
        message = context.get("message") or data.current_draft(state, student_id)
        body = data.append_link(message, data.wa_link(state, student_id))
        deeplink = data.whatsapp_deeplink(state, student_id, body)
        data.mark_sent(state, student_id)
        # She asked for a button with the link in it. A2UI v0.8 cannot: the
        # Button schema is additionalProperties:false over {child, primary,
        # action} with no url field, and Text excludes links (checked against
        # the standard catalog, 2026-08-03 -- v0.8 is the only version
        # published). The nearest thing the platform allows is a markdown link
        # wearing a button's label, which the chat surface renders as a single
        # tap. It leads the reply, and the raw url is gone: a wa.me link with
        # the whole message percent-encoded into it ran to several lines of
        # noise she had to read past.
        return (f"**[📲 Send to {first} on WhatsApp]({deeplink})**\n\n"
                "One tap opens WhatsApp with this message already written —"
                " you press send, never me. Once that sign-in lands, the"
                " activation is credited to you, usually within the hour."
                f"\n\n---\n\n{body}"), []

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
        # myRank is null when the cohort is unranked -- interpolating it gave
        # "ranked #None of 20".
        placing = (f", ranked #{board['myRank']} of {board['total']}"
                   if board.get("myRank") else ", not ranked yet")
        return (f"{board['basisNote']}. {cohort['label']} is at"
                f" {stats['activated']} of {stats['total']} ({stats['pct']}%)"
                f"{placing}. {data.milestone_line(state)}",
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
