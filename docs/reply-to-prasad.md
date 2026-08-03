Hi Prasad,

Thanks for turning that around fast. I re-ran everything against dev just now and can
confirm all four routes are registered. One thing worth flagging though: your check and
our blocker are measuring different things.

Every row in your table is a call made **without** the agent secret, so
`401 (secret required)` confirms "the route exists and auth is switched on" — but it
never exercises the flow itself. When we supply the secret and take the next step, we
hit a wall that hasn't moved since this morning:

- `GET /auth/agent-tokens` → **200** `{"tokens":[],"total":0}` — our secret is valid and
  current, and there are **zero tokens in dev**.
- `POST /auth/agent-tokens/exchange` with a **real, Google-signed, unexpired ID token**
  → **401 "Invalid Google ID token."**
- Every ambassador data route → **401**, because we hold no token.

To close off one possibility up front: we **are** already using the dev
`AGENT_AUTH_SECRET` you sent, on every call. It's accepted. The two failures are
distinguishable by their own error text —

| Call | Response |
|---|---|
| No secret, or a wrong secret | 401 `Invalid or missing X-Agent-Secret.` |
| Our secret + a real Google ID token | 401 `Invalid Google ID token.` |

Because exchange gets *past* the secret check and fails on the Google token instead, the
credential isn't what's blocking us.

So the endpoints are live but **not yet usable from our side** — we cannot obtain a
token, and without one there is nothing to integrate against. The agent is still on
dummy data.

Here is exactly what we need from you, in priority order.

---

### 1. Mint us one AMBASSADOR token in dev (fastest unblock)

This alone gets our integration moving today, independent of everything below. We can't
self-serve: `POST /auth/agent-tokens` correctly rejects us with `404 "User not found."`
because we have no way to discover a real `userId` or `tenantId`.

Please send the token, plus the `userId` and `tenantId` it's scoped to, over a secure
channel.

### 2. Tell us what audience `exchange` expects

Our ID token is genuinely valid: Google signed it, it hasn't expired, and
`email_verified` is true for `purna@tilicho.in`. Your doc says an email with no Sethu
account returns **404**, but we get **401** — so it looks like it's failing
signature/audience verification *before* the account lookup ever runs.

Our token's `aud` is gcloud's client ID, `32555940559.apps.googleusercontent.com`. If
your verifier is pinned to a specific OAuth client ID, that would explain it exactly.

Could someone check the server logs for `requestId: req-25`? From outside we can't
diagnose it — a garbage string, a fake-signature JWT and a genuine Google token all
return byte-identical errors.

### 3. Accept a Google **access token**, not just an ID token

This is the one that decides whether the agent can work at all in production.

Gemini Enterprise hands our agent an OAuth 2.0 **access token**, not an OIDC ID token.
(Our agent runs on the A2A protocol — required, because that's the only path that
supports the interactive cards the ambassador UI is built on.) So `exchange` as written
can never be called from the agent, no matter how the audience question resolves.

I've verified the fix works end to end — one call:

```bash
curl https://www.googleapis.com/oauth2/v3/userinfo -H "Authorization: Bearer <access_token>"
# -> {"sub":"...","email":"purna@tilicho.in","email_verified":true}
```

Requested change — additive, fully backward compatible:

```
POST /api/v1/auth/agent-tokens/exchange
X-Agent-Secret: <secret>
{ "googleAccessToken": "ya29..." }      // alternative to googleIdToken
```

Server-side: call the userinfo endpoint above; non-200 → your existing 401; otherwise
read the verified `email` and continue down the current code path unchanged, returning
the identical `{ token, tokenId, expiresAt, userId, role, tenantId }`. Security is
equivalent — Google stays the authority on identity, we never assert an email
ourselves, and `X-Agent-Secret` is still required.

### 4. Send us the API usage pack

This is the biggest time-saver and needs nothing deployed. Specifically:

**a. Sample response bodies** (dev data is fine) for:

- `GET /tenants/{tenantId}/cohorts/mine` — especially whether it carries the full
  student list, and whether that list is paged (we display 6 of 59 plus a true total)
- `GET /cohorts/mine/stragglers`
- `GET /tenants/{tenantId}/leaderboard`
- `GET /cohorts/mine/students/{studentId}` — the **touch history** shape above all

With these we can build and test the entire integration now and wire credentials in
last, instead of waiting on auth.

**b. A Postman/Insomnia collection or `.http` file**, if one exists — a working request
per endpoint beats a schema doc.

**c. Field-level notes** on anything with business meaning: what `status` values a
student can have, what `activatedAt` means when null, how pagination is expressed
(`page`/`limit`/`total`?), and what `channel`/`outcome` values a touch can carry.

**d. Error catalogue** — the `error.code` strings we should expect per endpoint (we've
seen `UNAUTHORIZED`, `VALIDATION_ERROR`, `NOT_FOUND`), and which are retryable.

**e. Rate limits or throttling** we should respect, if any.

### 5. Two gaps we found while building

**Is there a write endpoint to record a nudge?** When the ambassador sends a WhatsApp
message, we currently record it in conversation state only — Sethu never learns it
happened, so it won't appear in that student's touch history. Since the detail endpoint
exposes touch history, we assume touches get recorded somewhere. Is there a `POST` for
it, or is attribution meant to ride entirely on the `/go/` link click?

**Rewards tiers and the class roster** have no endpoints listed, and the agent renders
both. Should they come from the API, or stay as content on our side?

---

One last thing, kindly meant: the dev `AGENT_AUTH_SECRET` is written inside the guide
document itself. Your own security section says Secret Manager, never in files — worth
pulling it out before that doc circulates further. We've kept our copy out of version
control.

Happy to jump on a quick call if that's faster than a thread.

Thanks,
Purna

---
---

## Technical appendix — paste this into your AI assistant

### Context

We build the Gemini Enterprise agents that sit on top of Sethu. This concerns the
**ambassador agent**: a student ambassador opens it inside Gemini Enterprise and asks
things like "who should I message?", "how's my section doing?", "where am I on the
leaderboard?" It answers with interactive cards.

It's Python on Google's ADK, deployed to **Cloud Run as an A2A agent** and registered
into Gemini Enterprise. It currently runs entirely on hardcoded fixtures. Its data
access is isolated in a single module written to be swapped for HTTP calls, so
integration is cheap once auth works.

All testing is against dev only: `https://sethu-dev-api.onrender.com/api/v1`. We will
not touch prod until explicitly cleared.

### Reproduction

```bash
B=https://sethu-dev-api.onrender.com/api/v1
S=<AGENT_AUTH_SECRET>

# 1. Secret valid, dev holds no tokens  ->  200 {"tokens":[],"total":0}
curl -s "$B/auth/agent-tokens" -H "X-Agent-Secret: $S"

# 2. Real Google ID token, verified email  ->  401 "Invalid Google ID token."
T=$(gcloud auth print-identity-token)
#   aud=32555940559.apps.googleusercontent.com
#   email=purna@tilicho.in, email_verified=true, unexpired
curl -s -X POST "$B/auth/agent-tokens/exchange" \
  -H "X-Agent-Secret: $S" -H 'Content-Type: application/json' \
  -d "{\"googleIdToken\":\"$T\"}"

# 3. Admin mint with unknown ids  ->  404 "User not found."  (cannot self-provision)
curl -s -X POST "$B/auth/agent-tokens" \
  -H "X-Agent-Secret: $S" -H 'Content-Type: application/json' \
  -d '{"userId":"...","role":"AMBASSADOR","tenantId":"..."}'

# 4. Any data route  ->  401 Unauthorized
curl -s "$B/cohorts/mine/stragglers" -H "X-Agent-Secret: $S"
```

### Diagnostic detail for the 401 on exchange

Three different inputs produce byte-identical responses:

| Input | Response |
|---|---|
| `"not-a-token"` | 401 `Invalid Google ID token.` |
| Well-formed JWT, fake signature | 401 `Invalid Google ID token.` |
| Genuine Google ID token, verified email | 401 `Invalid Google ID token.` |

Since the documented behaviour for an unknown email is **404**, and `POST
/auth/agent-tokens` does correctly return `404 "User not found."`, the failure is
occurring in verification rather than in the account lookup. Audience mismatch is the
leading hypothesis. Failing `requestId`s: `req-25`, `req-d4`.

Suggestion regardless of cause: distinguish the failure modes in the response
(`INVALID_SIGNATURE` / `AUDIENCE_MISMATCH` / `TOKEN_EXPIRED` / `USER_NOT_FOUND`), or at
minimum log them. Right now the endpoint is undiagnosable from the client side.

### Route map observed on dev

Exists (401 without a token): `/tenants/{t}/cohorts/mine`, `/cohorts/mine/stragglers`,
`/cohorts/mine/students/{id}`, `/tenants/{t}/leaderboard`, `/faculty/agents`,
`/faculty/sections`, `/auth/me` (undocumented).

Not found: `/users`, `/tenants`, `/cohorts`, `/students`, `/leaderboard`, `/me`,
`/health`, `/admin`, `/docs`, `/openapi.json`, `/ambassadors`.

Error envelope we're coding against, confirmed consistent across every route:

```json
{"data": null,
 "error": {"code": "UNAUTHORIZED", "message": "Unauthorized"},
 "meta": {"timestamp": "2026-08-03T05:47:30.155Z", "requestId": "req-27"}}
```

We log `meta.requestId` on every failure so issues can be traced from your side.

### Why the access-token change is required, in detail

Gemini Enterprise agent registrations differ in what end-user credential they forward:

- **`adkAgentDefinition`** (agent hosted on Vertex AI Agent Engine): GE passes the end
  user's email directly as `user_id`.
- **A2A agent** (our case): with `authorizationConfig.agentAuthorization` set on the
  registration, GE runs a Google OAuth flow and forwards the end user's **OAuth 2.0
  access token** in the `Authorization: Bearer` header. That token is opaque
  (`ya29...`-style), not a signed JWT, so there is no signature for Sethu to verify
  against Google's JWKS.

We are on the A2A path because the interactive card extension the ambassador UI depends
on is only negotiated over A2A. So the ID-token route is structurally unavailable to us.

Verified working substitute — Google returns the identity for an access token:

```
GET https://www.googleapis.com/oauth2/v3/userinfo
Authorization: Bearer <access token>
->  200 {"sub":"1044979...","email":"purna@tilicho.in","email_verified":true}
```

Equivalent alternative: `GET https://oauth2.googleapis.com/tokeninfo?access_token=...`,
which additionally returns `aud` and `expires_in` if you want to pin the audience to our
OAuth client ID. We'll send that client ID once the Gemini Enterprise OAuth client is
created.

### Client behaviour we've already committed to

- **Token reuse** per your doc: check `GET /auth/agent-tokens?userId={userId}` for a
  live, unrevoked token before calling exchange; cache per user; re-exchange ahead of
  `expiresAt`.
- **Secret handling**: `X-Agent-Secret` lives in Google Secret Manager, injected as a
  Cloud Run environment variable, never committed.
- **Activation lag** understood: 0–15 min typical, up to ~6h worst case, `activatedAt`
  being Google's certified login time. We surface freshness in the UI rather than
  implying real-time.
- **Dev only** until explicitly cleared for prod.

### What we need to finish the integration

1. One AMBASSADOR agent token for dev, with its `userId` and `tenantId`.
2. The expected `aud` for `exchange`, or confirmation that audience isn't checked.
3. `googleAccessToken` support on `exchange`.
4. Sample response bodies for the four ambassador endpoints — the touch-history shape
   in `students/{id}` above all, since we've built the student-detail card against a
   guessed `{ at, channel, outcome }` per touch.
5. Whether a write endpoint exists for recording a nudge.
6. Whether rewards tiers and the class roster are API-served or our own content.
