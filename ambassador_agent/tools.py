"""Function tools that let the model reach the surfaces in any phrasing.

Keyword matching (`actions._INTENTS`) is copied from the prototype and only
recognises the wording the prototype used. "Is there anyone I should message?"
happens to contain "message"; "who's falling behind?" contains nothing, and
fell through to a generic answer with no card.

So the model gets a tool per surface. It decides which one an arbitrary
question means, the tool records WHICH surface to draw, and the renderer draws
it deterministically afterwards. The model chooses; it never composes the card.

Each tool returns the prototype's own sentence for that surface, and the
instruction tells the model to lead with it — so the copy the team is judging
stays fixed while the phrasing that reaches it can be anything.
"""

import functools

from google.adk.tools import ToolContext

from . import data, sethu

# What she is told when a Sethu call fails. The wording depends on WHY -- an
# outage, an unknown caller, and a caller who is not an ambassador are three
# different problems and only one of them is worth retrying.
UNAVAILABLE = sethu.UNAVAILABLE


def _survives_an_outage(tool):
    """A backend failure must cost her an answer, not the whole turn.

    Without this a timeout propagated out of the tool, ADK failed the node, and
    the reply she saw was the text "The read operation timed out".
    """
    @functools.wraps(tool)
    def guarded(*args, **kwargs):
        try:
            return tool(*args, **kwargs)
        except sethu.SethuError as error:
            return {"say": sethu.message_for(error)}
    return guarded


def _pick(tool_context: ToolContext, surface: str) -> None:
    """Record the surface for `render_surface` to draw after the model speaks."""
    tool_context.state["surface"] = surface


def show_stragglers(tool_context: ToolContext) -> dict:
    """Show the students who need a personal message from her.

    Use for anything about who to contact, nudge, chase, follow up, or who is
    falling behind, stalling, ignoring campaigns, or not signing in.
    """
    _pick(tool_context, "stragglers")
    state = tool_context.state
    pending = data.get_stragglers(state)
    if not pending:
        stats = data.get_cohort(state)["stats"]
        if stats["activated"] >= stats["total"]:
            return {"say": f"Nobody left to chase — all {stats['total']} are"
                           " activated."}
        return {"say": "Nobody is waiting on you. Everyone still pending is"
                       " inside Sethu’s campaign cycle; they escalate to you"
                       " only after ignoring two."}
    count = len(pending)
    verb = "student has" if count == 1 else "students have"
    return {
        "say": (f"{count} {verb} gone quiet on the campaigns — a broadcast"
                " won’t move them. I’ve drafted one message each, in the angle"
                " that converts best this week."),
        "students": [s["name"] for s in pending],
    }


def show_progress(tool_context: ToolContext) -> dict:
    """Show her section's activation progress and next milestone.

    Use for how far along she is, how many are left, how she is doing, pace,
    time remaining, or what her current numbers are.
    """
    _pick(tool_context, "cohort")
    stats = data.get_cohort(tool_context.state)["stats"]
    return {
        "say": data.milestone_line(tool_context.state),
        "activated": stats["activated"],
        "size": stats["total"],
        "percent": stats["pct"],
    }


def show_leaderboard(tool_context: ToolContext) -> dict:
    """Show the ambassador leaderboard and how ranking works.

    Use for rank, position, standing against other ambassadors, who is ahead,
    or how the ranking is calculated.
    """
    _pick(tool_context, "leaderboard")
    state = tool_context.state
    board = data.get_leaderboard(state)
    cohort = data.get_cohort(state)
    stats = cohort["stats"]
    return {
        "say": (f"{board['basisNote']}. {cohort['label']} is at"
                f" {stats['activated']} of {stats['total']} ({stats['pct']}%),"
                f" ranked #{board['myRank']} of {board['total']}."
                f" {data.milestone_line(state)}"),
        "my_rank": board["myRank"],
    }


def show_rewards(tool_context: ToolContext) -> dict:
    """Show the reward tiers, what is earned and what unlocks next.

    Use for rewards, badges, the certificate, the tee, the credential, or what
    she gets for hitting a milestone.
    """
    _pick(tool_context, "rewards")
    return {
        "say": data.milestone_line(tool_context.state),
        "tiers": data.get_rewards(tool_context.state),
    }


def show_roster(tool_context: ToolContext) -> dict:
    """Show the full list of students in her section and their status.

    Use for the roster, the class list, who is in her section, or who has
    already activated.
    """
    _pick(tool_context, "roster")
    cohort = data.get_cohort(tool_context.state)
    stats = cohort["stats"]
    return {
        "say": (f"{cohort['label']} —"
                f" {data.plural(stats['total'], 'student')} from the college"
                f" roster, {stats['activated']} activated."),
    }


def simulate_phase(phase: str, tool_context: ToolContext) -> dict:
    """Demo control: jump the section to a different state.

    `phase` must be "live" (the real activation count), "target" (75% of the
    section, so the milestone is earned) or "complete" (every student
    activated). Use only when she explicitly asks to simulate, jump to, or
    pretend a state for the demo.
    """
    try:
        data.set_phase(tool_context.state, phase)
    except ValueError:
        return {"say": 'Which one? Say "simulate live", "simulate 75%" or'
                       ' "simulate 100%".'}
    _pick(tool_context, "cohort")
    return {"say": f"Demo: showing the section at the {phase} state."
                   f" {data.milestone_line(tool_context.state)}"}


ALL_TOOLS = [
    _survives_an_outage(tool) for tool in (
        show_stragglers,
        show_progress,
        show_leaderboard,
        show_rewards,
        show_roster,
        simulate_phase,
    )
]
