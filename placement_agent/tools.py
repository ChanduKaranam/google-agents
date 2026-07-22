"""Application-tracker tools.

The only real tools in the system. Everything else moves between agents via
`output_key` + `{key?}` instruction templating, which can only overwrite a
value — application history has to be appended to, so it needs actual code.
"""

from google.adk.tools.tool_context import ToolContext

# PRD application lifecycle. Free text would let the model invent statuses that
# no downstream instruction knows how to reason about.
STATUSES = (
    "Applied",
    "OA Scheduled",
    "Interview",
    "Referral Requested",
    "Offer",
    "Rejected",
)


def track_application(
    company: str,
    role: str,
    status: str,
    notes: str,
    tool_context: ToolContext,
) -> dict:
    """Record or update a job application for this student.

    Args:
      company: Company name, e.g. "Google".
      role: Role applied for, e.g. "Software Engineer Intern".
      status: One of Applied, OA Scheduled, Interview, Referral Requested,
        Offer, Rejected.
      notes: Free-text notes, e.g. a referral contact or interview date.
        Pass an empty string if there is nothing to add.

    Returns:
      A dict with the recorded application and the total count so far.
    """
    if status not in STATUSES:
        return {
            "error": f"Unknown status {status!r}.",
            "valid_statuses": list(STATUSES),
        }

    apps = tool_context.state.get("applications") or []
    # Same company+role is an update, not a second application — otherwise a
    # student moving Applied -> Interview ends up with two rows and the coach
    # agent double-counts their pipeline.
    for app in apps:
        if app["company"].lower() == company.lower() and app["role"].lower() == role.lower():
            app["status"] = status
            if notes:
                app["notes"] = notes
            tool_context.state["applications"] = apps
            return {"updated": app, "total": len(apps)}

    app = {"company": company, "role": role, "status": status, "notes": notes}
    apps.append(app)
    # Reassign rather than mutate in place: ADK tracks state deltas by
    # assignment, and an in-place append can be missed.
    tool_context.state["applications"] = apps
    return {"added": app, "total": len(apps)}


def list_applications(tool_context: ToolContext) -> dict:
    """List every application recorded for this student in this session."""
    apps = tool_context.state.get("applications") or []
    return {"applications": apps, "total": len(apps)}
