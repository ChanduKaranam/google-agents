"""A2UI v0.8 message construction for Gemini Enterprise. Copy this file as-is.

Extracted from a live agent (Campus Ambassador, painting in GE since
2026-07-28). Every guard here exists because something failed silently in
production -- a card that does not render logs NOTHING server-side, and at best
shows a red "This content could not be displayed" box in the chat.

The catalog is closed and small: no Table, no ProgressBar, no ChoicePicker, no
link primitive. Only Button carries an action, so any value a user types
reaches the agent solely through a Button's action.context via a data-model
path.

Usage:
    from .a2ui import (build_card, to_genai_parts, uid, parse_user_action,
                       text, button, row, column, card, surface)

    messages = build_card(
        surface_id=uid(state, "attendance"),
        lines=["CSE-3A", "Strength 62 | Attendance 81%"],
        buttons=[("Show CSE-3B", "show_section", {"section": "CSE-3B"})],
    )
    return types.Content(role="model", parts=to_genai_parts(messages))
"""

import json
import re

from google.genai import types

# v0.8 spelling. `application/a2ui+json` is v0.9+ and will NOT render in GE:
# measured 2026-08-03 with a card advertising both v0.8 and v0.9.1, GE
# activated v0.8 only.
A2UI_MIME_TYPE = "application/json+a2ui"

# `body` is also a valid Text.usageHint and GE's validator rejects it as an id;
# the official v0.8 fixture names that node `main-column`. Namespacing every id
# under a surface prefix (which `surface()` enforces) sidesteps the whole class.
RESERVED_IDS = frozenset({"body", "root", "title", "head", "html", "main"})

# Gemini Enterprise drops an oversized surface SILENTLY -- the reply arrives as
# text with no card at all. Measured: 5.6KB rendered; 12.7KB and 14.2KB did
# not. Build lists to sit near 6KB and page the rest behind a button.
SURFACE_BYTE_CEILING = 6000

# A Row does not wrap and the card does not scroll: buttons past the right edge
# are simply unreachable. Measured 2026-08-07 in GE -- a six-button menu lost
# its last button entirely, with no scrollbar and nothing logged. So rows are
# split by how wide their labels are, not by how many buttons there are: three
# short labels fit where two long ones do not.
#
# The budget is in characters. In the measured screenshot roughly 63 characters
# of label survived across a wide desktop pane before the next button was cut,
# so 38 leaves most of that as headroom for a narrower phone pane. It is also
# the point where the cards here lay out sensibly: two section buttons pair up,
# while "Department - All Sections" still gets a row to itself. Losing a button
# is silent and costs more than an extra row does, so err low.
BUTTON_ROW_CHAR_BUDGET = 38
MAX_BUTTONS_PER_ROW = 3


# --- components -----------------------------------------------------------

def text(component_id: str, content: str, hint: str = "body") -> dict:
    return {
        "id": component_id,
        "component": {"Text": {"text": {"literalString": content},
                               "usageHint": hint}},
    }


def button(component_id: str, label_id: str, name: str,
           context: dict | None = None) -> dict:
    action: dict = {"name": name}
    if context:
        action["context"] = [
            {"key": k, "value": {"literalString": str(v)}}
            for k, v in context.items()
        ]
    return {
        "id": component_id,
        "component": {"Button": {"child": label_id, "action": action}},
    }


def text_field(component_id: str, label: str, path: str,
               field_type: str = "shortText") -> dict:
    """A typed input. It CANNOT notify the agent on its own.

    TextField binds to the data model; only a Button dispatches. To collect a
    typed value, pair this with `button_with_values(..., {"key": {"path": p}})`
    referencing the same path.
    """
    return {
        "id": component_id,
        "component": {"TextField": {
            "label": {"literalString": label},
            "text": {"path": path},
            "textFieldType": field_type,
        }},
    }


def button_with_values(component_id: str, label_id: str, name: str,
                       values: dict) -> dict:
    """Like `button`, but each value is a full A2UI value object.

    Needed because a Button is the ONLY way a typed value reaches the agent:
    pass {"roll_number": {"path": "/roll_number"}} to send whatever the user
    typed into the TextField bound to that path.
    """
    return {
        "id": component_id,
        "component": {"Button": {
            "child": label_id,
            "action": {"name": name,
                       "context": [{"key": k, "value": v}
                                   for k, v in values.items()]},
        }},
    }


def button_rows(prefix: str, labels: list[str], button_ids: list[str],
                budget: int | None = None,
                cap: int | None = None) -> tuple[list[dict], list[str]]:
    """Lay buttons out in rows narrow enough to stay on screen.

    Returns the Row components and their ids, to be added as children of the
    card's column. A single Row of everything is what loses the last button.

    `budget` and `cap` override the defaults for one card. Raise them only for
    a card whose labels are short enough to have measured headroom — the
    default is deliberately conservative because a button past the right edge
    is unreachable and nothing logs it.
    """
    budget = BUTTON_ROW_CHAR_BUDGET if budget is None else budget
    cap = MAX_BUTTONS_PER_ROW if cap is None else cap
    groups, current, width = [], [], 0
    for index, label in enumerate(labels):
        if current and (width + len(label) > budget
                        or len(current) >= cap):
            groups.append(current)
            current, width = [], 0
        current.append(index)
        width += len(label)
    if current:
        groups.append(current)

    components, row_ids = [], []
    for position, group in enumerate(groups):
        row_id = f"{prefix}-buttons{position}"
        components.append(row(row_id, [button_ids[i] for i in group]))
        row_ids.append(row_id)
    return components, row_ids


def column(component_id: str, children: list[str]) -> dict:
    return {"id": component_id,
            "component": {"Column": {"children": {"explicitList": children}}}}


def row(component_id: str, children: list[str]) -> dict:
    return {"id": component_id,
            "component": {"Row": {"children": {"explicitList": children}}}}


def card(component_id: str, child: str) -> dict:
    return {"id": component_id, "component": {"Card": {"child": child}}}


def data_model(surface_id: str, contents: dict) -> dict:
    """Seed the data model backing any TextField paths on this surface."""
    return {"dataModelUpdate": {"surfaceId": surface_id, "contents": contents}}


# --- assembly -------------------------------------------------------------

def surface(prefix: str, components: list[dict], root_id: str) -> list[dict]:
    """Wrap components into the two messages a client needs to paint.

    Raises rather than asserts: `python -O` strips assertions, and this is the
    only guard between a bad id and a card that fails silently.
    """
    seen: set[str] = set()
    for component in components:
        component_id = component["id"]
        if component_id in RESERVED_IDS:
            raise ValueError(
                f"{component_id!r} is reserved and GE's validator rejects it")
        if not component_id.startswith(f"{prefix}-"):
            raise ValueError(
                f"{component_id!r} is not namespaced under {prefix!r};"
                " ids must be unique across every surface drawn in one turn")
        if component_id in seen:
            raise ValueError(f"duplicate component id {component_id!r}")
        seen.add(component_id)
    return [
        {"surfaceUpdate": {"surfaceId": prefix, "components": components}},
        {"beginRendering": {"surfaceId": prefix, "root": root_id}},
    ]


def uid(state, base: str) -> str:
    """A surfaceId that has never been used in this conversation.

    A2UI treats a repeated surfaceId as an UPDATE to that surface. Drawing the
    same kind of card twice therefore rewrites the earlier card further up the
    transcript and leaves the NEW turn blank. This is a property of every
    surface, not of paging, and it is the single most common A2UI bug.
    """
    if state is None:
        return base
    sequence = int(state.get("surface_seq", 0) or 0) + 1
    state["surface_seq"] = sequence
    return f"{base}{sequence}"


def build_card(surface_id: str, lines: list[str],
               buttons: list[tuple] = (), seed: dict | None = None,
               row_budget: int | None = None, row_cap: int | None = None
               ) -> list[dict]:
    """The common case: a card of text lines with a row of buttons beneath.

    `buttons` is a list of (label, action_name, context_dict). `seed` seeds the
    data model for any TextField paths you add yourself.
    """
    components, children = [], []
    for index, line in enumerate(lines):
        line_id = f"{surface_id}-line{index}"
        components.append(text(line_id, line, "h3" if index == 0 else "body"))
        children.append(line_id)

    button_ids = []
    for index, (label, name, context) in enumerate(buttons):
        label_id = f"{surface_id}-btn{index}-label"
        button_id = f"{surface_id}-btn{index}"
        components.append(text(label_id, label))
        components.append(button(button_id, label_id, name, context))
        button_ids.append(button_id)
    if button_ids:
        rows, row_ids = button_rows(
            surface_id, [label for label, _, _ in buttons], button_ids,
            row_budget, row_cap,
        )
        components += rows
        children += row_ids

    components.append(column(f"{surface_id}-main-column", children))
    components.append(card(f"{surface_id}-card", f"{surface_id}-main-column"))

    messages = surface(surface_id, components, f"{surface_id}-card")
    if seed:
        messages.insert(1, data_model(surface_id, seed))
    return messages


# --- the wire --------------------------------------------------------------

def to_genai_parts(messages: list[dict]) -> list[types.Part]:
    """Emit A2UI messages as A2A DataParts.

    ADK has no public API for this. It does have a documented conversion
    (`a2a/converters/part_converter.py`): inline_data with mime text/plain
    whose bytes are a serialised DataPart between <a2a_datapart_json> tags
    becomes a real DataPart on the wire. One DataPart per message is what lets
    a client paint incrementally.
    """
    parts = []
    for message in messages:
        payload = json.dumps(
            {"data": message, "metadata": {"mimeType": A2UI_MIME_TYPE}},
            separators=(",", ":"),
        ).encode("utf-8")
        parts.append(types.Part(inline_data=types.Blob(
            mime_type="text/plain",
            data=b"<a2a_datapart_json>" + payload + b"</a2a_datapart_json>",
        )))
    return parts


_TAGGED = re.compile(r"<a2a_datapart_json>(.*?)</a2a_datapart_json>", re.S)


def parse_user_action(content: str) -> dict | None:
    """Return the inbound userAction payload, or None for ordinary text.

    A button press arrives INSIDE the user turn as a tag-wrapped blob, not as
    `part.text` and not on a separate channel. A handler reading only text will
    never see a click.

    GE also sends a companion text part reading "User action triggered." --
    that is its placeholder, not your payload.
    """
    if not content:
        return None
    for match in _TAGGED.finditer(content):
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            continue
        body = payload.get("data") or payload
        action = body.get("userAction")
        if action and action.get("name"):
            return action
    return None


def incoming_text(callback_context) -> str:
    """Everything the user turn carried, text and tag-wrapped blobs alike."""
    content = getattr(callback_context, "user_content", None)
    chunks = []
    for part in (getattr(content, "parts", None) or []):
        if getattr(part, "text", None):
            chunks.append(part.text)
        blob = getattr(part, "inline_data", None)
        if blob is not None and getattr(blob, "data", None):
            chunks.append(blob.data.decode("utf-8", "replace"))
    return "\n".join(chunks)


def strip_a2ui_from_response(callback_context=None, llm_response=None):
    """after_model_callback: scrub A2UI blobs out of the model's own text.

    The model reads its own history, sees A2UI JSON in it, and copies it into a
    reply -- which reaches the user as a wall of JSON. Observed live.

    ADK invokes this with KEYWORD arguments, so both parameter names must match
    exactly or every model call raises "unexpected keyword argument".
    """
    if llm_response is None:
        return None
    content = getattr(llm_response, "content", None)
    for part in (getattr(content, "parts", None) or []):
        if getattr(part, "text", None) and "<a2a_datapart_json>" in part.text:
            part.text = _TAGGED.sub("", part.text).strip()
    return None
