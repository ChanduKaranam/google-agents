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
      company: Company name, e.g. "Freshworks" or "Google".
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
    """List the applications tracked in the current conversation.

    This is deliberately session-scoped. It cannot see previous visits, and it
    must not pretend to: an agent that reports "you have no applications" when
    the student has ten would be worse than one that says "this conversation".

    Why it cannot reach further: this tool runs inside a specialist invoked
    through `AgentTool`, and `agent_tool.py:253` gives every sub-agent a fresh
    empty `InMemoryMemoryService()` rather than forwarding the real one. So
    `search_memory` here always returns nothing, whatever the deployment. (It
    does forward session state in both directions -- `state=state_dict` at
    :269 and the state_delta forwarding at :283 -- which is why `{key?}`
    templating works fine.)

    Cross-session history reaches the student through the root agent instead,
    which holds the real memory service and `PreloadMemoryTool`.
    """
    apps = tool_context.state.get("applications") or []
    return {
        "applications_this_conversation": apps,
        "total": len(apps),
        "note": (
            "Session-scoped only. Applications from the student's earlier"
            " visits are supplied by the orchestrator, not by this tool."
        ),
    }
