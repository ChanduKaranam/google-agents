"""UI tools that build A2UI server-side for MedSight.

Why this exists: Gemini malforms function calls when it has to emit a large,
deeply-quoted JSON *string* argument (the classic broken-escaping error). Rather
than have the model produce the whole A2UI component tree, it calls one of these
tools with a handful of tiny arguments and THIS code assembles the exact
``Card -> Column -> [...]`` A2UI that Gemini Enterprise renders.

Each tool returns ``{"validated_a2ui_json": [...]}`` — the same shape the A2UI SDK
tool produces — so the A2A ``A2uiPartConverter`` (constructed with
``bypass_tool_check=True``) ships it as an ``application/json+a2ui`` DataPart,
and the server then injects the matching ``beginRendering``.

Tools:
- ``show_card``          navigation / choices (no disclaimer) — intake, next steps
- ``show_finding_card``  a medical result: optional echoed image + confidence +
                         findings + a persistent disclaimer footer + buttons
- ``show_comparison``    two images side-by-side (before/after, two views) + footer
"""

from __future__ import annotations

import base64
import io
import json
import uuid

from google.adk.tools.tool_context import ToolContext
from a2ui.parser.payload_fixer import parse_and_fix

from .a2ui_setup import CATALOG

# A single source of truth for the disclaimer so it can't drift or be shortened
# by the model — it is rendered as a fixed UI footer on every result card.
DISCLAIMER = "For study/education only — not a diagnosis. Consult a qualified clinician."


# ---------------------------------------------------------------------------
# small builders shared by every card
# ---------------------------------------------------------------------------
def _surface_id() -> str:
    return f"surface_{uuid.uuid4().hex[:8]}"


def _text(cid: str, s: str, hint: str = "body") -> dict:
    return {"id": cid, "component": {"Text": {"text": {"literalString": s}, "usageHint": hint}}}


def _button_components(buttons: list[str], components: list[dict]) -> list[str]:
    """Append Text+Button pairs for each label; return the button ids.

    ``action.name`` is the label itself, so when the user taps it you receive
    that exact label back as their next message."""
    ids: list[str] = []
    for i, label in enumerate(buttons):
        label = str(label).strip()
        if not label:
            continue
        label_id = f"btn{i}-label"
        button_id = f"btn{i}"
        components.append(_text(label_id, label))
        components.append(
            {
                "id": button_id,
                "component": {"Button": {"child": label_id, "action": {"name": label}}},
            }
        )
        ids.append(button_id)
    return ids


def _finalize(components: list[dict], column_children: list[str], tool_context: ToolContext) -> dict:
    """Wrap the column in a Card, validate against the catalog, and return."""
    components.append(
        {"id": "col", "component": {"Column": {"children": {"explicitList": column_children}}}}
    )
    components.append({"id": "root", "component": {"Card": {"child": "col"}}})
    message = {"surfaceUpdate": {"surfaceId": _surface_id(), "components": components}}
    try:
        CATALOG.validator.validate(parse_and_fix(json.dumps(message)))
    except Exception as e:  # noqa: BLE001
        return {"error": f"Could not build the card UI: {e}"}
    # Don't let the model re-summarize the raw JSON back as text.
    tool_context.actions.skip_summarization = True
    return {"validated_a2ui_json": [message]}


async def _image_data_uri(tool_context: ToolContext, filename: str, max_px: int = 768):
    """Load an uploaded image artifact and return a downscaled PNG data URI, or
    None if it is missing/undecodable. Downscaling bounds the A2UI payload — the
    echo is for visual context next to the findings, not for analysis (the model
    already read the full-resolution image via load_artifacts)."""
    if not filename or not filename.strip():
        return None
    try:
        from PIL import Image as PILImage  # lazy: only needed when echoing an image

        part = await tool_context.load_artifact(filename)
        blob = getattr(part, "inline_data", None)
        if not blob or not getattr(blob, "data", None):
            return None
        img = PILImage.open(io.BytesIO(blob.data))
        img.thumbnail((max_px, max_px))
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:  # noqa: BLE001 - a missing image must never break the card
        return None


def _image_component(cid: str, uri: str, alt: str) -> dict:
    return {
        "id": cid,
        "component": {
            "Image": {
                "url": {"literalString": uri},
                "altText": {"literalString": alt},
                "fit": "contain",
            }
        },
    }


def _footer(components: list[dict], column_children: list[str]) -> None:
    """Append the fixed disclaimer footer (Divider + muted caption) to a card."""
    components.append({"id": "rule", "component": {"Divider": {"axis": "horizontal"}}})
    column_children.append("rule")
    components.append(_text("disc", DISCLAIMER, "caption"))
    column_children.append("disc")


# ---------------------------------------------------------------------------
# public tools
# ---------------------------------------------------------------------------
async def show_card(
    heading: str,
    body: str,
    buttons: list[str],
    tool_context: ToolContext,
) -> dict:
    """Render a navigation card with tappable buttons. Use this for offering
    choices or next steps that are NOT a medical result (e.g. the intake menu, a
    viva prompt, or a structured refusal). For a medical answer use
    show_finding_card so the disclaimer footer is always attached.

    Args:
      heading: Short title/question (e.g. "What would you like to do?").
      body: Optional supporting text. Pass "" if none.
      buttons: Tappable button labels in order; the tapped label comes back as
        the user's next message. Keep labels short.

    Returns:
      A dict the runtime turns into the rendered card, or an "error".
    """
    if not buttons or not isinstance(buttons, list):
        return {"error": "show_card needs a non-empty list of button labels."}

    components: list[dict] = []
    col: list[str] = []
    components.append(_text("line0", heading, "h3"))
    col.append("line0")
    if body and body.strip():
        components.append(_text("line1", body))
        col.append("line1")

    button_ids = _button_components(buttons, components)
    if not button_ids:
        return {"error": "show_card needs at least one non-empty button label."}
    components.append({"id": "buttons", "component": {"Row": {"children": {"explicitList": button_ids}}}})
    col.append("buttons")

    return _finalize(components, col, tool_context)


async def show_finding_card(
    heading: str,
    findings: str,
    confidence: str,
    image_filename: str,
    buttons: list[str],
    tool_context: ToolContext,
) -> dict:
    """Render a MEDICAL RESULT card: an optional echoed image, a confidence line,
    the findings text, a fixed consult-a-clinician disclaimer footer, and
    next-step buttons. Use this for every image interpretation and every text
    medical answer (medicine explainer, case reasoning) so the disclaimer is
    always shown as UI, not just prose.

    Args:
      heading: Short title, e.g. "Chest X-ray — interpretation" or
        "Amoxicillin — overview".
      findings: The body of the answer. For an image, structure it as
        "Findings: ...\\nImpression: ...\\nRecommendation: ...". Tag anything you
        are unsure of inline (e.g. "(uncertain on this view)"). Never fabricate.
      confidence: A short overall calibration line, e.g. "moderate — lateral view
        would help" or "high". Pass "" to omit.
      image_filename: The artifact filename of the uploaded image to echo beside
        the findings (the same name you passed to load_artifacts). Pass "" for a
        text-only answer (e.g. medicine explainer).
      buttons: Next-step labels, e.g. ["Download a PDF summary", "Explain a
        finding", "Analyze another image"].

    Returns:
      A dict the runtime turns into the rendered card, or an "error".
    """
    if not buttons or not isinstance(buttons, list):
        return {"error": "show_finding_card needs a non-empty list of button labels."}

    components: list[dict] = []
    col: list[str] = []
    components.append(_text("line0", heading, "h3"))
    col.append("line0")

    uri = await _image_data_uri(tool_context, image_filename)
    if uri:
        components.append(_image_component("img", uri, heading))
        col.append("img")

    if confidence and confidence.strip():
        components.append(_text("conf", f"Confidence: {confidence}", "caption"))
        col.append("conf")

    if findings and findings.strip():
        components.append(_text("findings", findings, "body"))
        col.append("findings")

    _footer(components, col)

    button_ids = _button_components(buttons, components)
    if button_ids:
        components.append({"id": "buttons", "component": {"Row": {"children": {"explicitList": button_ids}}}})
        col.append("buttons")

    return _finalize(components, col, tool_context)


async def show_comparison(
    heading: str,
    label_a: str,
    findings_a: str,
    image_a: str,
    label_b: str,
    findings_b: str,
    image_b: str,
    buttons: list[str],
    tool_context: ToolContext,
) -> dict:
    """Render two images SIDE-BY-SIDE for comparison (e.g. before/after, or two
    views), each with its own label and findings, plus the disclaimer footer and
    next-step buttons. Use this whenever the user provides two images to compare.

    Args:
      heading: Short title, e.g. "Before vs after — chest X-ray".
      label_a / label_b: Short labels for the left/right image (e.g. "Baseline",
        "Follow-up").
      findings_a / findings_b: The findings text for each image. Pass "" if none.
      image_a / image_b: The artifact filenames of the two uploaded images.
      buttons: Next-step labels.

    Returns:
      A dict the runtime turns into the rendered card, or an "error".
    """
    if not buttons or not isinstance(buttons, list):
        return {"error": "show_comparison needs a non-empty list of button labels."}

    components: list[dict] = []
    col: list[str] = []
    components.append(_text("line0", heading, "h3"))
    col.append("line0")

    async def _side(prefix: str, label: str, findings: str, image: str) -> str:
        child_ids: list[str] = []
        uri = await _image_data_uri(tool_context, image)
        if uri:
            components.append(_image_component(f"{prefix}-img", uri, label))
            child_ids.append(f"{prefix}-img")
        components.append(_text(f"{prefix}-lab", label, "h4"))
        child_ids.append(f"{prefix}-lab")
        if findings and findings.strip():
            components.append(_text(f"{prefix}-find", findings, "body"))
            child_ids.append(f"{prefix}-find")
        components.append(
            {"id": f"{prefix}-col", "component": {"Column": {"children": {"explicitList": child_ids}}}}
        )
        return f"{prefix}-col"

    col_a = await _side("a", label_a, findings_a, image_a)
    col_b = await _side("b", label_b, findings_b, image_b)
    components.append({"id": "cmp", "component": {"Row": {"children": {"explicitList": [col_a, col_b]}}}})
    col.append("cmp")

    _footer(components, col)

    button_ids = _button_components(buttons, components)
    if button_ids:
        components.append({"id": "buttons", "component": {"Row": {"children": {"explicitList": button_ids}}}})
        col.append("buttons")

    return _finalize(components, col, tool_context)
