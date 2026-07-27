# A2A Host Hardening Implementation Plan (Ticket 1 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve Job Helper Agent from a Cloud Run A2A endpoint with the same
state, memory, and identity guarantees it has today on Agent Engine.

**Architecture:** Wrap the unchanged `root_agent` with ADK's `to_a2a()`, but
pass an explicitly-constructed `Runner` instead of accepting the in-memory
defaults. Sessions and Memory Bank continue to be backed by the **existing**
Vertex AI Agent Engine instance — only request serving moves to Cloud Run.
Identity comes from A2A call context, with the existing privacy guard widened
to reject the new synthetic-user sentinel.

**Tech Stack:** Python 3.12, `google-adk==2.4.0` (`[a2a]` extra), Starlette +
uvicorn, Cloud Run, Vertex AI Agent Engine (sessions + Memory Bank).

**Spec:** `docs/superpowers/specs/2026-07-27-a2ui-gemini-enterprise-design.md`
(Decision 2, "What the migration breaks").

## Global Constraints

- No changes to `Job_Helper_agent/agent.py`. The eight specialists, their
  models, instructions, `output_key`s, and `AgentTool` wiring are untouched.
- Root orchestrator stays `gemini-2.5-pro`; specialists stay `gemini-2.5-flash`.
- A Gemini built-in tool never shares an `Agent` with a custom function tool.
  The existing structural assertion must stay green.
- Tests are structural and offline: no network, no LLM calls, no GCP calls.
- Test harness is plain functions run by `.venv/bin/python test_agent.py` —
  **not pytest**. Every new test is a module-level `test_*` function using bare
  `assert`.
- Exit criterion for this ticket is **behavioral parity** with the current
  Agent Engine deployment. No user-visible change. No A2UI work.
- `VertexAiSessionService` and `VertexAiMemoryBankService` both take
  `(project, location, agent_engine_id)`. The existing reasoning engine is
  retained as the backing store — do not delete it.

---

### Task 1: Widen the identity guard to reject synthetic A2A users

`callbacks.py:require_real_user` rejects only the literal `default-user-id`.
On a Cloud Run A2A server with auth off, ADK's `_get_user_id`
(`google/adk/a2a/converters/request_converter.py:66-77`) returns
`f'A2A_USER_{request.context_id}'` — a per-conversation value, not a person.
The guard would pass it and stop guarding.

This task ships first and alone: it is the safety net for every task after it.

**Files:**
- Modify: `Job_Helper_agent/callbacks.py:24,32-46`
- Test: `test_agent.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `require_real_user(callback_context) -> types.Content | None`
  (unchanged signature). Returns non-`None` (a refusal) for `default-user-id`
  and for any `user_id` beginning with `A2A_USER_`; returns `None` otherwise.

- [ ] **Step 1: Write the failing test**

Add to `test_agent.py`. Add `require_real_user` to the imports at the top:

```python
from Job_Helper_agent.callbacks import require_real_user
```

```python
class _FakeCallbackContext:
    def __init__(self, user_id):
        self.user_id = user_id


def test_identity_guard_rejects_untrustworthy_user_ids():
    # Agent Engine's silent fallback.
    assert require_real_user(_FakeCallbackContext("default-user-id")) is not None

    # ADK's A2A fallback when auth is off. Per-conversation, not per-student:
    # letting this through means Memory Bank scopes history to a single chat
    # and the privacy guard is effectively disabled.
    assert require_real_user(_FakeCallbackContext("A2A_USER_ctx-abc123")) is not None
    assert require_real_user(_FakeCallbackContext("A2A_USER_")) is not None

    # A real signed-in student must still get through.
    assert require_real_user(_FakeCallbackContext("student@example.com")) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python test_agent.py`
Expected: FAIL — `AssertionError` on the `A2A_USER_ctx-abc123` line, because the
current guard returns `None` for it.

- [ ] **Step 3: Write minimal implementation**

In `Job_Helper_agent/callbacks.py`, replace the `_DEFAULT_USER_ID` constant:

```python
_DEFAULT_USER_ID = "default-user-id"

# ADK's A2A server synthesises this when no authenticated caller is present
# (`google/adk/a2a/converters/request_converter.py:66-77`). It is scoped to one
# conversation, not one student, so treating it as an identity would silently
# reset a returning student's history and collapse the Memory Bank scope.
_A2A_ANONYMOUS_PREFIX = "A2A_USER_"


def _is_real_user(user_id: str | None) -> bool:
    if not user_id or user_id == _DEFAULT_USER_ID:
        return False
    return not user_id.startswith(_A2A_ANONYMOUS_PREFIX)
```

Then change the guard body:

```python
def require_real_user(callback_context: CallbackContext) -> types.Content | None:
    """Block the turn unless the caller supplied a real user identity."""
    if _is_real_user(callback_context.user_id):
        return None
    return types.Content(
        role="model",
        parts=[
            types.Part(
                text=(
                    "I can't continue: this request arrived without a user"
                    " identity, so I have no safe way to keep your data"
                    " separate from anyone else's. Please open me from"
                    " Gemini Enterprise while signed in."
                )
            )
        ],
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python test_agent.py`
Expected: PASS — all 7 checks, including the 6 pre-existing ones.

- [ ] **Step 5: Commit**

```bash
git add Job_Helper_agent/callbacks.py test_agent.py
git commit -m "fix: reject synthetic A2A user ids in the identity guard"
```

---

### Task 2: Build the hardened runner

`to_a2a()` builds its default runner with `InMemorySessionService`,
`InMemoryMemoryService`, and `InMemoryArtifactService`
(`google/adk/a2a/utils/agent_to_a2a.py:157-165`). On Cloud Run that means
session state dies when an instance recycles and Memory Bank writes go nowhere.

This task produces the runner factory only — no server yet, so it stays
testable offline.

**Files:**
- Create: `Job_Helper_agent/runtime.py`
- Test: `test_agent.py`

**Interfaces:**
- Consumes: `Job_Helper_agent.agent.root_agent`.
- Produces: `build_runner() -> google.adk.runners.Runner`, reading
  `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `AGENT_ENGINE_ID` from
  the environment. Raises `RuntimeError` naming the missing variable if any is
  unset. Also produces the module constant `REQUIRED_ENV` (a tuple of those
  three names) for tests and deploy docs to share.

- [ ] **Step 1: Write the failing test**

Add to `test_agent.py`, with these imports at the top of the file:

```python
import os

from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.sessions.in_memory_session_service import InMemorySessionService

from Job_Helper_agent.runtime import REQUIRED_ENV, build_runner
```

```python
def test_build_runner_refuses_to_start_without_backing_store_config():
    # Fail loudly at boot rather than silently serving from memory: an
    # in-memory session service on Cloud Run loses a student's tracked
    # applications the moment the instance recycles.
    saved = {k: os.environ.pop(k, None) for k in REQUIRED_ENV}
    try:
        raised = None
        try:
            build_runner()
        except RuntimeError as e:
            raised = e
        assert raised is not None, "build_runner started with no configuration"
        assert "AGENT_ENGINE_ID" in str(raised)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_build_runner_uses_persistent_services_not_in_memory_defaults():
    saved = {k: os.environ.get(k) for k in REQUIRED_ENV}
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
    os.environ["AGENT_ENGINE_ID"] = "1234567890"
    try:
        runner = build_runner()
        # These three are the regression guard for the migration. Each default
        # is a silent data-loss path, not a performance nicety.
        assert not isinstance(runner.session_service, InMemorySessionService)
        assert not isinstance(runner.memory_service, InMemoryMemoryService)
        assert runner.agent is not None
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python test_agent.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'Job_Helper_agent.runtime'`

- [ ] **Step 3: Write minimal implementation**

Create `Job_Helper_agent/runtime.py`:

```python
"""The runner that keeps a student's data alive across turns and visits.

`to_a2a()` will happily build its own runner, but that default uses
`InMemorySessionService` and `InMemoryMemoryService`
(`google/adk/a2a/utils/agent_to_a2a.py:157-165`). On Cloud Run, which runs
several instances and recycles them freely, that means a student's tracked
applications can vanish between two turns of one conversation, and nothing is
ever written to Memory Bank. Neither failure raises -- the board just comes
back empty.

Sessions and memory stay backed by the existing Agent Engine instance. Only
request serving moves to Cloud Run.
"""

import os

from google.adk.artifacts.gcs_artifact_service import GcsArtifactService
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.memory.vertex_ai_memory_bank_service import VertexAiMemoryBankService
from google.adk.runners import Runner
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService

from .agent import root_agent

REQUIRED_ENV = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "AGENT_ENGINE_ID")

APP_NAME = "job_helper_agent"


def _require_env() -> tuple[str, str, str]:
    missing = [name for name in REQUIRED_ENV if not os.environ.get(name)]
    if missing:
        raise RuntimeError(
            "Refusing to start without persistent session and memory storage."
            f" Missing environment: {', '.join(missing)}."
        )
    return tuple(os.environ[name] for name in REQUIRED_ENV)


def build_runner() -> Runner:
    """Build a Runner whose state survives an instance restart."""
    project, location, agent_engine_id = _require_env()

    # Artifacts hold uploaded resumes. A bucket is optional -- without one the
    # agent still works within a single turn, so this degrades rather than
    # blocks. GOOGLE_CLOUD_STORAGE_BUCKET turns on cross-turn resume storage.
    bucket = os.environ.get("GOOGLE_CLOUD_STORAGE_BUCKET")
    artifact_service = (
        GcsArtifactService(bucket_name=bucket) if bucket else InMemoryArtifactService()
    )

    return Runner(
        app_name=APP_NAME,
        agent=root_agent,
        session_service=VertexAiSessionService(
            project=project, location=location, agent_engine_id=agent_engine_id
        ),
        memory_service=VertexAiMemoryBankService(
            project=project, location=location, agent_engine_id=agent_engine_id
        ),
        artifact_service=artifact_service,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python test_agent.py`
Expected: PASS — 9 checks.

If `VertexAiSessionService` raises `missing_extra('google-cloud-aiplatform', 'gcp')`,
install the dependency before re-running:
`.venv/bin/pip install google-cloud-aiplatform`

- [ ] **Step 5: Commit**

```bash
git add Job_Helper_agent/runtime.py test_agent.py
git commit -m "feat: persistent session and memory services for the A2A host"
```

---

### Task 3: Serve the agent over A2A

**Files:**
- Create: `Job_Helper_agent/main_a2a.py`
- Create: `Job_Helper_agent/agent_card.json`
- Test: `test_agent.py`

**Interfaces:**
- Consumes: `build_runner()` from Task 2.
- Produces: `Job_Helper_agent/main_a2a.py:app`, a Starlette application; and
  `agent_card.json` declaring the A2UI v0.8 extension with `streaming: true`.

The agent card declares A2UI now, in this ticket, even though nothing emits
A2UI yet. `required: false` means a client that negotiates the extension still
receives plain text, so declaring it early is harmless — and it means Ticket 2
needs no re-registration in Gemini Enterprise.

- [ ] **Step 1: Write the failing test**

Add to `test_agent.py`, with this import at the top:

```python
import json
import pathlib
```

```python
def test_agent_card_declares_a2ui_and_streaming():
    card = json.loads(
        (pathlib.Path(__file__).parent / "Job_Helper_agent" / "agent_card.json").read_text()
    )
    caps = card["capabilities"]
    # Without streaming, progress updates cannot be painted incrementally.
    assert caps["streaming"] is True

    exts = caps["extensions"]
    a2ui = [e for e in exts if "a2ui" in e["uri"]]
    assert len(a2ui) == 1, "agent card must declare exactly one A2UI extension"

    # Gemini Enterprise supports A2UI v0.8 only. A version bump here silently
    # stops rendering in GE.
    assert a2ui[0]["uri"] == "https://a2ui.org/a2a-extension/a2ui/v0.8"

    # Must stay false: it is what lets the agent fall back to plain text for
    # any client that does not negotiate A2UI.
    assert a2ui[0]["required"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/python test_agent.py`
Expected: FAIL — `FileNotFoundError` for `agent_card.json`.

- [ ] **Step 3: Write minimal implementation**

Create `Job_Helper_agent/agent_card.json`:

```json
{
  "protocolVersion": "0.3.0",
  "name": "job-helper-agent",
  "description": "Turns a student's resume into a company shortlist, alumni contacts, and a tracked application pipeline.",
  "version": "1.0.0",
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [],
  "capabilities": {
    "streaming": true,
    "extensions": [
      {
        "uri": "https://a2ui.org/a2a-extension/a2ui/v0.8",
        "required": false,
        "params": {
          "supportedCatalogIds": [
            "https://a2ui.org/specification/v0_8/standard_catalog_definition.json"
          ]
        }
      }
    ]
  }
}
```

Create `Job_Helper_agent/main_a2a.py`:

```python
"""Cloud Run entrypoint. Serves the agent over A2A for Gemini Enterprise.

`to_a2a` is passed an explicit runner. Letting it build its own would silently
swap persistent sessions and Memory Bank for in-memory stand-ins -- see
`runtime.py` for why that loses student data.
"""

import os
import pathlib

import uvicorn
from google.adk.a2a.utils.agent_to_a2a import to_a2a

from .agent import root_agent
from .runtime import build_runner

PORT = int(os.environ.get("PORT", 8080))
# Cloud Run terminates TLS and gives the public https URL; the agent card must
# advertise that URL, not the container's http listener.
PUBLIC_HOST = os.environ.get("PUBLIC_HOST", "localhost")
PROTOCOL = os.environ.get("PUBLIC_PROTOCOL", "https")

AGENT_CARD = pathlib.Path(__file__).parent / "agent_card.json"

app = to_a2a(
    root_agent,
    host=PUBLIC_HOST,
    port=PORT,
    protocol=PROTOCOL,
    agent_card=str(AGENT_CARD),
    runner=build_runner(),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=PORT)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python test_agent.py`
Expected: PASS — 10 checks.

- [ ] **Step 5: Commit**

```bash
git add Job_Helper_agent/main_a2a.py Job_Helper_agent/agent_card.json test_agent.py
git commit -m "feat: A2A entrypoint with explicit runner and A2UI-capable agent card"
```

---

### Task 4: Containerise

**Files:**
- Create: `Job_Helper_agent/Dockerfile`
- Create: `.dockerignore`
- Modify: `Job_Helper_agent/requirements.txt`

**Interfaces:**
- Consumes: `main_a2a.py:app` from Task 3.
- Produces: a container listening on `$PORT`, entrypoint
  `uvicorn Job_Helper_agent.main_a2a:app`.

Note the module path: the app is imported as a **package** (`Job_Helper_agent.main_a2a`),
because `main_a2a.py` uses relative imports. The build context is the repo root,
not the agent directory. `my_agent/Dockerfile` copies a flat directory and uses
`main_a2a:app` — do not copy that pattern here, it will fail on the relative
imports.

- [ ] **Step 1: Pin the dependencies**

Set `Job_Helper_agent/requirements.txt` to:

```
google-adk[a2a]==2.4.0
google-cloud-aiplatform
uvicorn
```

The `[a2a]` extra is what provides `google.adk.a2a` and the `a2a-sdk`
dependency. The version is pinned because `to_a2a` is decorated
`@a2a_experimental` in this release — an unpinned upgrade can change its
signature without a major version bump.

- [ ] **Step 2: Write the Dockerfile**

Create `Job_Helper_agent/Dockerfile`:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY Job_Helper_agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY Job_Helper_agent/ ./Job_Helper_agent/

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn Job_Helper_agent.main_a2a:app --host 0.0.0.0 --port $PORT"]
```

Create `.dockerignore` at the repo root:

```
.venv/
__pycache__/
*.pyc
docs/
.git/
my_agent/
doubt_solver/
faculty_agent/
```

- [ ] **Step 3: Verify the image builds and boots**

```bash
cd "/mnt/c/Users/PurnaChandraRao/Documents/Google GECX"
docker build -f Job_Helper_agent/Dockerfile -t job-helper-a2a .
```

Expected: build succeeds.

Then confirm the boot guard from Task 2 actually fires:

```bash
docker run --rm -p 8080:8080 job-helper-a2a
```

Expected: the container **exits** with
`RuntimeError: Refusing to start without persistent session and memory storage.`
That is the correct result — it proves the guard works. A container that boots
happily here would mean it is serving from memory.

- [ ] **Step 4: Commit**

```bash
git add Job_Helper_agent/Dockerfile Job_Helper_agent/requirements.txt .dockerignore
git commit -m "build: container image for the Cloud Run A2A host"
```

---

### Task 5: Deploy, register, and verify parity

This task is operational — it produces no new code, and its deliverable is
recorded evidence. `AGENT_ENGINE_ID` is the numeric ID of the **existing**
reasoning engine (the tail of `projects/.../reasoningEngines/1234567890`), reused
as the session and Memory Bank backing store.

**Files:**
- Modify: `DEPLOYING_ADK_AGENTS.md` (add an "A2A on Cloud Run" section)

- [ ] **Step 1: Deploy to Cloud Run**

```bash
PROJECT=$(gcloud config get-value project)
gcloud run deploy job-helper-a2a \
  --source . \
  --region us-central1 \
  --no-allow-unauthenticated \
  --min-instances 1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT,GOOGLE_CLOUD_LOCATION=us-central1,AGENT_ENGINE_ID=<existing-engine-id>,PUBLIC_HOST=<service-host>,GOOGLE_GENAI_USE_VERTEXAI=1"
```

`--min-instances 1` avoids a cold start in front of a `gemini-2.5-pro` first
turn. `--no-allow-unauthenticated` is required: GE calls with a service-agent
credential, and that credential is what populates the real user identity.

`PUBLIC_HOST` is only known after the first deploy. Deploy once, read the URL
from the output, then re-deploy with it set.

- [ ] **Step 2: Grant Gemini Enterprise permission to invoke**

```bash
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud run services add-iam-policy-binding job-helper-a2a \
  --region us-central1 \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

- [ ] **Step 3: Confirm the agent card is reachable**

```bash
curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  https://<service-host>/.well-known/agent-card.json | jq .capabilities
```

Expected: `streaming: true` and the A2UI v0.8 extension.

- [ ] **Step 4: Register in Gemini Enterprise as an A2A agent**

```bash
curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "Content-Type: application/json" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_NUMBER}/locations/global/collections/default_collection/engines/<ENGINE_ID>/assistants/default_assistant/agents" \
  -d "{\"a2aAgentDefinition\": {\"jsonAgentCard\": $(jq -Rs . < Job_Helper_agent/agent_card.json)}}"
```

Note this is the `a2aAgentDefinition` path — the `adkAgentDefinition` path
cannot render A2UI, which is the whole reason for this ticket.

Record the returned agent name. Per the
[GE dead-agent memory](../../../CLAUDE.md), verify the returned pointer resolves
before concluding anything about behaviour — a truncated engine ID produces an
agent that silently does nothing.

- [ ] **Step 5: Verify parity in the GE chat surface**

Run each check in GE against the newly registered agent and record the result
in the ticket's Verification Log. Parity, not improvement, is the bar.

1. Ask for a company shortlist from a pasted resume. Expect the same quality of
   answer as the Agent Engine registration.
2. Track an application, then **ask for the pipeline again in a later turn**.
   The application must still be there. This is the Regression 3 check.
3. Close the conversation, start a new one, and ask about earlier applications.
   History must come back. This is the Regression 2 check — and it is the one
   most likely to fail first, since it depends on Memory Bank writes landing.
4. Confirm the agent answers at all — if every turn returns the "I can't
   continue: this request arrived without a user identity" refusal, then auth
   is not populating `call_context.user.user_name` and identity must be fixed
   before this ticket ships. Do **not** work around it by loosening the guard.

- [ ] **Step 6: Document and commit**

Add an "A2A on Cloud Run" section to `DEPLOYING_ADK_AGENTS.md` covering the
deploy command, the required env vars, the `run.invoker` binding, and the
`a2aAgentDefinition` registration call.

```bash
git add DEPLOYING_ADK_AGENTS.md
git commit -m "docs: A2A on Cloud Run deploy and registration path"
```

- [ ] **Step 7: Retire the old registration — only after Step 5 passes**

Leave the Agent Engine **instance** in place; it is the session and memory
backing store. Remove only its GE *registration*, so students see one agent.

---

## Self-Review

**Spec coverage:**

| Spec requirement | Task |
|---|---|
| Migrate to Cloud Run A2A host | 3, 4, 5 |
| Persistent session service | 2 |
| Memory Bank service | 2 |
| Real user identity via auth | 5 (step 1, verified step 5.4) |
| Widen `require_real_user` for `A2A_USER_*` | 1 |
| Agent card with A2UI v0.8 + streaming | 3 |
| `roles/run.invoker` for Discovery Engine SA | 5 |
| Register via `a2aAgentDefinition` | 5 |
| Retire old registration after parity | 5 |
| Test: persistent services, not in-memory | 2 |
| Test: guard rejects both sentinels | 1 |
| Test: agent card declares extension | 3 |
| Existing built-in/function-tool assertion stays green | Global constraint; every task runs the full suite |

A2UI rendering, the `DataPart` emit hook, `a2ui.py` builders, and the resume
upload spike are deliberately absent — they are Ticket 2.

**Placeholder scan:** No TBDs. `<existing-engine-id>`, `<service-host>`, and
`<ENGINE_ID>` are deployment values that cannot be known until deploy time;
Task 5 says where each comes from.

**Type consistency:** `build_runner()` and `REQUIRED_ENV` are defined in Task 2
and used under those exact names in Tasks 2 and 3. `app` is defined in Task 3
and referenced as `Job_Helper_agent.main_a2a:app` in Task 4.

## Open risk carried into Ticket 2

Whether Gemini Enterprise forwards a chat attachment to an A2A agent as a
`FilePart` is still unverified. Task 5's parity checks do not cover resume
upload, because upload is not part of today's behaviour. The spike belongs in
Ticket 2.
