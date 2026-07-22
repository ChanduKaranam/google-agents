# Placement Intelligence Agent — Design

**Date:** 2026-07-22
**Status:** Spike 0 closed; ready for implementation planning. Every
architecturally load-bearing assumption has been measured against the live
Gemini Enterprise + Agent Runtime stack, not inferred from docs — see §4.1,
§2.1, §3.5.
**Scope:** MVP slice of the Placement Intelligence Agent PRD v1.0
**End goal:** deployed to Agent Runtime, registered as a custom agent in a
Gemini Enterprise app, used by students.

## 1. Scope

This spec covers **the ADK agent system**, delivering the PRD's eight
functional modules as a multi-agent app. It is developed locally through
`adk web` and deployed to Agent Runtime for real users.

Because Gemini Enterprise is the destination rather than a later idea, this
design is constrained by the deployed runtime from the start. Several things
that would be fine in a local-only MVP are not deferrable (§3.5, §4.1, §7).

**Resumes are never stored.** The student uploads their resume each session;
it is read, structured, and discarded. Only application history persists
(§3.4). This is a privacy decision, not a cost one — a thousand resumes is
about a gigabyte, which is pennies; the reason not to keep them is that a
durable store of student PII is an obligation with no product benefit.

Explicitly **out of scope** for this slice:

- Next.js frontend (Gemini Enterprise *is* the UI)
- FastAPI backend (Agent Runtime serves the agent)
- Firebase Auth (Gemini Enterprise supplies user identity — §3.6)
- Vertex AI Vector Search / Pinecone, `text-embedding-004`
- Greenhouse / Lever job-board APIs
- Everything in PRD section 12 (Future Enhancements)

## 2. Environment

Verified 2026-07-22 against the project's `.venv` and the live GEAP docs.
Claims below cite either a doc URL or an installed-source `file:line`; nothing
here is from memory, because this platform was renamed in 2026 and recalled
URLs and API fields for it are unreliable.

- `google-adk==2.4.0`, Python 3.12, model `gemini-2.5-flash`
- Local: `adk web`. Deployed: Agent Runtime (`reasoningEngines/<id>`)
- Registration: Gemini Enterprise → app → Agents → Add agent → Custom agent
  via Agent Platform

### 2.1 Local and deployed are different code paths

This is the single most important environmental fact, and the source of most
of the risk in this design.

`adk web` invokes the agent through the local runner. Gemini Enterprise
invokes `streaming_agent_run_with_events`
(`vertexai/agent_engines/templates/adk.py:1294`; its docstring states it *"is
primarily meant for invocation from AgentSpace"* — AgentSpace being Gemini
Enterprise pre-rename). That method takes a different request envelope
(`message`, `events`, `artifacts`, `authorizations`, `user_id`, `session_id`
— `:188-217`) and, on the branch where no `session_id` is supplied, **creates
a fresh session per call** (`:777-805`).

`adk deploy agent_engine` does register this method on the deployed resource
(`google/adk/cli/cli_deploy.py:374-391`, applied at `:1222`), so the path is
live. But it is never exercised locally. **Anything verified only through
`adk web` is unverified for production.**

**Measured 2026-07-22 — the feared behaviour does not occur.** Two consecutive
turns in one Gemini Enterprise conversation reused a single session
(`3754369520618176512`, one session listed for the user, event count 2 → 6).
GE passes a stable `session_id`, so the fresh-session-per-call branch is not on
our path and `output_key` + `{key?}` works across turns as designed.

Two caveats on that result. Session *state* persistence is strongly implied but
not directly proven — the probe never wrote state, so `state_keys` was empty
both turns; the real agent's first deploy confirms it (§8.3). And this section's
general warning stands: the code path is still different from local, so
"works in `adk web`" remains insufficient evidence for anything else.

## 3. Architecture

### 3.1 Topology

A single root `LlmAgent` (the Orchestrator) holds eight specialists, each
wrapped in `AgentTool`. The root retains control for the whole conversation;
specialist results return into the root's context, where the root aggregates
and replies.

`AgentTool` was chosen over `sub_agents` transfer because the root must
aggregate across several specialists in one turn. It was chosen over a fixed
`SequentialAgent` pipeline because the student must be able to ask ad-hoc
questions without re-running the whole flow.

This shape is independently confirmed as Google's own pattern for built-in
tools: `google/adk/cli/built_in_agents/adk_agent_builder_assistant.py:89`
states *"ADK's built-in tools (google_search, url_context) are designed as
agents"*, and `:95-98` wraps such an agent in `AgentTool`.

### 3.2 File layout

```
placement_agent/
  __init__.py        # from . import agent
  agent.py           # eight specialists + root_agent
  tools.py           # track_application, list_applications
  callbacks.py       # user_id assertion (§3.6)
  requirements.txt   # read by `adk deploy agent_engine`
  .env               # read by `adk deploy agent_engine`
spikes/
  spike0_upload/     # throwaway probe agent (§4.1) — delete once §9 closes
test_agent.py
```

`requirements.txt` and `.env` live in the agent folder from day one because
`adk deploy agent_engine` reads them from there. Adding them now costs
nothing; retrofitting means re-verifying every pin at deploy time.

### 3.3 Agents and within-turn memory

Each specialist declares an `output_key`; downstream specialists read it via
`{key?}` optional instruction templating. Verified in the installed source:
`output_key` writes to session state at `google/adk/agents/llm_agent.py:996`,
and `{key?}` yields an empty string for an absent key
(`google/adk/utils/instructions_utils.py`, `_replace_match`).

| Agent | Reads from state | `output_key` | Tools |
|---|---|---|---|
| `profile_agent` | — | `profile` | — |
| `company_agent` | `profile` | `companies` | `google_search` |
| `alumni_agent` | `profile` | `alumni` | `google_search` |
| `matching_agent` | `profile`, `alumni` | `matches` | — |
| `resume_gap_agent` | `profile` | `gaps` | `url_context` |
| `outreach_agent` | `profile`, `matches` | — | — |
| `tracker_agent` | — | — | `track_application`, `list_applications` |
| `coach_agent` | `profile`, `gaps`, `applications` | — | — |

`outreach_agent` and `coach_agent` have no `output_key` because their output
is prose for the student, not input to another agent.

**Scope of this mechanism: one turn only.** Per §2.1, session state cannot be
assumed to survive between turns in production. Everything above is *intra-turn
plumbing* — correct for "find companies, then alumni at the top three, then
rank them" within a single student request. It is not the durable store.

### 3.4 Durable memory: Memory Bank

**Resumes are never stored** (§4.1), so the profile is re-extracted from a
fresh upload each session and needs no durable home. What *cannot* be
re-derived from a resume is the student's application history — what they
applied to, current status, which alumni they contacted. That is the only
durable data in this system.

It is also small: a few KB per student, and it carries no PII beyond company
and contact names. Thousands of students is megabytes, not gigabytes.

Memory Bank is the documented home for this
(`docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank`):
it stores LLM-distilled facts scoped per identity and isolated across
identities (*"Memory consolidation and retrieval is isolated to a specific
identity"*), with similarity search and TTL expiry. ADK reads and writes it
through `VertexAiMemoryBankService`
(`google/adk/memory/vertex_ai_memory_bank_service.py:172`; scope built at
`:348`/`:423` as `{'app_name', 'user_id'}` against the `reasoningEngines` id).

Wiring:

- Deploy with `--memory_service_uri agentengine://<resource-id>`. No GCS
  bucket and no Cloud Storage role required.
- `PreloadMemoryTool` (`google/adk/tools/preload_memory_tool.py:32`)
  auto-injects the user's memories each turn — use this on the **root**, so a
  returning student's application history is present without being asked for.
- `tracker_agent` writes each application to Memory Bank as it is recorded.

**Explicitly not stored:** the resume PDF, and the extracted profile. Both are
regenerated per session from the student's upload. This is a deliberate
privacy choice — a durable store of student resumes is a data-protection
obligation with no corresponding product benefit, since the student has the
file in hand anyway.

### 3.5 Gemini built-in tool constraint (hard, and unguarded)

A Gemini built-in tool (`google_search`, `url_context`) cannot share an
`LlmAgent` with custom function tools. **This is enforced by the Gemini API,
not by ADK — ADK raises nothing.** Verified in the installed source:

- `llm_agent.py:139-176` silently *rewrites* rather than validating, with the
  comment *"the built-in tools cannot be used together with other tools"* and
  `TODO(b/448114567)`.
- The auto-wrap escape hatch defaults to **off**:
  `google/adk/tools/google_search_tool.py:43` `bypass_multi_tools_limit: bool
  = False`, and the module-level `google_search` singleton is built with
  defaults, so it is inert.
- `url_context` has **no such workaround at all** — no bypass flag, no agent
  wrapper anywhere in the package.

So a misconfigured specialist fails at the API with an opaque model error,
possibly only in production. The §8 test asserts the constraint statically.

The table in §3.3 satisfies it: `company_agent`, `alumni_agent`, and
`resume_gap_agent` each carry exactly one built-in and nothing else;
`tracker_agent` carries only custom tools.

**Region caveat:** `docs.cloud.google.com/gemini/enterprise/docs/locations`
lists *"Grounding with Google Search — Only available in the global region"*
under Gemini Enterprise features. Whether that binds a `google_search` call
made from inside a deployed ADK agent is **NOT DOCUMENTED**. Deploy to
`global`/`us-central1` unless and until this is tested.

### 3.6 Identity and isolation

Gemini Enterprise supplies user identity: the registration doc's agent
governance table states *"ADK agents receive the user's email address from
Gemini Enterprise."*

The failure mode is silent and severe. `templates/adk.py:211-214` reads
`user_id`/`userId` from the request and **falls back to
`_DEFAULT_USER_ID = "default-user-id"` (`:102`) when absent**. Every session,
artifact, and Memory Bank scope keys off that value. If the field is ever
missing, every student's profile, applications, and memories silently merge
into one bucket — no error, no warning.

**Mitigation:** a `before_agent_callback` in `callbacks.py` that asserts
`user_id != "default-user-id"` and refuses the turn otherwise. Cheap, and it
converts a silent data-mixing bug into a loud failure.

## 4. Data flow

### 4.1 Resume ingestion — UNRESOLVED, gated behind Spike 0

**The design cannot be finalised here until this is tested.** Stated plainly
because the whole ingestion path depends on it.

What is verified:

- Gemini Enterprise end users can upload files, but every doc saying so
  describes *"the assistant"*
  (`docs.cloud.google.com/gemini/enterprise/docs/assistant-chat`).
- `register-and-manage-an-adk-agent` contains **zero** occurrences of
  `upload`, `attach`, `artifact`, `multimodal`, `inline_data`, or `pdf`.
- The transport nonetheless exists: the request envelope carries
  `artifacts: Optional[List[_Artifact]]` (`templates/adk.py:188-217`) where an
  artifact version is a genai `Part` (`:150-166`, so it can carry
  `inline_data` bytes + mime type), and these are saved via
  `artifact_service.save_artifact(...)` **before the runner runs** (`:807-836`,
  on both the new-session `:803` and existing-session `:1332` paths).
- ADK's documented mechanism for user-uploaded files is the artifact service
  plus `LoadArtifactsTool` (`adk.dev/artifacts/`), which lists available
  artifacts to the model and appends the selected contents to the request.

What is **not** verified: whether the Gemini Enterprise chat UI actually
populates `artifacts` (or an inline-data `Part`) for a turn routed to a
*custom* agent.

**Spike 0** — deploy a throwaway agent whose only tool logs
`tool_context.list_artifacts()` and dumps `message.parts`; register it in the
Gemini Enterprise app; upload a PDF; read the trace. One afternoon, and it
decides between Paths A and B below.

Spike 0 blocks **only** the root agent's ingestion instruction (roughly fifteen
lines) and the artifact-service decision. It does not block the eight
specialists, the tools, or the tests, because Paths A and B differ only in how
resume *text* reaches `profile_agent`. Build the agent system first if GCP
access is not yet in place; run Spike 0 before the ingestion instruction is
written.

**Resumes are ephemeral by design.** The student uploads the resume each
session; it is read, structured into `profile`, and never persisted. The
deployed default `InMemoryArtifactService` (`templates/adk.py:1003-1007`,
`:704`) is therefore the *correct* choice here rather than a landmine — the
artifact dies with the container, which is exactly what we want.

This removes an entire subsystem: no GCS artifact service, no
`--artifact_service_uri` flag, no `"user:"` cross-session namespace, no
retention or deletion policy, and no Cloud Storage IAM role (which the
deploying account does not have anyway — §8.4). Uploaded resumes are also
never written to disk, which matters because Agent Runtime has no persistent
disk at all.

Deploy flags that *are* needed, verified by running
`adk deploy agent_engine --help` against the installed 2.4.0:

| Flag | Value | Why |
|---|---|---|
| `--memory_service_uri` | `agentengine://<resource-id>` | Memory Bank for application history (§3.4) |
| `--session_service_uri` | set explicitly | unset falls back per `--use_local_storage` |

Note `--use_local_storage` *"cannot be combined with explicit service URIs"*,
and its help warns that when the agents directory isn't writable — *"common in
Cloud Run/Kubernetes"* — ADK silently falls back to in-memory. Set URIs
explicitly; do not rely on defaults.

**Path A — file reaches the agent. CONFIRMED on the ADK side 2026-07-22.**

Measured against the deployed probe: a PDF sent in the `artifacts` list of a
`streaming_agent_run_with_events` call arrives intact, and the agent's
`list_artifacts()` returns `["resume.pdf"]`.

Two things that measurement corrected:

- **The file is an artifact, not part of the message.** In the same call,
  `user_content.parts` contained only the user's text — no `inline_data`. So
  the root agent **cannot** read the PDF directly off `user_content`. It must
  hold `LoadArtifactsTool`
  (`google/adk/tools/load_artifacts_tool.py`), which lists available artifacts
  to the model and appends the selected content to the request when the model
  calls `load_artifacts`. This is a custom function tool, and the root holds no
  Gemini built-ins, so it does not collide with §3.5.
- **`session_id` is effectively required.** Omitting it crashes the deployed
  template server-side — `templates/adk.py:1367` → `:793` raises
  `AttributeError: 'NoneType' object has no attribute 'create_session'`,
  because the no-session branch reaches for an `in_memory_session_service` that
  was never initialised. The client sees an **empty stream and no error**. Any
  "the agent returned nothing" symptom in production should look here first.

So Path A is: root sees an artifact is present → calls `load_artifacts` to pull
the PDF into context → reads it multimodally → passes the extracted text to
`profile_agent` as the request string (`AgentTool` forwards only text, so the
root must be the one that sees the file). `profile_agent` structures it and
writes `profile` to session state via `output_key`. Nothing is persisted.

**CONFIRMED END-TO-END 2026-07-22 through the real Gemini Enterprise chat UI.**
A PDF attached by a signed-in user reached the registered custom agent:

```json
{"artifacts": ["Chetan_Kumar_Molli_Resume.pdf"],
 "user_id": "purna@tilicho.in", "user_id_is_default": false,
 "message_parts": [{"kind":"text","chars":13},
                   {"kind":"text","chars":61},
                   {"kind":"text","chars":59}]}
```

**How Gemini Enterprise presents an upload.** The user message arrives as three
*text* parts — no `inline_data` anywhere:

```
"run the probe"
"\n<start_of_user_uploaded_file: Chetan_Kumar_Molli_Resume.pdf>"
"<end_of_user_uploaded_file: Chetan_Kumar_Molli_Resume.pdf>\n"
```

**There is nothing between the start and end markers.** GE announces the file
and names it; the bytes go to the artifact service only. This makes
`LoadArtifactsTool` mandatory rather than merely convenient — without it the
root sees a marker naming a resume it cannot read, and the likely failure is a
*hallucinated* profile rather than an error. The root's instruction must
therefore state: when an uploaded-file marker is present, call
`load_artifacts` for that filename, and if the load fails, say so rather than
proceeding.

The marker filename is also the reliable signal that a resume was attached *on
this turn* — `list_artifacts()` is not, because artifacts persist for the whole
session (below).

**Artifacts persist across turns.** Measured: a second turn with no attachment
still reported `artifacts: ["Chetan_Kumar_Molli_Resume.pdf"]`. So the student
uploads **once per conversation**, not once per message, and a later turn
("now compare it to this JD") can re-load the same resume without a re-upload.
The root should load the artifact when it needs resume content and `profile` is
not already in state — not blindly on every turn.

**Path B — Spike 0 fails (file does not reach custom agents).** The student
pastes resume text, or provides a link to it. `profile_agent` takes the text
directly; the rest of the flow is unchanged. This is strictly worse UX and no
worse architecturally — which is why the rest of this spec does not depend on
which path we land on.

### 4.2 Job description ingestion

`resume_gap_agent` accepts a JD as pasted text **or** a URL. Its instruction:
if the input contains a URL, fetch it with `url_context`; otherwise treat the
input as JD text. `url_context` is a Gemini built-in, so Gemini fetches and
extracts the page itself — this handles JS-rendered job pages that a
`requests` + `BeautifulSoup` scraper would fail on, and adds no dependency.

### 4.3 Typical full flow

```
returning student            → root preloads profile from Memory Bank
new student, resume in hand  → root → profile_agent → state.profile + Memory Bank
  → company_agent                    → state.companies
  → alumni_agent (per target company) → state.alumni
  → matching_agent                   → state.matches
  → resume_gap_agent (text or URL)   → state.gaps
  → outreach_agent                   → messages, shown to student
  → tracker_agent                    → state.applications
  → coach_agent                      → recommendations
```

The root runs any subset. A student asking only "what's missing from my resume
for this JD" gets `resume_gap_agent` against the preloaded profile, nothing
else.

## 5. Tools

Only the tracker needs real tools, because application history is appended to
rather than overwritten, and `output_key` can only overwrite.

```python
def track_application(company: str, role: str, status: str,
                      notes: str, tool_context: ToolContext) -> dict
def list_applications(tool_context: ToolContext) -> dict
```

`track_application` appends to `tool_context.state['applications']`, creating
the list if absent. `status` is free text constrained by the agent's
instruction to the PRD lifecycle: Applied, OA Scheduled, Interview, Referral
Requested, Offer, Rejected.

Session state alone would lose applications between sessions (§2.1), and
applications are long-lived by nature — so `track_application` also writes to
Memory Bank (§3.4), and the root's `PreloadMemoryTool` brings the history back
on the student's next visit. This is the one piece of durable state in the
system.

## 6. Error handling

- **Missing state.** Every read uses `{key?}`, so an agent invoked out of order
  gets an empty string rather than a `KeyError`. Each instruction says what to
  do when its input is empty — normally "ask the student for a resume first".
- **Missing/default `user_id`.** Hard-fails the turn (§3.6). This is the one
  place the design deliberately refuses to degrade gracefully.
- **Search returning nothing.** The agent reports finding nothing. It does not
  invent companies or alumni; each search agent's instruction states this
  explicitly, since fabricated alumni are the highest-harm failure here — a
  student may act on them in public.
- **Unreachable JD URL.** `resume_gap_agent` reports the failure and asks for
  pasted text.
- **Tool exceptions.** ADK surfaces them to the calling agent, which reports
  them. No retry logic.
- **Silent empty response.** Observed on the spike agent: the model called its
  tool, the tool returned correctly, and the final model event was
  `{"text": ""}` with `finishReason: STOP` — the Gemini Enterprise UI rendered
  a blank reply while the session log held the full result. An orchestrator
  that delegates to `AgentTool`s is exposed to exactly this shape, so the root
  instruction must require a user-facing summary after tool calls, and §8.3
  should check that a reply is non-empty rather than merely that a turn
  completed. "Blank answer in the UI" and "agent crashed" look identical from
  the outside; they are distinguished by reading the session events.

### 6.1 Prompt injection

Student-supplied resume text and fetched JD pages are untrusted input that
flows into Memory Bank, which the Memory Bank docs flag for memory-poisoning
risk. The registration doc is explicit that this is not handled for us:
*"developers must configure Model Armor using the REST API within their
agent's application code. The Model Armor settings in the Google Cloud console
for Gemini Enterprise don't automatically protect ADK agents."*

Not implemented in this slice, but recorded here so it is a decision rather
than an oversight. Revisit before any non-pilot rollout.

## 7. Recorded simplifications

Each cuts a real corner. Ceilings and upgrade paths stated so the decision can
be revisited rather than rediscovered. Recorded as `ponytail:` comments at the
relevant code sites.

| Cut | Ceiling | Upgrade when |
|---|---|---|
| LLM scores alumni similarity directly; no embeddings or vector DB | Degrades past roughly 50 alumni in one prompt | Alumni sets outgrow a single prompt |
| Resume re-uploaded every session; nothing cached | Student repeats the upload each visit | Never, by choice — storing resumes is a PII liability with no product benefit |
| Applications in Memory Bank only; no relational queries | Cannot answer "which companies did the whole batch apply to" — no cross-student analytics | The placement-cell dashboard (PRD phase 3) is built; that needs Firestore, **not SQLite** — Agent Runtime has no persistent disk, so a SQLite file is silently lost between invocations while appearing to work locally |
| `google_search` only; no Greenhouse/Lever APIs | Job openings are LLM-summarized prose, not structured rows with apply links | Tracker needs to auto-populate from real postings |
| No Model Armor (§6.1) | Untrusted resume/JD text reaches Memory Bank unfiltered | Before non-pilot rollout |
| Default `container_concurrency` (9) and quota | ~45 concurrent students at 2 req/min on the default 90 QPM | Cohort size approaches that — see §8.2 |

## 8. Verification

### 8.1 Static test

One `test_agent.py`, runnable with `pytest`, no network or LLM calls:

1. **Tree assertion** — import `root_agent`; assert it holds the eight
   specialist `AgentTool`s by name, **plus** `LoadArtifactsTool` (§4.1, how the
   resume reaches the model) and `PreloadMemoryTool` (§3.4, how application
   history returns) — ten in total; assert each specialist's `output_key`
   matches §3.3. The two non-specialist tools are easy to drop in a refactor
   and their absence is silent: the agent simply never sees the resume, or
   never remembers an application.
2. **Built-in tool constraint** — assert no agent carries both a Gemini
   built-in and a custom function tool. This is the highest-value assertion in
   the suite: per §3.5 ADK will not catch it, and it may fail only in
   production.
3. **Tracker behaviour** — call `track_application` twice and
   `list_applications` once against a stub `ToolContext` holding a plain dict;
   assert both records return in order and that the first call creates the
   list.

Instruction quality is not unit-testable and is left to manual use.

### 8.2 Pre-launch quota request

Defaults, read from the raw HTML of
`docs.cloud.google.com/gemini-enterprise-agent-platform/resources/agent-quotas`
(devsite tables are dropped by HTML→markdown converters, so they were read as
raw HTML):

| Quota (per project, per region) | Default |
|---|---|
| `Query`/`StreamQuery` per minute | **90** |
| Maximum Agent Platform resources | **100** |
| Concurrent `BidiStreamQuery` | 10 |
| Memory Bank write / read per minute | 100 / 300 |

Express mode is roughly 10x tighter (10 resources, 10 QPM, 1 concurrent bidi).

`AgentTool` hops are **not** separate Query calls — the Query quota counts
inbound `streamQuery` requests, so 90/min supports roughly 45 concurrent
students at 2 req/min. The quota that scales with our eight-way fan-out is
`session_event_append_requests`; the quotas page notes *"a single query can
generate multiple session events in a chain"* and its own worked example
(250 users × 2 req/min → request 750 QPM, i.e. 1.5x headroom) raises
`session_event_append_requests` and `session_write_requests` alongside.

Request quota **before** launch, sized to cohort × 2 req/min × 1.5.

### 8.3 Deployment smoke test

Automated as `scripts/smoke_test.py`, which calls the deployed agent through
`streaming_agent_run_with_events` with the resume as an artifact plus GE's
empty marker parts — the production path, which `adk web` never exercises.

**Run 2026-07-22 against `reasoningEngines/1858334629883281408`: all passed.**

| Check | Result |
|---|---|
| `load_artifacts` called | PASS |
| Resume *actually* read | PASS — reply contained `SemanticShelf`, `NIT Warangal`, `900ms to 120ms`, `F1 from 0.71 to 0.86`, verbatim from the PDF |
| `profile` persisted to session state | PASS — `state keys: ['companies', 'profile']` after turn 2 |
| `company_agent` search ran from `us-central1` | PASS — returned real live openings |
| Non-empty replies, both turns | PASS |
| Identity guard did not fire for a real user | PASS |

The "actually read" check is deliberately two-sided: asserting only that
`load_artifacts` was *called* would pass even if the model received an empty
document and invented a plausible profile — the exact failure §4.1 warns about.
The synthetic resume carries distinctive strings that fabrication will not
accidentally reproduce.

Turn 2 deliberately re-uploads nothing. Its success closes §2.1's residual
risk: session state does survive between turns in production.

**Not covered:** Memory Bank. Cross-session application history needs a second
session under the same `user_id` and is checked separately.

### 8.4 Deployment environment (verified 2026-07-22)

Project `supadha-dev`, region `us-central1`, deploying account
`purna@tilicho.in`.

- Roles held: `aiplatform.admin`, `discoveryengine.agentspaceAdmin`,
  `resourcemanager.projectIamAdmin`, `serviceusage.serviceUsageAdmin` —
  sufficient to deploy to Agent Runtime and to register in Gemini Enterprise.
- APIs enabled: `aiplatform`, `discoveryengine`, `storage-api`,
  `cloudresourcemanager`.
- **No Cloud Storage role** (`storage.buckets.list` → 403). Irrelevant given
  §4.1: nothing is stored in GCS.
- `gcloud` in the WSL shell is the *Windows* SDK reading a Linux config dir;
  it requires
  `CLOUDSDK_CONFIG=/mnt/c/Users/PurnaChandraRao/AppData/Roaming/gcloud` for
  both the CLI and Python ADC. Without it the shell appears unauthenticated
  and `gcloud auth login` hangs (no browser in WSL).

## 9. Open items

1. ~~**Spike 0**~~ — **CLOSED 2026-07-22, Path A confirmed** through the live
   Gemini Enterprise UI. Uploads reach custom agents; students upload normally.
   See §4.1 for the marker format and the resulting `LoadArtifactsTool`
   requirement. `user_id` also confirmed as the real email.
   Probe still deployed:
   `projects/1019856256943/locations/us-central1/reasoningEngines/7108968845443858432`
   plus GE agent `.../agents/7816742926517116369` on app `ai-ge_1784736359549`.
   **Delete both** — the reasoning engine counts against the 100-resource cap.
2. ~~**Artifact service on deploy**~~ — CLOSED 2026-07-22, twice over. The flag
   exists (`--artifact_service_uri`, verified via `--help`, undocumented on the
   deploy page), and the ephemeral-resume decision means we don't need it.
3. ~~**Session continuity**~~ — **CLOSED 2026-07-22.** Gemini Enterprise reuses
   one session across turns (§2.1), so the crash-on-missing-`session_id` branch
   is not on our path and intra-session `output_key` memory works. Residual:
   session *state* persistence is implied, not proven — confirm on the real
   agent's first deploy (§8.3).
4. ~~**Search region binding**~~ — **CLOSED 2026-07-22.** `company_agent` ran
   `google_search` from a `us-central1`-deployed agent and returned real live
   job openings. The global-region restriction documented for Gemini Enterprise
   features does **not** bind `google_search` called from inside a deployed ADK
   agent.

**All four open items are now closed.** Remaining unverified behaviour is
Memory Bank cross-session persistence (§8.3), which needs a second session
under the same `user_id`.
