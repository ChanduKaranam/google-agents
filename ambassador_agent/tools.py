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

from google.adk.tools import ToolContext

from . import data


def _pick(tool_context: ToolContext, surface: str) -> None:
    """Record the surface for `render_surface` to draw after the model speaks."""
    tool_context.state["surface"] = surface


def show_stragglers(tool_context: ToolContext) -> dict:
    """Show the students who need a personal message from her.

    Use for anything about who to contact, nudge, chase, follow up, or who is
    falling behind, stalling, ignoring campaigns, or not signing in.
    """
    _pick(tool_context, "stragglers")
    pending = data.get_stragglers(tool_context.state)["data"]
    if not pending:
        if tool_context.state.get("phase") == "complete":
            return {"say": "Nobody left to chase — all 59 are activated."}
        return {"say": "Nobody is waiting on you. Everyone still pending is"
                       " inside Sethu’s campaign cycle; they escalate to you"
                       " only after ignoring two."}
    count = len(pending)
    verb = "student has" if count == 1 else "students have"
    return {
        "say": (f"{count} {verb} ignored two campaigns — a broadcast won’t"
                " move them. I’ve drafted one message each, in the angle that"
                " converts best this week."),
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
        "size": stats["size"],
        "percent": stats["pct"],
    }


def show_leaderboard(tool_context: ToolContext) -> dict:
    """Show the ambassador leaderboard and how ranking works.

    Use for rank, position, standing against other ambassadors, who is ahead,
    or how the ranking is calculated.
    """
    _pick(tool_context, "leaderboard")
    board = data.get_leaderboard(tool_context.state)
    stats = data.get_cohort(tool_context.state)["stats"]
    return {
        "say": (f"You’re ranked on % of your section activated — sections"
                f" under 30 students are pooled. Sec B is at"
                f" {stats['activated']} of {stats['size']}"
                f" ({stats['pct']}%). {data.milestone_line(tool_context.state)}"),
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
    activated = data.get_cohort(tool_context.state)["stats"]["activated"]
    return {
        "say": (f"EEE Sem 3, Sec B — 59 students from the college roster,"
                f" {activated} activated."),
    }


def simulate_phase(phase: str, tool_context: ToolContext) -> dict:
    """Demo control: jump the section to a different state.

    `phase` must be "live" (43 activated), "target" (54, the 75% milestone
    earned) or "complete" (59, every student activated). Use only when she
    explicitly asks to simulate, jump to, or pretend a state for the demo.
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
    show_stragglers,
    show_progress,
    show_leaderboard,
    show_rewards,
    show_roster,
    simulate_phase,
]
