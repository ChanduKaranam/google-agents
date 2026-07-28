# A2UI — agent-drawn UI in the Gemini Enterprise chat surface

Verified 2026-07-28 against `google-adk==2.4.0`, `a2a-sdk==0.3.26`, a live Cloud
Run A2A service and a live `supadha-dev` GE registration. Method is stated per
claim; treat anything unmarked as unverified.

**Verification status.** End-to-end confirmed 2026-07-28 in the live Gemini
Enterprise web app: a valid v0.8 card **paints**, and a button press **returns a
real `userAction` DataPart** to the agent. Both directions work. Earlier
revisions of this file called the render unverified; it no longer is.

Note the ordering, because it cost several deploy cycles to separate: "the
payload is correct on the wire" and "GE renders it" and "GE sends clicks back"
are three distinct claims with three distinct failure modes. Verify them
separately.

## What A2UI is

The agent returns a JSON description of a UI instead of text. The client
validates it against its own component catalog and draws it in its own design
language. Interaction comes back as the next conversational turn — there is no
separate callback channel.

## The constraint that decides your architecture

**A2UI renders only for agents registered via the A2A path (`a2aAgentDefinition`).**
Agents deployed to Agent Runtime and registered via `adkAgentDefinition` do not
render A2UI. (Docs: `/gemini/enterprise/docs/a2ui-agents/register-and-manage-an-a2ui-agent`.)

So "add A2UI to our deployed agent" is never a UI task. It is a runtime
migration to a self-hosted A2A endpoint (Cloud Run/GKE), and it drags in
everything the managed runtime was doing for you — see **Migration blast radius**.

**Gemini Enterprise supports A2UI v0.8 only.** A v0.9/v1.0 payload will not
render there, and the spec has already moved to v1.0 upstream.

## Wire format (v0.8)

A flat list of messages. Source: the v0.8 renderer fixtures in the A2UI repo,
`renderers/angular/src/v0_8/test_data/mocks/contact-card.json` — read those
rather than inferring, the shape is easy to get subtly wrong.

```json
[
  {"surfaceUpdate": {"surfaceId": "my-surface", "components": [
      {"id": "root",  "component": {"Card":   {"child": "col"}}},
      {"id": "col",   "component": {"Column": {"children": {"explicitList": ["name"]}}}},
      {"id": "name",  "component": {"Text":   {"text": {"literalString": "Ada"}, "usageHint": "h2"}}}
  ]}},
  {"beginRendering": {"surfaceId": "my-surface", "root": "root"}}
]
```

- Components are a flat list; they reference each other by **id string**. A
  dangling reference drops that subtree silently.
- `Text.text` takes either `{"literalString": "..."}` or `{"path": "/key"}`. The
  `path` form reads a separate `dataModelUpdate` message; the inline form needs
  no data model at all. GE renders the inline form today, and a deterministic
  renderer has no token pressure, so inline is usually right.
- v0.8 standard catalog: `AudioPlayer, Button, Card, CheckBox, Column,
  DateTimeInput, Divider, Icon, Image, List, Modal, MultipleChoice, Row, Slider,
  Tabs, Text, TextField, Video`
  (`https://a2ui.org/specification/v0_8/standard_catalog_definition.json`).
- **`Text` supports simple Markdown but explicitly excludes links.** `Button`
  dispatches a client-side *action*, it does not open a URL. So there is no
  "clickable link" primitive in v0.8 — render the URL as text, or accept that a
  Button means "ask the agent to do something", not "navigate".

### The A2A part it travels in

```python
Part(root=DataPart(data=<one message>, metadata={"mimeType": "application/json+a2ui"}))
```

One `DataPart` **per message** — that is what lets a client paint incrementally.

Mime, from `a2ui/a2a/parts.py`: v0.8 and v0.9 use `application/json+a2ui`;
`application/a2ui+json` is the newer spelling and will not be recognised by a
v0.8 client. The SDK calls the v0.8 one "deprecated" — use it anyway for GE.

## Path A — convert an already-deployed ADK agent

Use when you already have a working ADK agent and want widgets without
rewriting it. Rendering is deterministic Python; no model generates UI.

Why deterministic: everything worth drawing is already structured data in
session state. And it makes a no-invention guarantee *structural* — a value not
in state cannot be rendered. A hallucinated fact is a sentence; a hallucinated
fact wearing a button is worse.

Serve with `to_a2a()` (see **Migration blast radius**), then emit A2UI from an
`after_agent_callback` that reads state and returns `types.Content`.

ADK has no public API for emitting an A2A `DataPart`. It does have a documented
conversion (`google/adk/a2a/converters/part_converter.py:231-245`): inline_data
with mime `text/plain` whose bytes are a serialised `DataPart` between
`<a2a_datapart_json>` tags becomes a real `DataPart`.

```python
import json
from google.genai import types

def a2ui_parts(messages: list[dict]) -> list[types.Part]:
    parts = []
    for message in messages:
        payload = json.dumps(
            {"data": message, "metadata": {"mimeType": "application/json+a2ui"}}
        ).encode()
        parts.append(types.Part(inline_data=types.Blob(
            mime_type="text/plain",
            data=b"<a2a_datapart_json>" + payload + b"</a2a_datapart_json>",
        )))
    return parts
```

Returning `Content` from `after_agent_callback` **adds** an event — the model's
own text reply survives alongside the widget (verified on the wire: history
showed `agent [text]` and `agent [data, data]`). Return `None` when there is
nothing to draw, and wrap the whole renderer in try/except: a broken widget must
never cost the user their answer.

**`dict(callback_context.state)` raises `KeyError: 0`.** ADK's `State` has no
`keys()`, so `dict()` falls back to reading it as a sequence of pairs. Use
`.get()`. Verified live — and because the renderer swallowed it, the widget
silently never drew while every offline test passed.

## Path B — build an A2UI agent from scratch

Use when the UI is the point and you want the model to compose it. This is the
shape Google's own sample uses:
`samples/community/agent/adk/gemini_enterprise/v0_8/` in `github.com/google/a2ui`
(both `agent_engine/` and `cloud_run/` variants). Read it before writing code.

```bash
pip install a2ui-agent-sdk
```

The sample does **not** use `to_a2a`. It implements an `AgentExecutor` directly:

```python
from a2ui.a2a import try_activate_a2ui_extension, parse_response_to_parts
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog

schema_manager = A2uiSchemaManager(version="0.8", catalogs=[BasicCatalog.get_config("0.8")])
instruction = schema_manager.generate_system_prompt(
    role_description=..., workflow_description=..., ui_description=..., include_schema=True,
)
```

Key pieces:
- `generate_system_prompt()` teaches the model the catalog and ends with
  "Respond ONLY with the A2UI JSON array."
- The model emits JSON inside `<a2ui-json>` tags; `parse_response_to_parts` /
  `A2uiPartConverter` validate it against the catalog and repair what they can.
- `try_activate_a2ui_extension(context, agent_card)` negotiates the extension per
  request — clients that don't ask for A2UI must still get text.
- Widget interactions arrive back as a `DataPart` whose `data` contains
  `userAction`. Check for it before treating the turn as free text.

**Choosing between the paths:** if the data is already structured, Path A is
cheaper, faster, and cannot hallucinate. If the UI must adapt to open-ended
requests, Path B is the only option — but every widget is then model output, so
whatever guarantees you have about not inventing facts must survive being
expressed as a prompt.

## Agent card

```json
{
  "protocolVersion": "0.3.0",
  "name": "my-agent",
  "url": "https://REPLACE-AT-RUNTIME/",
  "capabilities": {
    "streaming": true,
    "extensions": [{
      "uri": "https://a2ui.org/a2a-extension/a2ui/v0.8",
      "required": false,
      "params": {"supportedCatalogIds": [
        "https://a2ui.org/specification/v0_8/standard_catalog_definition.json"]}
    }]
  }
}
```

`required: false` is what preserves the plain-text fallback. `streaming: true`
is needed for incremental painting.

**Build the card in code, not as a file path.** `to_a2a(agent_card=<path>)` uses
the card verbatim (`agent_to_a2a.py:203-205`) and its `host`/`port`/`protocol`
arguments only feed the builder that runs when *no* card is given. A static card
therefore advertises whatever `url` is on disk — usually `localhost`. Load the
JSON, inject `url` from the environment, pass the `AgentCard` object.

Register the card the **service serves**, not the file in the repo:

```bash
CARD=$(curl -sf -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "$SERVICE_URL/.well-known/agent-card.json")
python3 -c "import json,sys; assert json.loads(sys.argv[1])['url'].startswith('https://')" "$CARD"
```

Then POST `{"a2aAgentDefinition": {"jsonAgentCard": "<card as a JSON string>"}}`
to the `.../assistants/default_assistant/agents` endpoint. Registration still
does not make the agent visible — sharing is console-only (see main SKILL.md).

## Migration blast radius (Path A, or any move off Agent Runtime)

`to_a2a()` builds its default runner with `InMemorySessionService`,
`InMemoryMemoryService`, `InMemoryArtifactService`
(`agent_to_a2a.py:157-165`). On Cloud Run that means state dies when an instance
recycles and Memory Bank never receives anything. Pass an explicit `Runner`.

**`app_name` is the Memory Bank scope key.** The Agent Runtime template defaults
it to `GOOGLE_CLOUD_AGENT_ENGINE_ID`
(`vertexai/agent_engines/templates/adk.py:995-1001`). Any other value orphans
every memory already written — `preload_memory` returns nothing, with no error.
Set `app_name` to the engine id.

**There is no authenticated user.** `to_a2a` builds a bare `Starlette` with no
`AuthenticationMiddleware`, so `request.user` raises, gets suppressed to
`UnauthenticatedUser` (`user_name == ''`), and `_get_user_id`
(`request_converter.py:66-76`) falls through to `f'A2A_USER_{context_id}'` — a
per-conversation id, not a person. Verified live: an agent that guards on
identity refuses every turn.

**Measured 2026-07-28 against a live GE call: Gemini Enterprise forwards NO
end-user identity to an A2A agent.** The request carried only:

```
a2a-extensions, accept, cache-control, content-length, content-type, forwarded,
host, traceparent, user-agent, x-a2a-extensions, x-cloud-trace-context,
x-forwarded-for, x-forwarded-proto, x-serverless-authorization
```

with empty message metadata and an unauthenticated principal. `x-serverless-authorization`
is the **Discovery Engine service agent** — identical for every user. Never use
it as an identity: that is the one value that genuinely collapses every user
into a single memory scope.

Two ways forward, and the choice is a product decision, not a technical one:

- **Conversation-scoped (works immediately).** Accept ADK's
  `A2A_USER_{context_id}`. `context_id` is a per-conversation UUID, so this
  **fragments** the scope into one private bucket per conversation rather than
  collapsing it. No user can see another's data; the cost is that a returning
  user starts fresh, because their next conversation is a new id. Note the
  asymmetry: fragmenting is forgetful, collapsing is a leak. Guard against the
  *collapsing* values (`default-user-id`, empty) and let the fragmenting one
  through — a guard that refuses the sentinel simply takes the agent offline.
- **Real per-user identity.** Set `authorizationConfig.agentAuthorization` on
  the GE registration. GE then runs a Google OAuth flow and forwards a user
  access token — but it is **opaque**, so recovering the email needs token
  introspection on every call.

If a header ever does appear, lift it from `call_context.state['headers']`
(populated at `a2a/server/apps/jsonrpc/jsonrpc_app.py:151`) via
`A2aAgentExecutorConfig(request_converter=...)`, which both executor paths
honour (`a2a_agent_executor.py:211`). Accept only proxy-managed names
(`x-goog-*`) — a header like `x-user-email` is not stripped by any proxy, so any
caller could assert someone else's identity with it.

**GE does negotiate the A2UI extension**: the same call carried `a2a-extensions`
and `x-a2a-extensions`.

Sessions/Memory Bank both need an `agent_engine_id`, so the Agent Runtime
instance stays provisioned as the store even after serving moves to Cloud Run.
Don't delete it.

## Getting structured data into the renderer

`output_key` on an agent with an `output_schema` stores the **parsed object**,
not the JSON string — `llm_agent.py:989-996` runs `validate_schema` before
writing `state_delta[output_key]`. So a renderer reads `state["companies_data"]`
as a dict, no `json.loads` needed.

Without a schema, `output_key` stores whatever prose the model wrote. That is
the usual reason a card cannot be built from an existing agent: `output_key`
alone gives you text, and text is not drawable. Adding the schema is what turns
an existing specialist into something a renderer can use — subject to the
Search-tool conflict in the blockers table.

Read state through `.get()`, never `dict(state)` — ADK's `State` has no
`keys()`, so `dict()` raises `KeyError: 0`.

## The return leg — handling a button press

**Confirmed working in Gemini Enterprise, 2026-07-28.** Only `Button` carries an
`action`; `TextField`, `CheckBox`, `MultipleChoice` and `Slider` bind to the
client data model and **cannot notify the agent at all**. So a Button is the
only way anything a user does gets back to you — including anything they typed,
which must ride along in that Button's `action.context` as a `path` reference.

Outbound, a button looks like this (`action.name` is required; `context` is a
list of key/value pairs, each value a literal or a data-model path):

```json
{"id": "greet-sug0", "component": {"Button": {
  "child": "greet-sug0-label",
  "action": {"name": "ask",
             "context": [{"key": "question",
                          "value": {"literalString": "Who should I message?"}}]}}}}
```

Inbound, GE sends **two parts in the same user turn**. The real payload, copied
from a live session event log:

```json
{"data": {"userAction": {
    "name": "ask",
    "surfaceId": "greet",
    "sourceComponentId": "greet-sug0",
    "timestamp": "2026-07-28T07:02:26.921Z",
    "context": {"question": "Who should I message?"}}},
 "kind": "data",
 "metadata": {"mimeType": "application/json+a2ui", "is_user_input": true}}
```

Note `context` arrives as a **flat object**, not the key/value list you sent —
bindings are resolved client-side before dispatch.

**GE also sends a companion text part reading `"User action triggered."`** That
string is GE's own transcript placeholder, not something you emitted. Do not
route on it, and do not treat a turn as free text merely because a text part is
present — check for the DataPart first.

**How it reaches an ADK agent.** An inbound `DataPart` carrying no ADK metadata
is converted to an `inline_data` Blob, mime `text/plain`, whose bytes are the
serialised DataPart between `<a2a_datapart_json>` tags
(`part_converter.py:176-183`) — the same envelope you use outbound. So it is
**not** on `part.text`; a handler that only reads text parts will never see it:

```python
raw = "".join(
    (p.inline_data.data or b"").decode("utf-8", "replace")
    for p in (content.parts or []) if p.inline_data)
```

Parse that deterministically in a `before_agent_callback` and short-circuit the
turn. Letting the model interpret raw `userAction` JSON is strictly worse: it
already knows which button was pressed and what it carried, and a model asked to
re-derive that will sometimes answer the question instead of performing the
action.

## Debugging a card that will not draw

GE gives you exactly one signal, and it is in the chat, not the logs: a red box
reading **"This content could not be displayed."**, a short fragment string, and
*Report to agent* / *Dismiss* buttons. The agent's text reply renders normally
above it — so a broken widget looks like a working agent with a red box stapled
underneath, and nothing at all appears in Cloud Logging.

The fragment is the useful part. Observed 2026-07-28: **``se`body` ``** on a card
whose Column node had `id: "body"`. Read the fragment as naming the offending
component id.

**Do not name a component `body`.** It is also a valid `Text.usageHint` value,
and the official v0.8 fixture names that node `main-column`, never `body`.
Treat `body`, `root`, `title`, `head`, `html`, `main` as reserved.

**Namespace every id per surface.** Several surfaces can render in one turn
(e.g. an upload prompt, a results card and a status board), and each naively
built card wants to call its wrapper `root`. Prefix ids with the surface name
and assert uniqueness across the whole message list in a test — a duplicate id
across two surfaces is invisible offline.

Check enums against the catalog rather than guessing; a bad enum fails the same
silent way:
- `Text.usageHint` ∈ `h1 h2 h3 h4 h5 caption body`
- `Column.alignment` / `Row.alignment` ∈ `center end start stretch`

And check every `child` / `children.explicitList` reference resolves to a
component that exists in the same `surfaceUpdate`. A dangling reference drops
the subtree silently rather than erroring.

## Blockers that only appear at runtime

| Symptom | Cause | Fix |
|---|---|---|
| `400 INVALID_ARGUMENT: controlled generation is not supported with Search tool` | `output_schema` on an agent holding `google_search`. ADK's `output_schema` docstring claims schema and tools compose; for the Search built-in they do not. | Split into a `SequentialAgent`: search agent (tool, prose) → structuring agent (no tools, `output_schema`). |
| Container dies, `failed to start and listen on port 8080`, no useful trace |
 `google-adk[a2a]` pulls `a2a-sdk` **without** its `http-server` extra, so `sse-starlette` is missing. `A2AStarletteApplication` raises at *construction*, inside lifespan startup — every import-level test passes. | Add `a2a-sdk[http-server]`. Assert `import sse_starlette` in tests, not just the ADK import. |
| `gcloud run deploy --source .` ignores your Dockerfile | gcloud only uses a Dockerfile at the **root** of the source dir; nested, it silently falls through to Buildpacks. No flag points at a nested one. | Put the Dockerfile at the repo root. Confirm the log says "Building using Dockerfile". |
| A secret ships inside the image | `.dockerignore` is **root-anchored**, unlike `.gitignore`. A bare `.env` matches only a top-level `.env`. | Use `**/.env`. Entries like `docs/` work only because they happen to sit at the context root. |
| Widget never appears, no error anywhere | `dict(callback_context.state)` → `KeyError: 0`, swallowed by the renderer's own guard. | `.get()` on the State. Keep the guard; add a test with a State-like double. |
| Red "This content could not be displayed" box under an otherwise-normal reply | A component id or enum GE's validator rejects. Nothing is logged server-side. | Read the fragment in the box — it names the offender. See **Debugging a card that will not draw**. |
| An orchestrator answers with its own tool instead of delegating, so the specialist never runs and its state key is never written | A root agent holding a fallback function tool will often use it directly rather than calling the specialist that would have produced the structured data. | Either generate the value deterministically in the renderer, or don't give root a tool that duplicates the specialist's job. |

## Worked example: structured output from a search agent

The split the blockers table prescribes. The search half keeps the built-in and
writes prose to `output_key`; the structuring half has **no tools**, reads that
prose with `{key?}` templating, and re-emits it under `output_schema`. Wrapping
both in a `SequentialAgent` means callers invoke one thing and the structuring
cannot be skipped.

```python
from google.adk.agents.llm_agent import Agent
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.tools import google_search

# Plain dict schema — no Pydantic needed.
COMPANIES_SCHEMA = {
    "type": "object",
    "properties": {
        "companies": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "why_it_fits": {"type": "string"},
                    "url": {"type": "string",
                            "description": "Omit entirely rather than guessing."},
                },
                "required": ["name", "why_it_fits"],
            },
        }
    },
    "required": ["companies"],
}

search = Agent(
    model="gemini-2.5-flash",
    name="company_search_agent",
    instruction="Research companies that fit this student...",
    tools=[google_search],          # built-in, alone. No output_schema here.
    output_key="companies",         # prose
)

structure = Agent(
    model="gemini-2.5-flash",
    name="company_structure_agent",
    instruction=(
        "Convert the shortlist below into the required JSON.\n\n"
        "Shortlist:\n{companies?}\n\n"
        "Copy only what the shortlist already says. You are reformatting, not"
        " researching: add no company and no link that does not appear above,"
        " and never repair a partial URL into a plausible one."
    ),
    output_schema=COMPANIES_SCHEMA,  # no tools, so controlled generation is legal
    output_key="companies_data",     # structured — this is what a renderer draws
)

company_agent = SequentialAgent(
    name="company_agent",
    description="Recommends companies that fit the student's profile.",
    sub_agents=[search, structure],
)
```

Two consequences worth planning for:

- **The `SequentialAgent` has no `output_key` of its own** — the keys live on its
  sub-agents. Structural tests that iterate your specialists and assert
  `agent.output_key` must flatten `sub_agents` first, or they will crash on the
  wrapper. The same flattening is what keeps the one-built-in-per-agent
  assertion reaching the leaves.
- **The structuring agent can only reformat what the search agent wrote.**
  Anything produced by a *different* tool — e.g. fallback links generated by a
  function tool the search agent cannot hold, because it already holds a
  built-in — never reaches the prose and so never reaches the structured output.
  Either generate those values deterministically in the renderer, or pass them
  through state explicitly. Verified the hard way: an orchestrator answered with
  fallback links from its own tool, the specialist never ran, and the widget had
  nothing to draw.

## Verification methods

| Claim | Verified how | Re-check with |
|---|---|---|
| A2UI needs `a2aAgentDefinition` | GE doc page, 2026-07-28 | refetch the register-and-manage page |
| v0.8 only; mime `application/json+a2ui` | GE doc + `a2ui/a2a/parts.py` source | read `parts.py` in the a2ui SDK |
| Wire format, component names | v0.8 renderer fixtures in `google/a2ui` | `gh api repos/google/a2ui/contents/renderers/angular/src/v0_8/test_data/mocks/contact-card.json` |
| DataPart emission via tag-wrapped inline_data | **live A2A call — real DataParts returned** | POST `message/send`, inspect `artifacts[].parts[].kind == "data"` |
| `output_schema` + `google_search` → 400 | **live Gemini API error** | attach a schema to a search agent and call it |
| missing `sse-starlette` | **live container crash** | deploy without `a2a-sdk[http-server]` |
| in-memory runner defaults, `app_name`, `_get_user_id` | ADK source, cited above | read the cited lines |
| GE forwards no end-user identity; negotiates the A2UI extension | **live GE call, 2026-07-28** | log header names in the request converter |
| **GE painting the widget; buttons returning `userAction`** | **live GE web app, 2026-07-28 — both confirmed** | send a message, tap a button, read the session events |
