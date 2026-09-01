---
name: fix-bug
description: Fix a bug in a shipped feature. Grills the report, reproduces it, traces the root cause, stops for your confirmation, then fixes it test-first at the root — not at the symptom.
---

You are fixing a bug: **$ARGUMENTS**

A bug report names a *symptom*. It does not name a cause, and it does not name a fix — even when it sounds like it does, and even when the reporter is you. This command exists to keep those three apart.

---

## Step 0 — Identity check

Read `docs/TEAM.md` frontmatter (`leads:` and `devs:`). Run `git config user.email`. Not in either list → stop.

---

## Step 1 — Understand the report

**Invoke the `grilling` skill.** One question at a time, each with your recommended answer.

Grilling's second rule matters more here than anywhere else in this pipeline: **facts get looked up, decisions get asked.** Do not ask the user what you can find yourself.

Look up, don't ask:
- Which specialist or tool this belongs to — `grep` `Job_Helper_agent/` for the symptom or the output_key.
- What the code currently does — read it.
- When it last worked — `git log -S'{the symptom string}'`, `git log` the file.
- Whether there's an existing test for this path in `test_agent.py` — there probably isn't, which is itself the finding.

Ask the user, one at a time:
- What did you expect to happen, and what happened instead? (These are two answers. Get both.)
- The exact steps — the input, the prompt, the transcript. Not "it breaks on alumni search" — the steps.
- Every time, or sometimes? If sometimes, how often, and what's different when it does?
- Error text or model output, verbatim. Whatever exists.
- Who's affected, and how badly? (This sets severity — and if a fabricated person or link was surfaced, severity is automatically high per `REAL_PEOPLE_RULES`.)

Stop when you can state the bug in one sentence and the user agrees that sentence is the bug.

---

## Step 2 — Find the feature it broke

Resolve the parent ticket from `docs/tickets/`. Read its Goal, its Acceptance Criteria, and its Test Plan.

Most bugs are one of three things, and knowing which shapes the fix:
1. **An acceptance criterion that was never true** — it shipped broken; the AC was never verified.
2. **A state nobody designed** — usually the no-results, upstream-key-missing, or model-failure path. Check the ticket's Agent Walkthrough for what it *said* should happen.
3. **A regression** — it worked, then a later change broke it. `git log -S` will find it.

Say which one this is. If it's (1) or (2), the ticket's design was wrong, not just the code — note that in the bug ticket, because the same gap is probably in the ticket's siblings.

---

## Step 3 — Open the bug ticket and a branch

Next bug number: `ls docs/tickets/ | grep -E '^BUG-[0-9]' | sort | tail -1`

Copy `docs/tickets/_BUG_TEMPLATE.md` → `docs/tickets/BUG-XXX-$ARGUMENTS.md`. Fill: Symptom (expected / actual / error text / affects), the parent ticket, severity, `reported_by`, `reported_at`.

**Invoke the `superpowers:using-git-worktrees` skill** for an isolated workspace on `fix/$ARGUMENTS`, branched from `pre-dev`. Fall back to `git switch -c fix/$ARGUMENTS pre-dev` if it declines.

Update `docs/STATE.md` and `docs/tickets/_active.md` so a `/handoff` mid-fix has something true to hand off.

---

## Step 4 — Reproduce it. This is not optional.

**Invoke the `superpowers:systematic-debugging` skill.** Its iron law governs everything from here:

> NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.

Reproduce the bug consistently, on this branch, before you theorise about it. Record the exact steps in the ticket's `## Reproduction`.

**If you cannot reproduce it, stop.** Say so plainly, set `reproduced: false`, and go back to the user with what you tried. A fix for a bug you never saw is a guess wearing a commit message. Ask for the missing condition — the input shape, the model response, the search result — rather than fixing something plausible and hoping.

---

## Step 5 — Trace it to the root cause

Still inside `systematic-debugging`. Work backward from the symptom to the source:

- Read the error or transcript **completely**. It usually names the agent or tool. People skim past it and go looking.
- Instrument every specialist boundary the data crosses — print the actual `output_key` value at each hop, do not reason about what it "must be".
- Trace the data backward until you find the first place it is wrong. That place is the root cause. Everything downstream of it is a symptom, including the specialist the error surfaced in.
- Find a working example in this codebase — a sibling specialist that handles the same shape of failure correctly — and list every difference. That list usually contains the answer.

One hypothesis at a time. One variable at a time. **Never stack fixes.** If a hypothesis fails, you get a new hypothesis, not an additional change.

**If three fixes have failed: stop.** Do not attempt a fourth. Record the failed hypotheses in the ticket's `## Delays & Blockers` and bring it back to the user — at three, the problem is the design, and no amount of poking at the code will reveal that.

---

## Step 6 — HARD STOP. Confirm the diagnosis before writing anything.

**Write no code until the user confirms this section.** Not a test, not a stub, not "just trying something".

Fill the ticket's `## Root Cause` and `## Blast Radius`, then present:

```
BUG-XXX — DIAGNOSIS

Symptom:      {one sentence, the user's words}
Root cause:   {path}:{line} — {function}
Why:          {the causal chain, traced. not "probably".}
Evidence:     {what you observed that proves it}

Blast radius — every caller of {function}:
  {path}:{line}   also broken · covered by this fix
  {path}:{line}   not broken   · {why not}
  Patching only the reported path would leave broken: {list, or "nothing"}

Proposed fix:  {one paragraph}
Rejected:      {the symptom-level patch you are NOT doing, and why}

Confirm this diagnosis before I write the fix.
```

**Grep every caller before you write this.** This is the whole reason the step exists — every specialist that reads a shared `output_key` or calls a shared tool function is a caller. A bug report names one broken path; the root cause usually breaks several, and the callers nobody reported are the ones that bite in three weeks. One guard in the shared function is both the smaller diff *and* the one that fixes the siblings — the lazy fix and the correct fix are the same fix, and they are both at the root.

If the user pushes back on the diagnosis, that is a new hypothesis, not a debate. Go back to Step 5.

---

## Step 7 — Write the failing test first

**Invoke the `superpowers:test-driven-development` skill.**

> NO PRODUCTION CODE WITHOUT A FAILING TEST FIRST.

The regression test comes before the fix. Always. It must:
- reproduce the reported symptom — the actual symptom, not a convenient proxy for it,
- fail against the **unfixed** code, and
- fail **for the right reason** — read the failure output and confirm it's the bug, not a typo in your test.

```bash
.venv/bin/python test_agent.py    # observe the failure. Confirm the failure message is the bug.
```

Record its function name in the ticket's `## Regression Test`.

If the test passes against the unfixed code, you have not reproduced the bug — you have written a test for something else. Go back to Step 4.

---

## Step 8 — Fix it, at the root, minimally

Now write the fix, at the root cause identified in Step 6.

**Ponytail governs the diff.** The smallest change that fixes the *cause*:
- Fix it once, in the shared prompt/tool/state contract every caller routes through — not once per specialist.
- Do not refactor the surrounding code because you're in there. A bug fix that also restructures a module is two changes, and if it breaks, nobody knows which one did it.
- Do not add a dependency. Do not add a new specialist. Do not "harden" adjacent code you weren't asked about.
- If you cut a corner deliberately, mark it: `# ponytail: {ceiling}, {upgrade trigger}`.

Never lazy about: the built-in/function-tool separation, the `NO_INVENTION`/`REAL_PEOPLE_RULES` guarantees. If the bug *is* one of those, the fix is not the minimum that makes the test pass — it's the one that closes the class of bug.

```bash
.venv/bin/python test_agent.py    # observe GREEN, and the whole suite, and a pristine output.
```

---

## Step 9 — Prove the red-green

**Invoke the `superpowers:verification-before-completion` skill.**

A regression test earns its name only if you have watched it fail. Revert the fix, run the test, watch it go red, restore the fix, watch it go green. Do it now, in this message, and paste both outputs.

```bash
git stash            # revert the fix
.venv/bin/python test_agent.py    # must show the failure — this is the proof
git stash pop        # restore it
.venv/bin/python test_agent.py    # must show "all checks passed"
```

Tick all three boxes in the ticket's `## Regression Test`. An unproven regression test is a test that will silently stop testing anything the moment someone refactors past it.

There is no lint or typecheck configured for this project — do not claim either passed.

Fill the ticket's `## Verification Log` with what you actually observed.

---

## Step 10 — Review

**Invoke the `superpowers:requesting-code-review` skill** over `BASE_SHA..HEAD_SHA` — the `code-reviewer` agent is the reviewer. Give it the diagnosis, not just the diff: a reviewer who doesn't know the root cause can only review the syntax.

Then **invoke the `superpowers:receiving-code-review` skill** to act on it. Verify each finding against the code before implementing it. Push back with reasoning where warranted. State the fix; don't thank the reviewer.

Ask the reviewer specifically: **does this fix the cause, or does it hide the symptom?** That is the failure mode of every bug fix, and it is invisible in a green test run.

---

## Step 11 — Commit and hand off

```bash
git add -A && git commit -m "fix($ARGUMENTS): {what broke, in the user's terms} (BUG-XXX)"
```

Set ticket `status: READY_FOR_REVIEW`, `fixed_by`, `fixed_at`. Update `docs/STATE.md`.

Report:

```
BUG-XXX FIXED
Symptom:      {one sentence}
Root cause:   {path}:{line}
Fix:          {one line} · {n} files, {+a}/{-d}
Regression:   {test name} — red-green proven
Also fixed:   {sibling call sites the root-cause fix covered, or "none"}
Suite:        {actual output}

Next: /complete-feature $ARGUMENTS
```

Then run **`/complete-feature $ARGUMENTS`** to ship it. The gates are the same for a fix as for a feature — evidence, both review lenses, shortcuts harvested, PR opened against `pre-dev`. A one-line fix that skips the gates is exactly how the next bug gets in.

---

## Notes for Claude

- A bug report is a symptom. Your first job is to disbelieve every explanation in it — including the reporter's, including your own first one.
- Reproduce before you diagnose. Diagnose before you fix. Confirm before you code. Test before you fix. There are no small bugs that earn an exemption from this; "it's a one-liner" is the sentence people say right before they patch the wrong line.
- Grep the callers. Every time. The reported path is one of several, more often than not.
- If you cannot reproduce it, say so and stop. Do not ship a plausible fix for an unobserved bug.
- Three failed fixes means stop, not fix number four.
