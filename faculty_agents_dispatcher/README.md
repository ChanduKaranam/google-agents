# Faculty-Agent (Dispatcher Agent)

An ADK agent that lives in Gemini Enterprise. A professor pastes the link to an
AI agent they just created and asks Faculty-Agent to share it; Faculty-Agent
checks the sections against the college's roster, confirms the send, and
triggers the WhatsApp blast.

Built against *Sethu Agent Auth — How GE Agents Call Sethu APIs Without a Human
Login* (Tilicho Labs, 2026-08-03), corrected against the running dev API where
the two disagree — see [Where the docs are wrong](#where-the-docs-are-wrong).

## Auth

No human login, and nothing about the professor is hardcoded:

1. Gemini Enterprise runs Google OAuth when the professor opens the agent and
   forwards their **OAuth access token** — opaque, not a signed JWT. On Agent
   Engine it lands in session state keyed by the authorization id, readable as
   `tool_context.state[GE_AUTHORIZATION_ID]`. There is no Google ID token to be
   had from a GE agent; the ID-token flow in the guide is unreachable.
2. `auth.get_session` trades it at `POST /auth/agent-tokens/exchange`
   (`X-Agent-Secret`) for a 30-day Sethu token scoped to that person. The
   request field is `googleAccessToken`.
3. The response carries `token`, `tokenId`, `expiresAt`, `userId`, `role` and
   `tenantId`. Every later call uses `Authorization: Bearer <token>`, so a
   professor can only ever act within their own college. Sections are not
   owned: professors are not assigned sections, and any of them can send to any
   section in the college.
4. Tokens are cached in ADK `user:` state, which survives across sessions, so a
   returning professor reuses their token. If the cache is cold a new one is
   minted — a previously minted token cannot be recovered, because
   `GET /auth/agent-tokens` returns metadata only and never the token string.
5. Nothing arrives until the agent's `authorizationConfig.toolAuthorizations` is
   set in Gemini Enterprise. An unconfigured agent receives no identity at all,
   which looks exactly like the platform not supporting it. `diagnose_identity`
   exists to tell those two apart.

## Conversation flow

1. Professor pastes an agent link: "share this with Section A, 2nd year CSE"
2. `find_agent_by_link` → matches the link against `geUrl` on their agents
   - already published → skip to step 5 via `prepare_send`
   - `not_published` → continue
3. Gather three things: the sections, the semester, and a name for the agent.
   `list_college_sections` confirms the sections the professor named actually
   exist in the college — an existence check, not an ownership check.
4. `publish_agent` → one `POST /faculty/agents` carrying the share link and the
   section *names* together. Registers the agent and returns `studentCount`.
   Messages nobody. Sethu cannot delete or re-point a published agent.
5. *"You are about to send this agent to Section A, Year 2, CSE (62 students)
   via WhatsApp. Do you want to proceed?"*
6. On "yes" → `send_agent_to_sections` → `POST .../notify` → Sethu fans out
   over WABA
7. Reports completion

`send_agent_to_sections` refuses to run unless a count was quoted for that exact
agent id, and clears that state after sending — so a confirmation given for one
agent cannot be spent on another, and a stray second "yes" cannot double-blast.
The guard keys on the agent id alone, not on the section list.

## Files

| File | Purpose |
| --- | --- |
| `agent.py` | The agent: model, instruction, tools |
| `tools.py` | The six tools, plus the confirm-before-send guard |
| `auth.py` | Google access token → Sethu token, with reuse across sessions |
| `sethu_client.py` | The only file that knows Sethu's HTTP shape |
| `config.py` | Environment configuration |
| `sethu_openapi.json` | Sethu's spec. Stale in places — see below |
| `SETHU-403-faculty-sections.md` | Bug report for the backend team |
| `SETHU-whatsapp-notify-500.md` | 🔴 Blocker: WhatsApp send returns 500 |
| `SETHU-proposal-sections-endpoint.md` | Proposal: server-to-server sections endpoint |

## Setup

```bash
pip install -r requirements.txt
```

Set `AGENT_AUTH_SECRET` and `SETHU_API_BASE_URL` in `.env` (dev) or Secret
Manager (deployed). Then from the parent directory:

```bash
adk web
```

To exercise it locally, outside Gemini Enterprise, set
`FACULTY_AGENT_ALLOW_DEV_AUTH=1` **and one** of:

- `SETHU_DEV_AGENT_TOKEN` — a Sethu agent token, used as-is with no exchange.
- `FACULTY_AGENT_DEV_GOOGLE_ACCESS_TOKEN` — a Google OAuth access token,
  exchanged normally.

Both are ignored on a deployed runtime even if set, because a pre-minted token
on a deployment is a data leak: every professor would act as one test account
and see one person's students. Without them there is no caller identity and
every tool fails at the first call.

## Deployed

Verified 2026-08-03 against the live project:

| | |
| --- | --- |
| Project | `supadha-dev` (`1019856256943`) |
| Agent Engine | `projects/supadha-dev/locations/us-central1/reasoningEngines/7549916988647145472` — *Faculty Dispatcher Agent* |
| Gemini Enterprise app | `AI_GE` (`ai-ge_1784736359549`, global) |
| Registered agent | `12220860024771704401`, state `ENABLED`, bound to engine `7549916988647145472` |
| Authorization resource | `projects/1019856256943/locations/global/authorizations/sethu-faculty` |

The authorization resource id is what `GE_AUTHORIZATION_ID` must match, and it
does. Each resource attaches to only one agent, which is why this agent has its
own rather than sharing the Campus Ambassador's.

Redeploy over the same instance. Run from the **parent** directory, passing the
agent package folder as the final argument:

```bash
adk deploy agent_engine --project=supadha-dev --region=us-central1 \
  --agent_engine_id=7549916988647145472 \
  --display_name="Faculty Dispatcher Agent" faculty_dispatcher
```

`AGENT_AUTH_SECRET` must reach the deployment — confirm it lands as an env var
on the engine rather than assuming `.env` is uploaded. Without it the exchange
fails and every professor gets "Sethu rejected the sign-in".

Comment the dev token lines out of `.env` first — Agent Engine rejects env vars
with empty values, and a dev identity must never reach a deployment.

## Verified against dev

Probed on 2026-08-03 with a FACULTY token against
`sethu-dev-api.onrender.com`:

- `GET /auth/me` → **200**. The cheapest proof a token works end to end.
- `GET /faculty/agents` → **200**. Records carry `id`, `name`, `geUrl`,
  `shareToken`, `sections[]`, `studentCount`, `status`, `attention`.
- `POST /faculty/agents` → publishes link and sections in one call, comes back
  `status: "live"`. `sections` must be plain strings; a list of objects is
  rejected with "Expected string, received object".
- `GET /faculty/sections` → **200**, but only for a token carrying an `email`
  claim. A token without one gets 403 while every other `/faculty/*` route
  still accepts it. Returns 55 sections across 7 departments — CSE, AI&DS,
  AI&ML, CIVIL, ECE, EEE, MECH — as objects, not strings:
  `{department, year, section, label, students}`. The payload nests as
  `{"data": {"department": <caller's own>, "sections": [...]}}`.
  `section` alone is "A"/"B" and repeats across every department and year, so
  `label` ("CSE · Year 1 · Sec A") is the only self-identifying field.
- `GET /faculty/section-recipient` → param is `section`, not `sectionId`. It
  returns a single arbitrary name for *any* value, including sections that do
  not exist. Unusable for counting, so it is off the send path.

## Where the docs are wrong

Both `sethu_openapi.json` and the team guide describe an API that does not
match the running one. Left uncorrected here because the spec is Sethu's to
own; raised with them instead.

- The exchange takes `googleAccessToken`, not `googleIdToken`.
- There is no `POST /faculty/agents/{id}/claim`.
- There is no `PUT /faculty/agents/{id}/sections`. Publishing carries the
  sections; nothing assigns them afterwards.
- `POST /faculty/agents` takes `{geUrl, name, semester, sections}`, not
  `{name, description, whoCanUse}`.
- `GET /auth/me`, `GET /auth/agent-tokens` and the revoke endpoint are absent
  from the spec entirely.

## Open items

- ~~**`GET /faculty/sections` returns 403.**~~ Resolved 2026-08-03: the route
  requires a token carrying an `email` claim. A token minted without one is
  refused by this route alone.
- **⚠️ Does `POST /auth/agent-tokens/exchange` mint tokens with `email`?**
  This is the open question that decides whether the fix reaches production.
  The working token was supplied by hand; the agent mints its own through the
  exchange, and the earlier exchange-minted token had no `email` claim and got
  403. If exchange still omits it, the deployed agent stays broken however well
  this works locally. Verify before the next faculty test.
- ~~**What string does `publish_agent` take for a section?**~~ Resolved
  2026-08-03 by reading existing records rather than publishing a test one.
  `label` is correct: every live agent with a non-zero `studentCount` stores
  full labels like `"CSE · Year 1 · Sec A"`. ⚠️ A bare `"A"` is **accepted**,
  published `status: "live"`, and reaches `studentCount: 0` — it fails
  silently, permanently, and cannot be deleted. See the `probe` record.
  `publish_agent` now resolves every section against the roster before the
  POST and refuses anything it cannot match, so this failure is caught while
  it is still recoverable. Loose forms ("CSE 1 A", "CSE Year 1 Section A")
  resolve to the canonical label; unknown ones are refused.
- **🔴 `studentCount` on the agent record is unreliable — likely a regression.**
  Agent `019fc850-…e73` published to `"AI&DS · Year 1 · Sec B"`, a correct
  canonical label, came back `studentCount: 0` while the roster reports 3.
  Every agent published 2026-07-30 has a plausible count; both published
  2026-08-03 have 0. A zero therefore does **not** mean the section failed to
  resolve — it can be simply wrong. Backend issue; blocks sends.
  **Not to be confused with the roster's per-section `students` field from
  `GET /faculty/sections`, which is accurate** and is the number to trust.
- **🔴 `POST /faculty/agents/{id}/notify` returns 500 `INTERNAL`.** Reproduced
  2026-08-03T16:58Z on the zero-recipient `probe` agent, requestId `req-d3`.
  Whether it also fails with real recipients is untested and untestable without
  messaging actual students. **No WhatsApp send has ever succeeded through this
  agent.** Both blockers are written up in `SETHU-403-faculty-sections.md`.
- **Token rows accumulate.** Resolved 2026-08-03: `GET /auth/agent-tokens`
  returns metadata only, so the recover-a-minted-token path was impossible and
  has been removed. Every cold cache now mints a new row. Ask Sethu whether
  that is acceptable, or whether stale rows should be revoked on mint.
- **Student count comes from `studentCount`** on the agent record. Confirm that
  is the intended source before quoting it to a professor ahead of a send.
- ~~**The Gemini Enterprise identity path has never been exercised end to
  end.**~~ Verified 2026-08-03: `diagnose_identity` run from inside GE resolved
  a real signed-in faculty member by name with `role: FACULTY`, and the agent's
  `authorizationConfig` reads `.../authorizations/sethu-faculty`, matching
  `GE_AUTHORIZATION_ID`. GE forwards the access token, the exchange works, and
  `/auth/me` resolves. The 403 reproduced for that account too — see
  `SETHU-403-faculty-sections.md`.
- **The deployment predates today's fixes.** Engine `updateTime` is
  2026-08-03T13:29Z; the `_reuse_live_token` crash fix and the corrected
  sections wording landed after. Redeploy before the next faculty test.
- **College-wide sends.** `publish_agent` requires a non-empty section list. If
  "send to the whole college" is a real case, the wire format for it is unknown.
- **Channels.** The confirmation sentence says WhatsApp; the spec's `notify`
  response says "WhatsApp and Email notifications sent". Confirm which, and
  reword the confirmation if both.
