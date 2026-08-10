"""Application planning — the student's next actions, derived not imagined.

A deterministic ladder over what the state already knows: profile gaps,
research coverage, and stored deadlines. Nothing here invents a deadline or
a requirement; it only sequences what other components verified.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from app.config.settings import STATE_KNOWLEDGE
from app.services.question_service import readiness
from app.tools.profile_tools import _read_profile

MAX_STEPS = 5


def get_next_steps(tool_context: ToolContext) -> dict:
    """The student's next few concrete actions, in order.

    Returns:
        Up to five actions derived from the profile gaps, research
        coverage, and any verified deadlines — never more than the student
        can act on this week.
    """
    profile = _read_profile(tool_context.state)
    ready = readiness(profile)
    knowledge = tool_context.state.get(STATE_KNOWLEDGE)
    knowledge = knowledge if isinstance(knowledge, dict) else {}

    steps: list[str] = []

    if not ready["basic_recommendations"]["complete"]:
        gaps = ", ".join(
            p.split(".")[1] for p in ready["basic_recommendations"]["missing"][:3]
        )
        steps.append(f"Complete your core profile — still missing: {gaps}.")

    has_english = (
        profile.test_scores.ielts is not None or profile.test_scores.toefl is not None
    )
    if not has_english:
        steps.append(
            "Book an English test (IELTS Academic or TOEFL) — most programs "
            "require it, and slots fill early."
        )

    if not knowledge:
        steps.append(
            "Build a shortlist: research programs in your target country so "
            "requirements and deadlines rest on verified pages."
        )
    else:
        missing_deadlines = [
            record["university"]
            for record in knowledge.values()
            if "application_deadline" not in (record.get("facts") or {})
        ]
        if missing_deadlines:
            steps.append(
                "Verify application deadlines for: "
                + ", ".join(sorted(set(missing_deadlines))[:4])
                + "."
            )
        deadlines = [
            f"{record['university']}: {record['facts']['application_deadline']['value']}"
            for record in knowledge.values()
            if "application_deadline" in (record.get("facts") or {})
        ]
        if deadlines:
            steps.append(
                "Work back from the verified deadlines — " + "; ".join(deadlines[:3])
            )

    steps.append(
        "Line up application materials: transcripts, resume, two or three "
        "recommenders, and a first SOP draft."
    )

    return {
        "status": "success",
        "readiness": ready,
        "next_steps": steps[:MAX_STEPS],
    }
