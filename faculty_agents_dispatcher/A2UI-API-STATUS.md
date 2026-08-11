# A2UI ↔ Sethu API status

The read/write endpoints the **Champion Faculty (A2UI)** agent can call, and why
the rest of `A2UI-VIEWS.md` is not yet servable. This is the counterpart to
`A2UI-VIEWS.md`: that doc records what the cards want; this one records what the
API actually returns today.

**Base URL.** All endpoints are prefixed `/api/v1`.

**Auth.** Every faculty endpoint is behind the agent-token → faculty-email flow.
The agent exchanges its identity for a Sethu JWT that carries `role: FACULTY`,
`tenantId`, and the acting faculty's `email`; the same token the agent already
uses for `GET /faculty/agents`. Endpoints resolve the caller's **department**
from that email, so **the token MUST carry an email claim** — without it these
routes return `403`.

**Envelope.** Every response is the standard `ApiResponse<T>`:
`{ "ok": true, "data": <T>, "requestId": "…" }`. The shapes below are the `data`.

**Scope.** Read endpoints are scoped to the caller's **own department**. An admin
/ non-roster email gets the whole-college view with `department: ""` (mirrors
`GET /faculty/sections`).

**Honest numbers.** Every figure comes from the response verbatim. `rank`,
`pooled`, totals, and idle-days are computed server-side so the agent never ranks,
pools, or composes a number the API didn't return.

---

## ✅ Implemented

### `GET /faculty/department-progress` — NEW
Serves **"How is my department doing?"** and **"Show the leaderboard"** from one
round-trip. Dept rollup + every section, each with its ambassador, activation
counts, server-computed leaderboard rank, and the pooling flag.

```jsonc
{
  "department": "CSE",        // "" for admin/non-roster (whole-college view)
  "activated": 268,           // ACTIVATED students across the scoped sections
  "total": 357,               // == sum of section totals (one baseline)
  "syncedAt": "2026-08-07T…", // GE license-sync freshness; null before first sync
  "sections": [               // ordered by rank (best first); each carries its rank
    {
      "department": "CSE",
      "year": 7,
      "section": "A",
      "label": "CSE · Year 7 · Sec A",
      "ambassador": "Nikhil Bose",  // null when no ambassador
      "activated": 49,
      "total": 57,
      "rank": 1,               // 1 = best; pooled sections always rank last
      "pooled": false          // true when total < 30 (SECTION_POOL_MIN_SIZE)
    }
  ]
}
```

**⚠️ Measured 2026-08-10: the scope cannot be changed by the caller.** Requesting
`?department=CSE` from an EEE professor returns EEE — the parameter is ignored,
not rejected, so the only way to notice is to compare `department` on the
response against what was asked for. The agent does that and withdraws its
department buttons when it happens.

This leaves faculty seeing progress for one department while `GET
/faculty/sections` offers them all 55 sections to send to, which is the
inconsistency to settle: either this endpoint takes a `department`, or it
returns the college for faculty the way `/faculty/sections` does. The agent
side is built and gated behind `FACULTY_DEPARTMENT_SWITCH=1` — flip it on when
the endpoint honours the parameter and the buttons appear with no code change.

Client still does: percentages, "3 behind", "sections at 75%+", worst-first
re-sort for the dashboard. All of it is arithmetic over these fields — nothing
requires another call.

**Pooling rule (v1).** Sections with `total < 30` are flagged `pooled: true` and
ranked **below every full-size section regardless of their %**, so a 4-of-4
(100%) micro-section can't top a 28-of-61 (46%) real one. Applied once,
server-side; confirm the threshold with product before it hardens.

### `GET /faculty/ambassadors` — NEW
Serves **"Who / How are my ambassadors?"**. Roster for the caller's department,
**worst-first**, plus the sections that have no ambassador.

```jsonc
{
  "department": "CSE",
  "syncedAt": "2026-08-07T…",
  "ambassadors": [            // worst-first: never-active, then most-idle, then lowest %
    {
      "name": "Rohit Varma",
      "section": "CSE · Year 3 · Sec B",
      "activated": 41,
      "total": 60,
      "lastActivityAt": "2026-08-01T…", // null if the cohort never activated
      "idleDays": 6                      // whole days since lastActivityAt; null if that's null
    }
  ],
  "sectionsWithoutAmbassador": [
    { "section": "CSE · Year 5 · Sec B", "total": 61 }
  ]
}
```

**⚠️ Activity is a PROXY.** `lastActivityAt` / `idleDays` are the most recent
**student** activation in the ambassador's cohort — NOT the ambassador's own
action (Sethu has no per-ambassador action log). "Quiet 6 days" means *no one in
their section activated in 6 days*. Label it as such in the card; do not present
it as "the ambassador did nothing for 6 days".

> **Open product question (not technical).** Whether faculty should see named
> ambassador performance at all is still unsettled (see `A2UI-VIEWS.md` §"The
> larger question"). The endpoint exists and returns real data; the decision is
> whether A2UI *surfaces* it, not whether the data flows.

### `GET /faculty/sections` — existing
Every `(department, year, section)` in the tenant roster with headcounts —
caller's branch first. Powers the "Who can use it" section picker. **Headcount
only, no activation.**

```jsonc
{ "department": "CSE",
  "sections": [ { "department":"CSE","year":3,"section":"A",
                  "label":"CSE · Year 3 · Sec A","students":60 } ] }
```

### `GET /faculty/agents` — existing
The caller's own agents (live + unclaimed). Each carries a `stats` block whose
**usage values are unpopulated today** (see below).

```jsonc
{ "id":"…", "name":"DBMS — Exam Prep", "subject":"DBMS", "semester":"5",
  "sections":["CSE · Year 5 · Sec A"], "studentCount":58,
  "publishedAt":"2026-…", "status":"live", "geUrl":"https://…",
  "shareToken":"…", "attention":null, "unclaimed":false,
  "stats": { "usedBy":0, "questionsThisWeek":null,
             "signInsCaused":12, "topUnanswered":null },
  "statsSyncedAt": null }   // null → usage never synced; label the numbers with this
```

### `GET /faculty/agents/:id/laggards` — existing
Students in an agent's sections who have not activated, with how far their `/go`
link got. Faculty counterpart to ambassador stragglers.

### `POST /faculty/agents/:id/notify` — existing
Sends (or previews with `{ "preview": true }`) the agent's WhatsApp announcement
to its sections. Guarded by `Idempotency-Key`. **Takes an agent id only** — no
audience, message body, or schedule (see "Send a campaign" below).

```jsonc
// → { "recipientCount": 45, "skippedCount": 3, "enqueued": true, "shareUrl": "https://…/go/…" }
```

### Other existing faculty writes
`POST /faculty/agents` (register), `PATCH /faculty/agents/:id/sections` (edit
audience), `PATCH /faculty/agents/:id/claim` (claim a GE-sync-detected agent),
`GET /faculty/section-recipient` (a real student first-name for a test send).

---

## ⚠️ Partially servable — "How are my agents used?"

**No new endpoint needed.** `GET /faculty/agents` already returns the exact shape
the card wants. What's missing is the **values**, not the contract:

| Card field | Source | Today |
|---|---|---|
| Agent name, sections | `name`, `sections[]` | ✅ populated |
| "214 activations" (Sethu-attributed sign-ins) | `stats.signInsCaused` | ✅ populated (from `/go` clicks) |
| Section headcount | `studentCount` | ✅ populated |
| "used by N students" | `stats.usedBy` | ❌ `0` until GE usage sync |
| "4,918 chats" | `stats.questionsThisWeek` | ❌ `null` until GE usage sync |
| "unanswered: …" | `stats.topUnanswered` | ❌ `null` until GE usage sync |
| "64% return" | — | ❌ no candidate field, undefined metric |

**Why not fully implemented:** the usage fields are written only by a **GE usage
sync worker that does not exist yet**. The DB column, the service that writes it
(`updateFacultyAgentStats`), and the response field are all in place, but nothing
calls the writer, so `statsSyncedAt` is `null` on every row. Populating them is a
**separate integration ticket** gated on Gemini Enterprise analytics API access —
not a Sethu data-exposure task. It was deliberately kept out of this slice so it
doesn't block the three views that need no new integration.

**Buildable now:** the card can render honestly today with agent name, sections,
`signInsCaused`, and `studentCount`, showing the GE-sourced metrics as "no data
yet" while `statsSyncedAt` is `null`. `"64% return"` additionally needs a
**definition** (return within what window, to what) before it can have a source.

---

## 🔴 Not implemented — "Send a campaign"

Deliberately left out. This is a product, not an endpoint, and it is blocked on a
decision the API team cannot make unilaterally.

- **WABA template blocker.** Business-initiated WhatsApp messages must use a
  Meta-pre-approved template with fixed wording + numbered placeholders. The
  mockup's free-prose draft and its "Reword it" (model-regenerated copy) are
  precisely what WABA does not permit. Until the template question is settled the
  screen can't be designed, let alone built.
- **`notify` is not a campaign engine.** It takes an agent id and nothing else.
  The card needs audience segmentation (students who haven't activated), a
  message/template choice, scheduled delivery, and **server-side** quiet-hours +
  the 2-per-student-per-week cap — none of which `notify` exposes. Displaying
  "earliest slot Thu 17:30" while Sethu sends immediately would make the
  guarantee decorative.
- **Model-written copy in the send path** reaches real students irreversibly —
  the one thing every built flow deliberately avoids.

**Sequence, when wanted:** (1) settle the WABA template regime; (2) reuse the
activation data the three views already surface for audience targeting; (3)
extend `notify` with audience/template/schedule + enforce the cap and quiet hours
inside Sethu; (4) close the `notify` idempotency question at campaign scale; (5)
then the cards, which are the easy part.

---

## Summary

| A2UI view | Endpoint | Status |
|---|---|---|
| How is my department doing? | `GET /faculty/department-progress` | ✅ implemented |
| Show the leaderboard | `GET /faculty/department-progress` (same call) | ✅ implemented |
| Who / How are my ambassadors? | `GET /faculty/ambassadors` | ✅ implemented (product-gated for display) |
| How are my agents used? | `GET /faculty/agents` (existing) | ⚠️ contract ready; usage values await a GE usage-sync worker |
| Send a campaign | — | 🔴 blocked on WABA templates + a new campaign capability |
