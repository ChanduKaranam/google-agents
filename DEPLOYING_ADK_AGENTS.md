# Deploying an ADK Agent to Gemini Enterprise — a practical guide

This is the exact path we used to build and ship the **Job Helper Agent**. Follow it
top to bottom and you'll have your own agent running inside Gemini Enterprise, reachable
by real users in the chat UI.

It's written for someone who has **never done this before**. Where a step has a trap that
wasted us hours, it's called out with ⚠️.

> **The one-sentence version:** write a Python agent → test it locally → `adk deploy` it →
> register it in a Gemini Enterprise app → share it with users in the console.

---

## 0. What you need before you start

| Thing | How to check |
|---|---|
| Python 3.12 + a virtualenv | `python --version` |
| `google-adk` installed | `pip install google-adk` (we used `2.4.0`) |
| A Google Cloud project with billing | e.g. `supadha-dev` |
| `gcloud` CLI, authenticated | see the ⚠️ box below — this trips everyone up |
| A Gemini Enterprise app already created | in the console: **Gemini Enterprise → Create app**. Creating one is out of scope here. |
| These GCP roles on your account | `roles/aiplatform.admin`, `roles/discoveryengine.agentspaceAdmin` |

Enable the APIs once per project:

```bash
gcloud services enable aiplatform.googleapis.com discoveryengine.googleapis.com \
  storage.googleapis.com cloudresourcemanager.googleapis.com --project=YOUR_PROJECT
```

---

## ⚠️ The gcloud trap that will waste your afternoon (WSL users)

If you're on **WSL** and `gcloud auth list` says *"No credentialed accounts"* even though
you've logged in — **do not run `gcloud auth login` again. It will hang forever** (WSL has
no browser, so the login page never opens).

The real problem: on WSL, `gcloud` is often the **Windows** SDK reading the **Linux**
config directory, which is empty. Point it at the Windows config where your credentials
actually live:

```bash
export CLOUDSDK_CONFIG="/mnt/c/Users/<YOU>/AppData/Roaming/gcloud"
```

Put that line in your `~/.bashrc` so you never think about it again. It fixes both the
`gcloud` CLI **and** the Python SDK that `adk deploy` uses.

Verify:

```bash
gcloud auth list          # should show your account with a *
gcloud config get-value project
```

---

## 1. Write the agent

Minimum layout — one folder, three files:

```
my_agent/
  __init__.py         # exactly: from . import agent
  agent.py            # defines root_agent
  requirements.txt    # e.g. google-adk==2.4.0
  .env                # project config (see below)
```

`agent.py` — the smallest thing that works:

```python
from google.adk.agents.llm_agent import Agent

root_agent = Agent(
    model="gemini-2.5-flash",
    name="my_agent",
    description="What this agent does — the router uses this to decide when to call it.",
    instruction="You are ... . Do ... .",
)
```

`__init__.py`:

```python
from . import agent
```

`.env` — `adk deploy` reads this automatically:

```
GOOGLE_GENAI_USE_VERTEXAI=1
GOOGLE_CLOUD_PROJECT=YOUR_PROJECT
GOOGLE_CLOUD_LOCATION=us-central1
```

> **Never commit `.env`.** Put it in `.gitignore` and commit a `.env.example` instead.

---

## 2. Test it locally first

```bash
adk web        # opens a local chat UI at http://localhost:8000
# or
adk run my_agent
```

⚠️ **Local success is NOT proof it works deployed.** `adk web` uses a *different code path*
than Gemini Enterprise. Things that work locally (file upload, session memory) can behave
differently once deployed. Treat local testing as "does it load and roughly work", not
"it's ready".

---

## 3. Deploy to Agent Runtime

```bash
adk deploy agent_engine \
  --project=YOUR_PROJECT \
  --region=us-central1 \
  --display_name="My Agent" \
  --description="One-line description shown in the console." \
  my_agent
```

Takes a few minutes. It prints a resource path — **save it**:

```
projects/YOUR_PROJECT/locations/us-central1/reasoningEngines/1234567890
```

### If your agent needs memory that survives between sessions

Add `--memory_service_uri`. Chicken-and-egg: the URI needs the resource id that deploy
*produces*, so deploy once without it, then redeploy in place using `--agent_engine_id`:

```bash
adk deploy agent_engine \
  --project=YOUR_PROJECT --region=us-central1 \
  --agent_engine_id=1234567890 \
  --display_name="My Agent" \
  --memory_service_uri="agentengine://1234567890" \
  my_agent
```

⚠️ `--memory_service_uri` only **wires up** the service. Nothing writes to it unless your
agent explicitly saves — see "Memory" in the rules section below.

---

## 4. Register it in Gemini Enterprise

**Console way** (easiest): Gemini Enterprise → your app → **Agents** → **Add agent** →
**Custom agent via Agent Runtime** → paste the `reasoningEngines/...` path → **Create**.

**API way** (scriptable):

```bash
TOKEN=$(gcloud auth print-access-token)
curl -s -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "X-Goog-User-Project: YOUR_PROJECT" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/YOUR_PROJECT/locations/global/collections/default_collection/engines/YOUR_APP_ID/assistants/default_assistant/agents" \
  -d '{
    "displayName": "My Agent",
    "description": "Description the LLM uses to decide whether to invoke your agent.",
    "adkAgentDefinition": {
      "provisionedReasoningEngine": {
        "reasoningEngine": "projects/YOUR_PROJECT/locations/us-central1/reasoningEngines/1234567890"
      }
    }
  }'
```

⚠️ **Don't write a "try endpoint A, fall back to B" loop.** Both
`discoveryengine.googleapis.com` and `global-discoveryengine.googleapis.com` accept this
call and each creates a **separate** agent — you'll get duplicates.

⚠️ Find `YOUR_APP_ID`: it's the engine id of your Gemini Enterprise app, e.g.
`ai-ge_1784736359549`. List them:

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: YOUR_PROJECT" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/YOUR_PROJECT/locations/global/collections/default_collection/engines" | python3 -m json.tool
```

---

## 5. Share it — or nobody can see it

⚠️ **Registering an agent does NOT make it visible.** It shows `ENABLED` but won't appear
in the chat until you **share** it. Sharing is **console-only** (no API):

> Gemini Enterprise → your app → **Agents** → click your agent → **User permissions** tab
> → **Add user** → add yourself (or **All users**) → **Save**.

Reload the chat and your agent now appears.

**Before you let real users in:** open the chat yourself and try a real task end to end.
The deployed path differs from local (step 2), so this is the first time you're seeing
true behaviour.

---

## The ADK rules that WILL bite you

These cost us real time. Read them before you build something non-trivial.

### 1. A Gemini built-in tool can't share an agent with your own tools
`google_search`, `url_context`, `code_execution` cannot sit in the same agent as a custom
Python function tool. **ADK does not warn you** — it fails at the Gemini API, sometimes
only once deployed. Give each built-in its **own** leaf agent (one built-in, nothing
else), and reach it from your orchestrator via `AgentTool`.

### 2. An empty reply has three different causes
If a turn comes back blank: the model returned empty text, OR the server crashed, OR you
hit a `429` quota error. They look identical from the outside. To tell them apart, read
the session's event log:

```python
from vertexai import agent_engines
import vertexai
vertexai.init(project="YOUR_PROJECT", location="us-central1")
a = agent_engines.get("projects/.../reasoningEngines/1234567890")
s = a.get_session(user_id="someone@example.com", session_id="...")
for e in s["events"]:
    if e.get("errorMessage"): print(e["errorMessage"])   # 429s hide here
```

Instruct your orchestrator to **always write a text reply after calling a tool** — a turn
that ends on a tool call with no text is a blank screen to the user.

### 3. Sub-agents called via `AgentTool` get an EMPTY memory service
Only your **root** agent can see Memory Bank. A `search_memory` call inside a sub-agent
silently returns nothing. If a specialist needs past context, have the root read memory
and **restate the facts into the request** it passes down. (`AgentTool` *does* forward
session state and uploaded files — just not memory.)

### 4. Nothing writes to Memory Bank for you
`--memory_service_uri` wires it up but writes nothing. Save the conversation yourself with
an after-turn callback:

```python
async def remember(ctx):
    try:
        await ctx.add_session_to_memory()
    except Exception:
        pass  # best-effort; never break the user's turn over a memory write

root_agent = Agent(..., after_agent_callback=remember)
```

Memory writes are **asynchronous** — a new session seconds later won't see them yet
(~1 min lag). Don't conclude it's broken; check the `.../reasoningEngines/ID/memories`
REST endpoint.

### 5. Uploaded files arrive as artifacts, not as text
When a user attaches a file in Gemini Enterprise, your agent gets a marker like
`<start_of_user_uploaded_file: resume.pdf>` with **no content between the markers** — the
bytes are held aside. Give the root the `load_artifacts` tool and instruct it to call it,
or it will see a filename it can't read and may invent the contents.

### 6. Verify with CODE, not just instructions
If your agent produces links or facts users act on, "the model promised not to make things
up" is not enough — models produce plausible-but-fake URLs. Add a real function tool that
HTTP-fetches and checks. A `404` can't be argued with; a prompt can.

### 7. Quota is lower than you think
Default is **90 requests/minute per project per region**. An orchestrator that fans out to
several sub-agents spends several requests per user turn, so real capacity is well under 90
concurrent users. Request a quota increase **before** a launch, not after the `429`s.

---

## Command cheat-sheet

```bash
# one-time per project
gcloud services enable aiplatform.googleapis.com discoveryengine.googleapis.com --project=P

# deploy (new)
adk deploy agent_engine --project=P --region=us-central1 --display_name="X" my_agent

# redeploy in place (same resource id)
adk deploy agent_engine --project=P --region=us-central1 --agent_engine_id=ID \
  --display_name="X" --memory_service_uri="agentengine://ID" my_agent

# list your deployed agents
gcloud beta ai reasoning-engines list --region=us-central1 --project=P

# delete one (frees a slot — the cap is 100 per project)
curl -s -X DELETE -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: P" \
  "https://us-central1-aiplatform.googleapis.com/v1/projects/P/locations/us-central1/reasoningEngines/ID?force=true"
```

---

## When you're done testing — clean up

Deployed agents count against a **100-per-project** cap, and throwaway ones count too.
Delete probes and experiments:

```bash
# 1. remove its Gemini Enterprise registration (console: Agents → ... → delete)
# 2. delete the reasoning engine (the curl above, with ?force=true for child sessions)
```

---

## The single most useful habit

**Test the deployed agent, not just the local one.** Almost every real bug we hit —
blank replies, empty tracker, silent quota errors, fabricated links — was invisible in
`adk web` and only showed up once deployed and driven the way Gemini Enterprise drives it.
Write a small script that calls your deployed agent through
`streaming_agent_run_with_events` and reads the session events back. That script finds
problems your users otherwise would.
