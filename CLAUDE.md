# Job Helper Agent — Claude Operating Manual

> **Loaded every session.** Keep short. Anything you can derive from code, git, or skills does NOT belong here.

## Project

**Job Helper Agent** — an 8-specialist Google ADK agent (orchestrator + specialists, wired with `AgentTool`) that helps students turn a resume into a shortlist, alumni contacts, and a tracked application pipeline. Deployed to Gemini Enterprise. See `docs/superpowers/specs/2026-07-22-placement-intelligence-agent-design.md` for the original design spec and `DEPLOYING_ADK_AGENTS.md` for the deploy path.

## Stack

| Layer | Tech | Path |
|-------|------|------|
| Agent | Python 3.12, `google-adk==2.4.0` | `Job_Helper_agent/` |
| Orchestrator + specialists | `Agent`, `AgentTool` | `Job_Helper_agent/agent.py` |
| Function tools | plain Python | `Job_Helper_agent/tools.py`, `fetch.py`, `links.py`, `verify.py` |
| Callbacks (session memory, user checks) | plain Python | `Job_Helper_agent/callbacks.py` |
| Tests | structural, no network | `test_agent.py` |

## Commands cheat sheet

```bash
.venv/bin/python test_agent.py         # run the structural test suite
pip install -r Job_Helper_agent/requirements.txt
adk web                                 # local interactive test UI
adk deploy agent_engine ...             # see DEPLOYING_ADK_AGENTS.md for the full flow
```

## Branch model

`pre-dev` is the source-of-truth working branch. Feature/fix branches come off `pre-dev`, not `main`, and merge back into `pre-dev` once tested and working. `main` is protected — no direct edits, no PRs target it from this pipeline.

## Process — non-negotiable

The slash commands run this chain. Do not improvise around it.

**Design** (`/new-feature` → `/groom-ticket` → `/review-ticket`): `superpowers:brainstorming` for the design, `grilling` for the risk round — one question at a time. No code during design, not even a stub.
**Plan**: `superpowers:writing-plans` writes the ticket's `## Implementation Plan`. No TBDs — an unfilled step is a plan failure.
**Build** (`/build-ticket`): `superpowers:test-driven-development`. **No production code without a failing test first.** Code written before its test gets deleted, not adapted. Anything breaks → `superpowers:systematic-debugging`: no fix without root cause, and three failed fixes means stop and question the design.
**Fix** (`/fix-bug`): a bug report is a symptom, not a cause. Reproduce it, trace the root cause, **stop and get the diagnosis confirmed before writing anything**, then failing-test-first and fix at the root — once, where the callers route through. Grep every caller: the reported path is rarely the only broken one.
**Ship** (`/complete-feature`): `superpowers:verification-before-completion`. **No completion claim without fresh evidence** — if you did not run the command in this message, you cannot say it passes.

**Ponytail is active.** Before writing anything, climb the ladder: does this need to exist at all → is it already in this codebase (grep first) → stdlib → native platform feature → an already-installed dependency → one line → only then, the minimum code that works. Deliberate corner-cuts get a `# ponytail:` comment naming the ceiling and the upgrade trigger.

Never lazy about: the built-in/function-tool separation, the `NO_INVENTION`/`REAL_PEOPLE_RULES` guarantees, error handling that prevents silent data loss, or anything explicitly asked for.

## Code rules — non-negotiable

1. A Gemini built-in tool (`google_search`, `url_context`) never shares an `Agent` with a custom function tool. ADK does not validate this — it silently rewrites and the request fails at the Gemini API, sometimes only in production. `test_agent.py` asserts this structurally; keep it passing.
2. Specialists exchange data only through session state: an `output_key` on the producer, `{key?}` templating on the reader. No second data-passing channel.
3. The root orchestrator runs `gemini-2.5-pro`; specialists run `gemini-2.5-flash`. This split is empirically load-bearing (see `agent.py`, measured 2026-07-22) — don't downgrade the root without re-verifying.
4. Any agent surfacing named individuals (alumni, contacts) obeys `NO_INVENTION`/`REAL_PEOPLE_RULES` in `agent.py` verbatim: no person without a found link, no gender guessing, no padding thin lists.
5. No REST envelope, no Pydantic, no ORM — tool I/O is plain Python type hints; state is ADK session state via `callbacks.py`.
6. Fetches respect the existing domain blocks (e.g. LinkedIn) in `fetch.py`/`links.py` — don't add a new fetch path that bypasses them.

## Domain map

| Domain | Module | Status |
|--------|--------|--------|
| Profile extraction | `profile_agent` (`agent.py`) | Shipped |
| Company matching | `company_agent`, `matching_agent` | Shipped |
| Alumni/contact search | `alumni_agent`, `links.py` | Shipped |
| Link verification | `verification_agent`, `verify.py` | Shipped |
| Resume gap analysis | `resume_gap_agent` | Shipped |
| Outreach drafting | `outreach_agent` | Shipped |
| Application tracking | `tracker_agent`, `tools.py` | Shipped |
| Coaching | `coach_agent` | Shipped |

## Available agents

code-reviewer

## Available skills

grilling · testing-patterns

## Slash commands

- `/new-feature {slug}` — start a feature (interview → ticket)
- `/groom-ticket {id}` — deep-design a ticket
- `/review-ticket {id}` — lead-only: approve or request changes
- `/claim-ticket {id}` — pick up an approved ticket
- `/build-ticket {slug}` — write the code, TDD, task by task
- `/fix-bug {slug}` — reproduce → root cause → confirm → test-first fix
- `/complete-feature {slug}` — verification gates + PR
- `/handoff` — save state and pause
- `/resume-session` — restore context and continue

Team pipeline: a dev's ticket travels `TODO` → `/groom-ticket` → `GROOMED` → a lead's `/review-ticket` → `APPROVED` before `/claim-ticket`. A lead's own tickets from `/new-feature` are auto-approved.

## Before starting any work

1. Read `docs/STATE.md` — what's the active session?
2. Read `docs/tickets/_active.md` — who owns what?
3. `git status` + `git log --oneline -5` — confirm clean state.
4. `.venv/bin/python test_agent.py` — confirm the baseline is green before touching anything.

## When you're stuck or context is full

- `/clear` between unrelated tasks.
- `Esc-Esc` or `/rewind` to undo a misstep.
- Use a subagent (`> use the code-reviewer agent to ...`) to investigate without polluting your context.
