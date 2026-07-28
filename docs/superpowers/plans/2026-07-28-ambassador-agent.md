# Ambassador Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Campus Ambassador agent in Gemini Enterprise that reproduces the
`Sethu Ambassador GE Chat.html` prototype as closely as A2UI v0.8 allows, on mock
data.

**Architecture:** ADK agent served as A2A on Cloud Run, registered in Gemini
Enterprise via `a2aAgentDefinition`. Cards are built deterministically in Python
from fixtures; the model writes prose and picks a surface. Button clicks arrive
as `userAction` DataParts and are routed in code, not by the model.

**Tech Stack:** Python 3.12, `google-adk[a2a]==2.4.0`, `a2a-sdk[http-server]`,
A2UI v0.8, Cloud Run, `supadha-dev`.

**Spec:** `docs/superpowers/specs/2026-07-28-ambassador-agent-a2ui-design.md`

## Global Constraints

- **A2UI v0.8 only.** DataPart metadata mime is `application/json+a2ui`. The
  `application/a2ui+json` spelling is v0.9+ and will not render in GE.
- **Component catalog is closed:** `Text, Image, Icon, Video, AudioPlayer, Row,
  Column, List, Card, Tabs, Divider, Modal, Button, CheckBox, TextField,
  DateTimeInput, MultipleChoice, Slider`. No `Table`, no `ProgressBar`, no
  `ChoicePicker`.
- **Only `Button` has an `action`.** `TextField`, `CheckBox`, `MultipleChoice`,
  `Slider` bind to the data model but cannot notify the agent.
- **No links inside cards.** `Text` markdown excludes links; only media
  components take URLs. WhatsApp links go in the agent's plain text reply.
- **Reserved component ids:** never name a component `body`, `root`, `title`,
  `head`, `html`, or `main`. Namespace every id per surface (`cohort-card`,
  `strag-pn-send`).
- **Enums:** `Text.usageHint` ∈ `h1 h2 h3 h4 h5 caption body`;
  `Column.alignment`/`Row.alignment` ∈ `center end start stretch`.
- **Read ADK state with `.get()`**, never `dict(state)` — `State` has no
  `keys()` and `dict()` raises `KeyError: 0`.
- **Section size is 59.** Phases: `live` → 43 activated, `target` → 54,
  `complete` → 59.
- **Copy is verbatim from the prototype.** Every user-facing string in this plan
  is taken from `Sethu Ambassador GE Chat.html`; do not paraphrase.
- **Product rules:** the agent never sends as her; counts come from certified
  reporting; her section only; rank always shows % **and** count with the basis;
  rewards follow outcomes, never effort; no streaks.
- Tests are plain functions in `test_ambassador.py`, run by `__main__`, no
  pytest, no network — matching `test_agent.py`.

---

## File Structure

| File | Responsibility |
|---|---|
| `ambassador_agent/__init__.py` | exports `root_agent` |
| `ambassador_agent/fixtures.py` | Sneha's world. Pure data, no logic. |
| `ambassador_agent/data.py` | Accessors returning API-shaped dicts + state mutations. The backend seam. |
| `ambassador_agent/a2ui.py` | v0.8 primitives: surface builder, component helpers, DataPart emission. |
| `ambassador_agent/surfaces.py` | One builder per surface. |
| `ambassador_agent/actions.py` | `userAction` parsing and routing. |
| `ambassador_agent/agent.py` | The ADK agent, instruction, callbacks. |
| `ambassador_agent/runtime.py` | Runner with explicit services (copied pattern). |
| `ambassador_agent/card.py` | Agent card loader with url injection. |
| `ambassador_agent/main_a2a.py` | Cloud Run entrypoint. |
| `ambassador_agent/agent_card.json` | Static card; `url` injected at runtime. |
| `ambassador_agent/requirements.txt` | pinned deps |
| `test_ambassador.py` | structural + rendering tests, offline |

---

## Task 1: Package skeleton and Cloud Run host

Get a deployable, registerable A2A agent that replies in text. No cards yet.
This proves the host before any A2UI complexity is layered on.

**Files:**
- Create: `ambassador_agent/__init__.py`, `agent.py`, `runtime.py`, `card.py`,
  `main_a2a.py`, `agent_card.json`, `requirements.txt`
- Create: `test_ambassador.py`

**Interfaces:**
- Consumes: the patterns in `Job_Helper_agent/{runtime,card,main_a2a}.py`
- Produces: `root_agent` (`google.adk.agents.Agent`), `app` (ASGI), and
  `build_runner()`

- [ ] **Step 1: Write the failing test**

```python
# test_ambassador.py
import importlib

def test_root_agent_exists():
    mod = importlib.import_module("ambassador_agent")
    assert mod.root_agent.name == "ambassador_agent"

def test_a2a_http_server_deps_are_installed():
    # google-adk[a2a] omits a2a-sdk[http-server]; A2AStarletteApplication then
    # raises at construction inside lifespan startup, so every import-level
    # test passes and the container dies on deploy instead.
    import sse_starlette  # noqa: F401

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\nall tests passed")
```

- [ ] **Step 2: Run it to verify it fails**

Run: `python test_ambassador.py`
Expected: `ModuleNotFoundError: No module named 'ambassador_agent'`

- [ ] **Step 3: Write `requirements.txt`**

```
google-adk[a2a]==2.4.0
a2a-sdk[http-server]
google-cloud-aiplatform
uvicorn
```

- [ ] **Step 4: Write the agent**

```python
# ambassador_agent/agent.py
from google.adk.agents import Agent

INSTRUCTION = """You are the Campus Ambassador agent for Sethu at SVEC Tirupati.

You work with ONE ambassador: Sneha Reddy, who looks after EEE Sem 3, Sec B.
You only ever know her section. There is no search, no other cohort.

Answer briefly and plainly. Never invent an activation count, a rank, or a
student. Never claim to have sent a message: you draft, she sends from her own
WhatsApp."""

root_agent = Agent(
    model="gemini-2.5-flash",
    name="ambassador_agent",
    description="Campus Ambassador cockpit for one section.",
    instruction=INSTRUCTION,
)
```

```python
# ambassador_agent/__init__.py
from .agent import root_agent

__all__ = ["root_agent"]
```

- [ ] **Step 5: Copy the host modules**

Copy `Job_Helper_agent/runtime.py` and `Job_Helper_agent/card.py` to
`ambassador_agent/`, changing only the module docstrings to name this agent.
`runtime.py` must keep `app_name=agent_engine_id` — that is the Memory Bank
scope key and any other value orphans state silently.

- [ ] **Step 6: Write the agent card**

```json
{
  "protocolVersion": "0.3.0",
  "name": "ambassador_agent",
  "description": "Campus Ambassador cockpit for one section.",
  "url": "https://REPLACE-AT-RUNTIME/",
  "version": "1.0.0",
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "capabilities": {
    "streaming": true,
    "extensions": [{
      "uri": "https://a2ui.org/a2a-extension/a2ui/v0.8",
      "required": false,
      "params": {"supportedCatalogIds": [
        "https://a2ui.org/specification/v0_8/standard_catalog_definition.json"]}
    }]
  },
  "skills": []
}
```

`required: false` preserves the plain-text fallback. `url` is injected by
`card.py` from `PUBLIC_HOST`; a static card would advertise whatever is on disk.

- [ ] **Step 7: Write the entrypoint**

```python
# ambassador_agent/main_a2a.py
import os

from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .card import load_agent_card, require_public_host
from .runtime import build_runner

# require_public_host takes the env VALUES, not their names. Passing the names
# makes the first argument always truthy, the guard never fires, and the card
# advertises `https://PUBLIC_HOST/` -- a dead agent that boots green.
PUBLIC_HOST = require_public_host(
    os.environ.get("PUBLIC_HOST"), os.environ.get("K_SERVICE")
)
PROTOCOL = os.environ.get("PUBLIC_PROTOCOL", "https")

app = to_a2a(
    root_agent,
    agent_card=load_agent_card(PUBLIC_HOST, PROTOCOL),
    runner=build_runner(),
)
```

- [ ] **Step 8: Make the root Dockerfile serve either agent**

The existing root `Dockerfile` is hardcoded to `Job_Helper_agent`, and
`gcloud run deploy --source .` only honours a Dockerfile at the **root** — there
is no flag pointing at a nested one, it silently falls through to Buildpacks.
So one Dockerfile must build both services, selecting the module by env var.

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY Job_Helper_agent/requirements.txt ./requirements-job.txt
COPY ambassador_agent/requirements.txt ./requirements-ambassador.txt
RUN pip install --no-cache-dir -r requirements-job.txt \
                                -r requirements-ambassador.txt

COPY Job_Helper_agent/ ./Job_Helper_agent/
COPY ambassador_agent/ ./ambassador_agent/

ENV PORT=8080
# ADK's own cli_deploy.py bakes this. Without it google-genai talks to the
# Gemini Developer API and needs an API key, so the container boots green and
# then fails on the first model call. .env is excluded from the image and
# nothing calls load_dotenv, so it has to be baked here.
ENV GOOGLE_GENAI_USE_VERTEXAI=1
# Which agent this container serves. The ambassador service overrides it.
ENV AGENT_MODULE=Job_Helper_agent.main_a2a
EXPOSE 8080

CMD ["sh", "-c", "uvicorn $AGENT_MODULE:app --host 0.0.0.0 --port $PORT"]
```

Keep both requirements files pinned to the same `google-adk` version. A version
skew between them resolves to one winner at build time and the loser fails only
at runtime, in whichever service was not tested.

Verify the existing Job Helper service still starts from this image before
moving on — this step changes a deployed service's build.

- [ ] **Step 9: Run the tests**

Run: `python test_ambassador.py`
Expected: both tests pass.

- [ ] **Step 10: Commit**

```bash
git add ambassador_agent test_ambassador.py Dockerfile
git commit -m "feat(ambassador): package skeleton and Cloud Run A2A host"
```

---

## Task 2: A2UI layer, greeting card, and the userAction verdict

The first real card, the first button, and the answer to whether GE sends clicks
back. Everything after this task assumes that answer.

**Files:**
- Create: `ambassador_agent/a2ui.py`, `ambassador_agent/actions.py`
- Modify: `ambassador_agent/agent.py`, `test_ambassador.py`

**Interfaces:**
- Produces: `surface(prefix, components, root_child) -> dict`,
  `text(id, s, hint) -> dict`, `button(id, label_id, name, context) -> dict`,
  `to_genai_parts(messages) -> list[types.Part]`,
  `parse_user_action(content) -> dict | None`

- [ ] **Step 1: Write the failing tests**

```python
def test_surface_ids_are_namespaced_and_unique():
    from ambassador_agent.a2ui import build_greeting
    messages = build_greeting("Hi Sneha", ["Who should I message?"])
    ids = [c["id"]
           for m in messages if "surfaceUpdate" in m
           for c in m["surfaceUpdate"]["components"]]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    assert all(i.startswith("greet-") for i in ids), ids
    reserved = {"body", "root", "title", "head", "html", "main"}
    assert not (set(ids) & reserved)

def test_every_child_reference_resolves():
    from ambassador_agent.a2ui import build_greeting
    messages = build_greeting("Hi", ["A"])
    for m in messages:
        if "surfaceUpdate" not in m:
            continue
        comps = m["surfaceUpdate"]["components"]
        known = {c["id"] for c in comps}
        for c in comps:
            spec = next(iter(c["component"].values()))
            refs = []
            if isinstance(spec.get("child"), str):
                refs.append(spec["child"])
            children = spec.get("children") or {}
            refs.extend(children.get("explicitList") or [])
            for r in refs:
                assert r in known, f"dangling reference {r!r}"

def test_datapart_mime_is_v08():
    from ambassador_agent.a2ui import to_genai_parts, build_greeting
    parts = to_genai_parts(build_greeting("Hi", []))
    blob = parts[0].inline_data.data.decode()
    assert "application/json+a2ui" in blob
    assert "application/a2ui+json" not in blob
    assert blob.startswith("<a2a_datapart_json>")

def test_parse_user_action_reads_a_tagged_datapart():
    from ambassador_agent.actions import parse_user_action
    payload = (
        '<a2a_datapart_json>{"kind":"data","data":{"userAction":'
        '{"name":"show_stragglers","surfaceId":"greet","sourceComponentId":'
        '"greet-b0","timestamp":"2026-07-28T00:00:00Z","context":{"x":"1"}}}}'
        "</a2a_datapart_json>"
    )
    action = parse_user_action(payload)
    assert action["name"] == "show_stragglers"
    assert action["context"] == {"x": "1"}

def test_parse_user_action_ignores_plain_text():
    from ambassador_agent.actions import parse_user_action
    assert parse_user_action("who should I message?") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `python test_ambassador.py`
Expected: `ModuleNotFoundError: No module named 'ambassador_agent.a2ui'`

- [ ] **Step 3: Write the A2UI primitives**

```python
# ambassador_agent/a2ui.py
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
    """Wrap components into the two messages a client needs to paint."""
    for component in components:
        assert component["id"] not in RESERVED_IDS, component["id"]
        assert component["id"].startswith(f"{prefix}-"), component["id"]
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


def build_greeting(message: str, chips: list[str]) -> list[dict]:
    prefix = "greet"
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
```

- [ ] **Step 4: Write the action parser**

```python
# ambassador_agent/actions.py
"""Parse and route A2UI button clicks.

An inbound A2A DataPart carrying no ADK metadata is converted to an inline_data
blob wrapped in <a2a_datapart_json> tags (`part_converter.py:176-183`), so the
click arrives inside the user turn rather than on a separate channel. Parsing it
here keeps routing deterministic: the model never has to guess which button was
pressed.
"""

import json
import re

_TAGGED = re.compile(r"<a2a_datapart_json>(.*?)</a2a_datapart_json>", re.S)


def parse_user_action(content: str) -> dict | None:
    """Return the userAction payload, or None when this is ordinary text."""
    if not content:
        return None
    for match in _TAGGED.finditer(content):
        try:
            payload = json.loads(match.group(1))
        except ValueError:
            continue
        data = payload.get("data") or payload
        action = data.get("userAction")
        if action and action.get("name"):
            return action
    return None
```

- [ ] **Step 5: Run the tests**

Run: `python test_ambassador.py`
Expected: all pass.

- [ ] **Step 6: Wire the greeting into the agent**

Add to `ambassador_agent/agent.py`:

```python
import logging

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from .a2ui import build_greeting, to_genai_parts

logger = logging.getLogger(__name__)

DEFAULT_CHIPS = [
    "Who should I message?",
    "Where do I stand?",
    "How is my rank calculated?",
    "What unlocks next?",
]


def render_surface(callback_context: CallbackContext) -> types.Content | None:
    """Draw a card alongside the model's own reply.

    Returning Content from an after-agent callback ADDS an event, so the text
    answer survives next to the widget. A renderer bug must never cost the user
    their answer, so the whole thing is guarded.
    """
    try:
        messages = build_greeting(
            "Ask me anything about your section, or pick a suggestion below.",
            DEFAULT_CHIPS,
        )
        return types.Content(role="model", parts=to_genai_parts(messages))
    except Exception:  # noqa: BLE001 - a broken widget must not break the answer
        logger.warning("Could not render A2UI surface", exc_info=True)
        return None


root_agent = Agent(
    model="gemini-2.5-flash",
    name="ambassador_agent",
    description="Campus Ambassador cockpit for one section.",
    instruction=INSTRUCTION,
    after_agent_callback=render_surface,
)
```

- [ ] **Step 7: Deploy and register**

Follow `docs/a2a-deploy-runbook.md`, substituting the ambassador service name.
Register with `a2aAgentDefinition` — A2UI does not render via
`adkAgentDefinition`. Share the agent in the console; registration alone does
not make it visible.

- [ ] **Step 8: Answer the userAction question**

In Gemini Enterprise, send "hi", then **tap a suggestion button**. Then read the
logs:

```bash
gcloud run services logs read ambassador-a2a --region=us-central1 \
  --project=supadha-dev --limit=100
```

Record in the ledger which of these happened:

| Observation | Meaning |
|---|---|
| A turn arrives containing `userAction` | Buttons work. Continue as planned. |
| A turn arrives with the button's label as plain text | GE degrades clicks to text. Route on the label instead; design survives. |
| No turn arrives at all | Buttons are inert. **Stop and report** — surfaces become read-only and the plan needs revising. |
| Red "This content could not be displayed" box | A component id or enum was rejected. The fragment in the box names the offender. Fix and redeploy. |

- [ ] **Step 9: Commit**

```bash
git add ambassador_agent test_ambassador.py
git commit -m "feat(ambassador): A2UI layer, greeting card, userAction routing"
```

---

## Task 3: Fixtures and the data layer

Sneha's world, shaped like the real API so the backend swap touches one file.

**Files:**
- Create: `ambassador_agent/fixtures.py`, `ambassador_agent/data.py`
- Modify: `test_ambassador.py`

**Interfaces:**
- Produces: `get_cohort(state)`, `get_stragglers(state)`,
  `get_leaderboard(state)`, `get_rewards(state)`, `get_roster(state)`,
  `milestone_line(state)`, `draft_for(student_id, angle)`,
  `mark_sent(state, student_id)`, `set_phase(state, phase)`

- [ ] **Step 1: Write the failing tests**

```python
def test_live_phase_matches_the_prototype():
    from ambassador_agent.data import get_cohort
    cohort = get_cohort({})
    assert cohort["stats"] == {"activated": 43, "size": 59, "pct": 72.9}
    assert cohort["ambassador"] == {"name": "Sneha Reddy",
                                    "section": "EEE Sem 3 · Sec B"}

def test_milestone_line_is_verbatim():
    from ambassador_agent.data import milestone_line
    assert milestone_line({}) == (
        "2 more activations clear your 75% milestone.")
    assert milestone_line({"phase": "target"}) == (
        "Your 75% milestone is earned. 5 more makes Full House, "
        "the 100% badge.")
    assert milestone_line({"phase": "complete"}) == (
        "Every student in Sec B is activated — nothing left to unlock.")

def test_target_phase_leaves_two_stragglers():
    from ambassador_agent.data import get_stragglers
    assert len(get_stragglers({})["data"]) == 6
    ids = [s["studentId"] for s in get_stragglers({"phase": "target"})["data"]]
    assert ids == ["dg", "rt"]
    assert get_stragglers({"phase": "complete"})["data"] == []

def test_sent_students_drop_out_of_the_pending_list():
    from ambassador_agent.data import get_stragglers, mark_sent
    state = {}
    mark_sent(state, "pn")
    ids = [s["studentId"] for s in get_stragglers(state)["data"]]
    assert "pn" not in ids and len(ids) == 5

def test_drafts_change_with_the_angle():
    from ambassador_agent.data import draft_for
    assert draft_for("pn", "Exam panic").startswith(
        "Hey Priya — internals Tuesday.")
    assert draft_for("pn", "Placement").startswith(
        "Hey Priya — the placement agent")
    assert draft_for("pn", "Plain").startswith(
        "Hey Priya — your college study agents are ready.")

def test_leaderboard_shows_percent_and_count_together():
    from ambassador_agent.data import get_leaderboard
    board = get_leaderboard({})
    assert board["myRank"] == 19
    me = [r for r in board["data"] if r["name"] == "You"][0]
    assert me["pct"] == 72.9 and me["activated"] == 43 and me["size"] == 59
    assert [r["rank"] for r in board["data"]] == [1, 2, 3, 19]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python test_ambassador.py`
Expected: `ModuleNotFoundError: No module named 'ambassador_agent.fixtures'`

- [ ] **Step 3: Write the fixtures**

```python
# ambassador_agent/fixtures.py
"""Sneha's world, verbatim from the GE Chat prototype.

Pure data. Every user-facing string here appears in the prototype; the demo is
judged against it, so paraphrase is a defect.
"""

AMBASSADOR = {"name": "Sneha Reddy", "section": "EEE Sem 3 · Sec B"}
COLLEGE = "SVEC Tirupati"
SECTION_SIZE = 59

# activated count per demo phase
PHASES = {"live": 43, "target": 54, "complete": 59}

STRAGGLERS = [
    {"studentId": "pn", "name": "Priya Nandakumar",
     "context": "ignored 2 campaigns · 11 days"},
    {"studentId": "sk", "name": "Suresh Kumar",
     "context": "ignored 2 campaigns · 9 days"},
    {"studentId": "ar", "name": "Anjali Rao",
     "context": "ignored 2 campaigns · 14 days"},
    {"studentId": "vm", "name": "Vikram Mehta",
     "context": "never opened a link · 16 days"},
    {"studentId": "dg", "name": "Deepa Gowda",
     "context": "ignored 2 campaigns · 8 days"},
    {"studentId": "rt", "name": "Rahul Tiwari",
     "context": "ignored 2 campaigns · 12 days"},
]

ROSTER = [
    ("Aarti Sharma", "activated", "via your link · 4 Jul"),
    ("Bharath Reddy", "activated", "via campaign · 6 Jul"),
    ("Chandana M", "pending", "in campaign cycle"),
    ("Divya Prakash", "activated", "via your link · 2 Jul"),
    ("Eshwar Naidu", "pending", "ignored 2 campaigns"),
    ("Farhan Ali", "activated", "via faculty agent · 8 Jul"),
]
ROSTER_FOOTNOTE = "Showing 6 of 59"

# Other ambassadors on the board. Sneha's row is computed from live state.
PEERS = [
    {"name": "Ananya Nair", "cohortSection": "CSE Sem 5 · A",
     "pct": 96.7, "activated": 58, "size": 60},
    {"name": "Farhan Sheikh", "cohortSection": "ECE Sem 3 · A",
     "pct": 94.9, "activated": 56, "size": 59},
    {"name": "Divya Tripathi", "cohortSection": "IT Sem 3 · A",
     "pct": 89.5, "activated": 51, "size": 57},
]
BOARD_FOOTNOTE = "178 qualifying sections · under-30 pooled"

ANGLES = [
    ("Exam panic", "internals are Tuesday"),
    ("Placement", "final-year framing"),
    ("Plain", "no angle"),
]

DRAFTS = {
    "Exam panic": (
        "Hey {first} — internals Tuesday. The Circuits agent makes practice"
        " papers from ma’am’s actual notes. One tap, college login:"),
    "Placement": (
        "Hey {first} — the placement agent has the companies that actually"
        " recruit here, with real interview questions. Two minutes to set up,"
        " college login:"),
    "Plain": (
        "Hey {first} — your college study agents are ready. One tap, college"
        " login, nothing to install:"),
}

REWARD_TIERS = [
    ("25%", "Starter"),
    ("50%", "Half-way"),
    ("75%", "75% Club — tee + certificate"),
    ("100%", "Full House — the 100% badge"),
]
```

- [ ] **Step 4: Write the data layer**

```python
# ambassador_agent/data.py
"""Accessors returning the ambassador API's documented response shapes.

This module is the backend seam. Today every function reads `fixtures`; when the
API lands, each body becomes an HTTP call and nothing else in the agent moves.
Shapes follow `ambassador-flow.pdf` (2026-07-28).

Mutations write to ADK session state so progress is real inside a conversation:
the sent count climbs as she works through the list.
"""

import math

from . import fixtures


def _get(state, key, default=None):
    # ADK's State has no keys(); dict(state) raises KeyError: 0.
    return state.get(key, default) if state is not None else default


def _phase(state) -> str:
    return _get(state, "phase", "live")


def _activated(state) -> int:
    return fixtures.PHASES[_phase(state)]


def _pct(activated: int) -> float:
    return round(activated / fixtures.SECTION_SIZE * 100, 1)


def set_phase(state, phase: str) -> None:
    if phase not in fixtures.PHASES:
        raise ValueError(f"unknown phase {phase!r}")
    state["phase"] = phase


def mark_sent(state, student_id: str) -> None:
    sent = list(_get(state, "sent", []))
    if student_id not in sent:
        sent.append(student_id)
    state["sent"] = sent


def is_sent(state, student_id: str) -> bool:
    return student_id in (_get(state, "sent", []) or [])


def get_stragglers(state) -> dict:
    """GET /api/v1/cohorts/mine/stragglers"""
    phase = _phase(state)
    if phase == "complete":
        pool = []
    elif phase == "target":
        pool = fixtures.STRAGGLERS[4:]
    else:
        pool = fixtures.STRAGGLERS
    pending = [s for s in pool if not is_sent(state, s["studentId"])]
    data = [
        {**s, "waLink": f"sethu.app/go/{s['studentId']}8x2"}
        for s in pending
    ]
    return {"data": data, "total": len(data), "page": 1, "limit": 20}


def get_cohort(state) -> dict:
    """GET /api/v1/cohorts/mine"""
    activated = _activated(state)
    return {
        "ambassador": dict(fixtures.AMBASSADOR),
        "stats": {"activated": activated, "size": fixtures.SECTION_SIZE,
                  "pct": _pct(activated)},
        "nextMilestone": _next_milestone(state),
        "stragglers": get_stragglers(state)["data"],
        "fullRoster": get_roster(state),
    }


def get_roster(state) -> list[dict]:
    return [
        {"name": name, "status": status, "how": how}
        for name, status, how in fixtures.ROSTER
    ]


def get_leaderboard(state) -> dict:
    """GET /api/v1/tenants/:id/leaderboard"""
    activated = _activated(state)
    mine = {"name": "You", "cohortSection": fixtures.AMBASSADOR["section"],
            "pct": _pct(activated), "activated": activated,
            "size": fixtures.SECTION_SIZE}
    rows = sorted([*fixtures.PEERS, mine], key=lambda r: -r["pct"])
    # Live, she sits at #19 of 178; once she climbs, the visible slot is her
    # sorted position. The prototype shows the same four rows either way.
    slots = [1, 2, 3, 19] if _phase(state) == "live" else [1, 2, 3, 4]
    for slot, row in zip(slots, rows):
        row["rank"] = slot
    my_rank = [r["rank"] for r in rows if r["name"] == "You"][0]
    return {"data": rows, "myRank": my_rank}


def _needed_for_75(state) -> int:
    target = math.ceil(fixtures.SECTION_SIZE * 0.75)
    return max(target - _activated(state), 0)


def _next_milestone(state) -> dict:
    if _phase(state) == "complete":
        return {"target": 100, "reward": "Full House — the 100% badge"}
    if _phase(state) == "target":
        return {"target": 100, "reward": "Full House — the 100% badge"}
    return {"target": 75, "reward": "75% Club — tee + certificate"}


def milestone_line(state) -> str:
    phase = _phase(state)
    if phase == "complete":
        return "Every student in Sec B is activated — nothing left to unlock."
    remaining = fixtures.SECTION_SIZE - _activated(state)
    if phase == "target":
        return (f"Your 75% milestone is earned. {remaining} more makes Full"
                " House, the 100% badge.")
    need = _needed_for_75(state)
    verb = "activation clears" if need == 1 else "activations clear"
    return f"{need} more {verb} your 75% milestone."


def get_rewards(state) -> list[dict]:
    activated = _activated(state)
    phase = _phase(state)
    remaining = fixtures.SECTION_SIZE - activated
    statuses = {
        "25%": "earned",
        "50%": "earned",
        "75%": f"{_needed_for_75(state)} more" if phase == "live" else "earned",
        "100%": "earned" if phase == "complete" else f"{remaining} more",
    }
    return [
        {"at": at, "reward": reward, "status": statuses[at]}
        for at, reward in fixtures.REWARD_TIERS
    ]


def student(student_id: str) -> dict | None:
    for entry in fixtures.STRAGGLERS:
        if entry["studentId"] == student_id:
            return entry
    return None


def draft_for(student_id: str, angle: str = "Exam panic") -> str:
    entry = student(student_id)
    if entry is None:
        raise KeyError(student_id)
    first = entry["name"].split(" ")[0]
    return fixtures.DRAFTS[angle].format(first=first)


def wa_link(student_id: str) -> str:
    return f"sethu.app/go/{student_id}8x2"
```

- [ ] **Step 5: Run the tests**

Run: `python test_ambassador.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ambassador_agent test_ambassador.py
git commit -m "feat(ambassador): fixtures and API-shaped data layer"
```

---

## Task 4: Cohort summary surface

The card the prototype shows for "where do I stand?".

**Files:**
- Create: `ambassador_agent/surfaces.py`
- Modify: `test_ambassador.py`

**Interfaces:**
- Consumes: `data.get_cohort`, `data.milestone_line`, `a2ui.*`
- Produces: `cohort_summary(state) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
def test_cohort_card_carries_the_certified_label_and_both_numbers():
    from ambassador_agent.surfaces import cohort_summary
    strings = _literals(cohort_summary({}))
    assert "EEE SEM 3 · SEC B — CERTIFIED" in strings
    assert "43 / 59" in strings
    assert any("72.9%" in s for s in strings)  # may share a node with the meter
    assert any("2 more activations clear your 75% milestone." in s
               for s in strings)
    assert "Show the 6 who need me" in strings
    assert "How is my rank calculated?" in strings

def test_cohort_card_button_names_are_routable():
    from ambassador_agent.surfaces import cohort_summary
    names = _action_names(cohort_summary({}))
    assert "show_stragglers" in names
```

Add these helpers to `test_ambassador.py`:

```python
def _components(messages):
    return [c for m in messages if "surfaceUpdate" in m
            for c in m["surfaceUpdate"]["components"]]

def _literals(messages):
    out = []
    for c in _components(messages):
        spec = c["component"].get("Text")
        if spec:
            out.append(spec["text"]["literalString"])
    return out

def _action_names(messages):
    return [c["component"]["Button"]["action"]["name"]
            for c in _components(messages) if "Button" in c["component"]]
```

- [ ] **Step 2: Run to verify it fails**

Run: `python test_ambassador.py`
Expected: `ModuleNotFoundError: No module named 'ambassador_agent.surfaces'`

- [ ] **Step 3: Write the surface**

```python
# ambassador_agent/surfaces.py
"""One builder per surface.

A2UI v0.8 has no ProgressBar, so activation is a text meter. It has no Table, so
the leaderboard, roster and rewards are one Card per entry: the catalog offers
no column widths and no per-cell alignment, and an emulated grid misaligns and
reads as broken. The fairness rule that matters survives either way — % and
count are always shown together, with the ranking basis stated.

Styling is two fields, `font` and `primaryColor`, so no row can be highlighted
by colour. Meaning lives in the text.
"""

from . import data
from .a2ui import button, card, column, row, suggestions, surface, text

METER_WIDTH = 20


def meter(pct: float) -> str:
    filled = round(pct / 100 * METER_WIDTH)
    return "█" * filled + "░" * (METER_WIDTH - filled)


def cohort_summary(state) -> list[dict]:
    prefix = "cohort"
    cohort = data.get_cohort(state)
    stats = cohort["stats"]
    pending = len(cohort["stragglers"])
    note = data.milestone_line(state)
    if pending:
        plural = "student needs" if pending == 1 else "students need"
        note += f" {pending} {plural} a personal message from you."

    components = [
        text(f"{prefix}-label", "EEE SEM 3 · SEC B — CERTIFIED", "caption"),
        text(f"{prefix}-value", f"{stats['activated']} / {stats['size']}", "h2"),
        text(f"{prefix}-meter", f"{meter(stats['pct'])}  {stats['pct']}%"),
        text(f"{prefix}-note", note),
    ]
    child_ids = [f"{prefix}-label", f"{prefix}-value", f"{prefix}-meter",
                 f"{prefix}-note"]

    primary_label = (f"Show the {pending} who need me" if pending
                     else "Show my cohort")
    components.append(text(f"{prefix}-cta0-label", primary_label))
    components.append(button(f"{prefix}-cta0", f"{prefix}-cta0-label",
                             "show_stragglers" if pending else "show_roster"))
    components.append(text(f"{prefix}-cta1-label",
                           "How is my rank calculated?"))
    components.append(button(f"{prefix}-cta1", f"{prefix}-cta1-label", "ask",
                             {"question": "how is my rank calculated?"}))
    components.append(row(f"{prefix}-ctas",
                          [f"{prefix}-cta0", f"{prefix}-cta1"]))
    child_ids.append(f"{prefix}-ctas")

    components.append(column(f"{prefix}-main-column", child_ids))
    components.append(card(f"{prefix}-card", f"{prefix}-main-column"))
    return surface(prefix, components, f"{prefix}-card")
```

- [ ] **Step 4: Run the tests**

Run: `python test_ambassador.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ambassador_agent test_ambassador.py
git commit -m "feat(ambassador): cohort summary surface"
```

---

## Task 5: Straggler list with send and edit

The hero surface. One card per student, each with two buttons.

**Files:**
- Modify: `ambassador_agent/surfaces.py`, `test_ambassador.py`

**Interfaces:**
- Produces: `straggler_list(state) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
def test_straggler_list_draws_one_card_per_pending_student():
    from ambassador_agent.surfaces import straggler_list
    messages = straggler_list({})
    names = _action_names(messages)
    assert names.count("send_whatsapp") == 6
    assert names.count("open_edit") == 6
    strings = _literals(messages)
    assert "Priya Nandakumar" in strings
    assert "ignored 2 campaigns · 11 days" in strings
    assert any("sethu.app/go/pn8x2" in s for s in strings)

def test_send_buttons_carry_the_student_id():
    from ambassador_agent.surfaces import straggler_list
    sends = [c["component"]["Button"]["action"]
             for c in _components(straggler_list({}))
             if "Button" in c["component"]
             and c["component"]["Button"]["action"]["name"] == "send_whatsapp"]
    ids = [ctx["value"]["literalString"]
           for a in sends for ctx in a["context"] if ctx["key"] == "student_id"]
    assert ids == ["pn", "sk", "ar", "vm", "dg", "rt"]

def test_sent_students_leave_the_list():
    from ambassador_agent.data import mark_sent
    from ambassador_agent.surfaces import straggler_list
    state = {}
    mark_sent(state, "pn")
    assert "Priya Nandakumar" not in _literals(straggler_list(state))

def test_ids_stay_unique_across_six_student_cards():
    from ambassador_agent.surfaces import straggler_list
    ids = [c["id"] for c in _components(straggler_list({}))]
    assert len(ids) == len(set(ids))
```

- [ ] **Step 2: Run to verify it fails**

Run: `python test_ambassador.py`
Expected: `ImportError: cannot import name 'straggler_list'`

- [ ] **Step 3: Write the surface**

```python
def straggler_list(state) -> list[dict]:
    prefix = "strag"
    students = data.get_stragglers(state)["data"]
    components: list[dict] = []
    child_ids: list[str] = []

    for entry in students:
        sid = entry["studentId"]
        base = f"{prefix}-{sid}"
        draft = data.draft_for(sid)
        components.extend([
            text(f"{base}-name", entry["name"], "h5"),
            text(f"{base}-meta", entry["context"], "caption"),
            text(f"{base}-msg", draft),
            text(f"{base}-link", entry["waLink"], "caption"),
            text(f"{base}-send-label", "Send from my WhatsApp"),
            button(f"{base}-send", f"{base}-send-label", "send_whatsapp",
                   {"student_id": sid}),
            text(f"{base}-edit-label", "Edit"),
            button(f"{base}-edit", f"{base}-edit-label", "open_edit",
                   {"student_id": sid}),
            row(f"{base}-actions", [f"{base}-send", f"{base}-edit"]),
            column(f"{base}-column", [
                f"{base}-name", f"{base}-meta", f"{base}-msg",
                f"{base}-link", f"{base}-actions",
            ]),
            card(f"{base}-card", f"{base}-column"),
        ])
        child_ids.append(f"{base}-card")

    components.append(text(
        f"{prefix}-foot",
        "You send from your own WhatsApp — I never send as you."
        " Your link carries your credit.",
        "caption"))
    child_ids.append(f"{prefix}-foot")

    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")
```

- [ ] **Step 4: Run the tests**

Run: `python test_ambassador.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ambassador_agent test_ambassador.py
git commit -m "feat(ambassador): straggler list with send and edit"
```

---

## Task 6: Edit form

Angle switch as three buttons, an editable body, and a send that carries the
edited text back.

**Files:**
- Modify: `ambassador_agent/surfaces.py`, `ambassador_agent/a2ui.py`,
  `test_ambassador.py`

**Interfaces:**
- Produces: `edit_form(state, student_id) -> list[dict]`,
  `a2ui.text_field(id, label, path)`, `a2ui.button_with_values(...)`

- [ ] **Step 1: Write the failing test**

```python
def test_edit_form_offers_three_angles_and_a_send():
    from ambassador_agent.surfaces import edit_form
    messages = edit_form({}, "pn")
    strings = _literals(messages)
    assert "Edit before sending — Priya Nandakumar" in strings
    # Angles render with a selection marker ("● Exam panic"), so match on
    # substring. An exact assertion here would push the implementer to
    # restructure the card just to satisfy the test.
    for angle in ("Exam panic", "Placement", "Plain"):
        assert any(angle in s for s in strings)
    assert "Send to Priya" in strings
    names = _action_names(messages)
    assert names.count("set_angle") == 3
    assert "send_whatsapp" in names

def test_send_carries_the_edited_text_by_path():
    from ambassador_agent.surfaces import edit_form
    send = [c["component"]["Button"]["action"]
            for c in _components(edit_form({}, "pn"))
            if "Button" in c["component"]
            and c["component"]["Button"]["action"]["name"] == "send_whatsapp"][0]
    by_key = {ctx["key"]: ctx["value"] for ctx in send["context"]}
    assert by_key["student_id"] == {"literalString": "pn"}
    assert by_key["message"] == {"path": "/draft/text"}

def test_sent_form_locks_and_relabels():
    from ambassador_agent.data import mark_sent
    from ambassador_agent.surfaces import edit_form
    state = {}
    mark_sent(state, "pn")
    strings = _literals(edit_form(state, "pn"))
    assert "Sent — Priya Nandakumar" in strings
    assert "Sent to Priya ✓" in strings
```

- [ ] **Step 2: Run to verify it fails**

Run: `python test_ambassador.py`
Expected: `ImportError: cannot import name 'edit_form'`

- [ ] **Step 3: Add the TextField and path-aware button helpers**

```python
# ambassador_agent/a2ui.py  (append)

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
```

- [ ] **Step 4: Write the surface**

```python
def edit_form(state, student_id: str) -> list[dict]:
    from .a2ui import button_with_values, data_model, text_field

    prefix = f"edit-{student_id}"
    entry = data.student(student_id)
    if entry is None:
        raise KeyError(student_id)
    first = entry["name"].split(" ")[0]
    sent = data.is_sent(state, student_id)
    angle = (state.get("angles", {}) or {}).get(student_id, "Exam panic")
    draft = (state.get("drafts", {}) or {}).get(student_id) \
        or data.draft_for(student_id, angle)

    title = (f"Sent — {entry['name']}" if sent
             else f"Edit before sending — {entry['name']}")
    cta = f"Sent to {first} ✓" if sent else f"Send to {first}"

    components = [
        text(f"{prefix}-heading", title, "h5"),
        text(f"{prefix}-angle-label", "Angle", "caption"),
    ]
    angle_ids = []
    for index, (name, _hint) in enumerate(fixtures_angles()):
        marker = "● " if name == angle else "○ "
        components.append(text(f"{prefix}-a{index}-label", marker + name))
        components.append(button(f"{prefix}-a{index}", f"{prefix}-a{index}-label",
                                 "set_angle",
                                 {"student_id": student_id, "angle": name}))
        angle_ids.append(f"{prefix}-a{index}")
    components.append(row(f"{prefix}-angles", angle_ids))

    components.append(text_field(f"{prefix}-body", "Message", "/draft/text"))
    components.append(text(f"{prefix}-cta-label", cta))
    components.append(button_with_values(
        f"{prefix}-cta", f"{prefix}-cta-label", "send_whatsapp",
        {"student_id": {"literalString": student_id},
         "message": {"path": "/draft/text"}}))
    components.append(column(f"{prefix}-main-column", [
        f"{prefix}-heading", f"{prefix}-angle-label", f"{prefix}-angles",
        f"{prefix}-body", f"{prefix}-cta",
    ]))
    components.append(card(f"{prefix}-card", f"{prefix}-main-column"))

    messages = surface(prefix, components, f"{prefix}-card")
    # The data model seeds the TextField and is what the send button reads back.
    messages.insert(1, data_model(prefix, {"draft": {"text": draft}}))
    return messages


def fixtures_angles():
    from . import fixtures
    return fixtures.ANGLES
```

- [ ] **Step 5: Run the tests**

Run: `python test_ambassador.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ambassador_agent test_ambassador.py
git commit -m "feat(ambassador): edit form with angle buttons and bound draft"
```

---

## Task 7: Leaderboard, rewards and roster

Three list surfaces, all as cards rather than tables.

**Files:**
- Modify: `ambassador_agent/surfaces.py`, `test_ambassador.py`

**Interfaces:**
- Produces: `leaderboard(state)`, `rewards(state)`, `roster(state)`

- [ ] **Step 1: Write the failing test**

```python
def test_leaderboard_always_shows_percent_and_count_and_the_basis():
    from ambassador_agent.surfaces import leaderboard
    strings = _literals(leaderboard({}))
    assert any("96.7%" in s and "58 / 60" in s for s in strings)
    assert any("72.9%" in s and "43 / 59" in s for s in strings)
    assert any(s.startswith("#19") for s in strings)
    assert "178 qualifying sections · under-30 pooled" in strings

def test_leaderboard_marks_her_row_in_text_not_colour():
    from ambassador_agent.surfaces import leaderboard
    assert any("You" in s and "EEE Sem 3 · Sec B" in s
               for s in _literals(leaderboard({})))

def test_rewards_lists_four_tiers_with_status():
    from ambassador_agent.surfaces import rewards
    strings = _literals(rewards({}))
    assert "75% Club — tee + certificate" in strings
    assert "Full House — the 100% badge" in strings
    assert any("2 more" in s for s in strings)  # renders as "at 75% — 2 more"
    assert strings.count("earned") == 2

def test_roster_shows_six_of_fiftynine():
    from ambassador_agent.surfaces import roster
    strings = _literals(roster({}))
    assert "Aarti Sharma" in strings
    assert "Showing 6 of 59" in strings
```

- [ ] **Step 2: Run to verify it fails**

Run: `python test_ambassador.py`
Expected: `ImportError: cannot import name 'leaderboard'`

- [ ] **Step 3: Write the three surfaces**

```python
def _entry_card(prefix: str, key: str, lines: list[tuple[str, str]]) -> tuple[list[dict], str]:
    """One card per row. `lines` is (suffix, content), first line is the head."""
    components, child_ids = [], []
    for index, (suffix, content) in enumerate(lines):
        component_id = f"{prefix}-{key}-{suffix}"
        components.append(text(component_id, content,
                               "h5" if index == 0 else "caption"))
        child_ids.append(component_id)
    components.append(column(f"{prefix}-{key}-column", child_ids))
    components.append(card(f"{prefix}-{key}-card", f"{prefix}-{key}-column"))
    return components, f"{prefix}-{key}-card"


def leaderboard(state) -> list[dict]:
    prefix = "board"
    board = data.get_leaderboard(state)
    components, child_ids = [], []
    for index, entry in enumerate(board["data"]):
        head = f"#{entry['rank']}  {entry['name']}"
        detail = (f"{entry['cohortSection']} — {entry['pct']}%"
                  f" · {entry['activated']} / {entry['size']}")
        made, card_id = _entry_card(prefix, f"r{index}",
                                    [("head", head), ("detail", detail)])
        components.extend(made)
        child_ids.append(card_id)

    components.append(text(f"{prefix}-basis",
                           "Ranked on % of section activated · under-30 pooled"
                           " · verified activations only", "caption"))
    components.append(text(f"{prefix}-foot", fixtures_board_footnote(),
                           "caption"))
    child_ids.extend([f"{prefix}-basis", f"{prefix}-foot"])
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def rewards(state) -> list[dict]:
    prefix = "rew"
    components, child_ids = [], []
    for index, tier in enumerate(data.get_rewards(state)):
        made, card_id = _entry_card(prefix, f"t{index}", [
            ("head", tier["reward"]),
            ("detail", f"at {tier['at']} — {tier['status']}"),
        ])
        components.extend(made)
        child_ids.append(card_id)
    components.append(text(
        f"{prefix}-foot",
        "Your credential is yours regardless of rank. Rewards are fulfilled at"
        " close-out, and follow section outcomes — never effort.", "caption"))
    child_ids.append(f"{prefix}-foot")
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def roster(state) -> list[dict]:
    prefix = "ros"
    components, child_ids = [], []
    for index, entry in enumerate(data.get_roster(state)):
        made, card_id = _entry_card(prefix, f"s{index}", [
            ("head", entry["name"]),
            ("detail", f"{entry['status']} · {entry['how']}"),
        ])
        components.extend(made)
        child_ids.append(card_id)
    components.append(text(f"{prefix}-foot", fixtures_roster_footnote(),
                           "caption"))
    child_ids.append(f"{prefix}-foot")
    components.append(column(f"{prefix}-main-column", child_ids))
    return surface(prefix, components, f"{prefix}-main-column")


def fixtures_board_footnote():
    from . import fixtures
    return fixtures.BOARD_FOOTNOTE


def fixtures_roster_footnote():
    from . import fixtures
    return fixtures.ROSTER_FOOTNOTE
```

- [ ] **Step 4: Run the tests**

Run: `python test_ambassador.py`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ambassador_agent test_ambassador.py
git commit -m "feat(ambassador): leaderboard, rewards and roster surfaces"
```

---

## Task 8: Routing, intents, chips and the phase simulator

Wire everything together: clicks route deterministically, typed questions map to
surfaces, chips change with the surface shown, and the demo can jump phases.

**Files:**
- Modify: `ambassador_agent/actions.py`, `ambassador_agent/agent.py`,
  `test_ambassador.py`

**Interfaces:**
- Produces: `route(state, action) -> tuple[str, list[dict]]`,
  `intent_for(question) -> str`, `chips_for(surface_name) -> list[str]`

- [ ] **Step 1: Write the failing test**

```python
def test_intents_match_the_prototype_keywords():
    from ambassador_agent.actions import intent_for
    assert intent_for("who should I message?") == "stragglers"
    assert intent_for("time to nudge someone") == "stragglers"
    assert intent_for("how is my rank calculated?") == "leaderboard"
    assert intent_for("what unlocks next?") == "rewards"
    assert intent_for("show my cohort") == "roster"
    assert intent_for("where do I stand?") == "cohort"
    assert intent_for("what is the weather") == "unknown"

def test_chips_change_with_the_surface():
    from ambassador_agent.actions import chips_for
    assert chips_for("stragglers") == [
        "Where do I stand?", "What unlocks next?", "Show my cohort"]
    assert chips_for("leaderboard") == [
        "Who should I message?", "What unlocks next?"]
    assert chips_for("rewards") == [
        "Who should I message?", "Where do I stand?"]
    assert len(chips_for("cohort")) == 4

def test_send_marks_the_student_and_returns_the_link():
    from ambassador_agent.actions import route
    state = {}
    reply, _messages = route(state, {"name": "send_whatsapp",
                                     "context": {"student_id": "pn"}})
    assert "Opened WhatsApp with the message for Priya." in reply
    assert "sethu.app/go/pn8x2" in reply
    assert state["sent"] == ["pn"]

def test_set_angle_redrafts_and_keeps_the_link():
    from ambassador_agent.actions import route
    state = {}
    route(state, {"name": "set_angle",
                  "context": {"student_id": "pn", "angle": "Placement"}})
    assert state["angles"]["pn"] == "Placement"
    assert "placement agent" in state["drafts"]["pn"]

def test_simulate_phase_moves_the_numbers():
    from ambassador_agent.actions import route
    from ambassador_agent.data import get_cohort
    state = {}
    route(state, {"name": "simulate_phase", "context": {"phase": "complete"}})
    assert get_cohort(state)["stats"]["activated"] == 59

def test_no_stragglers_message_is_verbatim():
    from ambassador_agent.actions import route
    state = {"phase": "complete"}
    reply, _ = route(state, {"name": "show_stragglers", "context": {}})
    assert reply == "Nobody left to chase — all 59 are activated."
```

- [ ] **Step 2: Run to verify it fails**

Run: `python test_ambassador.py`
Expected: `ImportError: cannot import name 'intent_for'`

- [ ] **Step 3: Write the router**

```python
# ambassador_agent/actions.py  (append)

from . import data, surfaces

# Keyword sets lifted from the prototype's own reply() so the demo answers the
# same questions with the same surfaces.
_INTENTS = [
    ("stragglers", ("nudge", "message", "who should")),
    ("leaderboard", ("rank", "leader")),
    ("rewards", ("reward", "badge", "credential", "unlock", "next")),
    ("roster", ("cohort", "list", "roster", "who is")),
    ("cohort", ("how many", "progress", "pace", "left", "stand")),
]

_CHIPS = {
    "stragglers": ["Where do I stand?", "What unlocks next?", "Show my cohort"],
    "leaderboard": ["Who should I message?", "What unlocks next?"],
    "rewards": ["Who should I message?", "Where do I stand?"],
}
_DEFAULT_CHIPS = [
    "Who should I message?",
    "Where do I stand?",
    "How is my rank calculated?",
    "What unlocks next?",
]

UNKNOWN_REPLY = (
    'I only know your section. Try "who should I message?", "where do I'
    ' stand?", "how is my rank calculated?" or "what unlocks next?"')


def intent_for(question: str) -> str:
    lowered = (question or "").lower()
    for name, keywords in _INTENTS:
        if any(keyword in lowered for keyword in keywords):
            return name
    return "unknown"


def chips_for(surface_name: str) -> list[str]:
    return list(_CHIPS.get(surface_name, _DEFAULT_CHIPS))


def _stragglers_reply(state) -> tuple[str, list[dict]]:
    pending = data.get_stragglers(state)["data"]
    if not pending:
        if state.get("phase") == "complete":
            return "Nobody left to chase — all 59 are activated.", []
        return ("Nobody is waiting on you. Everyone still pending is inside"
                " Sethu’s campaign cycle; they escalate to you only after"
                " ignoring two."), []
    count = len(pending)
    verb = "student has" if count == 1 else "students have"
    return (f"{count} {verb} ignored two campaigns — a broadcast won’t move"
            " them. I’ve drafted one message each, in the angle that converts"
            " best this week.",
            surfaces.straggler_list(state))


def route(state, action: dict) -> tuple[str, list[dict]]:
    """Handle one button press. Returns (prose reply, A2UI messages)."""
    name = action.get("name")
    context = action.get("context") or {}
    student_id = context.get("student_id")

    if name == "show_stragglers":
        return _stragglers_reply(state)

    if name == "open_edit":
        return "", surfaces.edit_form(state, student_id)

    if name == "set_angle":
        angle = context.get("angle", "Exam panic")
        angles = dict(state.get("angles", {}) or {})
        angles[student_id] = angle
        state["angles"] = angles
        drafts = dict(state.get("drafts", {}) or {})
        drafts[student_id] = data.draft_for(student_id, angle)
        state["drafts"] = drafts
        return "", surfaces.edit_form(state, student_id)

    if name == "send_whatsapp":
        entry = data.student(student_id)
        first = entry["name"].split(" ")[0]
        message = context.get("message") or data.draft_for(
            student_id, (state.get("angles", {}) or {}).get(
                student_id, "Exam panic"))
        data.mark_sent(state, student_id)
        link = data.wa_link(student_id)
        # The link goes in prose, not the card: A2UI v0.8 Text excludes links
        # and Button dispatches an action rather than navigating.
        return (f"Opened WhatsApp with the message for {first}. Once that"
                " sign-in lands, the activation is credited to you — usually"
                f" within the hour.\n\n{message}\n{link}"), []

    if name == "show_leaderboard":
        return "", surfaces.leaderboard(state)

    if name == "show_rewards":
        return "", surfaces.rewards(state)

    if name == "show_roster":
        return "", surfaces.roster(state)

    if name == "simulate_phase":
        data.set_phase(state, context.get("phase", "live"))
        return "", surfaces.cohort_summary(state)

    if name == "ask":
        return route_question(state, context.get("question", ""))

    return UNKNOWN_REPLY, []


def route_question(state, question: str) -> tuple[str, list[dict]]:
    intent = intent_for(question)
    if intent == "stragglers":
        return _stragglers_reply(state)
    if intent == "leaderboard":
        cohort = data.get_cohort(state)["stats"]
        return (f"You’re ranked on % of your section activated — sections under"
                f" 30 students are pooled. Sec B is at {cohort['activated']} of"
                f" 59 ({cohort['pct']}%). {data.milestone_line(state)}",
                surfaces.leaderboard(state))
    if intent == "rewards":
        return data.milestone_line(state), surfaces.rewards(state)
    if intent == "roster":
        activated = data.get_cohort(state)["stats"]["activated"]
        return (f"EEE Sem 3, Sec B — 59 students from the college roster,"
                f" {activated} activated.", surfaces.roster(state))
    if intent == "cohort":
        return "", surfaces.cohort_summary(state)
    return UNKNOWN_REPLY, []
```

- [ ] **Step 4: Wire it into the agent**

Replace `render_surface` in `agent.py` with a callback that reads the incoming
turn, routes it, appends chips, and emits both prose and cards. Use
`before_agent_callback` for clicks (so the model is skipped entirely on a
button press) and `after_agent_callback` for typed turns.

```python
def handle_click(callback_context: CallbackContext) -> types.Content | None:
    """Short-circuit a button press: the router already knows the answer."""
    try:
        content = callback_context.user_content
        raw = "".join(part.text or "" for part in (content.parts or [])) \
            if content else ""
        raw += "".join(
            (part.inline_data.data or b"").decode("utf-8", "replace")
            for part in (content.parts or []) if part.inline_data)
        action = parse_user_action(raw)
        if action is None:
            return None
        state = callback_context.state
        reply, messages = route(state, action)
        messages = messages + chips_surface(chips_for_action(action))
        parts = []
        if reply:
            parts.append(types.Part(text=reply))
        parts.extend(to_genai_parts(messages))
        return types.Content(role="model", parts=parts)
    except Exception:  # noqa: BLE001 - never cost the user their turn
        logger.warning("Could not handle A2UI action", exc_info=True)
        return None
```

Add `chips_surface(labels)` to `surfaces.py` building a standalone chip row with
prefix `chips`, and `chips_for_action(action)` in `actions.py` mapping the
action name to the surface name then calling `chips_for`.

- [ ] **Step 5: Run the tests**

Run: `python test_ambassador.py`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add ambassador_agent test_ambassador.py
git commit -m "feat(ambassador): action routing, intents, chips, phase simulator"
```

---

## Task 9: Deploy, register, and verify end to end

**Files:**
- Modify: `docs/a2a-deploy-runbook.md` (add the ambassador service)

- [ ] **Step 1: Run the full suite**

Run: `python test_ambassador.py`
Expected: every test passes. Do not deploy on a red suite.

- [ ] **Step 2: Deploy**

```bash
gcloud run deploy ambassador-a2a --source . --region=us-central1 \
  --project=supadha-dev --allow-unauthenticated=false \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=supadha-dev,GOOGLE_CLOUD_LOCATION=us-central1,AGENT_ENGINE_ID=<engine-id>,PUBLIC_HOST=<service-host>"
```

Confirm the build log says "Building using Dockerfile" — gcloud only honours a
Dockerfile at the source root and otherwise falls through to Buildpacks silently.

- [ ] **Step 3: Verify the served card**

```bash
CARD=$(curl -sf -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$SERVICE_URL/.well-known/agent-card.json")
python3 -c "import json,sys; c=json.loads(sys.argv[1]); \
assert c['url'].startswith('https://'), c['url']; \
assert c['capabilities']['extensions'][0]['uri'].endswith('v0.8')" "$CARD"
```

- [ ] **Step 4: Register and share**

POST the served card as `a2aAgentDefinition.jsonAgentCard`. Use one
discoveryengine endpoint spelling only — both work and each creates a separate
agent. Then share the agent in the console; registration alone does not make it
visible.

- [ ] **Step 5: Walk the prototype's flow in GE**

Verify each against the prototype:

1. "hi" → greeting card + four chips
2. "who should I message?" → prose + six straggler cards
3. Tap **Edit** on Priya → edit form, angle marked, body pre-filled
4. Tap **Placement** → body re-drafts, marker moves
5. Edit the body, tap **Send to Priya** → confirmation prose carrying the edited
   text and the link; Priya leaves the pending list
6. "where do I stand?" → cohort card, count now 5 pending
7. "how is my rank calculated?" → prose + leaderboard, `#19`, % and count
8. "what unlocks next?" → rewards, four tiers
9. "show my cohort" → roster, "Showing 6 of 59"
10. Phase simulator → 100%, "Every student in Sec B is activated"

- [ ] **Step 6: Record what did not work**

Any surface that draws a red "This content could not be displayed" box: read the
fragment, which names the offending component id, fix, redeploy. Any button that
does nothing: record it against the Task 2 verdict.

- [ ] **Step 7: Commit**

```bash
git add docs/a2a-deploy-runbook.md
git commit -m "docs(ambassador): deploy runbook and end-to-end verification"
```
