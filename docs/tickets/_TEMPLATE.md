---
ticket: TICKET-XXX
feature: { feature-slug }
branch: feature/{feature-slug}
status: TODO   # TODO | GROOMED | CHANGES_REQUESTED | APPROVED | IN_PROGRESS | BLOCKED | READY_FOR_REVIEW | COMPLETED
co_claimants:
  agent: ""
estimated_sessions: "—"
estimated_hours: "—"
started_at: ""
target_end_date: ""
actual_end_date: ""
groomed_by: ""
groomed_at: ""
grooming_round: 1
approved_by: ""
approved_at: ""
last_feedback_by: ""
last_feedback_at: ""
review_notes: ""
claimed_by: ""
claimed_at: ""
---

# TICKET-XXX — {Feature Name}

**Depends on:** none
**ADR:** (only if architectural — delete this line otherwise)

---

## Goal

One paragraph. Why this exists and what a student will be able to do once it ships.

---

## Reference

- Skills to load before agent work: `testing-patterns`
- Rules: `.claude/rules/agent.md` — built-in/function-tool separation, `output_key` contract, `NO_INVENTION`/`REAL_PEOPLE_RULES`, model split (flash specialists / pro orchestrator)
- Deviations from prior behavior: none

---

## Agent Walkthrough

> _Filled by `/groom-ticket`._ Per specialist touched (new or existing): its `description`, `instruction` prompt changes, its tools (built-in XOR function tools — never both), its `output_key`, and its model.

---

## Session-State Contract

> _Filled by `/groom-ticket`._

- **`output_key`s added/changed:** {key → producing agent}
- **Downstream readers:** {key → agents that read it via `{key?}`}
- **Empty-key degrade behavior:** {what happens when a reader sees `""` because the key is absent}

---

## Tool Contracts

> _Filled by `/groom-ticket`._

### `{function_name}` (`{path}`)

```python
def function_name(arg: type) -> ReturnType:
    ...
```

- **Purpose:** {what it fetches, verifies, or computes}
- **No-invention guarantee:** {how it avoids returning fabricated data, or "N/A — pure computation, no external data"}

---

## Test Scenarios

> _Filled by `/groom-ticket`._

- **Happy path:** {bulleted}
- **No-results path:** {what the specialist says when search/matching finds nothing}
- **Upstream-key-missing path:** {behavior when a required `output_key` is absent}
- **Model/tool-failure path:** {timeout, refusal, or empty turn handling}
- **Edge cases:** {bulleted}

---

## Test Plan

> _Filled by `/groom-ticket`._ Check the box when the `test_*` function lands in `test_agent.py`; replace with `N/A — {reason}` if it doesn't apply.

- [ ] `test_{name}` — {what it asserts}

---

## Risks, Dependencies, Rollback

> _Filled by `/groom-ticket`._

- **Structural risk:** {e.g. built-in/function-tool conflict recurring}
- **Real-people risk:** none — or {prose, if this touches named individuals}
- **Depends on:** none
- **Rollback plan:** {prose — usually: revert the agent registration in `agent.py`}
- **Performance/cost concerns:** {model choice implications, if any}

---

## Implementation Plan

> _Filled by `/groom-ticket` via the `superpowers:writing-plans` skill. Executed by `/build-ticket`._
>
> **No placeholders.** "TBD", "TODO", "add appropriate error handling", "similar to Task 1" — each of these is a plan failure, not a plan. A task is the smallest unit of work that carries its own test cycle. Steps are 2–5 minutes each.

### Global Constraints

> Verbatim values from the design above. These get copied word-for-word into every implementer prompt — paraphrasing a constraint is how it gets violated.

- **Built-in/function-tool separation:** a Gemini built-in tool (`google_search`, `url_context`) cannot share an `Agent` with custom function tools
- **`output_key` contract:** {list from Session-State Contract above}
- **Real-people rules:** `NO_INVENTION` / `REAL_PEOPLE_RULES` apply verbatim if this touches named individuals, else "N/A"
- **Model:** `gemini-2.5-flash` for specialists, `gemini-2.5-pro` reserved for the root orchestrator
- **Test command:** `.venv/bin/python test_agent.py`

### Task 1: {name}

**Files:** Create `{path}` · Modify `{path}` · Test `test_agent.py`
**Interfaces:** Consumes `{exact signature}` → Produces `{exact signature}`

- [ ] Write failing test in `test_agent.py` asserting `{specific behavior}`
- [ ] Run `.venv/bin/python test_agent.py` — verify RED, and that it fails for the right reason
- [ ] Implement `{path}` — minimal code to pass
- [ ] Run `.venv/bin/python test_agent.py` — verify GREEN, output pristine ("all checks passed")
- [ ] Commit `type(scope): description (TICKET-XXX)`

### Task 2: {name}

_(same structure — one task per test cycle)_

---

## Acceptance Criteria

- [ ] {criterion}

---

## Out of Scope

- Things explicitly deferred
- {edge cases known but not in this ticket}

---

## Lead Feedback

> _Appended by `/review-ticket` only when a lead requests changes._

---

## Documentation

- **ADRs:** (or "n/a")
- **Parent ticket:** none
- **Follow-up tickets:** none

---

## Automation Tests

| Layer | Path | Suites | Status |
|-------|------|--------|--------|
| — | — | — | — |

---

## Change Log

| Date | Change | Driver | Migration / Commit |
|------|--------|--------|--------------------|
| —    | —      | —      | —                  |

---

## Delays & Blockers

**Active blockers:** none

---

## Verification Log

Filled by `/build-ticket` (done gate) and `/complete-feature` (pre-merge gate), both via the `superpowers:verification-before-completion` skill — do not edit manually. Every row is a command that was actually run, with its actual output. An unrun row is an empty row, not a ticked one.

| Surface | Bullet | Verified by | Date | Pass |
|---------|--------|-------------|------|------|
| —       | —      | —           | —    | —    |

---

## Token Ledger

Filled by SessionEnd hook — do not edit manually.

**Estimate:** {N} sessions · ~{H}h
**Sessions:** 0 · **Total tokens:** 0 in / 0 out / 0 cache

| session_id | dev | started | duration | input | output | cache_read | cost_usd |
|------------|-----|---------|----------|-------|--------|------------|---------|
