Hi Prasad,

Thanks for the updated auth guide — the design is clear and the ambassador agent is
built to slot straight into it. Our data layer was written with exactly this swap in
mind, so once the two items below are sorted, going from dummy data to live is a
small change on our side.

Two things are blocking us, one small and one that needs a decision from you.

**1. The token endpoints aren't deployed on dev yet.**

I tested the dev API this morning. The good news: all four ambassador data routes are
live and correctly rejecting us with 401 — `/tenants/{tenantId}/cohorts/mine`,
`/cohorts/mine/stragglers`, `/cohorts/mine/students/{id}` and
`/tenants/{tenantId}/leaderboard`. So the data side is ready.

But every route that *issues* a token returns 404 — the whole `/auth/agent-tokens/*`
family, including `/exchange`. So there's currently no way to get past the 401. Could
someone deploy those to dev?

We're staying on dev end to end for now — we won't point anything at prod until you
tell us to.

**2. Google gives our agent a different kind of token than `exchange` expects.**

This is the one that needs a change on your side, and I want to explain it plainly
because it's easy to miss.

The guide assumes the agent receives the user's Google **ID token** — a signed
passport that Sethu can verify by itself against Google's public keys. That's true for
one style of Gemini Enterprise agent. Ours is a different style (an A2A agent on Cloud
Run — we had to build it that way because it draws interactive cards in the chat, which
only the A2A path supports). For our style, Google hands us an **access token**
instead — think coat-check ticket rather than passport. It's completely valid and
identifies the user perfectly, but it isn't a signed JWT, so `exchange`'s signature
check will reject it.

The fix is small: have `exchange` also accept an access token, and verify it by calling
Google directly —

    GET https://www.googleapis.com/oauth2/v3/userinfo
    Authorization: Bearer <the access token>

Google responds with the verified email. From there it's your existing path: look the
email up, check the user is active, mint the same token. Security is unchanged — Google
is still the one confirming who the person is, we never assert it ourselves. Something
like an optional `googleAccessToken` field alongside `googleIdToken` would do it.

**A stopgap, if useful.** If either item will take a while, you could mint us one
AMBASSADOR token for our demo ambassador via the admin route
(`POST /auth/agent-tokens`). That puts us on live data immediately for demo purposes.
It only works for a single fixed person, so it's a bridge, not the answer — but it
unblocks the demo while the real flow lands.

**One smaller question.** The agent also shows reward tiers, the full class roster
(paged — we display 6 of 59), and the WhatsApp message drafts. The guide doesn't list
endpoints for those. Should they come from the API, or stay as content on our side?

**And a security note, kindly meant:** the dev `AGENT_AUTH_SECRET` is written into the
guide document itself. Your own doc says Secret Manager, never in files — worth pulling
it out before the doc circulates further. We've kept our copy out of version control.

Happy to jump on a call if any of this is easier spoken.

Thanks,
Purna

---
---

## Technical appendix — full context for your AI assistant

Paste everything below into your AI coding assistant. It contains the complete
situation, the measurements behind it, and the specific change requested.

### Who we are and what we're building

We build the Gemini Enterprise (GE) agents that sit on top of Sethu. This message
concerns the **ambassador agent**: a student ambassador opens it inside Gemini
Enterprise and asks things like "who should I message?", "how's my section doing?",
"where am I on the leaderboard?". It answers with interactive cards.

The agent is written in Python with Google's ADK (`google-adk`) and is deployed to
**Cloud Run as an A2A agent** (Agent-to-Agent protocol), registered into Gemini
Enterprise. It is currently running entirely on hardcoded fixture data. Its data
access layer is isolated in a single module written specifically to be swapped for
HTTP calls, so integration is cheap once auth works.

### Measurements taken against the dev API on 2026-08-03

Base URL tested: `https://sethu-dev-api.onrender.com/api/v1`
Secret used: the dev `X-Agent-Secret` from the guide.

Service is up — `GET /` returns `{"status":"ok","service":"sethu-api"}`.

Route-by-route results:

| Method + Path | Status | Meaning |
|---|---|---|
| `GET /tenants/x/cohorts/mine` | 401 | route exists, auth required |
| `GET /cohorts/mine/stragglers` | 401 | route exists, auth required |
| `GET /cohorts/mine/students/x` | 401 | route exists, auth required |
| `GET /tenants/x/leaderboard` | 401 | route exists, auth required |
| `GET /faculty/agents` | 401 | route exists, auth required |
| `POST /auth/agent-tokens/exchange` | **404** | route not registered |
| `POST /auth/agent-tokens` | **404** | route not registered |
| `GET /auth/agent-tokens?userId=x` | **404** | route not registered |

The 404s carry Fastify's `{"message":"Route POST:/api/v1/auth/agent-tokens/exchange not
found","error":"Not Found","statusCode":404}` — i.e. genuinely unregistered, not an
auth rejection. **Request 1: deploy the `/auth/agent-tokens/*` routes to dev.**

Observed error envelope on the 401s, which we will code against:

```json
{"data":null,
 "error":{"code":"UNAUTHORIZED","message":"Unauthorized"},
 "meta":{"timestamp":"2026-08-03T05:03:54.221Z","requestId":"req-63"}}
```

We will log `meta.requestId` on every failure so issues can be traced from your side.

All work is scoped to the dev environment. The agent will be configured with the dev
base URL only — no prod URL will be referenced, configured, or called until Sethu
explicitly greenlights it.

### The token-type problem, precisely

Gemini Enterprise supports several agent registration styles. They differ in what
end-user credential the agent receives:

- **`adkAgentDefinition`** (agent hosted on Vertex AI Agent Engine): GE passes the end
  user's email through directly as `user_id`. We verified this on 2026-07-22.
- **A2A agent** (our case — required, because the interactive card extension the
  ambassador UI depends on is only negotiated over the A2A protocol): GE passes an
  **OAuth 2.0 access token** for the end user in the `Authorization: Bearer` header,
  provided the agent registration has `authorizationConfig.agentAuthorization` pointing
  at a GE authorization resource. That token is a Google OAuth access token
  (`ya29...`-style), **not** an OIDC ID token, and therefore has no JWT signature for
  Sethu to verify against Google's JWKS.

We tested our A2A endpoint on 2026-07-28 before configuring an authorization resource;
the inbound request carried no `Authorization` header at all (only
`x-serverless-authorization`, which is the Discovery Engine service agent and is
identical for every user — never usable as an end-user identity). We are now
configuring the authorization resource, which will populate `Authorization` with the
end user's access token. We will confirm the exact token type empirically and report
back.

**Request 2: extend `POST /api/v1/auth/agent-tokens/exchange` to accept a Google OAuth
access token.**

Suggested shape — additive, fully backward compatible:

```
POST /api/v1/auth/agent-tokens/exchange
X-Agent-Secret: <AGENT_AUTH_SECRET>
Content-Type: application/json

{ "googleAccessToken": "ya29..." }     // alternative to the existing googleIdToken
```

Server-side handling for the new field:

1. `GET https://www.googleapis.com/oauth2/v3/userinfo` with
   `Authorization: Bearer <googleAccessToken>`.
   (Equivalent: `GET https://oauth2.googleapis.com/tokeninfo?access_token=...`, which
   additionally returns `aud` and `expires_in`.)
2. Non-200 → return the existing 401 for an invalid token.
3. Read the verified `email` from the response body.
4. From here, the existing code path is unchanged: look up the email, confirm the user
   is active and tenant-bound, mint the 30-day agent token, return the identical
   `{ token, tokenId, expiresAt, userId, role, tenantId }` payload.

Security properties are equivalent to the ID-token path: Google remains the sole
authority on the user's identity, the agent never asserts an email itself, and the
`X-Agent-Secret` requirement is unchanged, so a leaked secret alone still cannot
impersonate anyone. Optional hardening: verify the `aud` returned by `tokeninfo`
matches the OAuth client ID we register with Gemini Enterprise, and we will send you
that client ID once created.

### Interim unblock (optional)

If either request will take time, mint one AMBASSADOR-role agent token for our demo
ambassador through the admin route `POST /api/v1/auth/agent-tokens` and send it to us
over a secure channel. We will hold it in Google Secret Manager. This lets us build and
demo against live data immediately, with the understood limitation that every session
resolves to that one person, so it cannot ship to real ambassadors.

### Endpoints we still need

Confirmed and sufficient for us: `cohorts/mine`, `cohorts/mine/stragglers`,
`cohorts/mine/students/{id}`, `tenants/{tenantId}/leaderboard`.

Not covered by the guide, and currently hardcoded in our agent:

1. **Reward tiers** — the 25/50/75/100% ladder with each tier's reward text and
   earned/locked status. API, or our content?
2. **Full section roster** — we display 6 of 59 with a "showing 6 of 59" footnote, so
   we need paging plus a true total. Does `cohorts/mine` already return the full student
   list, and is it paged? A sample response body would settle this.
3. **Outreach message drafts** — the WhatsApp copy we pre-fill, in three tones. Content
   on our side, or served so your team can tune it without a redeploy?

A real sample response body for `cohorts/mine`, `stragglers` and `leaderboard` (dev
data is fine) would let us finish the integration before the auth work lands — we can
write and test against the real shapes and wire the credentials in last.

### Operational notes

- **Activation lag** is understood: 0–15 min typical, up to ~6h worst case, and
  `activatedAt` is Google's certified login time. We will surface freshness in the UI
  rather than implying real-time.
- **Token lifecycle**: we will follow the documented reuse path — check
  `GET /auth/agent-tokens?userId={userId}` for a live, unrevoked token before calling
  exchange — and cache per user, re-exchanging ahead of `expiresAt`.
- **Secret handling**: `X-Agent-Secret` will live in Google Secret Manager and be
  injected as a Cloud Run environment variable, never committed.
