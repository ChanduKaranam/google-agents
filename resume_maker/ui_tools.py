"""A compact UI tool that builds A2UI server-side.

Why this exists: Gemini malforms function calls when it has to emit a large,
deeply-quoted JSON *string* argument (the classic
``print(default_api.send_a2ui_json_to_client(a2ui_json = "{"surfaceUpdate"...``
error with broken escaping). Rather than have the model produce the whole A2UI
component tree, it calls ``show_card`` with a handful of tiny arguments
(heading, body, button labels) and THIS code assembles the exact faculty-style
``Card -> Column -> [Text, Row-of-Buttons]`` A2UI that Gemini Enterprise renders.

The tool returns ``{"validated_a2ui_json": [...]}`` — the same shape the A2UI SDK
tool produces — so the A2A ``A2uiPartConverter`` (constructed with
``bypass_tool_check=True``) ships it as an ``application/json+a2ui`` DataPart,
and the server then injects the matching ``beginRendering``.
"""

from __future__ import annotations

import json
import uuid

from google.adk.tools.tool_context import ToolContext
from a2ui.parser.payload_fixer import parse_and_fix

from .a2ui_setup import CATALOG


async def show_card(
    heading: str,
    body: str,
    buttons: list[str],
    tool_context: ToolContext,
) -> dict:
    """Render a card in the chat with tappable buttons. Use this for EVERY point
    where you offer the user a choice or next steps — never write the options as
    plain text.

    Args:
      heading: Short title shown at the top of the card (e.g. "How would you like
        to start?" or "Choose a design").
      body: Optional supporting text under the heading (one or more sentences,
        e.g. an ATS summary or a recommendation). Pass "" if there is none.
      buttons: The tappable button labels in order, e.g.
        ["Upload my resume", "Paste resume text", "Start from scratch"]. Each
        becomes a button; when the user taps one you receive that exact label as
        their next message, so continue the flow based on it. Keep labels short.

    Returns:
      A dict the runtime turns into the rendered card. On bad input, an "error".
    """
    if not buttons or not isinstance(buttons, list):
        return {"error": "show_card needs a non-empty list of button labels."}

    surface_id = f"surface_{uuid.uuid4().hex[:8]}"
    components: list[dict] = []
    column_children: list[str] = []

    components.append(
        {
            "id": "line0",
            "component": {
                "Text": {"text": {"literalString": heading}, "usageHint": "h3"}
            },
        }
    )
    column_children.append("line0")

    if body and body.strip():
        components.append(
            {
                "id": "line1",
                "component": {
                    "Text": {"text": {"literalString": body}, "usageHint": "body"}
                },
            }
        )
        column_children.append("line1")

    button_ids: list[str] = []
    for i, label in enumerate(buttons):
        label = str(label).strip()
        if not label:
            continue
        label_id = f"btn{i}-label"
        button_id = f"btn{i}"
        components.append(
            {
                "id": label_id,
                "component": {
                    "Text": {"text": {"literalString": label}, "usageHint": "body"}
                },
            }
        )
        components.append(
            {
                "id": button_id,
                "component": {
                    # action.name = the label itself, so when the user taps it you
                    # receive that exact label back and know what was chosen.
                    "Button": {"child": label_id, "action": {"name": label}}
                },
            }
        )
        button_ids.append(button_id)

    if not button_ids:
        return {"error": "show_card needs at least one non-empty button label."}

    components.append(
        {
            "id": "buttons",
            "component": {"Row": {"children": {"explicitList": button_ids}}},
        }
    )
    column_children.append("buttons")

    components.append(
        {
            "id": "col",
            "component": {"Column": {"children": {"explicitList": column_children}}},
        }
    )
    components.append({"id": "root", "component": {"Card": {"child": "col"}}})

    message = {"surfaceUpdate": {"surfaceId": surface_id, "components": components}}

    try:
        CATALOG.validator.validate(parse_and_fix(json.dumps(message)))
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not build the card UI: {e}"}

    # Don't let the model re-summarize the raw JSON back as text.
    tool_context.actions.skip_summarization = True
    return {"validated_a2ui_json": [message]}
