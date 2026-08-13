# Moving an ADK agent off Agent Engine onto a self-hosted A2A endpoint

Read this only when Step 0 said "runtime migration" — the agent is registered
via `adkAgentDefinition`. A2UI cannot render for that registration.

**What you are giving up by leaving the managed runtime, and must rebuild:**
persistent sessions, Memory Bank, the end user's identity, and the Vertex
model backend. `to_a2a()` replaces all four with stand-ins that fail silently.
The files below exist to put them back. Skipping any one of them produces an
agent that boots green and misbehaves in production only.

**Nothing here is destructive.** The reasoning engine stays — it becomes the
session and Memory Bank store. The old GE registration stays live until the new
one passes verification.

---

## 1. `requirements.txt`

```
google-adk[a2a]==2.4.0
# google-adk[a2a] pulls a2a-sdk but NOT its http-server extra, so sse-starlette
# is absent and A2AStarletteApplication raises at construction -- at lifespan
# startup, not at import. The container dies with "failed to start and listen
# on port 8080" while every import test passes. Cost a Cloud Run revision.
a2a-sdk[http-server]>=0.3,<0.4
google-cloud-aiplatform
uvicorn
```

Pin `a2a-sdk` — unconstrained it resolves to 1.1.2, an incompatible layout.

## 2. `runtime.py` — keep sessions and memory alive

`to_a2a()` builds a runner using `InMemorySessionService` and
`InMemoryMemoryService` (`google/adk/a2a/utils/agent_to_a2a.py:157-165`). On
Cloud Run, which runs several instances and recycles them freely, a
conversation's state can vanish between two turns and nothing is ever written
to Memory Bank. Neither failure raises.

```python
REQUIRED_ENV = ("GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "AGENT_ENGINE_ID")

def build_runner() -> Runner:
    missing = [n for n in REQUIRED_ENV if not os.environ.get(n)]
    if missing:
        raise RuntimeError(
            "Refusing to start without persistent session and memory storage."
            f" Missing environment: {', '.join(missing)}.")
    project = os.environ["GOOGLE_CLOUD_PROJECT"]
    location = os.environ["GOOGLE_CLOUD_LOCATION"]
    engine_id = os.environ["AGENT_ENGINE_ID"]

    bucket = os.environ.get("GOOGLE_CLOUD_STORAGE_BUCKET")
    return Runner(
        # app_name is the Memory Bank retrieval SCOPE, not a label. The Agent
        # Engine template defaulted it to the engine id, so every memory
        # already written lives under the numeric id. Any other value makes
        # preload_memory query an empty scope and silently return nothing.
        app_name=engine_id,
        agent=root_agent,
        session_service=VertexAiSessionService(
            project=project, location=location, agent_engine_id=engine_id),
        memory_service=VertexAiMemoryBankService(
            project=project, location=location, agent_engine_id=engine_id),
        artifact_service=(GcsArtifactService(bucket_name=bucket) if bucket
                          else InMemoryArtifactService()),
        credential_service=InMemoryCredentialService(),
    )
```

## 3. `card.py` — build the card in code

`to_a2a()` uses a card handed to it **verbatim** and never fills anything in
(`agent_to_a2a.py:203-205`); its `host`/`port`/`protocol` arguments only feed
the builder that runs when no card is supplied. So the `url` GE calls back on
must be injected before the card is passed.

```python
def require_public_host(public_host_env, k_service_env):
    """A deploy that forgets PUBLIC_HOST boots green and serves a card
    advertising https://localhost:8080/ -- a dead agent that looks healthy.
    Cloud Run always sets K_SERVICE, so its presence means a real host was
    required."""
    if public_host_env:
        return public_host_env
    if k_service_env:
        raise RuntimeError("Refusing to serve a card pointing at localhost.")
    return "localhost:8080"

def load_agent_card(public_host, protocol):
    raw = json.loads(CARD_PATH.read_text())
    raw["url"] = f"{protocol}://{public_host}/"
    return AgentCard(**raw)
```

The card must declare the A2UI extension, **v0.8**:

```json
"capabilities": {
  "streaming": true,
  "extensions": [{
    "uri": "https://a2ui.org/a2a-extension/a2ui/v0.8",
    "required": false,
    "params": {"supportedCatalogIds": [
      "https://a2ui.org/specification/v0_8/standard_catalog_definition.json"]}
  }]
}
```

## 4. `identity.py` — who is asking

GE forwards the signed-in user's OAuth token in `Authorization: Bearer …`, but
**only once the GE registration carries `authorizationConfig.agentAuthorization`**.
Without that the header is simply absent and every request looks anonymous.

Trust rules, non-negotiable:

- `authorization` — **accepted.** GE sets it; Cloud Run's own IAM check rides
  on a different header.
- `x-serverless-authorization` — **refused.** That is the Discovery Engine
  service agent, byte-identical for every user. Accepting it collapses everyone
  into one person's data.
- `x-user-email` and friends — **refused, always.** No proxy strips them, so
  any caller could assert someone else's identity.

Install it as a `before_agent` interceptor — `to_a2a()` builds its own executor
with a default config that drops inbound headers:

```python
app = to_a2a(
    root_agent,
    agent_card=load_agent_card(PUBLIC_HOST, PROTOCOL),
    runner=build_runner(),
    agent_executor_factory=lambda runner: A2aAgentExecutor(
        runner=runner,
        config=A2aAgentExecutorConfig(execute_interceptors=[
            ExecuteInterceptor(before_agent=identity.install(auth_module))])),
)
```

Also call `logging.basicConfig(level=logging.INFO)` in the entrypoint. Uvicorn
leaves the root logger at WARNING, so every `logger.info` — including the one
line saying whether an end-user token arrived — is dropped, and the log check
below finds nothing and reads as "identity is broken".

## 5. `Dockerfile`

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY your_agent/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY your_agent/ ./your_agent/
ENV PORT=8080
# Without this google-genai talks to the Gemini Developer API and needs an API
# key: the container boots green and fails on the first model call. .env is
# excluded from the image and nothing calls load_dotenv, so bake it here.
ENV GOOGLE_GENAI_USE_VERTEXAI=1
EXPOSE 8080
CMD ["sh", "-c", "uvicorn your_agent.main_a2a:app --host 0.0.0.0 --port $PORT"]
```

---

## Deploy

```bash
export CLOUDSDK_CONFIG="$WINDOWS_GCLOUD_CONFIG"   # WSL only
export PROJECT=... REGION=us-central1 SERVICE=your-agent-a2a
```

**Find the engine that will back sessions and memory.** Getting this wrong
means a different Memory Bank scope and returning users silently read nothing.

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/reasoningEngines" \
  | python3 -m json.tool | grep -E '"name"|displayName'
export AGENT_ENGINE_ID=<numeric id>
```

**Deploy twice.** `PUBLIC_HOST` is unknown until the service exists, and the
first deploy is *expected* to fail readiness — that refusal is the guard in
`card.py` working. You only need the assigned URL.

```bash
gcloud run deploy "$SERVICE" --source . --region "$REGION" \
  --no-allow-unauthenticated --min-instances 1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=${REGION},AGENT_ENGINE_ID=${AGENT_ENGINE_ID}"

export SERVICE_URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
gcloud run services update "$SERVICE" --region "$REGION" \
  --update-env-vars "PUBLIC_HOST=${SERVICE_URL#https://},PROTOCOL=https"
```

Check the build log used the **Dockerfile**, not Cloud Native Buildpacks — if
it used buildpacks, none of the env or boot-guard work is in the image. Never
predict the URL from a sibling service; new services get project-number URLs.

**Let GE invoke it:**

```bash
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

**Register the card the service actually serves** — never the repo file, whose
`url` is a localhost placeholder:

```bash
CARD=$(curl -sf -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${SERVICE_URL}/.well-known/agent-card.json")
echo "$CARD" | python3 -c "import json,sys; u=json.load(sys.stdin)['url']; assert u.startswith('https://'), u; print('url ok:', u)"

curl -X POST -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: ${PROJECT}" -H "Content-Type: application/json" \
  ".../engines/${GE_ENGINE}/assistants/default_assistant/agents" \
  -d "$(python3 -c "import json,sys; print(json.dumps({'a2aAgentDefinition':{'jsonAgentCard': sys.stdin.read()}}))" <<< "$CARD")"
```

Then **share it** — registration is not visibility. App → Agents → the agent →
User permissions → Add user. Console-only; no REST path is documented.

Verify the token is arriving before debugging anything else:

```bash
gcloud run services logs read "$SERVICE" --region "$REGION" --limit 50 | grep -i token
```

Retire the old `adkAgentDefinition` registration only after the Step-5
verification in SKILL.md passes. **Leave the reasoning engine itself alone** —
deleting it destroys the sessions and memories this migration exists to keep.
