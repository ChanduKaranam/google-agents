"""A2A server for the MedSight agent — the deploy artifact Gemini Enterprise
needs to render A2UI.

Gemini Enterprise only renders A2UI for agents registered via the **A2A path**
(``a2aAgentDefinition``), which means the agent must be reachable as a
self-hosted A2A endpoint (JSON-RPC + a ``/.well-known`` agent card). This module
turns ``root_agent`` into exactly that, using ADK's ``to_a2a`` and injecting two
A2UI-specific pieces:

* ``gen_ai_part_converter`` -> a catalog-aware :class:`A2uiPartConverter` so the
  validated output of the card tools (``show_card`` / ``show_finding_card`` /
  ``show_comparison``) ships as an ``application/a2ui+json`` A2A DataPart (what
  GE renders), while normal text and file parts fall back to ADK's default
  converter.
* a ``before_agent`` interceptor that best-effort activates the A2UI A2A
  extension for clients that negotiate it. (GE does not send the extension
  header today; A2UI still works because the tool is enabled unconditionally.)

Run locally:
    uvicorn medsight.a2a_server:app --host 0.0.0.0 --port 8080

Deploy (Cloud Run): see ``Dockerfile`` + README. After deploy, register the
service URL in Gemini Enterprise via the A2A path.
"""

from __future__ import annotations

import os

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from google.adk.a2a.executor.a2a_agent_executor import A2aAgentExecutor
from google.adk.a2a.executor.config import A2aAgentExecutorConfig, ExecuteInterceptor
from google.adk.a2a.executor.interceptors.include_artifacts_in_a2a_event import (
    include_artifacts_in_a2a_event_interceptor,
)
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from a2ui.a2a.extension import get_a2ui_agent_extension, try_activate_a2ui_extension
from a2ui.a2a.parts import create_a2ui_part

from .a2ui_setup import A2UI_VERSION, CATALOG, build_part_converter
from .agent import root_agent

# --- where the service is reachable (Cloud Run injects PORT) ----------------
HOST = os.environ.get("A2A_HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
# Public URL advertised in the agent card; set this to the Cloud Run URL in prod.
PUBLIC_URL = os.environ.get("A2A_PUBLIC_URL", f"http://{HOST}:{PORT}")

# --- agent card advertising the A2UI extension ------------------------------
AGENT_CARD = AgentCard(
    name=root_agent.name,
    description=(
        root_agent.description
        or "MedSight — an A2UI-powered medical image & medicine study assistant."
    ),
    url=PUBLIC_URL,
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain", "application/a2ui+json"],
    capabilities=AgentCapabilities(
        streaming=True,
        # Advertise A2UI with the concrete catalog id via `supportedCatalogIds`.
        # Gemini Enterprise reads this to know which catalog to render the
        # components against; without it GE receives the A2UI parts but renders
        # nothing (plain text). This matches the other working A2UI agents in the
        # GE app. CATALOG.catalog_id is the v0.8 standard catalog definition URL.
        extensions=[
            get_a2ui_agent_extension(
                A2UI_VERSION,
                supported_catalog_ids=[CATALOG.catalog_id],
            )
        ],
    ),
    skills=[
        AgentSkill(
            id="medsight",
            name="Medical image analysis",
            description=(
                "Interpret medical images (X-rays, scans, pathology slides, lab"
                " reports) and explain medicines as an academic study aid, then"
                " export a PDF summary — with tappable A2UI choices at each step."
            ),
            tags=["medical", "imaging", "health", "study", "a2ui"],
        )
    ],
)

# --- A2UI part converter (single-part adapter for ADK's executor config) ----
_a2ui_converter = build_part_converter()


def _gen_ai_part_converter(part):
    """Convert a GenAI part to an A2A part, preferring A2UI.

    ``A2uiPartConverter.convert`` handles the ``show_card`` tool output
    (returning ``application/a2ui+json`` DataParts) and A2UI text tags, and
    returns a list. ADK's executor expects a single ``Optional[Part]``, so we
    take the first produced part; for anything the A2UI converter does not
    produce (plain text, files) we fall back to ADK's default converter.
    """
    a2ui_parts = _a2ui_converter.convert(part)
    if a2ui_parts:
        return a2ui_parts[0]
    # A2uiPartConverter ALREADY applies ADK's default conversion internally for
    # non-A2UI parts (plain text, files). An empty result therefore means "emit
    # nothing" — most importantly the A2UI tool's own function_call, which must be
    # dropped. Falling back to the default converter here re-added that call as a
    # stray data part in the agent's message, which broke rendering in Gemini
    # Enterprise (a working A2UI agent's message is pure text + the A2UI parts).
    return None


async def _activate_a2ui(context):
    """Best-effort activation of the A2UI extension for negotiating clients."""
    try_activate_a2ui_extension(context, AGENT_CARD)
    return context


def _is_leaked_tool_json(part) -> bool:
    """True if a Part is the raw ``show_card`` tool output leaking (as text OR as
    a plain data part). The real UI already ships as an ``application/*a2ui``
    DataPart, so this serialized copy would otherwise render as ugly JSON next to
    the chips. The legit A2UI DataPart is preserved because it carries an
    ``application/*a2ui`` mimeType and holds ``surfaceUpdate`` directly (not
    wrapped in ``validated_a2ui_json``)."""
    root = getattr(part, "root", part)
    kind = getattr(root, "kind", None)

    # Preserve the genuine A2UI DataPart (has an a2ui mimeType).
    meta = getattr(root, "metadata", None) or {}
    if "a2ui" in str(meta.get("mimeType", "")).lower():
        return False

    if kind == "text":
        text = (getattr(root, "text", "") or "").lstrip()
        return text.startswith("{") and (
            "validated_a2ui_json" in text or "surfaceUpdate" in text
        )
    if kind == "data":
        data = getattr(root, "data", None)
        if isinstance(data, dict) and "validated_a2ui_json" in data:
            return True
    return False


def _a2ui_data(part):
    """Return the A2UI message dict carried by an ``application/*a2ui`` DataPart,
    or None for any other part."""
    root = getattr(part, "root", part)
    meta = getattr(root, "metadata", None) or {}
    if "a2ui" in str(meta.get("mimeType", "")).lower():
        data = getattr(root, "data", None)
        if isinstance(data, dict):
            return data
    return None


def _root_component_id(surface_update: dict):
    """Pick the root component id for a surfaceUpdate: prefer id 'root', else the
    first component's id."""
    ids = [
        c.get("id")
        for c in surface_update.get("components", [])
        if isinstance(c, dict) and c.get("id")
    ]
    if "root" in ids:
        return "root"
    return ids[0] if ids else None


def _inject_begin_rendering(container) -> None:
    """Gemini Enterprise renders nothing for a bare ``surfaceUpdate`` — it needs a
    ``beginRendering`` message naming the surface and its root component. Models
    emit this inconsistently, so we synthesize it deterministically here.

    This matches the exact shape a working GE A2UI agent emits (verified against
    ``job-helper-a2a``): the ``surfaceUpdate`` comes FIRST (components must exist
    before rendering), then a ``beginRendering`` of just ``{surfaceId, root}`` —
    NO ``catalogId`` (it defaults to the standard v0.8 catalog). Idempotent:
    skipped for a surface that already has a ``beginRendering``."""
    parts = getattr(container, "parts", None)
    if not parts:
        return
    already = {
        d["beginRendering"].get("surfaceId")
        for p in parts
        if (d := _a2ui_data(p)) and "beginRendering" in d
    }
    rebuilt = []
    changed = False
    for p in parts:
        rebuilt.append(p)  # surfaceUpdate first
        d = _a2ui_data(p)
        if d and "surfaceUpdate" in d:
            su = d["surfaceUpdate"]
            sid = su.get("surfaceId")
            root_id = _root_component_id(su)
            if sid and root_id and sid not in already:
                rebuilt.append(
                    create_a2ui_part(
                        {"beginRendering": {"surfaceId": sid, "root": root_id}},
                        version=A2UI_VERSION,
                    )
                )
                already.add(sid)
                changed = True
    if changed:
        container.parts = rebuilt


def _process_parts_container(container) -> bool:
    """Strip leaked tool-output parts, then inject any missing ``beginRendering``.

    Returns True if the container ends up empty (caller may drop the event)."""
    parts = getattr(container, "parts", None)
    if not parts:
        return False
    kept = [p for p in parts if not _is_leaked_tool_json(p)]
    if len(kept) != len(parts):
        container.parts = kept
    if not kept:
        return True
    _inject_begin_rendering(container)
    return False


async def _strip_leaked_a2ui_text(ctx, a2a_event, adk_event):
    """after_event hook: (1) drop the serialized A2UI tool-output that ADK
    surfaces alongside the real A2UI DataPart, and (2) inject the ``beginRendering``
    message GE needs to actually render the ``surfaceUpdate``. Handles
    artifact-update, status-message, and bare message events."""
    try:
        artifact = getattr(a2a_event, "artifact", None)
        if artifact is not None:
            if _process_parts_container(artifact):
                return None  # artifact now empty -> drop the event
            return a2a_event

        status = getattr(a2a_event, "status", None)
        msg = getattr(status, "message", None) if status is not None else None
        if msg is not None:
            _process_parts_container(msg)
            return a2a_event

        if getattr(a2a_event, "parts", None) is not None:
            if _process_parts_container(a2a_event):
                return None
        return a2a_event
    except Exception:  # never let cleanup break the response
        return a2a_event


def _executor_factory(runner) -> A2aAgentExecutor:
    config = A2aAgentExecutorConfig(
        gen_ai_part_converter=_gen_ai_part_converter,
        execute_interceptors=[
            ExecuteInterceptor(
                before_agent=_activate_a2ui,
                after_event=_strip_leaked_a2ui_text,
            ),
            # Delivers artifacts the tools save (the generated PDF) to the client
            # as A2A file parts. Without this, save_artifact() succeeds but the
            # PDF never reaches Gemini Enterprise, so "Download a PDF summary"
            # comes back empty. Not wired by to_a2a by default, and our custom
            # interceptor list replaces the default, so we add it explicitly.
            include_artifacts_in_a2a_event_interceptor,
        ],
    )
    return A2aAgentExecutor(runner=runner, config=config)


# The ASGI app uvicorn serves.
app = to_a2a(
    root_agent,
    host=HOST,
    port=PORT,
    agent_card=AGENT_CARD,
    agent_executor_factory=_executor_factory,
)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=HOST, port=PORT)
