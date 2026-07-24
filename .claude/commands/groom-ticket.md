---
name: groom-ticket
description: Deep-design a TODO (or CHANGES_REQUESTED) ticket — adds agent design, session-state contracts, test scenarios, test plan, and risks. Sets status GROOMED (or auto-APPROVED if a lead runs it).
---

You are deepening the design of an existing ticket: **$ARGUMENTS**

## Step 1 — Sanity check

```bash
git status
```

If dirty, stop and ask to commit/stash first.

## Step 2 — Identity check

Read `docs/TEAM.md`. Check `git config user.email` against leads/devs.

## Step 3 — Resolve the ticket file

```bash
ls docs/tickets/${ARGUMENTS}-*.md 2>/dev/null
```

Read frontmatter, extract `status`, `feature`, `branch`.

## Step 4 — Status guard

- `TODO` → continue
- `CHANGES_REQUESTED` → continue (preserve prior Lead Feedback sections verbatim). **Invoke the `superpowers:receiving-code-review` skill** to work through the lead's feedback before re-designing: read all of it before reacting, restate each item in your own words, verify it against the actual ticket and codebase, then respond with a technical acknowledgement or a reasoned pushback. Do not write "You're absolutely right!" Do not thank the lead. If any item is unclear, stop and clarify all of them before changing a line.
- `GROOMED` → abort: "Already groomed; awaiting lead review."
- `APPROVED` and dev → abort: "Already approved. Run `/claim-ticket $ARGUMENTS`."
- `IN_PROGRESS | COMPLETED` → abort: "Past design phase."

## Step 5 — Switch to ticket branch

```bash
git switch {branch-from-frontmatter}
git pull --ff-only
```

## Step 6 — ENTER PLAN MODE, then design (rounds 1–4)

**Invoke the `superpowers:brainstorming` skill** to run these rounds. Three overrides, because this project keeps its design in tickets:

1. **The design artifact is this ticket file.** Do not write `docs/superpowers/specs/*` — write the design into the ticket's `## Agent Walkthrough`, `## Session-State Contract`, `## Tool Contracts`, `## Test Scenarios`, and `## Test Plan` sections (Step 8).
2. **Do not jump to `writing-plans`.** That is Step 7 of this command, after the risk grill. Brainstorming's hard gate still holds: no code, no scaffolding, until the design is written and the user has approved it.
3. Its "propose 2–3 approaches with trade-offs" step is where **ponytail's ladder** belongs. Before proposing anything: does this need to exist at all? Is it already in this codebase — grep `Job_Helper_agent/` for it. Can an existing specialist's prompt absorb this instead of a new agent? Recommend the laziest approach that actually holds, and say what you skipped.

Cover, in order:

### Round 1 — Agent walkthrough
For each specialist touched: its `description`, `instruction` prompt changes, its tools (built-in XOR function, never both), its `output_key`, and the model it runs on (flash for specialists, pro reserved for the root).

### Round 2 — Session-state contract
Which `output_key`s are added or changed? Which downstream agents read them via `{key?}` templating? What happens when the key is absent (empty-string degrade) — is that an acceptable default, or does the downstream prompt need an explicit "if empty, do X" branch?

### Round 3 — Tool contracts
For each new or changed function tool in `tools.py`/`fetch.py`/`links.py`/`verify.py`: signature, what it fetches or verifies, and confirmation it does not silently invent data (per `NO_INVENTION`). If it touches named people, confirm `REAL_PEOPLE_RULES` is applied verbatim in the calling agent's instruction.

### Round 4 — Test scenarios
Happy path, no-results path, upstream-key-missing path, tool/model-failure path, and (if applicable) the LinkedIn-fetch-block / real-people guard paths that `test_agent.py` already covers as precedent.

### Round 4b — Test plan (concrete test names)
Name the exact new `test_*` function(s) to add to `test_agent.py`, or mark `N/A — {reason}`.

### Round 5 — Risks, dependencies, rollback — GRILL THIS ONE

**Invoke the `grilling` skill** for round 5. This is the round where a bad design gets caught, so it is not a batched questionnaire: one question at a time, each with your recommended answer, walking the decision tree branch by branch. Look facts up (the current `agent.py` wiring, `docs/superpowers/specs/`) rather than asking for them — the *decisions* are the user's, the *facts* are yours to find.

Cover: risk of the built-in/function-tool conflict recurring, risk of a fabricated-person regression, depends-on tickets, rollback plan (revert the agent registration in `agent.py`), and any measured-behavior concerns like the flash-vs-pro orchestration issue already documented in `agent.py`. Do not stop on a question count — stop when the user confirms you have reached a shared understanding.

## Step 7 — Write the Implementation Plan

**Invoke the `superpowers:writing-plans` skill.** One override: the plan is written into this ticket's `## Implementation Plan` section, not `docs/superpowers/plans/*`.

It must produce:
- A `### Global Constraints` block — the verbatim values from the design (no REST envelope/validation lib/ORM apply here; instead: the `output_key` names, the built-in/function-tool separation rule, the model per agent, `NO_INVENTION`/`REAL_PEOPLE_RULES` where relevant). These get copied word-for-word into every implementer prompt in `/build-ticket`, so paraphrasing here is how a constraint gets violated later.
- One `### Task N` per test cycle, each with `**Files:**` (exact paths) and `**Interfaces:**` (exact signatures), then checkbox steps in strict TDD order: write failing test → run and verify RED → minimal implementation → run and verify GREEN → commit.

**No placeholders.** "TBD", "TODO", "add appropriate error handling", "similar to Task 1" — each of those is a plan failure. `/build-ticket` will refuse a ticket whose plan contains them.

## Step 7b — EXIT PLAN MODE

## Step 8 — Insert design sections into ticket

Write: Agent Walkthrough, Session-State Contract, Tool Contracts, Test Scenarios, Test Plan, Risks, and Implementation Plan.

## Step 9 — Update frontmatter

- `groomed_by`, `groomed_at`, `grooming_round`
- Lead runner → `status: APPROVED`; Dev runner → `status: GROOMED`

## Step 10 — Update _active.md

Dev: add row to Pending Lead Review table. Lead: remove from that table if present.

## Step 11 — Commit and push

```bash
git add docs/tickets/ && git commit -m "chore: groom $ARGUMENTS" && git push -u origin {branch}
```

## Step 12 — Report and pause

Print formatted summary with status, ticket path, and next step. Stop here.

---

## Notes for Claude

- Do not skip any round. Round 5 is grilled one question at a time — batching it defeats the point.
- The ticket leaves this command with a complete, TBD-free `## Implementation Plan`. That plan is the contract `/build-ticket` executes. A vague plan becomes a vague feature.
- No code. Not one line, not a scaffold, not a "quick stub to check the shape". This command designs.
- Push the branch so leads on other machines can pull.
- Lead self-approval is intentional (they are both author and reviewer).
