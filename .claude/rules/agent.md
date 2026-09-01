---
paths:
  - "Job_Helper_agent/**/*.py"
---

# Agent (Job_Helper_agent/**/*.py) rules

- A Gemini built-in tool (`google_search`, `url_context`) cannot share an `Agent` with custom function tools — ADK does not validate this at authoring time, it silently rewrites (`llm_agent.py:139-176`) and the request fails at the Gemini API, sometimes only in production. Each search-capable specialist holds exactly one built-in and nothing else. `test_agent.py` asserts this structurally — keep it passing.
- Specialists exchange data only through session state: each declares an `output_key`, and downstream agents read it with `{key?}` templating (the `?` yields empty string instead of raising when the key is absent). Do not invent a second data-passing channel.
- The orchestrator (`root_agent`) runs on `gemini-2.5-pro`; specialists run on `gemini-2.5-flash`. This split is empirically load-bearing (see `agent.py` comment, measured 2026-07-22) — flash orchestration silently drops turns. Don't downgrade the root model without re-running that walkthrough.
- Alumni/people-search agents must obey the `NO_INVENTION` and `REAL_PEOPLE_RULES` constants in `agent.py`: no person without a working, actually-found profile link; no gender guessing; no padding sparse lists with guesses. These are real named individuals, not suggestions — getting this wrong means a student contacts someone based on a false claim.
- No REST envelope, no Pydantic/validation library, no ORM — this is an ADK agent; tool I/O is plain Python type hints and state lives in ADK session state, matching `callbacks.py`.

- Detailed conventions: load the `testing-patterns` skill.
