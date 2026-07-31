# A2UI in Gemini Enterprise — Design

- **Date:** 2026-07-27
- **Status:** Approved (design). Not yet planned or built.
- **Scope:** Make Job Helper Agent render rich, interactive UI natively in the
  Gemini Enterprise chat surface, instead of plain markdown.

## Goal

Four surfaces the student should get instead of text:

1. **Pipeline board** — tracked applications as a status board, not a text dump.
2. **Clickable results** — company and alumni results as cards with verified
   links and act-on-it buttons.
3. **Live progress** — visible indication of which specialist is running.
4. **Resume upload** — attach a PDF/DOCX instead of pasting resume text.

## Background: how A2UI works

A2UI (Agent-to-UI) is an open protocol where the agent returns a JSON
description of a UI rather than text. Gemini Enterprise validates that JSON
against its own component catalog and renders it in GE's design language.

The runtime loop:

1. GE calls the agent's A2A endpoint, passing GE's A2UI catalog.
2. The agent replies with a flat list of A2UI messages — `beginRendering`,
   `surfaceUpdate`, `dataModelUpdate` — carried in an A2A `DataPart` with MIME
   type `application/json+a2ui`.
3. When the student interacts with a widget, **GE serializes the interaction
   and sends it back as the next conversational turn.** There is no separate
   callback channel; it is the same chat loop with structured input.

Because the payload is a flat list of small messages, it can be emitted
incrementally and painted as it arrives — this is the mechanism behind goal 3.

### The constraint that drives everything

A2UI rendering **requires the agent be registered with GE via the A2A path**
(`a2aAgentDefinition`). Agents deployed to Vertex AI Agent Engine and
registered via `adkAgentDefinition` — which is how Job Helper Agent ships
today — do not support A2UI rendering.

So this is not a UI feature added on top. It is a runtime migration:
`adk deploy agent_engine` → containerized A2A server on Cloud Run, re-registered
in GE as an A2A agent.

GE supports **A2UI v0.8 only**.

## Decision 1: rendering is deterministic Python, not LLM-generated

The documented ADK path injects `A2uiSchemaManager.generate_system_prompt()`
into the agent's instruction and has the model emit A2UI JSON directly. We are
**not** doing that.

Rejected alternatives:

- **Root orchestrator emits A2UI.** The root already carries eight `AgentTool`
  specialists plus the full `NO_INVENTION` / `REAL_PEOPLE_RULES` block. The
  A2UI system prompt ends with *"Respond ONLY with the A2UI JSON array."* That
  puts orchestration, safety rules, and schema-valid JSON generation in
  competition for one model's attention.
- **A `render_agent` specialist.** Better — orchestration stays clean — but
  still puts a language model in the rendering path.

Chosen: **plain Python builder functions that read session state and emit v0.8
component JSON.**

Rationale:

- Every surface requested is structured data the specialists already write to
  session state. There is nothing for a model to compose.
- It makes rule 4 structural rather than prompted. Under an LLM-generated UI, a
  hallucinated alumni link stops being text and becomes a **clickable button**.
  Under deterministic rendering, a link that is not in state cannot be
  rendered — `NO_INVENTION` is enforced by construction.
- It fits the existing rules: plain Python I/O (rule 5), state via `output_key`
  (rule 2), no prompt bloat on the root (rule 3), v0.8 components only.

The cost is rigidity: the UI looks how it was coded. For four fixed surfaces
that is the correct trade. Free-form replies (coaching, clarifying questions)
stay plain markdown, which GE renders as the natural fallback.

## Decision 2: two tickets, host hardening first

Leaving the managed Agent Engine runtime silently breaks three things that
`callbacks.py` and `tools.py` depend on. Verified by reading the installed
`google-adk==2.4.0` source.

`to_a2a()` builds its default runner with `InMemorySessionService`,
`InMemoryMemoryService`, and `InMemoryArtifactService`
(`google/adk/a2a/utils/agent_to_a2a.py:157-165`).

Identity resolves as (`google/adk/a2a/converters/request_converter.py:66-77`):

```python
def _get_user_id(request: RequestContext) -> str:
    if (request.call_context and request.call_context.user
            and request.call_context.user.user_name):
        return request.call_context.user.user_name
    return f'A2A_USER_{request.context_id}'
```

### Regression 1 — identity stops identifying the student

`callbacks.py` rests on a verified fact: GE sends the end user's email as
`user_id`. That is the **Agent Engine template's** behavior
(`vertexai/agent_engines/templates/adk.py:102`). On a Cloud Run A2A server
without auth enabled, `user_id` becomes `A2A_USER_{context_id}` — a
per-conversation identifier, not a person.

`require_real_user` rejects only the literal `default-user-id`. It sees
`A2A_USER_abc123`, passes it, and **the privacy guard silently stops
guarding** — the same class of failure it was written to prevent, under a
different sentinel value.

### Regression 2 — cross-session memory dies quietly

`remember_session` calls `add_session_to_memory()`, which post-migration writes
to an `InMemoryMemoryService` that vanishes with the container. The callback
deliberately swallows exceptions, so this fails with no error and no log of
substance. `list_applications` documents that earlier-visit history reaches the
student via the orchestrator's memory service; post-migration there is no
earlier visit.

### Regression 3 — the tracker can lose state mid-conversation

`track_application` stores `applications` in session state, now backed by
`InMemorySessionService`. Cloud Run runs multiple instances and recycles them.
If a subsequent turn lands on a different instance, the pipeline board is
empty. The headline UI surface is the most exposed.

### Resolution

Pass explicit services into `to_a2a(runner=...)` rather than accept defaults:

| Concern | Default (broken) | Required |
|---|---|---|
| Session state | `InMemorySessionService` | `VertexAiSessionService` (or `DatabaseSessionService`) |
| Memory | `InMemoryMemoryService` | `VertexAiMemoryBankService` |
| Identity | `A2A_USER_{context_id}` | Auth enabled so `call_context.user.user_name` is the real email |

And **tighten `require_real_user` to reject any `A2A_USER_*` value** in addition
to `default-user-id`. Without this, the migration ships with the guard disabled.

This is why the work splits in two. Shipping it as one ticket lands a pretty
pipeline board that forgets its students.

## Architecture

```
Gemini Enterprise chat
   │  A2A JSON-RPC (+ GE's A2UI catalog, X-A2A-Extensions)
   ▼
Cloud Run: main_a2a.py  ──  to_a2a(root_agent, runner=hardened_runner)
   │                          ├─ VertexAiSessionService
   │                          ├─ VertexAiMemoryBankService
   │                          └─ auth → real user email
   ▼
root_agent (gemini-2.5-pro)  ── 8 specialists via AgentTool  [UNCHANGED]
   │  writes: profile, companies, alumni, matches, gaps, applications
   ▼
a2ui.py  ── deterministic builders read session state → v0.8 JSON
   ▼
DataPart(mime="application/json+a2ui")
```

The eight-specialist graph, `AgentTool` wiring, `output_key` state passing, the
built-in/function-tool separation, and `NO_INVENTION` are all untouched. What
changes is the transport and the final presentation step.

### Components

| Component | Responsibility | Depends on |
|---|---|---|
| `main_a2a.py` | Build the hardened runner; expose the A2A Starlette app | ADK, a2a-sdk |
| `Job_Helper_agent/a2ui.py` | Pure functions: session state → A2UI v0.8 JSON | nothing (plain dicts) |
| A2UI emit hook | Wrap builder output as a `DataPart` with the A2UI MIME type | `a2ui.py` |
| `agent_card.json` | Declare the `a2ui/v0.8` extension and `streaming: true` | — |
| `callbacks.py` | Identity guard, widened to reject `A2A_USER_*` | — |

`a2ui.py` is the deep module here: one function per surface, each taking plain
dicts from state and returning plain dicts of A2UI JSON. No ADK imports, no
network, no model — which makes it trivially unit-testable in the repo's
existing no-network structural style.

### Agent card

```json
{
  "protocolVersion": "0.3.0",
  "name": "job-helper-agent",
  "capabilities": {
    "streaming": true,
    "extensions": [{
      "uri": "https://a2ui.org/a2a-extension/a2ui/v0.8",
      "required": false,
      "params": {
        "supportedCatalogIds": [
          "https://a2ui.org/specification/v0_8/standard_catalog_definition.json"
        ]
      }
    }]
  }
}
```

`required: false` matters — it lets the agent degrade to plain text for any
client that does not negotiate A2UI.

## Data flow per surface

| Surface | State key | Written by | Components | Interaction |
|---|---|---|---|---|
| Pipeline board | `applications` | `tools.py:track_application` | `Card` + `List` + `Text` | Status buttons → next turn calls `track_application` |
| Company shortlist | `companies`, `matches` | `company_agent`, `matching_agent` | `Card` + `Button` | "Track this" → `track_application` |
| Alumni cards | `alumni` | `alumni_agent` (verified by `verification_agent`) | `Card` + `Button(link)` | "Draft outreach" → `outreach_agent` |
| Live progress | — | emitted per specialist invocation | incremental `surfaceUpdate` | none |
| Resume upload | `profile` | `profile_agent` | GE native attachment | see below |

Widget interactions arrive as ordinary user turns containing structured text.
The root orchestrator routes them like any other request — no new dispatch
mechanism.

## Resume upload — unresolved, with a designed fallback

Whether GE forwards a chat attachment to an A2A agent as a `FilePart` is **not
documented** in the GE A2UI docs, the ADK A2UI integration guide, the Cloud Run
hosting tutorial, or the codelab. The codelab covers `save_artifact()` for
agent-*generated* files, not user uploads.

This is resolved by a spike, not by assumption. Until then the design is:

- `profile_agent` accepts a `FilePart` if one is present in the incoming
  message and extracts resume text from it.
- If no `FilePart` arrives, it falls back to the current behavior — pasted
  resume text — and the A2UI card prompts for a paste.

The feature works either way; the spike decides which path is live. If GE does
not forward attachments, goal 4 degrades to "prompted paste" rather than
failing, and that limitation gets recorded rather than silently dropped.

## Error handling

- **Invalid A2UI JSON.** Builders validate against the v0.8 catalog before
  emitting. On validation failure, fall back to the existing markdown answer.
  A broken widget must never cost the student their answer — the same principle
  `remember_session` already applies to memory writes.
- **Missing state.** Every builder handles an absent or empty state key by
  returning `None`, and the caller falls back to text. A student who has not
  run matching yet must not get an empty board rendered as if it were real.
- **Client does not negotiate A2UI.** `required: false` on the extension means
  plain text. Verified by testing with A2UI negotiation off.
- **Identity missing or synthetic.** `require_real_user` blocks the turn
  loudly, as today, now including `A2A_USER_*`.
- **Memory write failure.** Unchanged — best-effort, logged, never fatal.

## Testing

Consistent with `test_agent.py`: structural, no network.

- `a2ui.py` builders are pure functions — assert JSON shape against the v0.8
  catalog for each surface, given fixture state dicts.
- Assert every builder returns `None` for empty/missing state.
- Assert no builder can emit a link absent from its input state — the
  structural expression of `NO_INVENTION`.
- Assert the agent card declares the A2UI extension and `streaming: true`.
- Assert `require_real_user` rejects `default-user-id` **and** `A2A_USER_*`.
- Assert the runner passed to `to_a2a` uses persistent session and memory
  services, not the in-memory defaults. This is the regression guard for the
  three failures above.
- Keep the existing built-in/function-tool separation assertion green.

Live verification (not automated): deploy to Cloud Run, register in GE, confirm
each surface renders, and confirm a widget click arrives back as a turn.

## Ticket breakdown

**Ticket 1 — A2A host that preserves state and identity.** Migrate to Cloud Run
via `to_a2a` with explicit persistent session and memory services, real user
identity via auth, and a widened `require_real_user`. Register in GE via
`a2aAgentDefinition`. Grant `roles/run.invoker` to the Discovery Engine service
agent. No UI work. Ships when the agent behaves exactly as it does today, from
a new runtime.

**Ticket 2 — A2UI rendering.** Add `a2ui.py` builders, the `DataPart` emit
hook, and the agent card extension. Four surfaces, text fallback throughout.

Ticket 1's exit criterion is behavioral parity, which makes any regression in
ticket 2 unambiguously a UI bug.

## Risks

| Risk | Mitigation |
|---|---|
| GE pins A2UI v0.8; the spec is young and moving | Builders emit v0.8 only; version asserted in tests |
| `to_a2a` is marked `@a2a_experimental` in ADK 2.4.0 | Pin the ADK version; agent card `required: false` keeps text working |
| GE may not forward file attachments | Spike; pasted-text fallback ships regardless |
| Cloud Run cold starts on a `gemini-2.5-pro` root | Set min instances; measure before tuning |
| Deterministic UI cannot adapt to unanticipated answers | Intentional. Free-form replies stay markdown |
| Two live registrations during migration | Retire the Agent Engine registration only after parity is verified |

## Out of scope

- Any front end outside Gemini Enterprise.
- LLM-generated / adaptive UI.
- Changes to the eight specialists' reasoning, instructions, or models.
- Charts and data visualization — not among the four goals.
