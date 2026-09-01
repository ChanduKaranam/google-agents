# Deploying an ADK agent and registering it in Gemini Enterprise

Verified by execution or by fetching the page on **2026-07-17**, against
`google-adk==2.4.0`. Undated or NOT DOCUMENTED items are not facts. Re-verify.

⚠️ **`google-adk` 2.5.0 is already released.** Every `--help`-sourced claim below (the
deprecated-flag table, precedence, folder layout, "no staging bucket needed") was
checked on 2.4.0 and has **no doc page as a second source** — `adk.dev/deploy/agent-runtime/`
does not mention `adk deploy agent_engine` at all. Re-run `--help` before trusting them.

## The pipeline

```
ADK Python  ->  adk deploy agent_engine  ->  Agent Runtime instance
                                             (reasoningEngines/<id>)
                                                     |
                                                     v
                                     register into a Gemini Enterprise app
                                     (Console, or Discovery Engine REST)
                                                     |
                                                     v
                                       agent appears in the app's gallery
```

Gemini Enterprise does not host your Python. It points at a deployed runtime.

## Prerequisites

Source: https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/setup

**APIs to enable** (verbatim from the setup page): Gemini Enterprise Agent Platform,
Cloud Storage, Cloud Logging, Cloud Monitoring, Telemetry, Cloud Trace, and Resource
Manager. Enabling requires `roles/owner` or `roles/serviceusage.serviceUsageAdmin`.
The API host is still `aiplatform.googleapis.com`.

**IAM** — the headline role is **`roles/aiplatform.user`** ("Agent Platform User").

⚠️ `roles/aiplatform.admin` is **not** the documented role. A summarizer pass invented
that claim; raw HTML of the deploy page does not contain it. Do not propagate it.

Other roles, by situation:

| Role | When |
|---|---|
| `roles/aiplatform.user` | use Agent Runtime — the baseline |
| `roles/aiplatform.agentDefaultAccess`, `roles/aiplatform.agentContextEditor` | held by the agent identity, by default |
| `roles/aiplatform.reasoningEngineServiceAgent` | Google-managed default SA: `service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com` |
| `roles/storage.admin` | staging bucket (only for deploy methods that stage) |
| `roles/artifactregistry.reader` | grant to the default service agent |
| `roles/iam.serviceAccountUser` | deploying with a custom SA |
| `roles/secretmanager.secretAccessor` | pulling secrets at runtime |

Also on the setup page but easy to miss: `roles/iam.serviceAccountTokenCreator`
(cross-project SA) and `roles/resourcemanager.projectCreator` (new project).

**Enable the APIs** (the setup page names them in prose; these are the service IDs):

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  storage.googleapis.com \
  logging.googleapis.com \
  monitoring.googleapis.com \
  cloudtrace.googleapis.com \
  telemetry.googleapis.com \
  cloudresourcemanager.googleapis.com \
  discoveryengine.googleapis.com     # registration only
```

**Local setup:**

```bash
pip install google-adk                      # or: uv pip install google-adk
gcloud auth login
gcloud auth application-default login
gcloud config set project PROJECT_ID
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member=user:YOU@example.com --role=roles/aiplatform.user
```

**If your agent touches GCS/Firestore** (e.g. a dedupe ledger), grant the runtime's
service account access to that bucket. The runtime does not get it for free:

```bash
gcloud storage buckets add-iam-policy-binding gs://BUCKET \
  --member=serviceAccount:service-PROJECT_NUMBER@gcp-sa-aiplatform-re.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

## Deploy: three competing paths

1. **`adk deploy agent_engine`** — verified to exist via `--help` (ADK 2.4.0). Reads
   `.env` and `requirements.txt` from the agent folder. **Not mentioned on
   `adk.dev/deploy/agent-runtime/`** — zero occurrences of `adk deploy` or
   `agent_engine` in that page's HTML.
2. **Agents CLI** (`google-agents-cli`) — what `/build/runtime` and
   `/deploy/agent-runtime/` actually recommend: *"For a streamlined deployment
   experience with Agent Runtime, consider the Agents CLI."* But its official ADK
   quickstart uses `--deployment-target cloud_run` — **Cloud Run, not Agent Runtime**.
3. **SDK** — `client.agent_engines.create(agent=..., config={...})` from
   `google-cloud-aiplatform[agent_engines,adk]>=1.112.0`. The deploy docs' own path.

This skill uses (1) because it was executed and verified. Google's docs point at (2).
The divergence is real and unresolved — choose deliberately.

A hand-rolled `agent_engines.create(...)` wrapper script duplicates what (1) already
does; don't write one just to set env vars.

```bash
adk deploy agent_engine \
  --project=PROJECT_ID \
  --region=us-central1 \
  --display_name="My Agent" \
  ./my_agent
```

Folder layout the CLI expects:

```
my_agent/
  __init__.py                   # from . import agent
  agent.py                      # must expose root_agent
  requirements.txt              # optional; auto-created if absent
  .env                          # optional; read automatically
  .agent_engine_config.json     # optional; display_name/description
```

**Precedence** (from source, `cli_deploy.py`): CLI flags beat
`.agent_engine_config.json`. `.env` supplies environment variables to the deployed
agent; `GOOGLE_CLOUD_PROJECT`/`GOOGLE_CLOUD_LOCATION` in `.env` are overridden by
`--project`/`--region` when those are passed explicitly.

**No staging bucket needed** for the local-source deploy path. The "from an agent
object" (Colab-style) path does need one — that is the only reason a bucket appears in
deploy docs. A bucket for your own data (a ledger) is a separate concern.

### Deprecated flags (verified in `--help`, ADK 2.4.0)

| Flag | Do instead |
|---|---|
| `--staging_bucket` | omit — "no longer required or used" |
| `--requirements_file` | `requirements.txt` in agent folder |
| `--env_file` | `.env` in agent folder |
| `--trace_to_cloud` | `--otel_to_cloud` |
| `--adk_app`, `--adk_app_object` | omit |
| `--absolutize_imports` | omit |
| `--validate-agent-import` / `--skip-agent-import-validation` | omit |

Useful non-deprecated flags: `--agent_engine_id` (update in place instead of creating a
new instance), `--adk_version` (pin the runtime's ADK; defaults to your local version —
set it if your dev box drifts ahead of what you tested), `--trigger_sources`
(`pubsub,eventarc` for event-driven invocation), `--session_service_uri`,
`--memory_service_uri`, `--artifact_service_uri`.

Deploy prints the resource name — registration needs it:

```
projects/PROJECT_ID/locations/us-central1/reasoningEngines/RESOURCE_ID
```

## Verify the deploy before registering

```bash
gcloud beta ai reasoning-engines list --region=us-central1 --project=PROJECT_ID
# teardown — the cap is 100 per project/region; stranded runtimes count against it
gcloud beta ai reasoning-engines delete RESOURCE_ID --region=us-central1 --project=PROJECT_ID
```

Logs (Cloud Logging): resource type `aiplatform.googleapis.com/ReasoningEngine`,
filter `resource.labels.reasoning_engine_id`. Log IDs: `reasoning_engine_stdout`,
`reasoning_engine_stderr`, `reasoning_engine_build` (build failures land here).
Monitoring is automatic — request count, latencies, CPU/memory allocation time.
ADK telemetry metrics require ADK >= 2.4.0.

## Register: Console (documented, reliable)

Gemini Enterprise → click app name → **Agents** → **Add agent** → **Add** under
**Custom agent via Agent Platform**. Supply name, description, and the
`reasoningEngines/...` resource path.

- IAM: **Gemini Enterprise Admin**. The A2A page calls the same role
  `discoveryengine.agentspaceAdmin`. The two official pages disagree on the name —
  at least one is stale.
- API: **Discovery Engine API** enabled.
- Prereq: an existing Gemini Enterprise app.

## Register: REST

```
POST https://ENDPOINT_LOCATION-discoveryengine.googleapis.com/v1alpha/projects/PROJECT_ID/locations/global/collections/default_collection/engines/APP_ID/assistants/default_assistant/agents
```

Payload is **camelCase**. Snake_case is the common wrong guess:

```json
{
  "displayName": "…",
  "description": "…",
  "adkAgentDefinition": {
    "provisionedReasoningEngine": {
      "reasoningEngine": "projects/PROJECT_ID/locations/RESOURCE_LOCATION/reasoningEngines/RESOURCE_ID"
    }
  }
}
```

⚠️ **Three location placeholders, and the docs do not explain how they relate.**
`ENDPOINT_LOCATION` (hostname prefix), `locations/global` (in the path), and
`RESOURCE_LOCATION` (where the runtime lives, e.g. `us-central1`) are independent.
The mapping rule is **NOT DOCUMENTED**. `ENDPOINT_LOCATION` tracks where the Gemini
Enterprise **app** was created (commonly `global`, `us`, or `eu` — often *not*
`global`), which is not necessarily where the runtime is. Do not guess: check the app's
location in the Console, and prefer the Console registration path.

`v1alpha` — expect churn. Verify field names before trusting this block.

A2A agents: same base path but `locations/LOCATION` (not `global`), and
`a2aAgentDefinition.jsonAgentCard` carrying the agent card as a JSON **string**.

## The `register-gemini-enterprise` CLI

Exists, but **not where the official docs imply**. Flags below verified 2026-07-17
against `agent-starter-pack` v0.41.3 — a third-party-ish package, pin before scripting.

- Ships in **`agent-starter-pack`** (PyPI, requires-python >=3.10), a
  GoogleCloudPlatform GitHub project — **not gcloud, not an official Cloud product**.
- Run without installing: `uvx agent-starter-pack@latest register-gemini-enterprise`
- Flags: `--gemini-enterprise-app-id`, `--agent-card-url`, `--deployment-target`
  (`agent_engine`|`cloud_run`), `--display-name`, `--description`, `--authorization-id`,
  `--agent-engine-id`, `--project-id`, `--project-number`, `--metadata-file`,
  `--tool-description`. `--authorization-id` wires an OAuth authorization for the
  registered agent; its setup is **not covered here**.
- The official ADK registration page points at "Agents CLI" (`google-agents-cli`) for
  one-command registration. That CLI's reference has **zero** mentions of "register" or
  "Gemini Enterprise". The official pointer is misleading.

## Gotchas paid for in real time

- **`google_search` cannot coexist with other tools on one `LlmAgent`.** Gemini rejects
  the combination. Make the searching agent a leaf; let the parent route its output.
  (Observed 2026-07-16; exact error text not captured — ADK/Gemini rejects at call time.)
- **Agent Runtime has no persistent disk.** Files written by a tool vanish between runs,
  silently. A dedupe ledger on local disk means the agent redoes everything forever.
- **Agent Designer allows exactly one level of subagents** (observed refusal, 2026-07-16;
  NOT DOCUMENTED). ADK has no such limit.
- **90 QPM / 100 resources per project per region** — low. Expect `429 Resource
  Exhausted` on real workloads; request quota early.
