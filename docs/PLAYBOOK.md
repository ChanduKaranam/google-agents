# Job Helper Agent — Developer Playbook

> **Loaded on demand.** Claude does NOT auto-load this file. Human devs read it. Claude reads `CLAUDE.md`.

## 1. What this is

This playbook describes how humans and Claude collaborate to ship features in Job Helper Agent. The short version: Claude is your pair programmer; tickets are the contract between you; the pipeline is enforced by hooks.

## 2. The mental model

1. **Tickets are the design artifact.** Before code, there's a ticket. Before a ticket is built, it's approved. The ticket carries the design *and* the implementation plan — `/build-ticket` executes that plan literally, so a vague plan becomes a vague feature.
2. **Claude does the build; you do the decisions.** Claude writes code, commits, manages state. You answer the interview questions, approve designs, and merge PRs.
3. **The hook system is your guardrail.** You can't accidentally push to `main`. The system prevents the costly mistakes.
4. **The commands don't improvise a process — they run one.** Design is `superpowers:brainstorming` plus `grilling`. Planning is `superpowers:writing-plans`. Building is `superpowers:test-driven-development` (no production code without a failing test first). Shipping is `superpowers:verification-before-completion` (no claim without evidence you produced in that message). Ponytail runs across all of it: the laziest thing that actually works, and nothing built for a future nobody asked for.

## 3. Your toolkit

| Tool | Purpose | How to invoke |
|------|---------|---------------|
| `/new-feature {slug}` | Start a feature (interview → ticket) | Type in Claude |
| `/groom-ticket {id}` | Deep-design a ticket | Type in Claude |
| `/review-ticket {id}` | Lead-only. Approve or request changes on a groomed ticket | Type in Claude |
| `/claim-ticket {id}` | Pick up an approved ticket | Type in Claude |
| `/build-ticket {slug}` | **Write the code.** Executes the ticket's Implementation Plan under TDD | Type in Claude |
| `/fix-bug {slug}` | Something shipped is broken. Reproduce → root cause → your confirmation → test-first fix | Type in Claude |
| `/complete-feature {slug}` | Pre-merge gate + PR | Type in Claude |
| `/handoff` | Save state and pause | Type in Claude |
| `/resume-session` | Restore context and continue | Type in Claude |

There is no `/ui-fix` command — this project has no frontend surface. There are no `/dev-deploy`/`/prod-deploy` commands either: deployment is the `adk deploy` CLI flow, already fully documented step-by-step in `DEPLOYING_ADK_AGENTS.md`.

## 4. The end-to-end workflow

**Day 1 (design):**
1. `git switch pre-dev && git pull`
2. `/new-feature {slug}` — answer the interview, get a ticket.
3. `/groom-ticket {id}` — deep design: agent walkthrough, session-state contract, tool contracts, test plan, risks (grilled).
4. `/review-ticket {id}` — a lead approves or requests changes.

**Day 2 (build):**
1. `/claim-ticket {id}` (or continue from yesterday's context with `--continue`)
2. `/build-ticket {slug}` — this is where code gets written. It sets up an isolated workspace, takes a clean test baseline, then walks the ticket's Implementation Plan task by task: **failing test → verify it's red → minimal code → verify it's green → commit**, with a code review after each task. If something breaks it stops and finds the root cause rather than stacking fixes; if three fixes have failed it stops and tells you the design is wrong.

   You will be offered two execution modes. Subagent-driven (a fresh agent per task) is the default and usually the right call; inline keeps everything in your session if you want to watch closely.
3. Pausing mid-build: `/handoff` runs the tests before writing down what's done, so the state file is true rather than optimistic. `/resume-session` picks it back up — and if there were blockers, it debugs them first instead of routing around them.

**Day 3 (ship):**
1. `/complete-feature {slug}` — every gate here demands the command output that proves it, in the message that claims it. Two reviews run on the diff: `code-reviewer` for correctness (including the real-people-safety and ADK structural-invariant checks), `ponytail-review` for what should simply be deleted. Then the PR opens against `pre-dev`.
2. Lead reviews PR → merges to `pre-dev`.
3. When ready to deploy to Gemini Enterprise: follow `DEPLOYING_ADK_AGENTS.md` end to end (`adk deploy` → register the agent in the Gemini Enterprise console).

## 4b. When something breaks

`/fix-bug {slug}`. It does not go straight to the code, and that is deliberate:

1. **It grills the report.** One question at a time. What did you expect, what happened, the exact steps, every time or sometimes. It looks up whatever it can find itself (the parent ticket, when it last worked, whether a test covers that path) rather than asking you.
2. **It reproduces the bug before theorising about it.** If it can't reproduce it, it stops and tells you — rather than shipping a plausible fix for something nobody has seen.
3. **It traces the root cause, then stops.** You get the diagnosis, the evidence, and the *blast radius* — every caller of the broken function, and which of them the reported path never mentioned. Nothing gets written until you confirm it.
4. **The failing test comes before the fix.** It must fail against the unfixed code, for the right reason. Then the fix goes in at the root — once, where the callers route through, not once per caller.
5. **It proves the red-green**: reverts the fix, watches the test fail, restores it. A regression test you have never seen fail is not testing anything.

Then `/complete-feature` ships it through the same gates a feature gets. A one-line fix that skips the gates is how the next bug gets in.

## 4c. Joining the project

Identity is your **git email**. Claude runs `git config user.email` and looks it up in `docs/TEAM.md`. If it isn't in `leads:` or `devs:`, every ticket command refuses to run — it looks like the tooling is broken, but it isn't; it doesn't know who you are.

1. **Clone, and let the plugins load.** `.claude/settings.json` declares them; Claude Code offers to install on your first session here. Accept, restart.
2. **Get on the roster.** A lead adds you to `devs:` in `docs/TEAM.md`, or you add yourself and open a PR. Effective on merge.
3. **Check your email matches the roster exactly** — `git config user.email`. A work address in one and a personal one in the other is the most common way this fails.
4. **Read three files:** `CLAUDE.md` (the rules the code follows), this playbook (how the team works), `docs/tickets/_active.md` (what's in flight, and who has it).
5. **Take an APPROVED ticket:** `/claim-ticket {id}` → `/build-ticket {slug}`. Someone designed it and a lead approved it — the plan in the ticket is the contract. If it's wrong, say so and send it back to grooming rather than quietly building something else.

**Lead vs dev.** A lead can run `/review-ticket` and nobody else can; a lead's own tickets are auto-approved. A dev's ticket travels `TODO` → `/groom-ticket` → `GROOMED` → a lead's `/review-ticket` → `APPROVED` before it can be claimed. From `APPROVED` on, the pipeline is identical for both.

**Stepping up to lead:** move your entry from `devs:` to `leads:` in `docs/TEAM.md`, open a PR, have an existing lead merge it. You gain `/review-ticket` — and lose the safety net of someone else checking your designs, so grill your own tickets the way you'd grill theirs.

## 5. Commit message format

```
type(scope): description (TICKET-XXX) <= 72 chars

What changed, why it was needed.
Any follow-up tickets or gotchas.
```

Types: `feat` · `fix` · `chore` · `refactor` · `test` · `docs`

## 6. Where to ask for help

- Stuck on Claude behavior: check `CLAUDE.md` → "When you're stuck".
- Stuck on design: read the relevant skill (`/how-it-works` in Claude for skill docs).
- Stuck on team process: re-read this file and `docs/TEAM.md`.
- Stuck on deploying: `DEPLOYING_ADK_AGENTS.md` — including the WSL/gcloud auth trap.
