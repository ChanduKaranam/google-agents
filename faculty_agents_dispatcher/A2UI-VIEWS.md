# A2UI views: what is built, and what is wanted next

Running notes on the card-based interface for Champion Faculty. Views are added
here as they are asked for. Each one records what it needs from Sethu, because
that — not the UI — is what has held every step of this integration up.

**Where this runs.** A2UI renders only for the agent registered in Gemini
Enterprise as `a2aAgentDefinition` — `Champion Faculty (A2UI)`, served from
Cloud Run. The Agent Engine registration cannot draw cards whatever it emits,
so it keeps the prose interface. See `README.md` for the split.

---

## Built and deployed

### Opening menu
Answered in code on any greeting ("hello", "hi", "menu", "what can you do?"),
so it cannot be skipped by the model.

> How can I help you?
> **[ Send Agent ]  [ Section List ]  [ Department Progress ]**
> **[ Leaderboard ]  [ Ambassadors ]  [ My Agents ]**

The four read-only views were reachable only by typing the question until
2026-08-07. The model will answer "how is my department doing" without a
button, but a professor who does not know to ask never learns the view exists —
the greeting is the only place that inventory is ever shown. Each tap is
handled in code, like every other button: a click that reached the model would
produce a sentence with no card under it.

**[ Ambassadors ]** disappears when `FACULTY_AMBASSADOR_VIEW=0`.

### Send Agent
A `TextField` for the share link, plus scope. Only a Button can notify the
agent, so all three carry the field's data path in their action context.

> Paste the agent link
> `[ Agent link ................ ]`
> **[ All Departments ]  [ Department – All Sections ]  [ Manual Selection ]**

### Section pickers
Department buttons, then that department's sections. A drill-down rather than
one long list because a single card of 55 sections measures 6.4KB and Gemini
Enterprise drops an oversized surface **silently**.

### Name and publish
> What should this agent be called?
> `[ Agent name ................ ]`
> **[ Publish ]** — or **[ Save Agent Name ]** when it is already published

### Confirm send
> Send this agent over WhatsApp?
> CSE · Year 1 · Sec A — 12 students
> WhatsApp messages cannot be recalled.
> **[ Yes, send it ]  [ Cancel ]**

No Yes button is offered when the count is zero or unknown. After a send or a
cancel the opening menu returns and the send state is cleared, so a second send
cannot inherit the first one's link or sections.

### Department progress, leaderboard, ambassadors, agent usage
Built 2026-08-07 against the endpoints in `A2UI-API-STATUS.md`. Each is a
question, not a button: the model calls the matching tool and adds one line.

> `show_department_progress` · `show_leaderboard` · `show_ambassadors` ·
> `show_agent_usage` — built in `progress_ui.py`

Three deviations from the mockups, all forced:

* **Stat tiles are lines of text, not a 2x2 grid.** A `Row` of `Column`s of
  `Card`s is one nesting level deeper than anything proven to render here, and
  a surface that fails renders nothing and logs nothing. The figures are
  identical; the arrangement is not.
* **One rounding everywhere — `89.7%`, never `90%`.** The mockups disagree with
  each other on the same person; `progress_ui._pct` is the only place a
  percentage is formatted.
* **Ambassador idleness is worded as the section's, not the person's.**
  `idleDays` is the last *student* activation in their cohort, so the card says
  "no activation in their section for 6 days". See `A2UI-API-STATUS.md`.

Ranking and pooling are used exactly as `GET /faculty/department-progress`
returns them — never recomputed, so the leaderboard and the dashboard cannot
disagree. Pooled sections are marked on the row as well as in the footer: one
can sit last on 100%, which reads as a broken ranking without the marker.

Every list pages: rows are added until the next would breach the 6KB ceiling,
and the remainder goes behind "Show N more", which redraws from session state
rather than re-calling an API that sleeps. Measured at 42 sections: 24 rows in
the first surface at 5,968 bytes, 18 behind the button.

`FACULTY_AMBASSADOR_VIEW=0` turns the ambassador roster off without a code
change, for the open product question below.

---

## Requested: "How is my department doing?"

A progress dashboard: four stat tiles over a list of sections.

```
ACTIVATED · CERTIFIED     SECTIONS AT 75%+
268 / 357                 3 / 6
75.1% of CSE              3 behind

AMBASSADORS IDLE          SECTIONS UNCOVERED
2                         1
no activity 3+ days       no ambassador

CSE Sem 5 · B — no ambassador      45.9% · 28 of 61 activated
CSE Sem 3 · B — Rohit Varma        68.3% · 41 of 60 activated
CSE Sem 7 · B — Kiran Das          74.6% · 44 of 59 activated
CSE Sem 7 · A — Nikhil Bose        86.0% · 49 of 57 activated
```

**Built 2026-08-07.** `GET /faculty/department-progress` supplies everything
below except the idle count, which comes from `GET /faculty/ambassadors` on a
second call; if that call fails the tile is dropped rather than guessed.
Sections are shown worst-first here — this card is asked who needs attention,
while the leaderboard is where rank is the point.

### Verdict: buildable, blocked on data

**The layout is straightforward.** Stat tiles are a `Row` of `Column`s of
`Card`s; the list is a `Column` of `Card`s with two `Text` lines each. Same
primitives as the section cards, plus paging. A few hours.

**The data does not exist today.**

| Needed | Available? |
|---|---|
| Activated / certified counts | ✗ nothing exposes activation or certification |
| Sections at 75%+ | ✗ needs per-section activation |
| Ambassadors idle | ✗ ambassadors are not a faculty concept |
| Per-section "28 of 61 activated" | ✗ |
| Section names and headcounts | ✓ `GET /faculty/sections` |

`GET /faculty/sections` returns `department`, `year`, `section`, `label`,
`students` — a headcount, not an activation rate. Agent records carry a `stats`
block (`usedBy`, `questionsThisWeek`, `signInsCaused`), but `statsSyncedAt` is
`null` on every record observed, so it appears unpopulated.

The screenshot is very likely from Campus Ambassador: ambassadors, activation
and certification are its domain.

### What one endpoint would need to return

Ideally a single call — `GET /faculty/department-progress` or similar. Three
calls would mean three round-trips against an API that sleeps on Render, and a
partial failure would paint a professor a half-filled dashboard.

Per department: activated and total counts. Per section: label, the ambassador
(or that it has none), activated count and total. Everything else on that
screen — the percentages, "sections at 75%+", "3 behind", the ordering — is
arithmetic we can do here.

### Constraints to design around

1. **No colour.** The v0.8 catalog has no colour or severity field: `Text`
   takes a `usageHint`, `Card` takes a child. The amber `3 / 6`, the red `2`
   and the pink "no ambassador" row are the renderer's to decide. Emphasis has
   to live in the words — "3 behind", "no ambassador".
2. **6KB per surface, dropped silently.** Four sections fit; twenty will not.
   Needs a "show more" button sized from the real response.
3. **A fresh `surfaceId` per render.** A repeated one is an *update* — it
   rewrites the earlier card and leaves the new turn blank.
4. **Never invent a number.** Every figure must come from the response. A tile
   the model composed can show a number no tool returned, and will.

---

## Requested: "Who / How are my ambassadors?"

A roster of ambassadors, worst first, with a written summary above it.

Two mockups exist for this, differing only in the question — "Who are my
ambassadors?" and "How are my ambassadors?" — with identical cards beneath.
Treat them as one view with two phrasings rather than two views: "who" asks for
the roster, "how" asks for their state, and the answer to both is this list.
Any trigger for it should match both, plus the obvious neighbours ("are my
ambassadors active", "ambassador status").

```
2 of your 5 ambassadors have gone quiet — Rohit (CSE Sem 3 · B, quiet 6 days)
and Kiran (CSE Sem 7 · B, quiet 3 days). 1 section has no ambassador at all:
CSE Sem 5 · B.

Inactive ones are listed first.

(RV)  Rohit Varma      CSE Sem 3 · B   ⚠ no activity 6 days    68.3%   41 / 60
(KD)  Kiran Das        CSE Sem 7 · B   ⚠ no activity 3 days    74.6%   44 / 59
(AN)  Ananya Nair      CSE Sem 3 · A   active today            87.1%   54 / 62
(DT)  Divya Tripathi   CSE Sem 5 · A   active yesterday        89.7%   52 / 58
(NB)  Nikhil Bose      CSE Sem 7 · A   active today            86.0%   49 / 57
```

**Built 2026-08-07**, subject to the product question at the end of this
section. The summary paragraph is composed in `progress_ui.ambassador_summary`,
never by the model.

### Verdict: structure yes, decoration no, data missing

Same shape as the department dashboard — a `Column` of `Card`s — with each row
a `Row` holding a left `Column` (name, section, status) and a right `Column`
(percentage, `41 / 60`). All within the catalog.

**What will not survive the trip:**

| Element | Reality |
|---|---|
| Coloured initial avatars (RV, KD, AN…) | ✗ no component draws a filled circle with initials. `Icon` takes a named icon; `Image` takes a source. Neither renders arbitrary text on a coloured disc |
| Pink row background for inactive | ✗ `Card` has no variant or severity field |
| Amber vs blue percentages | ✗ `Text` carries a `usageHint`, not a colour |
| ⚠ warning glyph | ? `Icon` exists in the catalog but its icon set is unverified. A literal "⚠" in the text string is the reliable fallback |
| Sorting inactive first | ✓ ours to do |
| Right-aligned numeric column | ✓ `Row` of two `Column`s |

So the information all survives; the visual severity encoding does not. Rank
order and wording have to carry it — inactive rows first, "no activity 6 days"
spelled out — rather than colour. That is a real downgrade from the mockup and
worth agreeing before anyone expects the mockup.

**The summary paragraph must be composed in code, not by the model.** It is
made entirely of numbers and names — "2 of your 5", "quiet 6 days", "1 section
has no ambassador". A model writing that sentence from a tool result will
eventually get a count or a day-count wrong, and it will read as authoritative.
Build the string from the response and pass it through.

### Data needed

Nothing here exists today. Per ambassador: name, the section they cover, last
activity timestamp, activated count and section total. Plus the sections in the
department that have **no** ambassador, which the summary needs and which
cannot be derived from a list of ambassadors alone.

Same call as the department dashboard would be ideal — this view and
"How is my department doing?" are two readings of one dataset, and splitting
them across two endpoints would let the two screens disagree.

### The larger question

Ambassadors are Campus Ambassador's domain, not faculty's. Before building
this, worth settling whether faculty are meant to see ambassador performance at
all — names, activity and per-person rates are closer to staff monitoring than
to sending an agent to a class. That is a product decision, not a technical
one, and it should be made deliberately rather than because a mockup existed.

---

## Requested: "Show the leaderboard"

Sections ranked by percentage activated.

```
Your sections, ranked on % activated. CSE overall is at 75.1%.

#1 CSE Sem 5 · A — Divya Tripathi     90% · 52 of 58
#2 CSE Sem 3 · A — Ananya Nair        87% · 54 of 62
#3 CSE Sem 7 · A — Nikhil Bose        86% · 49 of 57
#4 CSE Sem 7 · B — Kiran Das          75% · 44 of 59
#5 CSE Sem 3 · B — Rohit Varma        68% · 41 of 60
#6 CSE Sem 5 · B — no ambassador      46% · 28 of 61

Ranked on % of the section activated — sections under 30 students are pooled.
```

**Built 2026-08-07.** Scope is whatever the endpoint returns — the caller's
department, or the whole college for an admin/non-roster email. Pooling and
rank come from the server, so "sections under 30 are pooled" is stated once,
in Sethu, and rendered here as given.

### Verdict: the easiest of the three to build

A `Column` of `Card`s, two `Text` lines each, with a `Text` above and below. No
avatars, no right-hand column, no icons. It maps onto the catalog almost
exactly, and the rank lives in the string (`#1 …`), so it survives — unlike the
colour encodings in the other two views.

The only thing lost is the pale highlight on `#1`, and `#1` already says it.
This is the view to build first when the data lands.

### Four things to settle before building it

**1. "Your sections" does not map onto our data.** Professors are not assigned
sections in this college — that is why the picker offers the whole college
roster. Whoever's mockup this is assumed faculty own a set of sections. Decide
what the leaderboard is scoped to: the professor's department, the sections
they have published agents to, or the whole college. Each is a different query
and a different meaning.

**2. The pooling rule has to live server-side.** "Sections under 30 students
are pooled" changes the ranking, and if this screen and the department
dashboard apply it differently they will disagree about who is doing well. It
belongs in the endpoint, applied once, with the resulting rank returned — not
re-derived by each client.

**3. Percentages are rounded here, unrounded elsewhere.** This screen shows
`90%`; the ambassador view shows `89.7%` for the same person. Pick one and
apply it everywhere, or the two screens look like they disagree.

**4. It is a public ranking of named colleagues.** #5 and #6 are identifiable
people shown to a professor as the bottom of a league table. That may be
exactly what is wanted, but it should be an intentional choice — the same
question raised under "Who are my ambassadors?".

### Data needed

Identical to the other two views: per section, its label, ambassador (or that
it has none), activated count and total; plus the department overall
percentage. Three readings of one dataset, so **one endpoint should serve all
three** — and it should return the rank and the pooling outcome, not leave
them to be recomputed.

---

## Requested: "How are my agents used?"

The professor's own published agents, ranked by how much students use them.

```
Your 4 agents, by how much your students actually use them:

Placement Prep — CSE
All CSE students · 214 activations · 4,918 chats · 64% return ·
unanswered: system-design rounds

DBMS — Exam Prep
Sem 5 · A + B · 96 activations · 1,180 chats · 52% return ·
unanswered: normalisation to 3NF

Data Structures — Doubts
Sem 3 · A + B · 138 activations · 2,140 chats · 61% return ·
unanswered: graph traversal proofs

OS — Revision
Sem 5 · A · 11 activations · 410 chats · 29% return ·
unanswered: deadlock detection

Activation counts come from Google's certified reporting.
```

**Built 2026-08-07, degrading honestly.** Name, sections, `studentCount` and
`signInsCaused` render today. Chat volume, `usedBy` and `topUnanswered` are
shown only once `statsSyncedAt` is non-null; until then the card says the
figures have not synced rather than printing `0`. An agent nobody has measured
is not an agent nobody uses. "64% return" is still undefined and unbuilt.

### Verdict: the most achievable of the four

Structurally the simplest yet — a `Column` of `Card`s, each a title `Text` and
one detail `Text`. No rank, no right-hand column, no avatars, no colour doing
any work. Nothing in this mockup is lost in translation.

**And unlike the other three, this is about agents, not ambassadors** — which
is squarely what this agent already does, and half the data is already in hand.

### Field mapping — what exists today

`GET /faculty/agents` already returns records carrying a `stats` block. The
mockup lines up against it unusually well:

| Mockup | Source | Status |
|---|---|---|
| Agent name ("DBMS — Exam Prep") | `name` | ✓ available now |
| Sections ("Sem 5 · A + B") | `sections[]` | ✓ available now |
| "unanswered: normalisation to 3NF" | `stats.topUnanswered` | ~ field exists, always null |
| "4,918 chats" | `stats.questionsThisWeek` | ~ field exists, always null; and weekly ≠ total |
| "214 activations" | `stats.signInsCaused` or `stats.usedBy` | ~ fields exist, always null |
| "64% return" | — | ✗ no candidate field |

So the *shape* is already in Sethu's model. What is missing is the values:
`statsSyncedAt` is `null` on every record observed, so nothing is populating
them. **This may need Sethu to switch on a sync rather than design a new
endpoint** — a much smaller ask than the ambassador views, and worth raising
separately so it does not get queued behind them.

### Questions to settle

1. **Where do activations actually come from?** The footnote says "Google's
   certified reporting", which suggests Gemini Enterprise's own analytics
   rather than Sethu. If Sethu ingests that, we read `stats`. If not, we would
   be querying GE directly — a different integration, and worth knowing before
   anyone estimates this.
2. **"64% return" needs defining.** Returning within what window, and returning
   to what — the agent, or any agent? It is the one figure with no candidate
   field, so it needs both a definition and a source.
3. **"chats" over what period?** The existing field is `questionsThisWeek`, but
   `4,918` next to `214 activations` reads like a lifetime total. Weekly and
   lifetime cannot share a line without saying which.
4. **Whose agents?** `GET /faculty/agents` currently returns what looks like
   every agent in the tenant, including ones discovered from GE and never
   published. "Your 4 agents" implies only the caller's published ones. Confirm
   the filter, or a professor will see colleagues' agents in their list.

### Build notes

- Numbers get thousands separators (`4,918`) and percentages are whole here
  (`64%`) — unlike the ambassador view's `89.7%`. Pick one convention across
  all views.
- The detail line is long and wraps. Fine as one `Text`; do not try to build a
  multi-column layout for it.
- Two buttons sit below the fold in the mockup, cut off. Whatever they are,
  they follow the same pattern as the existing cards.
- Compose every line in code from the response. A model handed four records
  and asked to summarise usage will eventually round, re-order, or invent a
  figure, and it will read as certified reporting.

---

## Requested: "Send a campaign"

```
I can message every CSE student who hasn't activated — 89 of your 357. Draft:

"Your DBMS exam-prep agent is live — it makes practice papers from my own
notes and question bank. Internals are on the 4th. One tap, college login:"

Quiet hours and the 2-per-student-per-week cap apply, so the earliest slot is
Thu 30 Jul, 17:30.

[ Send now ]  [ Schedule for Thu 17:30 ]
[ Only the sections under 75% ]  [ Reword it ]
```

### Verdict: the cards are trivial; everything behind them is new

Four buttons and two `Text` blocks — a `Column` of `Row`s. Half an hour of card
work. **Every other part of this is a capability we do not have**, and one of
them may not be possible at all.

Read plainly, this screen asks for: audience segmentation, a custom message
body, scheduled delivery, quiet-hours and rate-cap enforcement, and
model-generated copy sent to real students. That is a product, not a view.

### 🔴 The blocker: WhatsApp will not carry that draft

Business-initiated WhatsApp messages must use a **template pre-approved by
Meta** unless the student messaged the college in the last 24 hours — which
they have not. Templates are fixed wording with numbered placeholders.

The draft in this mockup is free prose, written per campaign, and "Reword it"
regenerates it on demand. **That is precisely what WABA does not permit.** What
is achievable:

- an approved template with a placeholder or two the professor fills;
- a small set of approved templates they choose between.

Not: arbitrary text composed per send. This needs settling with the Sethu team
before anything is designed, because it changes the whole screen — "Reword it"
may have no meaning under a template regime.

Email has no such restriction, so if `notify` also sends email, freeform copy
could be possible there. Two channels, two different message bodies, which the
UI would have to be honest about.

### What `notify` would need to become

Today: `POST /faculty/agents/{id}/notify` takes an agent id and nothing else —
no audience, no message, no schedule.

This screen needs all four:

| Need | Today |
|---|---|
| Audience = students who have not activated | ✗ no activation data, no per-student targeting |
| Message body or template choice | ✗ endpoint takes no message |
| Scheduled delivery ("Thu 17:30") | ✗ no scheduling; send is immediate |
| Quiet hours + 2-per-student-per-week cap | ✗ no such policy exposed |
| "Only the sections under 75%" | ✗ needs the same activation data as the other views |

**The cap and quiet hours must be enforced server-side, not by us.** If the
agent merely displays "the earliest slot is Thu 17:30" while Sethu will happily
send immediately, the guarantee is decorative — and the failure mode is
students being messaged at 03:00 or four times a week.

### Risk this view introduces

**Model-written copy reaching real students.** "Reword it" puts a model in the
outbound message path, sending to hundreds of people irreversibly. Everything
built so far deliberately keeps the model out of the send path — publishing and
confirming are handled in code precisely because a model asked to produce a
number or a phrase will eventually produce a wrong one. A reworded message is
the same risk with a far larger blast radius.

If it goes ahead: the professor must see the exact final text and approve that
text, not a description of it, and the approved string must be what is sent —
never regenerated after approval.

**Retry safety is now unavoidable.** `notify` idempotency is still unanswered
(see `SETHU-whatsapp-notify-500.md`). A scheduled campaign that fails halfway,
with no way to know what was delivered, cannot be safely retried — and at
campaign scale that means either double-messaging a cohort or abandoning it.

### Sequence, if this is wanted

1. Settle the WhatsApp template question. Everything else is moot until then.
2. Get activation data — shared with the other three views.
3. Extend `notify`: audience, template + parameters, schedule; enforce quiet
   hours and the cap inside Sethu.
4. Answer idempotency.
5. Then the cards, which are the easy part.

---

## Next

To be added as requested.
