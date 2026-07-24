---
name: claim-ticket
description: Pick up an APPROVED ticket from the queue. Branches off pre-dev, claims in _active.md, initializes STATE.md.
---

You are claiming an existing ticket: **$ARGUMENTS**

## Step 0 — Identity check

Read `docs/TEAM.md`. Verify `git config user.email` is in leads ∪ devs.

## Step 1 — Sanity check

```bash
git status && git switch pre-dev && git pull --ff-only origin pre-dev
```

## Step 2 — Resolve and read the ticket file

```bash
ls docs/tickets/${ARGUMENTS}-*.md 2>/dev/null
```

Extract: `feature`, `branch`, `status`, `estimated_sessions`, `groomed_by`, `approved_by`.

## Step 3 — Status guard (design-approval gate)

- `TODO` → abort: "Hasn't been groomed yet."
- `GROOMED` → abort: "Awaiting lead review."
- `CHANGES_REQUESTED` → abort: "Feedback pending revision."
- `APPROVED` → continue.
- `IN_PROGRESS` → abort: "Already claimed by {developer}."
- `COMPLETED` → abort: "Already done."

If `groomed_by` set and != current user, ask: "Was groomed by {groomed_by}. Claim anyway? (y/N)"

## Step 4 — Isolated workspace on the feature branch

**Invoke the `superpowers:using-git-worktrees` skill.** It prefers the harness's native worktree tool over raw `git worktree add`, detects whether you are already isolated so it will not nest, and installs dependencies (`pip install -r Job_Helper_agent/requirements.txt`) + checks a clean test baseline (`.venv/bin/python test_agent.py`) once the workspace exists.

If it declines (no permission to create a worktree, or the user prefers working in place), fall back to:

```bash
git switch -c {branch} pre-dev
```

## Step 5 — Update ticket frontmatter

- `status: IN_PROGRESS`
- `claimed_by: {email}`
- `claimed_at: {ISO-8601 now}`

## Step 6 — Update _active.md

Append to `active:` YAML list. Remove from Available follow-up tickets if listed there. Add row to Active Tickets table.

## Step 7 — Initialize STATE.md

```yaml
ticket: {id}
feature: {slug}
branch: {branch}
developer: {name}
timestamp: {now}
status: CLAIMED
last_action: Picked up from queue via /claim-ticket.
next_action: Run /build-ticket {slug} — it executes the ticket's Implementation Plan.
files_in_progress: []
blockers: []
```

## Step 8 — Commit (no push)

```bash
git add docs/ && git commit -m "chore({slug}): claim {TICKET-id}"
```

## Step 9 — Report and pause

Print a formatted summary ending with:

```
Next: /build-ticket $ARGUMENTS
```

Stop here. Do not write code in this command — `/build-ticket` owns implementation, and it runs TDD over the ticket's Implementation Plan. Starting here would skip the test-first cycle and the isolated baseline.

---

## Notes for Claude

- The APPROVED gate is non-negotiable. No bypasses for devs.
- Do not modify the ticket body — only the YAML frontmatter status/claimed_by/claimed_at.
- This command claims. It does not build. `/build-ticket` builds.
