---
name: testing-patterns
description: Use when writing tests for Job Helper Agent. Covers the structural, no-network test style, file placement, and the test plan requirements per ticket.
---
# Testing Patterns — Job Helper Agent

## Test taxonomy

| Layer | Framework | Location | When required |
|-------|-----------|----------|---------------|
| Structural (no network, no LLM calls) | `unittest`-style assertions, run via `.venv/bin/python test_agent.py` or `pytest` | `test_agent.py` | Always, for any change to agent/tool wiring |

There is no integration or E2E layer today — the agent talks to live Gemini APIs and Google Search, which structural tests deliberately avoid. If a future ticket adds a mocked-LLM integration layer, record the new location here.

## Test-first rule

For any new specialist, tool, or wiring change: write the structural assertion in `test_agent.py` **before** the implementation. This is non-negotiable — it forces clarity on the contract (built-in vs. function tool, `output_key` name) before any code exists.

## File placement

- All tests: `test_agent.py` (single file, top-level) — new checks are added as new `test_*` functions, following the existing `ok`/failure-print pattern.

## What to test

- **Structural invariants** — no agent mixes a Gemini built-in tool with function tools (`test_no_agent_mixes_builtin_and_function_tools`).
- **Output-key contract** — every specialist's declared `output_key` matches what downstream agents expect to read (`test_output_keys_match_the_spec`).
- **Root wiring** — the orchestrator holds all specialists plus its own infrastructure tools (`test_root_has_all_specialists_plus_infrastructure_tools`).
- **Tool behavior with fixtures** — pure-Python tools like `track_application`/`list_applications` get direct unit assertions, no mocking needed since they don't call out to a network.
- **Guardrails** — anything that blocks a known failure mode (e.g. `test_no_agent_can_fetch_linkedin`) gets its own test so a future refactor can't silently reintroduce it.

## What NOT to test

- Live Gemini/Search API calls — no network in this suite, by design (see `test_agent.py` docstring).
- ADK framework internals — trust `Agent`/`AgentTool` construction; test only this project's wiring on top of them.
- Prompt wording verbatim — test behavior/structure (which tools, which output keys), not exact prompt strings, which will drift.

## Test plan in tickets

The `## Test Plan` section in every ticket lists the new `test_*` function(s) to add to `test_agent.py`, or `N/A — {reason}`. `/complete-feature` enforces that `.venv/bin/python test_agent.py` passes (all `ok` lines, no failures) before the PR opens.
