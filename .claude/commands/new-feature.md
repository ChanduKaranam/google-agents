---
name: new-feature
description: Start a new feature — runs the architectural interview, writes the ticket file, estimates session count.
---

You are starting a new feature for Job Helper Agent: **$ARGUMENTS**

Follow this protocol exactly. The interview at the front is non-negotiable — it makes the build predictable.

## Step 0 — Identity check

Read `docs/TEAM.md` YAML frontmatter. Extract `leads:` and `devs:` lists.

```bash
git config user.email
```

If the runner's email is **not** present in `leads ∪ devs`, abort:

> "You're not listed in `docs/TEAM.md`. Add yourself under `devs:` (or ask a lead to) on a feature branch + PR, then re-run."

Record whether the runner is a lead (used in Step 8).

## Step 1 — Sanity check

```bash
git status
git switch pre-dev
git pull --ff-only origin pre-dev
```

If the working tree is dirty, stop and ask them to commit or stash first.

## Step 2 — Determine the next ticket number

```bash
ls docs/tickets/ | grep -E '^TICKET-[0-9]' | sort | tail -1
```

## Step 3 — Switch to feature branch (BEFORE Plan Mode)

```bash
git switch -c feature/$ARGUMENTS pre-dev
```

## Step 4 — ENTER PLAN MODE

Stay in Plan Mode for the entire interview. Files are written AFTER ExitPlanMode.

## Step 5 — Architectural interview (3 rounds, ≤4 questions per AskUserQuestion batch)

**Before Round 1, climb ponytail's first rung: does this feature need to exist at all?**

Ask it plainly. Is there a rung above building it — an existing specialist that already covers the case, a prompt tweak instead of a new agent, a thing the student could already do if the orchestrator routed better? If the honest answer is "this is speculative", say so in one line and stop before you spend a ticket on it. YAGNI is cheapest at the very start.

If it survives that, run the rounds. These are the fast, factual rounds — batched `AskUserQuestion` is right here. The deep design happens in `/groom-ticket`, and that one is grilled.

### Round 1 — Scope
1. Who's the student-facing scenario, and what are they trying to accomplish?
2. Which specialist does this touch — an existing one (`profile_agent`, `company_agent`, `alumni_agent`, `matching_agent`, `verification_agent`, `resume_gap_agent`, `outreach_agent`, `tracker_agent`, `coach_agent`) or a new one?
3. What does this specialist produce (its `output_key`), and who reads it downstream?
4. Does it need a Gemini built-in tool (`google_search`/`url_context`)? If so, confirm it will hold *no* other function tools — that combination silently breaks at the API.

### Round 2 — Failure and safety states (all required)
1. Empty/no-results — what does the specialist say when search or matching finds nothing? Must state that plainly per `NO_INVENTION` — never a plausible guess.
2. Missing upstream data — an earlier specialist's `output_key` is absent (e.g. no profile yet). What does `{key?}` degrade to, and is that acceptable?
3. Model/tool failure — timeout, refusal, or empty turn. Retry, fall back, or surface to the student?
4. Real people involved? If this specialist can surface named individuals (alumni, contacts), confirm `REAL_PEOPLE_RULES` applies verbatim — no unlinked names, no gender guessing, no padding.

### Round 3 — Boundaries
1. Model choice — `gemini-2.5-flash` (specialist default) or does this need the stronger orchestrator model? Only the root should ever need `gemini-2.5-pro`.
2. New function tool, or reuse existing (`fetch.py`, `links.py`, `verify.py`, `tools.py`)?
3. Does the orchestrator's `AgentTool` wiring in `agent.py` need to change, and does `test_agent.py` need a new structural assertion for it?

## Step 6 — Estimate session count

Based on answers, give a session range (1 session for a prompt/tool tweak, 2–3 for a new specialist end-to-end).

## Step 7 — EXIT PLAN MODE

## Step 8 — Write the ticket from the template

Copy `docs/tickets/_TEMPLATE.md` to `docs/tickets/TICKET-XXX-$ARGUMENTS.md` and fill in Goal, Acceptance Criteria, and session estimate.

- Lead runner → `status: APPROVED` (auto-approved)
- Dev runner → `status: TODO` (needs grooming + lead review)

## Step 9 — Claim in _active.md

Append to `active:` in `docs/tickets/_active.md`.

## Step 10 — Update STATE.md

Set status `SCAFFOLDED`, next action, empty files_in_progress.

## Step 11 — Commit (no push)

```bash
git add docs/tickets/ docs/STATE.md
git commit -m "chore($ARGUMENTS): initialize feature scaffold"
```

## Step 12 — Report and pause

Print a formatted summary with ticket path, branch, estimate, and next step. Stop here.

---

## Notes for Claude

- Do not skip the interview. Tickets without failure/safety states ship agents that either invent facts or go silent.
- Ask in batches of 4 max.
- If the dev says "decide later", that decision defers to `/groom-ticket`, which is the design command — not to build time. `/build-ticket` refuses a ticket whose Implementation Plan still contains TBDs, and it is right to: an unresolved decision does not get more resolved by having code written around it.
- This command scaffolds a ticket. It does not design one and it does not build one.
