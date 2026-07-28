# Job Helper Agent → Cloud Run A2A: deploy runbook

Task 5 of `docs/superpowers/plans/2026-07-27-a2a-host-hardening.md`, written out
as commands to run by hand. Everything before this is committed on
`feature/a2a-host-hardening` and tested; nothing here has been executed.

Project `supadha-dev`, region `us-central1`.

> **Read step 0 first.** Without it every `gcloud` command here reports "no
> credentialed accounts", and re-running `gcloud auth login` in WSL hangs
> forever with no browser to open.

---

## 0. Point gcloud at the Windows credentials

```bash
export CLOUDSDK_CONFIG="/mnt/c/Users/PurnaChandraRao/AppData/Roaming/gcloud"
export PROJECT=supadha-dev
export REGION=us-central1
gcloud config set project "$PROJECT"
gcloud auth list          # expect purna@tilicho.in
```

## 1. Find the Agent Engine that will back sessions and memory

The Cloud Run service does **not** replace the reasoning engine. It keeps using
it as the session store and Memory Bank. You need its numeric id.

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  "https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}/locations/${REGION}/reasoningEngines" \
  | python3 -m json.tool | grep -E '"name"|displayName'
```

Pick the one that is today's Job Helper Agent and export the trailing number:

```bash
export AGENT_ENGINE_ID=<numeric-id-from-above>
```

Getting this wrong is the failure mode to watch: a different engine id means a
different Memory Bank scope, and returning students silently read back nothing.

## 2. First deploy — to learn the service URL

`PUBLIC_HOST` is not known until the service exists, and the agent card must
advertise the real hostname. So deploy once, read the URL, then redeploy.

The first deploy is **expected to fail readiness**: `card.py` refuses to start
on Cloud Run (`K_SERVICE` set) without `PUBLIC_HOST`. That refusal is the guard
working. You only need the assigned URL from the output.

```bash
gcloud run deploy job-helper-a2a \
  --source . \
  --region "$REGION" \
  --no-allow-unauthenticated \
  --min-instances 1 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=${REGION},AGENT_ENGINE_ID=${AGENT_ENGINE_ID}"
```

**Check the build log says it used the Dockerfile.** If it mentions Cloud Native
Buildpacks instead, the repo-root `Dockerfile` was not picked up and none of the
import-path or boot-guard work is in the image.

```bash
export SERVICE_URL=$(gcloud run services describe job-helper-a2a --region "$REGION" --format='value(status.url)')
export PUBLIC_HOST=${SERVICE_URL#https://}
echo "$PUBLIC_HOST"
```

## 3. Redeploy with the hostname

```bash
gcloud run services update job-helper-a2a \
  --region "$REGION" \
  --update-env-vars "PUBLIC_HOST=${PUBLIC_HOST},PUBLIC_PROTOCOL=https"
```

The revision should now reach ready. If it does not, read the logs — the boot
guards fail loudly by design:

```bash
gcloud run services logs read job-helper-a2a --region "$REGION" --limit 50
```

Expect a startup line naming project, location, engine id and app_name. Confirm
`app_name` equals `AGENT_ENGINE_ID` — that is the Memory Bank scope.

## 4. Confirm `.env` did not ship in the image

```bash
gcloud run services describe job-helper-a2a --region "$REGION" --format='value(spec.template.spec.containers[0].image)'
# then, against that image tag:
gcloud container images describe <image> --format='value(image_summary.digest)'
```

Or simply — since `.dockerignore` has `**/.env` and `.gcloudignore` derives from
`.gitignore`, which already ignores `.env` — confirm the build context upload
did not include it by checking the Cloud Build log's file count. If in doubt,
`docker run --rm --entrypoint sh <image> -c "ls -a Job_Helper_agent/"` from any
machine with a working Docker daemon.

## 5. Let Gemini Enterprise invoke the service

```bash
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')
gcloud run services add-iam-policy-binding job-helper-a2a \
  --region "$REGION" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-discoveryengine.iam.gserviceaccount.com" \
  --role="roles/run.invoker"
```

## 6. Fetch the card the service actually serves

Do **not** register the static `agent_card.json` from the repo — its `url` is
`http://localhost:8080/`, a placeholder that `card.py` overrides at runtime.
Registering the file directly produces an agent that GE calls at localhost and
that therefore does nothing, which is the hardest GE failure to diagnose.

```bash
CARD=$(curl -sf -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  "${SERVICE_URL}/.well-known/agent-card.json")
echo "$CARD" | python3 -m json.tool | head -20
echo "$CARD" | python3 -c "import json,sys; u=json.load(sys.stdin)['url']; assert u.startswith('https://'), u; print('url ok:', u)"
```

## 7. Register in Gemini Enterprise as an A2A agent

`AI_GE` (`ai-ge_1784736359549`) is the existing multi-agent testing app and
already hosts the Job Helper Agent's `adkAgentDefinition` registration. Register
the new A2A one alongside it, leaving the old one live until step 9.

```bash
export GE_ENGINE=ai-ge_1784736359549

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: ${PROJECT}" \
  -H "Content-Type: application/json" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT_NUMBER}/locations/global/collections/default_collection/engines/${GE_ENGINE}/assistants/default_assistant/agents" \
  -d "$(python3 -c "import json,sys; print(json.dumps({'a2aAgentDefinition':{'jsonAgentCard': sys.stdin.read()}}))" <<< "$CARD")"
```

Record the returned agent name and verify the pointer resolves before concluding
anything from the agent's behaviour — a truncated engine id yields an agent that
silently does nothing.

## 8. Resolve the identity header — the agent is down until you do

**This is the one genuinely unknown step.** `to_a2a()` installs no
authentication middleware, so ADK falls back to a synthetic per-conversation
`A2A_USER_{context_id}`, which the privacy guard correctly refuses.
`Job_Helper_agent/identity.py` lifts the real end-user identity out of the
request headers instead — but which header GE sends is not documented anywhere
I could find, so it currently tries three candidates.

Send one message to the agent in GE, then read what arrived:

```bash
gcloud run services logs read job-helper-a2a --region "$REGION" --limit 100 | grep -i header
```

If you see no header log, add one temporarily in `identity.py`'s converter:

```python
logger.info("GE headers: %s", sorted(headers))
```

Then **narrow `IDENTITY_HEADERS` to the single confirmed name.** In particular
drop `x-user-email`: it is not a Google-managed header, so nothing strips a
client-supplied copy, and any principal able to invoke the service could use it
to assert another student's identity. Today only `--no-allow-unauthenticated`
prevents that, and no test enforces the flag.

If GE sends no usable identity at all, stop and redesign the identity path. Do
not widen the guard to accept the Discovery Engine service-agent identity — that
collapses every student into one Memory Bank scope, which is the exact leak
`callbacks.py` exists to prevent, and unlike a refusal it fails silently.

## 9. Parity checks — the bar is "same as before", not "better"

Run these in the GE chat surface against the new registration and record the
results in the ticket's Verification Log.

1. **It answers at all.** If every turn returns "I can't continue: this request
   arrived without a user identity", step 8 is unfinished. Do not work around it
   by loosening the guard.
2. **Shortlist quality** from a pasted resume matches the old registration.
3. **State survives a turn.** Track an application, then ask for the pipeline in
   a later turn. It must still be there. *(Regression 3 — instance recycling.)*
4. **History survives a session.** Close the conversation, start a new one, ask
   about earlier applications. It must come back. *(Regression 2 — and the check
   that confirms `app_name = AGENT_ENGINE_ID` was the right inference. If this
   fails, the Memory Bank scope is the first place to look.)*

## 10. Retire the old registration — only after step 9 passes

Remove the **GE registration** that points at the reasoning engine, so students
see one agent. **Leave the Agent Engine instance itself in place** — it is the
session and Memory Bank backing store, and deleting it destroys the data this
whole ticket exists to preserve.

---

## If you need to roll back

Nothing is destructive until step 10. Delete the new A2A agent registration and
the Cloud Run service; the original `adkAgentDefinition` registration and its
reasoning engine are untouched throughout.
