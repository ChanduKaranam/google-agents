# -*- coding: utf-8 -*-
"""
placement_agent/a2ui/probe.py
M1 spike: the smallest thing that answers "does A2UI render here at all?".

Deliberately carries no placement data. If this card renders, the transport,
the marker convention, the component contract and the model's ability to pass
the block through are all proven at once; if it does not, no amount of resume
dashboard work would have rendered either. Delete this module once real views
ship -- it exists to be a control, not a feature.
"""

from google.adk.tools.tool_context import ToolContext

from . import Surface
from .emit import queue_surface


def show_a2ui_probe_card(tool_context: ToolContext) -> dict:
    """
    Render a small interactive test card to check that rich UI works here.

    Use this only when the user asks to test, check or verify A2UI / rich UI /
    interactive card rendering. It is a diagnostic, not part of any resume or
    interview workflow.

    The card renders itself -- do not repeat, quote or describe its JSON.

    Returns:
        dict confirming the card was queued, plus a plain-text fallback.
    """
    surface = Surface()

    body = surface.column(
        "probe_body",
        [
            surface.text("probe_title", "A2UI is live"),
            surface.text(
                "probe_subtitle",
                "This card was declared by the Placement Assistant, not written as text.",
            ),
            surface.divider("probe_rule"),
            surface.button(
                "probe_cta",
                "Confirm you can see this",
                action="a2ui_probe_confirmed",
                context={"surface": "probe", "version": 1},
            ),
        ],
    )
    root = surface.card("probe_card", body)

    block = surface.block(root)
    queue_surface(tool_context, block)

    return {
        "success": True,
        "rendered": "A2UI probe card has been sent to the screen.",
        "say_next": (
            "Tell the user the card is on screen and ask them to press the "
            "button. Do NOT print or describe any JSON."
        ),
        "a2ui_block": block,
        "fallback_text": (
            "A2UI probe card (rich UI not rendering here — falling back to text): "
            "title 'A2UI is live', with a 'Confirm you can see this' button."
        ),
        "on_button_press": (
            "The client posts back userAction name 'a2ui_probe_confirmed'. "
            "Acknowledge it and report that A2UI round-trips."
        ),
    }
