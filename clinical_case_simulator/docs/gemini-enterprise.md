# Deploying, and how Gemini Enterprise actually registers this

## The thing to get right

Gemini Enterprise does **not** register an arbitrary HTTP endpoint. A raw
`adk api_server` URL is not a registerable agent. There are exactly two
supported routes, and this repository supports both:

| Route | What you deploy | What you register | Script |
|---|---|---|---|
| **A. Agent Runtime** (recommended) | The ADK agent, to Vertex AI Agent Engine | The resource path `projects/P/locations/L/reasoningEngines/ID` | `./deploy_agent_engine.sh` |
| **B. A2A on Cloud Run** | A container serving the A2A JSON-RPC interface plus an agent card | The **agent card JSON**, pasted into the console | `./deploy.sh` |

Route A is simpler: no agent card, no protocol-version questions, no two-pass
URL dance. Take route B when you need Cloud Run specifically — IAM-based access
control, VPC egress, or running the same image elsewhere.

## Local development

```bash
cp .env.example .env      # or use the .env already written for Vertex
./run_local.sh            # ADK dev UI at http://localhost:8000
```

Either backend works:

```ini
# A — Gemini API, fastest for development
GOOGLE_GENAI_USE_VERTEXAI=FALSE
GOOGLE_API_KEY=...

# B — Vertex AI, and what both deployment routes use
GOOGLE_GENAI_USE_VERTEXAI=TRUE
GOOGLE_CLOUD_PROJECT=your-project
GOOGLE_CLOUD_LOCATION=us-central1
```

The dev UI's state inspector shows the `enc` key live, which is the fastest way
to see what a student's actions actually recorded.

To exercise the A2A interface locally, exactly as Gemini Enterprise would:

```bash
A2A_PUBLIC_URL=http://localhost:8080 \
  uvicorn clinical_simulator.a2a_app:app --host 0.0.0.0 --port 8080

curl -s localhost:8080/.well-known/agent-card.json | head
curl -s localhost:8080 -H 'content-type: application/json' -d '{
  "jsonrpc":"2.0","id":"1","method":"message/send",
  "params":{"message":{"role":"user","kind":"message","messageId":"m1",
  "parts":[{"kind":"text","text":"List the beginner cases."}]}}}'
```

## Route A — Agent Runtime

```bash
PROJECT=your-project REGION=us-central1 ./deploy_agent_engine.sh
```

Then in the Gemini Enterprise console: your app → **Agents** → **Add agent** →
**Custom agent via Agent Runtime**, and give it the resource path the script
prints.

To update an existing deployment rather than create a second one, pass
`AGENT_ENGINE_ID=...`.

## Route B — A2A on Cloud Run

```bash
PROJECT=your-project REGION=us-central1 ./deploy.sh
```

Note that this route does **not** inherit Agent Engine's managed sessions — a
Cloud Run container holds sessions in memory and loses them when the instance
recycles. Route A gets persistence for free; route B would need a session
service wired up.

The script validates the case bank first (a case that leaks its diagnosis
should never reach a student), deploys twice — Cloud Run assigns the URL, and
the agent card has to advertise that URL — grants the runtime service account
`roles/aiplatform.user`, and verifies the card is being served.

Then:

```bash
python -m clinical_simulator.agent_card https://<service-url>
```

Paste that JSON into the console's **Agent card JSON** field under
**Add agent → A2A agent**. Because the service runs on Cloud Run with IAM
access control, OAuth 2.0 client credentials are not required; grant the Gemini
Enterprise service agent `roles/run.invoker` on the service instead.

### The agent card, and one thing to watch

`clinical_simulator/a2a_app.py` wraps the root agent with ADK's `to_a2a()`,
which serves JSON-RPC at `/` and the card at `/.well-known/agent-card.json`.

Two deliberate overrides of ADK's auto-generated card:

- **Curated skills.** The auto-generated card advertises one skill per tool, so
  it lists `reveal_answer` and `submit_differential` as though a student would
  ask for them. Gemini Enterprise uses skills to decide when to route to an
  agent, so `agent_card.py` declares the four things a student actually wants:
  start a case, interview the patient, reason through it, get the report.
- **Field shape.** `a2a-sdk` 1.1.2 emits the A2A **v1.0** card, which carries
  `supportedInterfaces` rather than a top-level `url` and `protocolVersion`.
  Google's registration documentation describes the **v0.3** fields, and states
  that v0.3 is supported with compatibility packages for v1.0.0+. So
  `python -m clinical_simulator.agent_card <url>` emits the v0.3 shape by
  default, and `--v1` emits the 1.0 shape.

**Not verified:** which of the two shapes the Gemini Enterprise console accepts
today. That needs a Gemini Enterprise tenant to test, which this build did not
have. If v0.3 is rejected, re-run with `--v1`. Everything else on this page was
checked against the running service.

## What was verified, and what was not

Checked directly against the code and a live Vertex AI backend:

- the agent runs a full encounter end to end (`console.py --smoke`);
- the A2A service serves a valid agent card at the well-known path (HTTP 200);
- the A2A JSON-RPC `message/send` method drives the agent and returns its reply;
- `to_a2a()` and `adk deploy agent_engine` both exist in ADK 2.7.1.

Checked against Google's documentation but not against a live tenant:

- the two registration routes and the identifiers each needs;
- that Cloud Run IAM removes the OAuth 2.0 credential requirement;
- the required agent-card fields.

Since verified against a live deployment in `ge-standard-trail`:

- `./deploy_agent_engine.sh` deploys successfully to Agent Runtime;
- the deployed agent runs encounters (session created, case started, patient
  replied in character);
- `./register_gemini_enterprise.sh` registers it with a Gemini Enterprise app —
  the agent appears in the app's agent list with state `ENABLED`;
- Agent Engine sessions persist encounter state without extra configuration.

Two caveats from that run, both worth knowing before you repeat it:

- `adk deploy agent_engine` can report `400 FAILED_PRECONDITION — there are
  other operations running on the ReasoningEngine` while the deployment
  actually **succeeds**. It creates the instance and then races its own create
  operation. Check the engine's spec before believing the error. Re-running
  creates a *second* engine, so pass `AGENT_ENGINE_ID` to update in place.
- The deploying machine needs `google-cloud-aiplatform[agent_engines,adk]`
  (the `deploy` extra in `pyproject.toml`), which is not pulled in by
  `google-adk` itself.

Still not attempted: driving the agent through the Gemini Enterprise chat UI as
a student would. The API surface is proven; the UI experience is not.

Not attempted at all: the Cloud Run / A2A route (route B).

## Model choice

| Setting | Default | Why |
|---|---|---|
| `CS_MODEL` | `gemini-2.5-flash` | Every conversational turn and every patient reply. Latency matters more than depth; the patient's job is to answer one question in one sentence |
| `CS_EVAL_MODEL` | `gemini-2.5-pro` | Once per encounter. The report is the product; it is worth the extra reasoning |

## Feature feasibility

Answering section 22E of the research doc for each V1 feature.

| Feature | Agent Designer alone? | ADK needed? | RAG needed? | Notes |
|---|:--:|:--:|:--:|---|
| Virtual patient conversation | Partly | **Yes** | No | Designer can hold a persona, but not the hidden-state split that stops answer-dumping |
| Hidden case state | No | **Yes** | No | Needs typed session state and tool gating |
| Gated examination and investigation results | No | **Yes** | No | Tools returning authored results; the model must not be able to invent one |
| Deterministic scoring | No | **Yes** | No | Pure Python. Not something a prompt can do reproducibly |
| Progressive hints | Partly | **Yes** | No | Hints are authored per case and must cost marks |
| Practice Mode | Partly | **Yes** | No | Enforced by architecture, not by instruction |
| Performance report | Partly | **Yes** | No | Needs the scorecard as input |
| Faculty case upload | No | No | Later | V2/V3. Today a case is a JSON file in the repo |
| Post-case teaching from guidelines | No | No | **Yes** | The natural first use of RAG — after the encounter, not during it |
| Student progress history | No | No | No | Needs a persistent session service and a datastore |

Short version: **ADK is required**, RAG is not required for V1, and Gemini
Enterprise is the right front door but not the right implementation surface.

## Where RAG belongs

The research doc puts RAG between the approved sources and the agent. In V1 the
structured case bank *is* the grounding layer, and it is a stronger one — a
retrieved passage can be misread, whereas an authored `result` string cannot.

Retrieval earns its place at V2, over clinical guidelines and faculty material,
in the teaching that follows the case: "here is the guideline your management
plan departed from". Keep it out of the encounter itself, where every retrieved
token is a fresh opportunity to contradict the case file.

## What to store, and the controls it needs

Deployed on Agent Runtime, encounters **already persist** — Agent Engine
provides a managed session store with no extra configuration, and the encounter
state (`enc`) survives between calls. Verified against the live deployment: a
session created, three turns run, then re-read afterwards still carried
`case_id: IM-001, phase: history`.

That means student assessment data already exists in the project, which brings
the following with it:

- transcripts, scorecards, per-student progression;
- retention, access control, and a clear statement to students about who can
  see their scores;
- an audit trail of which case version a student was marked against, since
  editing a rubric changes historical marks.

Worth designing before it is switched on, not after.

## Safety controls in place

- The simulator states it is an educational simulation and is instructed to
  stop and redirect a user who describes a real medical problem of their own.
- The agent card says the same, so it is visible before a user ever starts.
- No component that talks to the student holds the diagnosis.
- No tool can return a finding a clinician did not author.
- Case content is version-controlled, reviewable and provenance-tracked.
- `provenance.status` gates whether a case is cleared for student assessment.
