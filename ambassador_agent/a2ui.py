"""A2UI v0.8 message construction.

The catalog is closed and small: there is no Table, no ProgressBar and no
ChoicePicker. Only Button carries an action, so any value a user types reaches
the agent solely through a Button's action.context via a data-model path.

Ids are namespaced per surface because several surfaces can render in one turn
and each naively built card wants to call its wrapper the same thing. A
duplicate id across two surfaces is invisible offline and fails as a red
"This content could not be displayed" box in the chat with nothing in the logs.
"""

import json

from google.genai import types

A2UI_MIME_TYPE = "application/json+a2ui"

# `body` is also a valid Text.usageHint and GE's validator rejects it as an id;
# the official v0.8 fixture names that node `main-column`.
RESERVED_IDS = frozenset({"body", "root", "title", "head", "html", "main"})


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
               field_type: str = "longText") -> dict:
    return {
        "id": component_id,
        "component": {"TextField": {
            "label": {"literalString": label},
            "text": {"path": path},
            "textFieldType": field_type,
        }},
    }


def data_model(surface_id: str, contents: dict) -> dict:
    return {"dataModelUpdate": {"surfaceId": surface_id, "contents": contents}}


def button_with_values(component_id: str, label_id: str, name: str,
                       values: dict) -> dict:
    """Like `button`, but each value is a full A2UI value object.

    Needed because a Button is the ONLY way a typed value reaches the agent:
    TextField binds to the data model and cannot dispatch anything itself, so
    the send button references the draft by path.
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


def column(component_id: str, children: list[str]) -> dict:
    return {
        "id": component_id,
        "component": {"Column": {"children": {"explicitList": children}}},
    }


def row(component_id: str, children: list[str]) -> dict:
    return {
        "id": component_id,
        "component": {"Row": {"children": {"explicitList": children}}},
    }


def card(component_id: str, child: str) -> dict:
    return {"id": component_id, "component": {"Card": {"child": child}}}


def surface(prefix: str, components: list[dict], root_id: str) -> list[dict]:
    """Wrap components into the two messages a client needs to paint.

    Raises rather than asserts: `python -O` strips assertions, and this is the
    only guard between a bad id and a card that fails silently in Gemini
    Enterprise -- no server-side log, at most a red box in the chat.
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


def suggestions(prefix: str, labels: list[str]) -> tuple[list[dict], list[str]]:
    """Build the follow-up buttons that replace the app's tab bar."""
    components, ids = [], []
    for index, label in enumerate(labels):
        label_id = f"{prefix}-sug{index}-label"
        button_id = f"{prefix}-sug{index}"
        components.append(text(label_id, label))
        components.append(button(button_id, label_id, "ask",
                                 {"question": label}))
        ids.append(button_id)
    return components, ids


def build_greeting(message: str, chips: list[str],
                   prefix: str = "greet") -> list[dict]:
    """The opening card, and the card shown when Sethu cannot be reached.

    `prefix` is a parameter because the outage card can be drawn more than once
    in a conversation, and a repeated surfaceId updates the earlier card
    instead of adding one -- leaving the new turn blank.
    """
    components = [text(f"{prefix}-message", message)]
    child_ids = [f"{prefix}-message"]
    chip_components, chip_ids = suggestions(prefix, chips)
    components.extend(chip_components)
    if chip_ids:
        components.append(row(f"{prefix}-chips", chip_ids))
        child_ids.append(f"{prefix}-chips")
    components.append(column(f"{prefix}-main-column", child_ids))
    components.append(card(f"{prefix}-card", f"{prefix}-main-column"))
    return surface(prefix, components, f"{prefix}-card")


def to_genai_parts(messages: list[dict]) -> list[types.Part]:
    """Emit A2UI messages as A2A DataParts.

    ADK has no public API for this. It does have a documented conversion
    (`part_converter.py:231-245`): inline_data with mime text/plain whose bytes
    are a serialised DataPart between <a2a_datapart_json> tags becomes a real
    DataPart on the wire. One DataPart per message is what lets a client paint
    incrementally.
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
