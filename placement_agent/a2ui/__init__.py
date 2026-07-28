# -*- coding: utf-8 -*-
"""
placement_agent/a2ui
Builders for A2UI (Agent-to-UI) declarative component trees.

Pure data in, pure data out -- no ADK, no agent, no I/O. Existing tools keep
returning the dicts they always returned; this layer only decides how one of
those dicts is *presented*. Nothing here can change an analysis result.

The wire format is taken from ADK's own bundled A2UI client
(google/adk/cli/browser/chunk-2SRK2U7X.js), which is the renderer that will
judge our payload:

    [
      {"surfaceUpdate":  {"surfaceId": "@default", "components": [...]}},
      {"beginRendering": {"surfaceId": "@default", "root": "<component id>"}},
      {"dataModelUpdate":{"surfaceId": "@default", "contents": {...}}}   # optional
    ]

A component is ``{"id": ..., "component": {"<Type>": {...properties}}}`` with
exactly one type key. A property that names another component's id is written
as a bare string; a list of children is ``{"explicitList": [ids]}``. Scalars
are wrapped -- ``{"literalString": "hi"}`` -- because the renderer's shape
checks reject bare values outright.
"""

import json

# The renderer locates A2UI by scanning message text for these exact tags and
# strips them out before displaying what is left.
A2UI_OPEN = "<a2ui-json>"
A2UI_CLOSE = "</a2ui-json>"

DEFAULT_SURFACE_ID = "@default"


def literal(value) -> dict:
    """Wrap a scalar the way the renderer's value checks expect."""
    if isinstance(value, bool):
        return {"literalBoolean": value}
    if isinstance(value, (int, float)):
        return {"literalNumber": value}
    return {"literalString": str(value)}


class Surface:
    """Collects components, then emits the message list that renders them.

    Every builder returns the component's id, so trees read inside-out:

        card = s.card("root", s.column("body", [s.text("t", "ATS Score")]))
    """

    def __init__(self, surface_id: str = DEFAULT_SURFACE_ID):
        self.surface_id = surface_id
        self._components: list[dict] = []
        self._ids: set[str] = set()

    # -- primitives ---------------------------------------------------------

    def add(self, component_id: str, type_name: str, properties: dict) -> str:
        if component_id in self._ids:
            raise ValueError(f"duplicate A2UI component id: {component_id!r}")
        self._ids.add(component_id)
        self._components.append(
            {"id": component_id, "component": {type_name: properties}}
        )
        return component_id

    def text(self, component_id: str, value: str) -> str:
        return self.add(component_id, "Text", {"text": literal(value)})

    def divider(self, component_id: str) -> str:
        return self.add(component_id, "Divider", {})

    def column(self, component_id: str, children: list[str]) -> str:
        return self.add(
            component_id, "Column", {"children": {"explicitList": list(children)}}
        )

    def row(self, component_id: str, children: list[str]) -> str:
        return self.add(
            component_id, "Row", {"children": {"explicitList": list(children)}}
        )

    def card(self, component_id: str, child: str) -> str:
        return self.add(component_id, "Card", {"child": child})

    def button(
        self,
        component_id: str,
        label: str,
        action: str,
        context: dict | None = None,
    ) -> str:
        """A button needs its own label component; one is created for it.

        `action` is the name the client posts back as
        ``{"userAction": {"name": ..., "context": {...}}}`` -- it is how the
        agent knows which control was pressed.
        """
        label_id = self.text(f"{component_id}_label", label)
        return self.add(
            component_id,
            "Button",
            {
                "child": label_id,
                "action": {
                    "name": action,
                    "context": [
                        {"key": key, "value": literal(value)}
                        for key, value in (context or {}).items()
                    ],
                },
            },
        )

    # -- output -------------------------------------------------------------

    def messages(self, root: str, data: dict | None = None) -> list[dict]:
        """Components first: beginRendering resolves the root immediately."""
        if root not in self._ids:
            raise ValueError(f"root {root!r} was never declared on this surface")

        messages = [
            {
                "surfaceUpdate": {
                    "surfaceId": self.surface_id,
                    "components": self._components,
                }
            },
            {"beginRendering": {"surfaceId": self.surface_id, "root": root}},
        ]
        if data is not None:
            messages.append(
                {
                    "dataModelUpdate": {
                        "surfaceId": self.surface_id,
                        "contents": data,
                    }
                }
            )
        return messages

    def block(self, root: str, data: dict | None = None) -> str:
        """The full tagged block, ready to be emitted in the reply text."""
        payload = json.dumps(self.messages(root, data), separators=(",", ":"))
        return f"{A2UI_OPEN}{payload}{A2UI_CLOSE}"
