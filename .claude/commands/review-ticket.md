---
name: review-ticket
description: Lead-only command. Reviews a GROOMED ticket, asks questions, and either approves it or requests changes. Identity-gated — only leads listed in docs/TEAM.md can run this.
---

You are reviewing a groomed ticket for Job Helper Agent: **$ARGUMENTS**

## Step 0 — Identity check (leads only)

Read `docs/TEAM.md` YAML frontmatter. Extract `leads:` list.

```bash
git config user.email
```

If the runner's email is **not** in `leads:`, abort:

> "Only leads can run `/review-ticket`. If you need this ticket approved, ask a listed lead to run this command."

## Step 1 — Fetch and read the ticket

```bash
git fetch origin
git switch {branch-from-ticket}
git pull --ff-only
```

Read `docs/tickets/$ARGUMENTS-*.md` in full — all sections.

## Step 2 — ENTER PLAN MODE for lead review

This is the last gate before code exists. It is worth being slow here — a design flaw caught now costs one conversation; caught in `/complete-feature` it costs the branch.

**Invoke the `grilling` skill.** One question at a time, each carrying your recommended answer, walking the decision tree branch by branch. Anything you can *look up* — the current `agent.py` wiring, whether a specialist already exists, what `test_agent.py` already asserts — you look up. You only ask the lead about *decisions*.

Grill across:
- **Agent walkthrough** — correctness of the built-in/function-tool separation, model choice (flash vs. pro), prompt clarity.
- **Session-state contract** — completeness (every new `output_key` has a reader?), correct `{key?}` degrade behavior, no silent data loss between specialists.
- **Test plan** — gaps. Does coverage match the risk? Is a no-results or real-people path marked `N/A` when it shouldn't be?
- **Risk** — are the real blockers identified, or only the comfortable ones (per the flash/pro orchestration precedent already documented)? Is the rollback plan something you could actually execute?

Then apply a second lens to the `## Implementation Plan`:

**Invoke the `ponytail:ponytail-review` skill** on it. Not for correctness — purely for what should be cut. Is a task building a new specialist where a prompt change on an existing one would do? Adding a dependency for what a few lines do? Reinventing something `tools.py`/`fetch.py`/`links.py`/`verify.py` already has? Scaffolding for a future nobody has asked for? The cheapest task is the one that gets deleted at review.

Present the summary for the decision:
```
## Design Summary: $ARGUMENTS
Goal: {one line}
Agents touched: {list, new vs. existing}
Session-state changes: {output_key list}
Test plan: {N new tests + names}
Implementation Plan: {N tasks}
Risks: {brief}
Cuts proposed: {from ponytail-review, or "none — lean already"}
```

Ask: "Approve this design, or request changes?"

Do not act on it until the lead confirms. Grilling's exit condition is shared understanding, not a question count.

## Step 3 — EXIT PLAN MODE

## Step 4 — Apply decision

**If APPROVED:**
- Set `status: APPROVED`, `approved_by: {email}`, `approved_at: {ISO-8601 now}` in frontmatter.
- Remove ticket from `_active.md` Pending Lead Review table.
- Commit: `chore: approve $ARGUMENTS`

**If CHANGES REQUESTED:**
- Set `status: CHANGES_REQUESTED`, `last_feedback_by: {email}`, `last_feedback_at: {ISO-8601 now}`.
- Append `## Lead Feedback (Round {grooming_round})` section with numbered change requests.
- Commit: `chore: request changes on $ARGUMENTS`

Push in both cases: `git push origin {branch}`

## Step 5 — Report

Print outcome summary and next steps (who needs to act).

---

## Notes for Claude

- Identity check is non-negotiable. No bypasses.
- Feedback must be numbered and specific — "unclear" is not actionable. The dev will run `superpowers:receiving-code-review` against this feedback, and that skill requires each item to be verifiable against the code. Write items that can be verified.
- Preserve all prior Lead Feedback sections verbatim when adding a new one.
- Approving a ticket with a TBD in its `## Implementation Plan` means approving a vague feature. `/build-ticket` will reject it anyway — catch it here.
