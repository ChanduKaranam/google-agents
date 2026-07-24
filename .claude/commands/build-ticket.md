---
name: build-ticket
description: Build a claimed ticket. Executes the ticket's Implementation Plan task by task under TDD, reviews each task, and fills the Verification Log. This is where code gets written.
---

# /build-ticket $ARGUMENTS

Executes `docs/tickets/TICKET-XXX-$ARGUMENTS.md`. Everything before this command was design; everything in this command is code.

This command does not invent a process. It runs the superpowers chain over the plan the ticket already carries.

---

## Step 0 — Identity check

Read `docs/TEAM.md` frontmatter (`leads:` and `devs:`). Run `git config user.email`. If the email is not in either list, stop:

> You are not listed in docs/TEAM.md. Ask a lead to add you before building.

---

## Step 1 — Guards

Resolve the ticket file from `$ARGUMENTS`. Read it in full — Goal, Agent Walkthrough, Session-State Contract, Tool Contracts, Test Plan, and especially `## Implementation Plan`.

Then check, in order. Any failure stops the command:

1. **Status.** `IN_PROGRESS` → continue. `APPROVED` → continue (claim it: set `status: IN_PROGRESS`, `claimed_by`, `claimed_at`). `TODO` or `GROOMED` or `CHANGES_REQUESTED` → stop, the design is not approved yet. `COMPLETED` → stop.
2. **Claimant.** If `claimed_by` is someone else, ask before taking over.
3. **The plan exists.** `## Implementation Plan` must contain at least one `### Task N` block with real steps. If it is empty, a stub, or contains TBDs:

   > This ticket has no Implementation Plan. Run `/groom-ticket $ARGUMENTS` first — that is where the plan gets written.

   Stop. Do not improvise a plan here.
4. **Clean tree.** `git status --short` — anything uncommitted, stop and ask.

---

## Step 2 — Isolated workspace

**Invoke the `superpowers:using-git-worktrees` skill.**

It detects whether you are already isolated and will not nest. If it creates a worktree, all subsequent steps run inside it.

---

## Step 3 — Baseline

Record the starting commit — you need it for every review dispatch:

```bash
git rev-parse HEAD   # this is BASE_SHA. Never use HEAD~1 later.
```

Run `.venv/bin/python test_agent.py` once, now, before writing anything. Read the full output.

- All lines `ok`, ending "all checks passed" → proceed.
- Any failure → **report it and ask before continuing.** You are about to do TDD; a suite that is already red makes RED/GREEN meaningless. Do not start on a broken baseline without the user saying so explicitly.

---

## Step 4 — Choose the execution mode

Ask the user which mode, and recommend the first:

1. **Subagent-driven (recommended).** Invoke the `superpowers:subagent-driven-development` skill. Pass this ticket file as `PLAN_FILE` — its tasks are the `### Task N` headings under `## Implementation Plan`. Fresh implementer subagent per task, review after each, continuous execution.
2. **Inline.** Invoke the `superpowers:executing-plans` skill and work the tasks yourself in this session.

**If `subagent-driven-development`'s `scripts/task-brief` cannot parse the ticket** (it expects a plan document, and this is a ticket), say so out loud, then fall back to mode 2. Do not silently degrade, and do not hand-copy task text into subagent prompts as a workaround — file handoffs or inline, nothing in between.

Whichever mode: the ticket's `### Global Constraints` block is copied **verbatim** into every subagent prompt. Paraphrasing constraints (the built-in/function-tool separation, `output_key` names, `NO_INVENTION`/`REAL_PEOPLE_RULES`) is how they get violated.

---

## Step 5 — Per task: TDD, always

**The `superpowers:test-driven-development` skill governs every task.** Its iron law is not negotiable here:

> NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.

Per task, in this order:
1. Write the one minimal failing `test_*` function named in the task's steps, in `test_agent.py`.
2. Run `.venv/bin/python test_agent.py` — **verify it is RED (a failure/traceback), and that it fails for the right reason.** A test that fails because of a typo is not a red test.
3. Write the minimal code to pass.
4. Run `.venv/bin/python test_agent.py` — **verify GREEN ("all checks passed") and the output is pristine.**
5. Refactor if needed. No new behavior.
6. Commit: `type(scope): description (TICKET-XXX)`.

If code got written before its test, delete it. Do not keep it as reference, do not adapt it.

**Ponytail applies to every diff you write.** Climb the ladder before you write a line: does this need to exist at all → does an existing specialist's prompt already cover it (grep `Job_Helper_agent/agent.py` first) → does a function in `tools.py`/`fetch.py`/`links.py`/`verify.py` already do it → can it be one line. Do not add a dependency for what a few lines do. Do not build a new specialist with one caller.

If you deliberately cut a corner with a known ceiling, leave a marker naming the ceiling and the upgrade path — `/complete-feature` harvests these into the PR:

```python
# ponytail: hardcoded top-5 companies, revisit if student pool grows past one cohort
```

Never lazy about: the built-in/function-tool separation, the `NO_INVENTION`/`REAL_PEOPLE_RULES` guarantees, or anything the ticket explicitly asked for.

---

## Step 6 — When something breaks

Any failing test you did not expect, any bug, any "that's weird" — **invoke the `superpowers:systematic-debugging` skill.**

> NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.

Do not stack fixes. One hypothesis, one variable, one smallest-possible change. If three fixes have failed, **stop** — the design is wrong, not the code. Say so, record it in the ticket's `## Delays & Blockers`, and bring it back to the user.

---

## Step 7 — Per task: review

After each task's commit:

**Invoke the `superpowers:requesting-code-review` skill.** Capture `HEAD_SHA`, dispatch the reviewer over `BASE_SHA..HEAD_SHA` (the `code-reviewer` agent in `.claude/agents/` is the reviewer; it returns BLOCK / WARN / NIT).

Then **invoke the `superpowers:receiving-code-review` skill** to act on what comes back. Read all of it before reacting. Verify each finding against the actual code — reviewers are wrong sometimes. Push back with reasoning where it's warranted. Fix BLOCK immediately, WARN before the next task, note NIT.

Do not write "You're absolutely right!" Do not thank the reviewer. State the fix.

---

## Step 8 — Sync state after every task

The ticket and `docs/STATE.md` are what `/handoff` and `/resume-session` read. Keep them true:

- Tick the completed task's checkboxes in `## Implementation Plan`.
- Update `docs/STATE.md`: `last_action`, `next_action`, `files_in_progress`, `blockers`.
- Append a row to the ticket's `## Change Log`.

Commit these with the task, not separately.

---

## Step 9 — Done gate

When every task is complete:

**Invoke the `superpowers:verification-before-completion` skill.**

> NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE.

Run this **in this message**, and read the full output and exit code. You may not claim it passes on the strength of having run it earlier:

```bash
.venv/bin/python test_agent.py
```

There is no lint or typecheck configured for this project — do not claim either passed.

Then fill the ticket's `## Verification Log` table with what you actually observed — the command, the surface, the result. An unrun row is an empty row, not a ticked one.

Then report:

```
BUILD COMPLETE — TICKET-XXX
Tasks:        {n}/{n}
Tests:        {actual output summary}
Shortcuts:    {any ponytail: markers left, or "none"}

Next: /complete-feature $ARGUMENTS
```

---

## Notes for Claude

- The ticket is the plan. If the plan is wrong, stop and go back to `/groom-ticket` — do not fix it inline and build from your own version.
- The test-first order is not a suggestion. Verify RED before you write the implementation, every task, no exceptions for "too simple to test".
- Never claim a command passed without its output in the same message. "Should pass" and "probably fine" are the words that precede a broken merge.
- Three failed fixes means stop, not fix number four.
