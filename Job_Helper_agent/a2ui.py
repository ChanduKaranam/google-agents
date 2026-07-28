"""Render session state as A2UI v0.8 so Gemini Enterprise draws real widgets.

Deterministic on purpose. The documented ADK path injects an A2UI system prompt
and has the model emit the JSON itself; we do not. Everything rendered here is
structured data a tool already wrote to session state, so there is nothing for a
model to compose -- and letting one compose it would turn `NO_INVENTION` from a
structural guarantee into a prompt. A hallucinated company is a sentence; a
hallucinated company with a clickable button is worse. A value that is not in
state cannot be rendered by this module.

Wire format, from the A2UI v0.8 renderer test data
(`renderers/angular/src/v0_8/test_data/mocks/`): a flat list of messages, each
carrying one of `surfaceUpdate` / `dataModelUpdate` / `beginRendering`.
Components are a flat list of `{"id": ..., "component": {"<Type>": {...}}}` and
reference each other by id. We inline every value as `literalString` and skip
`dataModelUpdate` entirely -- the split data model exists to save tokens on long
conversations, which is not a problem a deterministic renderer has.

Gemini Enterprise supports **v0.8 only**, and identifies the payload by the
`mimeType` on the DataPart metadata (`a2ui/a2a/parts.py`). v0.8 uses
`application/json+a2ui`; the newer `application/a2ui+json` will not render there.
"""

from __future__ import annotations

import json

from google.genai import types

# a2ui/a2a/parts.py calls this the deprecated spelling, but it is the one v0.8
# clients -- which is all Gemini Enterprise supports -- actually look for.
A2UI_MIME_TYPE = "application/json+a2ui"

# How ADK smuggles an A2A DataPart out of a genai Part: inline_data with this
# mime whose bytes are the serialised DataPart between these tags gets converted
# back into a real DataPart (`google/adk/a2a/converters/part_converter.py:231-245`).
_ADK_DATAPART_MIME = "text/plain"
_ADK_START_TAG = b"<a2a_datapart_json>"
_ADK_END_TAG = b"</a2a_datapart_json>"

_PIPELINE_SURFACE = "job-helper-pipeline"

# Ordered worst-to-best so the board reads as progress. Mirrors STATUSES in
# tools.py; anything not listed sorts last rather than being dropped, because
# silently hiding a student's application is worse than an odd sort order.
_STATUS_ORDER = (
    "Offer",
    "Interview",
    "OA Scheduled",
    "Referral Requested",
    "Applied",
    "Rejected",
)


def _text(component_id: str, value: str, hint: str = "body") -> dict:
    return {
        "id": component_id,
        "component": {
            "Text": {"text": {"literalString": value}, "usageHint": hint}
        },
    }


def _column(component_id: str, children: list[str]) -> dict:
    return {
        "id": component_id,
        "component": {"Column": {"children": {"explicitList": children}}},
    }


def _row(component_id: str, children: list[str]) -> dict:
    return {
        "id": component_id,
        "component": {
            "Row": {"children": {"explicitList": children}, "alignment": "center"}
        },
    }


def _status_rank(status: str) -> int:
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return len(_STATUS_ORDER)


def pipeline_board(applications: list[dict]) -> list[dict] | None:
    """Build the tracked-application board, or None if there is nothing real.

    Returning None rather than an empty board matters: a student who has
    tracked nothing must not be shown a widget implying otherwise.
    """
    if not applications:
        return None

    components: list[dict] = []
    body: list[str] = ["title", "subtitle"]

    components.append(_text("title", "Your application pipeline", "h2"))
    count = len(applications)
    components.append(
        _text(
            "subtitle",
            f"{count} application{'' if count == 1 else 's'} tracked",
            "caption",
        )
    )

    ordered = sorted(
        applications, key=lambda a: _status_rank(str(a.get("status", "")))
    )
    for index, app in enumerate(ordered):
        company = str(app.get("company") or "").strip()
        role = str(app.get("role") or "").strip()
        status = str(app.get("status") or "").strip()
        notes = str(app.get("notes") or "").strip()
        if not company:
            # No company means no row. There is nothing truthful to draw.
            continue

        prefix = f"app{index}"
        heading = company if not role else f"{company} — {role}"
        children = [f"{prefix}-heading", f"{prefix}-status"]
        components.append(_text(f"{prefix}-heading", heading, "h3"))
        components.append(_text(f"{prefix}-status", status or "Applied", "body"))
        if notes:
            children.append(f"{prefix}-notes")
            components.append(_text(f"{prefix}-notes", notes, "caption"))

        components.append(_column(f"{prefix}-col", children))
        body.append(f"{prefix}-col")

        if index < len(ordered) - 1:
            divider_id = f"{prefix}-divider"
            components.append({"id": divider_id, "component": {"Divider": {}}})
            body.append(divider_id)

    if len(body) <= 2:  # title + subtitle only: every row was unrenderable
        return None

    components.append(_column("body", body))
    components.append({"id": "root", "component": {"Card": {"child": "body"}}})

    return [
        {
            "surfaceUpdate": {
                "surfaceId": _PIPELINE_SURFACE,
                "components": components,
            }
        },
        {"beginRendering": {"surfaceId": _PIPELINE_SURFACE, "root": "root"}},
    ]


def build_a2ui_messages(state: dict) -> list[dict]:
    """Render whatever the session state supports. Empty list renders nothing.

    Only `applications` is here because only `applications` is structured: it is
    written by `tools.track_application`. The other state keys (`companies`,
    `alumni`, `matches`, `gaps`) hold the specialists' prose, since they come
    from `output_key` on an LlmAgent -- there is no reliable structure to draw
    cards from. Rendering those needs those specialists to emit structured
    output first; see the ticket-2 notes in the design spec.
    """
    board = pipeline_board((state or {}).get("applications") or [])
    return board or []


def to_genai_parts(messages: list[dict]) -> list[types.Part]:
    """Wrap A2UI messages so ADK converts them into A2A DataParts.

    One DataPart per message, which is what makes incremental painting possible
    on the client -- the format is a flat list of small messages precisely so a
    renderer can draw as they arrive.
    """
    parts: list[types.Part] = []
    for message in messages:
        data_part = {"data": message, "metadata": {"mimeType": A2UI_MIME_TYPE}}
        payload = json.dumps(data_part, separators=(",", ":")).encode("utf-8")
        parts.append(
            types.Part(
                inline_data=types.Blob(
                    mime_type=_ADK_DATAPART_MIME,
                    data=_ADK_START_TAG + payload + _ADK_END_TAG,
                )
            )
        )
    return parts
