# Turning on per-ambassador identity

Right now the agent serves one hardcoded ambassador (`SETHU_AGENT_TOKEN`). This
runbook switches it to real per-student identity: each ambassador signs in once
in Gemini Enterprise, and every turn afterwards carries their own Google token,
which the agent trades with Sethu for that person's own cohort.

Everything below is Google Cloud configuration. The agent code is already done
(`identity.py` reads the header, `sethu.py` exchanges it).

## Your actual values

| What | Value |
|---|---|
| Project | `supadha-dev` (number `1019856256943`) |
| GE app (engine) | `ai-ge_1784736359549` (AI_GE) |
| Registered agent | `15654412355158356535` — "Campus Ambassador", `a2aAgentDefinition`, currently **no** `authorizationConfig` |
| Cloud Run service | `ambassador-a2a`, region `us-central1` |
| Authorization resource we will create | `projects/supadha-dev/locations/global/authorizations/sethu-ambassador` |

Verified against the live Discovery Engine API on 2026-08-03. The field is
`authorizationConfig.agentAuthorization`, and Google's own description of it is:
*"The authorization that is required to invoke the agent. Auth tokens will be
passed to the agent as part of the request auth header."* — which is exactly the
header `identity.py` reads.

Set this once per shell; without it gcloud can't see your credentials:

```bash
export CLOUDSDK_CONFIG="/mnt/c/Users/PurnaChandraRao/AppData/Roaming/gcloud"
export PROJECT=supadha-dev
export ENGINE=ai-ge_1784736359549
export AGENT=15654412355158356535
export AUTH_ID=sethu-ambassador
```

---

## Step 1 — Create the OAuth client (console only)

This part cannot be scripted; OAuth clients are console-only.

1. Go to **APIs & Services → Credentials** in project `supadha-dev`:
   https://console.cloud.google.com/apis/credentials?project=supadha-dev

2. If prompted to configure the **OAuth consent screen** first:
   - User type: **Internal** if `tilicho.in` is a Workspace domain, otherwise
     **External**. This is the step most likely to bite — see "Known
     obstacles" at the bottom.
   - App name: `Sethu Campus Ambassador`
   - Support email + developer contact: your own address.
   - Scopes: add `openid`, `.../auth/userinfo.email`,
     `.../auth/userinfo.profile`. Nothing else — we only need to know who the
     caller is.
   - If **External**, add each ambassador as a **Test user** while the app is
     unverified, or they'll be refused at consent.

3. **Create Credentials → OAuth client ID**
   - Application type: **Web application**
   - Name: `sethu-ambassador-ge`
   - **Authorised redirect URI** — must be exactly this, no trailing slash:

     ```
     https://vertexaisearch.cloud.google.com/oauth-redirect
     ```

4. Copy the **Client ID** and **Client secret**.

```bash
export CLIENT_ID='<paste>.apps.googleusercontent.com'
export CLIENT_SECRET='<paste>'
```

> A wrong redirect URI is the single most common failure here. It surfaces much
> later as `redirect_uri_mismatch` on the consent screen, not as an error now.

---

## Step 2 — Create the GE authorization resource

The `authorizationUri` is a full Google consent URL with the scopes baked in.
Note `access_type=offline` and `prompt=consent`, which are what get you a
refresh token so the ambassador consents once rather than every session.

```bash
AUTH_URI="https://accounts.google.com/o/oauth2/v2/auth\
?client_id=${CLIENT_ID}\
&redirect_uri=https://vertexaisearch.cloud.google.com/oauth-redirect\
&response_type=code\
&scope=openid%20email%20profile\
&access_type=offline\
&prompt=consent"

curl -X POST \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: ${PROJECT}" \
  -H "Content-Type: application/json" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT}/locations/global/authorizations?authorizationId=${AUTH_ID}" \
  -d "{
    \"name\": \"projects/${PROJECT}/locations/global/authorizations/${AUTH_ID}\",
    \"displayName\": \"Sethu Campus Ambassador\",
    \"serverSideOauth2\": {
      \"clientId\": \"${CLIENT_ID}\",
      \"clientSecret\": \"${CLIENT_SECRET}\",
      \"authorizationUri\": \"${AUTH_URI}\",
      \"tokenUri\": \"https://oauth2.googleapis.com/token\"
    }
  }"
```

Confirm it exists:

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: ${PROJECT}" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT}/locations/global/authorizations" \
  | python3 -m json.tool
```

---

## Step 3 — Flip the switch on the agent registration

Until this PATCH lands, Gemini Enterprise sends **no** user token at all — this
is the actual on/off switch, and it's why our 2026-07-28 measurement saw no
identity.

```bash
curl -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: ${PROJECT}" \
  -H "Content-Type: application/json" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT}/locations/global/collections/default_collection/engines/${ENGINE}/assistants/default_assistant/agents/${AGENT}?updateMask=authorizationConfig" \
  -d "{
    \"authorizationConfig\": {
      \"agentAuthorization\": \"projects/${PROJECT}/locations/global/authorizations/${AUTH_ID}\"
    }
  }"
```

Verify it stuck — `authorizationConfig` must now be present:

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: ${PROJECT}" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/${PROJECT}/locations/global/collections/default_collection/engines/${ENGINE}/assistants/default_assistant/agents/${AGENT}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('authorizationConfig'))"
```

---

## Step 4 — Swap the Cloud Run environment

Put the Sethu server-to-server secret in Secret Manager, and **remove** the
pre-minted token so the agent stops impersonating one ambassador.

```bash
# once. Paste the dev AGENT_AUTH_SECRET at the prompt rather than putting it on
# the command line -- an inline literal lands in shell history and, if this file
# is edited in place, in git.
read -rs SETHU_SECRET
printf '%s' "$SETHU_SECRET" \
  | gcloud secrets create sethu-agent-secret --data-file=- --project ${PROJECT}
unset SETHU_SECRET

# let the service read it (substitute the service's runtime SA if not default)
gcloud secrets add-iam-policy-binding sethu-agent-secret \
  --member="serviceAccount:1019856256943-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" --project ${PROJECT}

gcloud run services update ambassador-a2a \
  --region us-central1 --project ${PROJECT} \
  --update-secrets=SETHU_AGENT_SECRET=sethu-agent-secret:latest \
  --remove-env-vars=SETHU_AGENT_TOKEN
```

Deploy the current code first — Cloud Run is still running the pre-integration
build. See `docs/a2a-deploy-runbook.md`.

---

## Step 5 — Verify with a real ambassador

1. Open the Campus Ambassador agent in Gemini Enterprise as an ambassador who
   **exists in Sethu with role AMBASSADOR**. Google will show a consent screen
   once.
2. Ask "where do I stand?"
3. Check the logs — `identity.py` logs one line per request:

```bash
gcloud run services logs read ambassador-a2a --region us-central1 \
  --project ${PROJECT} --limit 50 | grep -E "end-user token|no end-user identity|Exchanged"
```

- `Request carried an end-user token (N chars)` → GE is forwarding identity.
- `Request carried no end-user identity` → step 3 didn't take effect, or the
  ambassador hasn't consented.
- `Exchanged a Sethu token: role=AMBASSADOR tenantId=…` → full chain working.

The decisive test: **two different ambassadors see different cohorts.** Until
that's confirmed, per-student identity isn't proven.

---

## Rollback

Point the agent back at the pre-minted token; no OAuth teardown needed.

```bash
gcloud run services update ambassador-a2a --region us-central1 --project ${PROJECT} \
  --update-env-vars=SETHU_AGENT_TOKEN='<the minted ambassador token>'
```

`SETHU_AGENT_TOKEN` takes precedence over the exchange flow, so setting it is a
complete rollback on its own.

---

## Known obstacles

**The consent screen is the risky step.** `tilicho.in`'s Workspace status is
disputed (MX records say yes, an earlier OAuth attempt said no) and
`supadha-dev` sits in an org we can't enumerate. If **Internal** is unavailable,
you're on **External**, which means either adding every ambassador as a test
user (100-user cap) or going through Google verification. Settle this before
building anything on top.

**Every ambassador must exist in Sethu** with role `AMBASSADOR` and a matching
email address. Anyone else gets a 404 from the exchange endpoint. The agent does
not yet report that failure gracefully — it currently raises, the callback
swallows it, and the model answers with no data. Worth fixing before rollout.

**Sethu's dev cohort is nearly empty** — Akhil's section holds one student
(himself) and returns no stragglers, so the chase-and-nudge flow has nothing to
show regardless of identity.
