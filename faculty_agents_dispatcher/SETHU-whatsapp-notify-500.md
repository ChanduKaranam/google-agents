# ✅ RESOLVED 2026-08-04 — WhatsApp send now works

Confirmed by the Sethu backend team's fix and verified end to end through the
Gemini Enterprise agent: a professor published an agent and the WhatsApp
message was delivered. This was the first successful send through this
integration.

Kept below as the original report and as the record of what was measured.

**Still open, and not covered by this fix:**

1. **Is `notify` idempotent?** Unanswered. Until it is, the agent must not
   offer a professor a retry after a failed send — a retry may double-message
   students.
2. **Does a freshly published agent get a correct `studentCount`?** Agents
   published 2026-08-03 all carried 0. The agent now quotes the roster's
   per-section headcount instead, so this no longer blocks a send, but the two
   numbers should agree.
3. **Which channels fire?** The confirmation sentence says WhatsApp; the spec
   says "WhatsApp and Email".

---

# Original report: `POST /faculty/agents/{id}/notify` returns 500

**Reported:** 2026-08-03
**Environment:** `https://sethu-dev-api.onrender.com/api/v1` (dev)
**Reporter:** Purna (purna@tilicho.in) — Faculty dispatcher GE agent
**Severity:** blocker — no WhatsApp message has ever been sent successfully
through this agent

## Summary

`POST /faculty/agents/{id}/notify` returns `500 INTERNAL` for a valid FACULTY
token that gets `200` on every other `/faculty/*` route.

This is the call that triggers the WhatsApp fan-out. The agent-side flow works
up to it — identity resolves, sections list, publishing succeeds with the
correct section label — and then the final step fails. **The end-to-end feature
has never once worked.**

## Reproduction

```
POST /api/v1/faculty/agents/019fc7c7-3105-7ea2-a31a-f0bef48f7445/notify
Authorization: Bearer <valid FACULTY token>
Content-Type: application/json

HTTP 500
{"data":null,
 "error":{"code":"INTERNAL","message":"Something went wrong."},
 "meta":{"timestamp":"2026-08-03T16:58:19.385Z","requestId":"req-d3"}}
```

**requestId `req-d3`** — please trace this one; it is the cleanest sample.

The same token, seconds apart, gets `200` from `/auth/me`, `/faculty/agents`
and `/faculty/sections`. So this is not authentication and not the token.

### Second occurrence

Agent `019fc850-866e-79a6-b4db-beedda390e73` ("Agent Testing", section
`"AI&DS · Year 1 · Sec B"`), at approximately **2026-08-03T16:00Z**, via the
deployed agent in Gemini Enterprise. Surfaced to the professor as an internal
error. Same symptom, different agent.

## Affected agents

| Agent id | name | sections | `studentCount` |
|---|---|---|---|
| `019fc7c7-…c7c7` | probe | `["A"]` | 0 |
| `019fc850-…0e73` | Agent Testing | `["AI&DS · Year 1 · Sec B"]` | 0 |

## What this proves, and what it does not

Both agents we are willing to call `notify` on have `studentCount: 0`.

**Proven:** `notify` returns 500 for a zero-recipient agent.

**Not established:** whether `notify` also fails for an agent with real
recipients. We cannot test that — it would put WhatsApp messages on real
students' phones — and we will not do it against dev.

Please close that gap from your side, where you can test without messaging
anyone.

## Why the 500 is wrong regardless

Even if the trigger turns out to be "no recipients", a 500 is the wrong answer:

- **`200` with a count of zero sent** — nothing to do, reported honestly; or
- **`4xx` naming the reason** — e.g. "this agent has no recipients".

An unhandled internal error gives the caller nothing to act on, and it is
indistinguishable from the WhatsApp provider being down. We have to show a
professor something truthful about whether their students were messaged.

## Likely related: `studentCount` looks like a recent regression

Probably the same underlying defect, so worth checking together.

Agent `019fc850-…0e73` was published to `"AI&DS · Year 1 · Sec B"` — the exact
canonical label your own roster returns:

```json
{ "sections": ["AI&DS · Year 1 · Sec B"], "studentCount": 0, "status": "live" }
```

`GET /faculty/sections` reports that same section as `"students": 3`.

### The pattern splits cleanly by publish date

| Agent | Published | Sections | `studentCount` | Roster says |
|---|---|---|---|---|
| Q&A agent | 2026-07-30 | 4 CSE/CIVIL sections | 7 | ~6 |
| Exam Prep ADK | 2026-07-30 | `CIVIL · Year 4 · Sec A` | 3 | 3 ✓ |
| Document Q&A Agent | 2026-07-30 | `MECH · Year 1 · Sec B` | 3 | 3 ✓ |
| probe | **2026-08-03** | `["A"]` (not a real section) | 0 | — correctly 0 |
| Agent Testing | **2026-08-03** | `AI&DS · Year 1 · Sec B` | 0 | **3** ✗ |

Every agent published 2026-07-30 carries a plausible count. Both agents
published 2026-08-03 carry 0, and one of them is provably wrong.

**This looks like a regression in the publish-time count computation, between
2026-07-30 and 2026-08-03.** Worth checking what changed in that window — it
may well be the same change that broke `notify`.

Note the two `notify` 500s are both on agents from the broken window. If the
publish path stopped resolving recipients, WhatsApp has nobody to send to,
which would explain both symptoms from one cause.

**Question:** which lookup should we trust for the number shown to a professor
before an irreversible send — the roster's per-section `students`, or the agent
record's `studentCount`?

Note the roster's `students` field appears **correct** and is the one number we
currently trust. `GET /faculty/sections` is not implicated in this report.

## Questions we need answered

1. **What is throwing?** `req-d3` should show it.
2. **Does `notify` fail specifically when there are no recipients**, or does it
   fail for populated agents too?
3. **Is `notify` idempotent?** ⚠️ If a professor retries after an error, can
   students receive the message twice? We have no way to tell whether a failed
   `notify` sent nothing, some, or all of the messages.
4. **Which channels does it use?** Our confirmation prompt says WhatsApp; your
   spec's `notify` response says "WhatsApp and Email notifications sent". If
   both fire, we must say so before an irreversible send.

**Question 3 is the most important.** Until it is answered we cannot let a
professor retry a failed send at all, because the failure mode is silently
double-messaging real students. Right now every failed send is a dead end for
the professor, by design.

## What we have done on our side meanwhile

- `send_agent_to_sections` refuses in code when the quoted student count is
  zero or missing, so a professor is never asked to confirm a send that would
  reach nobody, and no doomed `notify` call is made.
- Section names are resolved against your roster before publishing, so an
  unrecognised section can no longer be published to zero students.
- No retry-on-failure exists, deliberately, pending the answer to question 3.

None of this makes WhatsApp send. The fan-out is yours; we only call `notify`.

## Related

- `SETHU-403-faculty-sections.md` — the `email`-claim 403 and other API issues.
