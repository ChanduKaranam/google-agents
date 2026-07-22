"""Spike 0: does a file uploaded in Gemini Enterprise reach a custom ADK agent?

Throwaway probe. Deploy, register in the Gemini Enterprise app, attach a PDF,
read what comes back. Answers four questions from the design's section 9:

  1. Does the file arrive as an ARTIFACT?      -> artifacts[] is non-empty
  2. Does it arrive as INLINE DATA instead?    -> message_parts[] has inline_data
  3. Is user_id the caller's real identity?    -> user_id != "default-user-id"
  4. Is the session stable across turns?       -> session_id same on turn 2

Delete this whole folder once section 9 is closed.
"""

from google.adk.agents.llm_agent import Agent
from google.adk.tools.tool_context import ToolContext


async def probe(tool_context: ToolContext) -> dict:
    """Report everything this agent can see about the current request."""
    # list_artifacts raises if no artifact service is configured, which is
    # itself a finding worth reporting rather than crashing on.
    try:
        artifacts = await tool_context.list_artifacts()
    except ValueError as e:
        artifacts = f"<no artifact service: {e}>"

    parts = []
    user_content = tool_context.user_content
    if user_content and user_content.parts:
        for p in user_content.parts:
            if p.inline_data is not None:
                parts.append({
                    "kind": "inline_data",
                    "mime_type": p.inline_data.mime_type,
                    "bytes": len(p.inline_data.data or b""),
                })
            elif p.file_data is not None:
                parts.append({
                    "kind": "file_data",
                    "mime_type": p.file_data.mime_type,
                    "uri": p.file_data.file_uri,
                })
            elif p.text is not None:
                parts.append({"kind": "text", "chars": len(p.text)})
            else:
                # Unknown part type is the most interesting outcome of all:
                # it means the upload arrives in a shape we haven't accounted for.
                parts.append({"kind": "other", "repr": repr(p)[:300]})

    session = tool_context.session
    return {
        "artifacts": artifacts,
        "message_parts": parts,
        "user_id": tool_context.user_id,
        "user_id_is_default": tool_context.user_id == "default-user-id",
        "session_id": session.id,
        "event_count": len(session.events),
        "state_keys": sorted(session.state.keys()),
    }


root_agent = Agent(
    model="gemini-2.5-flash",
    name="spike0_upload_probe",
    description="Diagnostic probe for file upload and session identity.",
    instruction=(
        "You are a diagnostic probe, not an assistant. On EVERY message,"
        " regardless of what the user says, call the `probe` tool exactly once"
        " and then output its result as a JSON code block, verbatim and"
        " complete. Do not summarise it, do not omit fields, do not comment on"
        " it. If the user attached a file, do not attempt to read or describe"
        " the file — only report the probe output."
    ),
    tools=[probe],
)
