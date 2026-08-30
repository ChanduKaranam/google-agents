# Lodestar

The orchestrator of an insurance agency's lead pipeline, for Gemini Enterprise.
Raw leads in one end, phone calls out the other.

Lodestar itself does no work. It opens a batch, hands the leads to a **Policy
Analysis Agent**, hands the qualified ones to an **Outreach Agent** that calls
them through Hello.ai, and keeps the ledger that says who has actually been
reached.

```
lodestar/
  agent.py       root_agent — the orchestrator and its instruction
  sub_agents.py  the two specialists, Policy Analysis and Outreach
  tools.py       the batch ledger
  hello_ai.py    the Hello.ai client and the two tools Outreach dials through
  config.py      environment settings
```

## Status

All three agents carry their real prompts and the pipeline runs end to end.

**The calls are mocked.** Hello.ai have not handed over their API, so
`trigger_hello_ai_call` simulates the calls and places none. Outcomes are drawn
from the lead id rather than at random, so the same demo twice tells the same
story, and they improve on retry so a batch converges instead of grinding.

Every simulated result carries `mock: true` and a `[MOCK]` detail prefix that
survives into the ledger and out to `batch_status` as `simulated_calls`, and
both agents are instructed to open and close a simulated report by saying no
calls were placed. A demo cannot be mistaken for an afternoon of outreach.

**Setting `HELLO_AI_BASE_URL` and `HELLO_AI_API_KEY` switches to the real path
by itself** — there is no flag to remember to turn off. `HELLO_AI_MOCK=1`
forces the mock even with credentials set; `HELLO_AI_MOCK=0` forbids it, and an
unconfigured platform then refuses rather than inventing anything.

The real request and response shapes in `hello_ai.py` are a guess — no
documentation was available. `_payload` and `_normalise` are the only two
places any of it is decided; correct them there and no agent changes.

Each specialist's contract with Lodestar:

- **`policy_analysis_agent`** is given raw lead rows carrying a `lead_id`, and
  returns a JSON array: `lead_id`, `lead_name`, `extracted_profile`,
  `recommended_policy`, `reasoning`, `pitch_notes`. A lead it cannot qualify
  comes back with an empty `recommended_policy` and a reason — never dropped.
- **`outreach_agent`** is given `lead_id`, `name`, `phone`, `policy`,
  `pitch_notes`, `reasoning`, `profile` and `attempts_remaining`, and returns
  one record per lead: `lead_id`, `outcome` (`contacted` / `unattempted` /
  `failed` / `in_progress`), `attempts`, `call_id`, `detail`. Every lead it was
  given is reported, including the ones it did not call.

`record_analysis` and `record_outreach_results` in `tools.py` are the only
places those shapes are read.

## The lead sheet

Twelve columns: Name, Age, City, Phone Number, Marital Status, Dependents,
Occupation, Annual Income (SGD), Tobacco Use (Y/N), Existing Cover (SGD),
Hobbies, Recent Life Event. Money is Singapore dollars, written however the
file writes it — "96000", "S$96,000" and "96k" all normalise to the same
number.

Headers are read by meaning, not spelling — `_field` in `tools.py` normalises
case, spaces and underscores, because a header capitalised differently in the
next file used to blank every phone number silently.

**Phone Number and Hobbies close the two gaps the earlier sheet had.** Outreach
can dial, and the Personal Accident rule can actually fire. `open_batch` still
reports `leads_without_a_phone_number` at intake — a column existing does not
mean every row filled it in — and the mock still refuses to pretend it dialled
a blank.

**One gap left: Dependents is not children.** Where a rule wants children, the
sheet counts dependents, who may be parents. It fires on dependents, since that
is what the data holds.

## The policy catalogue

`singapore_policy_guidelines.md` is the catalogue: seven Singapore products,
each with its purpose, its target customer, and the criteria that select it.
It is the document to edit when a product or a criterion changes.

The seven cover the six categories the agency asked for — Critical Illness is
the ECI rider inside Whole Life rather than a product of its own — plus two the
list did not name: **Personal Accident & Disability Income**, without which the
Hobbies column has nothing to do, and the **CareShield Life Supplement**, which
is the only thing in the catalogue aimed at leads over 40.

**Every threshold lives in `config.py`**, not in the prompt: cover below
S$50,000, Term Life under S$60,000 and under 45, ILP under 35 and over
S$80,000, CareShield at 40 and over S$50,000. Move a line there and the prompt
moves with it, so redrawing one is a config change rather than an edit to an
instruction whose wording carries meaning.

### Two changes to the Policy Analysis prompt as supplied

**`lead_id` added to the output format.** The ledger matches every answer back
to the row it came from by id, and the format as written carried only
`lead_name` — empty, duplicated or "Unknown" often enough in a real
spreadsheet that name-matching loses leads silently.

**Rule precedence made explicit: first match wins, in the order written.** The
guidelines give each product a trigger and no order to apply them in, and real
leads match several at once — a married smoker with a new baby and a home loan
matches four. The order runs most-specific first:

1. Whole Life + ECI — tobacco, with a spouse or dependents
2. Maternity & Child Education Endowment — new child
3. Term Life to 65 — home loan or marriage, under S$60k, under 45
4. Personal Accident & Disability Income — high-risk hobby or gig occupation
5. Investment-Linked Policy — under 35, over S$80k
6. CareShield Life Supplement — 40 or over, above S$50k
7. Integrated Shield Plan + Rider — the baseline

**Integrated Shield is last precisely because it is the baseline.** Its own
criterion, cover below S$50,000, is true of most of the sheet; anywhere earlier
in the order and it swallows the batch before a more specific rule can fire.

Unknown fields are stated not to satisfy a rule, so an unknown smoking habit is
never read as a "no". Existing Cover is the one exception, and only in rule 7,
where a missing figure counts as a protection gap because that is what it
usually is. A lead that matches nothing comes back with an empty
`recommended_policy` and a reason, never forced into a product. Reorder the
list in `sub_agents.py` if the agency ranks them differently.

### Two changes to the Outreach prompt as supplied

**One shared attempt budget, not two.** The Outreach prompt keeps its own
retry queue and retries up to 3 times; the Root prompt separately instructs
retries on anything unattempted. Both running means up to nine calls to one
person. Worse, an Outreach-held queue does not survive: each invocation is a
fresh run, so the queue is gone the moment it returns. So the count lives in
the ledger. Outreach is handed `attempts_remaining` per lead and reports
`attempts` actually spent, and the ledger enforces the total.

**A live call is `in_progress`, not `unattempted`.** The prompt says to accept
a callback payload from Hello.ai, but nothing can receive a webhook mid-turn,
and a voice call takes minutes — longer than the HTTP request that started it.
So dispatch and result are two tools, and a call still ringing gets its own
state that is neither reached nor failed. Reporting it `unattempted` is what
would dial someone whose phone is ringing right now.

## Two things worth knowing

**The specialists are `AgentTool`s, not ADK `sub_agents`.** `sub_agents`
transfers the conversation away and it does not come back on its own, which
would strand the pipeline after analysis — the review, the calls and the
retries all happen *after* the specialist answers. As tools, control returns.

**The batch ledger is real, not remembered.** A model asked to carry "how many
processed, how many contacted, how many pending retry" across a long
conversation reports numbers that drift, and these numbers are what tells the
agency it has reached someone. So `tools.py` holds the counts in session state
and the instruction forbids quoting any figure that did not come from a tool
result. It also caps retries: "retry anything unattempted" has no natural end,
because a number nobody ever picks up is unattempted after every attempt.

## Running it

```bash
cp .env.example .env      # fill in the project
pip install -r requirements.txt
adk web                   # from the parent directory
```
