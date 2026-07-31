# Ambassador Agent — A2UI in Gemini Enterprise

**Date:** 2026-07-28
**Status:** design approved, pending spike results
**Sources:** `Sethu Ambassador Cockpit.html` (mobile prototype, turn 3), `Sethu
Ambassador GE Chat.html` (chat-native prototype), `ambassador-flow.pdf` (API and
data model, 2026-07-28)

## Goal

A Campus Ambassador agent inside Gemini Enterprise that carries the mobile
cockpit's job — see your section, find who needs a personal message, draft it,
send it, track rank and rewards — as A2UI cards and buttons rather than plain
chat.

Success for v1: a convincing demo for the team, on mock data shaped exactly like
the real API, so the backend swap is a change to one module.

## What an ambassador is

A student granted the `AMBASSADOR` role by a College Admin, responsible for one
section (department · year · section). They nudge classmates toward Gemini
Enterprise activation. One ambassador per section; they can see only their own
cohort; activations through their `/go/` link are credited to them.

Persona for the demo: **Sneha Reddy, EEE Sem 3 · Sec B, SVEC Tirupati**, 59
students, 43 activated.

## Architecture

New agent, own directory, own Cloud Run A2A service, own Gemini Enterprise
registration. It reuses the hardened host built for Job Helper (`runtime.py`,
`identity.py`, `card.py`, `main_a2a.py`) — that work is why agent #2 is mostly
configuration.

**Registration must use `a2aAgentDefinition`.** A2UI does not render for agents
registered via `adkAgentDefinition`. The team's own prototype states this; it is
independently confirmed in `references/a2ui.md`. The choice is made at
registration and cannot be changed later without re-registering.

### Rendering: deterministic Python, not model-generated UI

Cards are built by code from structured data, never emitted by the model. Three
reasons:

1. The data is already structured — it comes from a fixture today and from the
   documented API tomorrow. There is nothing for a model to infer.
2. The screens are fixed designs with exact copy. A model composing UI drifts
   between turns, which is fatal for a demo the team compares against a mockup.
3. It makes the no-invention guarantee structural: a value not present in the
   data cannot be drawn. Activation counts come from Google's certified
   reporting and must never be approximated.

The model still writes the prose and picks which surface to show. It just does
not draw.

### Module layout

| Module | Responsibility |
|---|---|
| `fixtures.py` | Sneha's world, verbatim from the chat prototype. Pure data. |
| `data.py` | Accessor layer returning **the API's exact response shapes**. The seam: swapping to real HTTP changes this file only. |
| `surfaces.py` | One builder per surface → A2UI messages. Ids namespaced per surface. |
| `actions.py` | `userAction` router: name → mutate state → next surface. |
| `agent.py` | One ADK agent. Talks; picks a surface on typed input. |

### The data contract

`data.py` returns the shapes documented in `ambassador-flow.pdf`:

```
GET /api/v1/cohorts/mine
  → {ambassador:{name,section}, stats:{activated,size,pct},
     nextMilestone:{target,reward}, stragglers:[...], fullRoster:[...]}

GET /api/v1/cohorts/mine/stragglers
  → {data:[{studentId,name,phone,waLink}], total, page, limit}

GET /api/v1/cohorts/mine/students/:studentId
  → student detail

GET /api/v1/tenants/:id/leaderboard
  → {data:[{rank,name,cohortSection,activated,size,pct,...}], myRank}
```

Mutations (`mark_sent`, `report_number`) write to ADK session state, so progress
is real within a conversation: the sent count climbs as she works.

## Surfaces

Built from the chat prototype's own component budget, corrected against the v0.8
catalog.

| Surface | Trigger | Components |
|---|---|---|
| **Greeting** | conversation start | Text + suggestion Buttons |
| **Cohort summary** | "where do I stand?", "how many left?" | Card, Text, Button ×2 |
| **Straggler list** | "who should I message?" | Card per student + Send/Edit Buttons |
| **Edit form** | Edit button | Text, angle Buttons ×3, TextField, Send Button |
| **Leaderboard** | "rank", "leaderboard" | Card per entry (see Tables below) |
| **Rewards** | "what unlocks next?", "badges" | Card per tier |
| **Roster** | "show my cohort", "roster" | Card per student |
| **Sent confirmation** | after Send | Text + `wa.me` link |

Every surface ends with **suggestion Buttons** whose set depends on the surface
just shown — the chat-native replacement for the app's tab bar, and the primary
way to move without typing.

### Component reality

The prototype's budget lists seven components. Three do not exist in the v0.8
standard catalog (fetched 2026-07-28 from
`a2ui.org/specification/v0_8/standard_catalog_definition.json`).

| Prototype | v0.8 |
|---|---|
| Text, Card, Button, TextField | exist as designed |
| ChoicePicker | **absent** — angles become three Buttons |
| Table | **absent** — redesigned as cards |
| ProgressBar | **absent** — text with a unicode meter |

Full catalog: `Text, Image, Icon, Video, AudioPlayer, Row, Column, List, Card,
Tabs, Divider, Modal, Button, CheckBox, TextField, DateTimeInput,
MultipleChoice, Slider`.

**Styling is two fields: `font` and `primaryColor`.** No per-row background, no
per-cell color. The prototype's blue "You" highlight and amber "pending" are not
expressible; meaning must live in the text.

### Tables become cards

Leaderboard, roster and rewards are redesigned as one Card per entry rather than
a grid. A2UI has no column widths and no per-cell alignment, so an emulated grid
misaligns and reads as broken rather than plain.

The fairness rule survives, which is what matters: **% and count always shown
together**, plus the ranking basis ("% of section activated · under-30 sections pooled ·
verified activations only"). Sneha's own row is marked in its text, not by color.

### Only Button dispatches actions

`MultipleChoice`, `CheckBox`, `TextField` and `Slider` bind to the client data
model but **cannot notify the agent**. Only `Button` carries an `action`.

Consequences:

- Angle selection must be three Buttons, not a chip picker. Tapping re-drafts
  via a round trip — same behaviour as the prototype, one visible hop.
- The edited message reaches the agent through the Send button's context:
  `{"key": "message", "value": {"path": "/draft/text"}}`. The TextField→data-model
  write-back is the one link in this chain not yet observed on the wire.

### Action inventory

`nav(surface)` · `show_stragglers` · `open_edit(student_id)` ·
`set_angle(student_id, angle)` · `send_whatsapp(student_id, message?)` ·
`open_student(student_id)` · `report_number(student_id)` · `show_leaderboard` ·
`show_rewards` · `show_roster` · `simulate_phase(phase)`

Inbound `userAction` is parsed **deterministically** before the model sees it.
An inbound `DataPart` with no ADK metadata arrives as an `inline_data` blob
wrapped in `<a2a_datapart_json>` tags (`part_converter.py:176-183`), so the
router can read it directly. Button routing is code, not model judgement.

### Phase simulator

The prototype cycles live → 75% → 100%. Reproduced as `simulate_phase`, because
the 100% victory state is unreachable from live data and is the demo's payoff.
Labelled as a demo affordance, not a feature.

## The WhatsApp handoff

`Button` dispatches an action; it cannot open a URL, and `Text` excludes links.
So `send_whatsapp` marks the student sent and the agent replies **in text** with
the `wa.me` link, which the GE chat surface renders normally.

One extra tap versus the prototype. This is the ceiling of v0.8, not a shortcut.

The product rule holds either way: **the agent never sends as her.** It drafts;
she sends from her own WhatsApp; her link carries her credit.

## Identity

**Gemini Enterprise forwards no end-user identity to an A2A agent** — measured
2026-07-28 against a live call. No email header, empty message metadata,
unauthenticated principal. The only credential present is
`x-serverless-authorization`, the Discovery Engine service agent, identical for
every caller and never usable as an identity.

Every ambassador endpoint is `/mine`-scoped, so without identity there is no
"mine". Attribution makes it sharper: the `/go/` link is a per
ambassador-student `GoToken`, so serving the wrong ambassador's link credits the
wrong person.

**Decision for v1: conversation-scoped, OAuth deferred.** This build has no
backend, so there are no `/mine` endpoints to scope and OAuth buys nothing. ADK's
`A2A_USER_{context_id}` fragments state into one private bucket per conversation
— forgetful, never leaky — and every demo viewer is Sneha, so a single fixture
identity is correct rather than a compromise.

`identity.py` stays pluggable: when the backend lands, OAuth drops in behind the
same interface without touching surfaces or actions.

OAuth setup, fetched from the A2A registration doc and recorded here for when it
is needed:

1. OAuth 2.0 Web client; authorized redirect URI must include
   `https://vertexaisearch.cloud.google.com/static/oauth/oauth.html`.
2. Authorization URI per Google's template, with
   `include_granted_scopes=true`, `response_type=code`,
   `access_type=offline`, `prompt=consent`. Scopes: `openid email`.
3. `POST .../v1alpha/projects/PROJECT_NUMBER/locations/LOCATION/authorizations?authorizationId=AUTH_ID`
   with `serverSideOauth2` (clientId, clientSecret, authorizationUri, tokenUri).
4. Register with `"authorizationConfig": {"agentAuthorization":
   "projects/.../authorizations/AUTH_ID"}`.

**Open risk.** The doc frames this only as "the agent accesses Google Cloud
resources on behalf of the user". It never states that the token is forwarded to
a self-hosted A2A endpoint, or in which header. The prior no-identity
measurement was taken **without** `authorizationConfig` set, so it does not
answer this either way. Resolved by the spike below.

`tilicho.in` is not a Workspace domain and `supadha-dev` has no GCP org, so the
consent screen will be External with a test-user list and an unverified-app
warning. Acceptable for a demo and pilot; verification is required before real
students use it.

## The unknown that shapes everything

**Does GE emit `userAction`?** The v0.8 spec defines the contract
(`specification/v0_8/json/client_to_server.json`: `name`, `surfaceId`,
`sourceComponentId`, `timestamp`, `context`). GE is the client and must
implement it. Cards are proven to go out; a click has never been seen coming
back.

If it works, every button in this design works. If it does not, the agent
degrades to read-only cards plus typing — still useful, but the "select instead
of replying" premise is gone.

This is answered by the **second task of the plan**, not by a throwaway: the
greeting card and its first button are real code we keep either way. Learning
the answer on day one is what stops eight surfaces being built on a false
assumption.

Confirmed in the same pass: TextField → data model → Button `context` via
`{"path": "/…"}`.

## Gaps in the backend, for the team

Not blockers for the demo; blockers for going real.

- **Rewards has no endpoint.** Listed in the flow doc as "(rewards endpoint)".
- **"What you drove" needs attribution**, but `/tenants/:id/attribution` is
  `SUPER_ADMIN, COLLEGE_ADMIN`. An ambassador cannot call it.
- **Touch timeline** — `/people/:studentId/touches` is also admin-only. Either
  `/cohorts/mine/students/:id` embeds touches or student detail is unbacked.
- **Campaign delivery/read state** ("covered by campaigns — 9 · next Tue 17:30")
  appears in no documented response shape.
- **Streaks contradiction.** The leaderboard API returns `streakDays` and
  `idleDays`; the cockpit prototype states "no streaks anywhere — activation is
  finite and completable". Both cannot be right.

## Product rules that must survive

From the prototype briefs, treated as non-negotiable:

- The agent never sends as her. It drafts; she sends.
- Activation counts come from Google's certified reporting only.
- She sees her own section only — no search, no other cohorts.
- Rank always shows % **and** count, with the basis stated.
- Rewards follow section outcomes, never message volume or effort.
- No streaks.

## Out of scope for v1

Real backend calls · admin/war-room/faculty surfaces · multi-ambassador
switching beyond OAuth identity · push or scheduled nudges · the mobile app's
native screens.
