# Building a Gemini Enterprise agent on Sethu — what we learned the hard way

Written 2026-08-03, after taking the **Campus Ambassador** agent from fixtures
to live Sethu data with real per-user identity. Everything here is measured
against the running system, not inferred from documentation — several of the
worst hours went into places where the documentation was wrong or silent.

Read this before writing code for the **Faculty agent**. The architecture is
identical; only the endpoints and the role differ.

> **Give this whole file to your coding agent.** The "Mistakes" section is the
> valuable part: every item cost us real debugging time, and most of them fail
> *silently* — green tests, healthy container, wrong or missing data on screen.

---

## 1. The shape of the thing

```
Ambassador/Faculty opens the agent in Gemini Enterprise
        │
        ▼  GE runs Google OAuth (once), then forwards the user's
           OAuth ACCESS token in the `Authorization` header
        │
   Cloud Run service (ADK agent, A2A protocol, A2UI cards)
        │
        ▼  POST /auth/agent-tokens/exchange { googleAccessToken }
           + X-Agent-Secret
        │
   Sethu returns { token, userId, role, tenantId, expiresAt }
        │
        ▼  Authorization: Bearer <that token>
   GET /tenants/{tenantId}/... etc.
```

Nothing about the user is hardcoded. The token carries who they are and which
college they belong to.

**Why A2A on Cloud Run and not Agent Engine:** only the A2A path can render
A2UI cards. An agent registered via `adkAgentDefinition` cannot draw UI. If
your faculty agent needs cards, you are on this path too, and you inherit the
identity problem below.

---

## 2. Environment (already exists — don't recreate)

| What | Value |
|---|---|
| Project | `supadha-dev`, number **`1019856256943`** |
| GE app (engine) | `ai-ge_1784736359549` (AI_GE) |
| Sethu dev API | `https://sethu-dev-api.onrender.com/api/v1` |
| OAuth client | `1019856256943-6ruv4ov6kjsshib3dqabjpf86o2j4kvb.apps.googleusercontent.com` |
| GE authorization resource | `projects/1019856256943/locations/global/authorizations/sethu-ambassador` |
| Reference implementation | `ambassador_agent/` in this repo |

**Never point anything at the Sethu prod API** (`api.sethu.tilicho.in`) until
Purna explicitly clears it. Dev only, including in docs and scripts.

gcloud in WSL needs this before every session, or it reports "no credentialed
accounts" and `gcloud auth login` hangs forever with no browser:

```bash
export CLOUDSDK_CONFIG="/mnt/c/Users/PurnaChandraRao/AppData/Roaming/gcloud"
```

---

## 3. Turning on per-user identity

**Good news: steps 1 and 2 are already done.** The OAuth client and the
authorization resource exist and are shared. The faculty agent needs **only
step 3** — pointing its own registration at the same authorization resource.

### Step 3 (the switch)

Until this is set, **GE forwards no identity at all** — no header, nothing.
The agent cannot know who is asking.

```bash
export CLOUDSDK_CONFIG="/mnt/c/Users/PurnaChandraRao/AppData/Roaming/gcloud"
export AGENT_ID=<your faculty agent's numeric id>

curl -X PATCH \
  -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: supadha-dev" -H "Content-Type: application/json" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/supadha-dev/locations/global/collections/default_collection/engines/ai-ge_1784736359549/assistants/default_assistant/agents/${AGENT_ID}?updateMask=authorizationConfig" \
  -d '{"authorizationConfig":{"agentAuthorization":"projects/1019856256943/locations/global/authorizations/sethu-ambassador"}}'
```

**The `agentAuthorization` value must use the project NUMBER, not the project
ID.** `projects/supadha-dev/...` is rejected with
`400 Invalid Authorization name`, even though you create the resource under the
project ID. This cost us a confusing failure.

Find your agent id:

```bash
curl -s -H "Authorization: Bearer $(gcloud auth print-access-token)" \
  -H "X-Goog-User-Project: supadha-dev" \
  "https://discoveryengine.googleapis.com/v1alpha/projects/supadha-dev/locations/global/collections/default_collection/engines/ai-ge_1784736359549/assistants/default_assistant/agents" \
  | python3 -c "
import sys,json
for a in json.load(sys.stdin)['agents']:
    print(a['name'].split('/')[-1], a.get('displayName'), a.get('authorizationConfig'))"
```

### If you must create your own authorization resource

Only if you want separate revocation. Reuse is simpler and the scopes are
identical. If you do create one, note the OAuth client's redirect URI must be
**exactly** `https://vertexaisearch.cloud.google.com/oauth-redirect`, and the
`authorizationUri` needs `access_type=offline&prompt=consent` or the user
re-consents every session.

---

## 4. Sethu API contract

Base `https://sethu-dev-api.onrender.com/api/v1`. Every response is wrapped:

```json
{"data": {...}, "error": null,
 "meta": {"timestamp": "...", "requestId": "req-27"}}
```

Log `meta.requestId` on every failure — Sethu's team can trace it.

Error codes seen: `UNAUTHORIZED`, `FORBIDDEN`, `NOT_FOUND`, `VALIDATION_ERROR`.

### Exchange

```
POST /auth/agent-tokens/exchange
X-Agent-Secret: <AGENT_AUTH_SECRET>       # ask Purna; it rotates
{ "googleAccessToken": "ya29..." }        # NOT googleIdToken — see mistake #1
```

Returns `{ token, tokenId, expiresAt, userId, role, tenantId }`. `role` is
`AMBASSADOR | FACULTY | COLLEGE_ADMIN`. Tokens last 30 days; reuse via
`GET /auth/agent-tokens?userId=...` before minting more.

### Faculty endpoints (require a FACULTY-role token)

| Method + path | Purpose |
|---|---|
| `GET /faculty/agents` | list the faculty member's GE agents |
| `POST /faculty/agents` | create one — `{name, description, whoCanUse}` |
| `PUT /faculty/agents/{id}/sections` | assign sections — `{sectionIds:[...]}` |
| `POST /faculty/agents/{id}/notify` | WhatsApp notify assigned sections |
| `POST /faculty/agents/{id}/claim` | claim an agent (idempotent) |
| `GET /faculty/sections` | the faculty member's own sections |
| `GET /faculty/section-recipient` | recipients for a section |

Also useful and undocumented: **`GET /auth/me`** returns
`{id, name, email, role, tenantId}` for the bearer token. Best possible smoke
test.

**Known dev bug:** `/faculty/sections` returned **403 to a valid FACULTY
token** on 2026-08-03 while `/faculty/agents` returned 200. Verify before
assuming your code is wrong.

---

## 5. Code patterns worth copying

Copy `ambassador_agent/sethu.py` and `identity.py` almost verbatim; change only
the endpoint paths and the role expected.

### identity.py — who is asking

```python
_current_user_token: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sethu_user_token", default=None)
```

- **A ContextVar, never a module global.** Cloud Run serves requests
  concurrently in one process; a global is shared mutable state, and two users
  overlapping by milliseconds read each other's data.
- **Accept only the `Authorization` header.** Explicitly refuse
  `x-serverless-authorization` (that's the Discovery Engine service agent —
  byte-identical for every user, so it would collapse everyone into one
  identity) and `x-user-email` (no proxy strips it, so any caller could assert
  anyone's identity).

### Wiring the hook

`to_a2a()` builds its own executor and drops the inbound headers, so every
request looks anonymous. Pass a factory:

```python
app = to_a2a(root_agent, agent_card=..., runner=...,
             agent_executor_factory=lambda runner: A2aAgentExecutor(
                 runner=runner,
                 config=A2aAgentExecutorConfig(execute_interceptors=[
                     ExecuteInterceptor(before_agent=identity.install(sethu))])))
```

Headers arrive at `context.call_context.state['headers']`
(`a2a/server/apps/jsonrpc/jsonrpc_app.py:153`).

### sethu.py — the client

- `TIMEOUT_SECONDS = 30` **plus one retry on transport failure.** Sethu's dev
  API sleeps on Render's free tier; the request that wakes it reliably times
  out (measured 45s cold).
- **Never retry a real API answer** (401/403/404) — only transport failures.
- **30-second response cache.** One card read the cohort five times; uncached
  that was 5 requests and ~10s. Sethu's numbers lag Google by 15min–6h anyway,
  so a few seconds of cache shows nothing staler than the endpoint does.
- **Error taxonomy, because the user-facing answer differs:**

| Failure | Class | What to say |
|---|---|---|
| No end-user token | `NoIdentity` | "I can't confirm who you are…" |
| Exchange 401 | `NoIdentity` | same — retrying can't change who you are |
| Exchange 404 | `NotRegistered` | "not registered as faculty in Sethu" |
| Data route 401/403 | `NotRegistered` | authenticated, wrong role/cohort |
| Timeout / unreachable | `SethuError` | "can't reach Sethu, try again" |

---

## 6. The mistakes — read this section twice

Every one of these was found in a deployed system, not by tests.

**1. Sethu's guide says send a Google *ID token*. You cannot.**
GE forwards an opaque OAuth **access token**, not a signed OIDC token. The
ID-token path is unreachable from a GE agent. Sethu added `googleAccessToken`
for exactly this. Verify identity yourself with
`GET https://www.googleapis.com/oauth2/v3/userinfo`.

**2. "GE sends no identity" was a measurement of an unconfigured agent.**
We concluded identity was impossible over A2A. It wasn't — we simply had not
set `authorizationConfig`. Never conclude a capability is absent from a test
you ran with it switched off.

**3. A pre-minted token in production is a data leak.**
We shipped with `SETHU_AGENT_TOKEN` so the demo had live data. Result: every
user, whoever they signed in as, saw one specific ambassador's cohort. Honour
such a token **only off Cloud Run** (`K_SERVICE` unset).

**4. Falling back to fixtures in production is worse than failing.**
Our data layer served recorded samples when the API was unreachable. Deployed,
that puts invented students with invented phone numbers in front of a real user
as though they were their class. In production: identify the user, or refuse.

**5. `urlopen(timeout=)` raises `TimeoutError`, not `URLError`.**
Our transport handler missed it, the exception escaped, ADK failed the node,
and the user's reply was the literal text "The read operation timed out".

**6. A swallowed error means a blank agent.**
Our render callback caught everything and returned `None`, so a Sethu timeout
produced the model's generic "How can I help?" with no card and no buttons —
indistinguishable from a dead agent. Always render *something*: an honest
message plus the option buttons.

**7. Live phone numbers have no country code.**
Sethu's sample showed `+919876543210`; real rows are `9876501041`. `wa.me`
silently opens an empty chat without a country code. The most important action
in the product, broken, with no error anywhere. Normalise.

**8. Uvicorn leaves the root logger at WARNING.**
Every `logger.info` is dropped, including the line that tells you whether GE
forwarded identity. Add `logging.basicConfig(level=logging.INFO)` in your
`main_a2a.py` or you will debug blind.

**9. Gemini Enterprise supports A2UI v0.8 only.**
v0.9.1 is current production and adds `openUrl` (a button that opens a URL —
genuinely useful for WhatsApp links). We advertised both and measured what GE
activated: **v0.8**. Do not advertise a version you cannot render — clients
negotiate the highest both sides claim, so the day GE upgrades, every card
breaks with no code change on your side.

**10. `GET /cohorts/mine/students/{id}` has a side effect.**
It *creates* a GoToken and writes a `link_shared` touch. A read that looks like
a read but writes history. Check whether any faculty endpoint does the same
before calling it in a loop.

**11. Secret Manager may be refused.**
`secretmanager.secrets.setIamPolicy` is denied for our accounts on
`supadha-dev`, so the runtime service account cannot be granted access to a new
secret. Env vars are the fallback for dev. Do not spend an hour on it.

**12. Never commit a secret.** The dev `AGENT_AUTH_SECRET` was pasted into a
shared doc and has since rotated. Read secrets from a prompt (`read -rs`), keep
them out of git, and expect rotation.

**13. Small-cohort arithmetic reads as broken.** A dev cohort of 1 produced
"1 students" and every reward tier reading "1 more". Pluralise, and sanity-check
your copy at n=0 and n=1.

---

## 7. Verification checklist

Do these in order. Each one has caught a real failure.

```bash
# 1. Secret is valid (200, and a wrong secret gives 401)
curl -s "$B/auth/agent-tokens" -H "X-Agent-Secret: $S"

# 2. Exchange works with a real Google access token
A=$(gcloud auth print-access-token)
curl -s -X POST "$B/auth/agent-tokens/exchange" -H "X-Agent-Secret: $S" \
  -H 'Content-Type: application/json' -d "{\"googleAccessToken\":\"$A\"}"

# 3. The token identifies the right person
curl -s "$B/auth/me" -H "Authorization: Bearer <token>"

# 4. Deployed agent serves a card (simulate GE exactly:
#    IAM token in x-serverless-authorization, user token in Authorization)
curl -s -X POST "$URL/" \
  -H "X-Serverless-Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Authorization: Bearer $A" -H 'Content-Type: application/json' \
  -H 'X-A2A-Extensions: https://a2ui.org/a2a-extension/a2ui/v0.8' \
  -d '{"jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":
       {"role":"user","messageId":"m1","parts":[{"kind":"text","text":"hi"}]}}}'

# 5. Identity actually arrived
gcloud run services logs read <service> --region us-central1 \
  --project supadha-dev --limit 50 | grep "identity:"
```

The decisive test is not "does it work" but **"do two different people see
different data?"** Until you have confirmed that with two accounts, per-user
identity is unproven.

---

## 8. Current state of the Sethu dev data

- Ambassador `akhil.sai@tilicho.in` has a cohort of **one student — himself**,
  0 activated, and no stragglers. Any flow that needs a populated section
  cannot be demonstrated yet.
- `purna@tilicho.in` exists as **FACULTY**, tenant
  `019fb168-8afb-7acc-bd07-e90fd3d9d1a5` — useful for faculty-agent testing.
- Ask Prasad (`prasad@tilicho.in`) for seeded data before promising a demo.

## 9. Open asks with Sethu

1. A **write endpoint to record a nudge**. Today a sent WhatsApp message exists
   only in conversation state; attribution rides entirely on the `/go/` link
   click.
2. A **read-only variant of the student-detail endpoint** (see mistake #10).
3. **Seeded cohorts** in dev.
