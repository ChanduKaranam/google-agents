# MSBuddy — guide for coding agents

## Commands

```bash
uv sync --all-groups                             # install
uv run pytest tests/unit tests/integration -q    # offline suite (fast, no network)
uv run pytest tests/eval -q                      # live tests (need a model backend)
uv run ruff check . && uv run ruff format .      # lint + format
uv run adk web . --port 8001                     # local UI
```

## Non-negotiable design rules

1. **LLMs propose; deterministic code decides.** `profile_agent` extracts
   but cannot write; `research_agent` searches but cannot store;
   `match_programs` numbers come from `matching_service.py`, never a model.
2. **Every researched fact is graded** against the evidence ledger (what
   search actually retrieved) in `save_research`. Do not add any path into
   `STATE_KNOWLEDGE` that skips grading.
3. **`research_agent` holds `google_search` and nothing else.** A Gemini
   built-in tool cannot share an agent with function tools — the API
   rejects it, sometimes only in production. Structural tests enforce this.
4. **Prose before template** in the research agent's answers: grounding
   attribution is computed over prose; a template-only answer yields zero
   grounding and every claim grades unverified.
5. **Missing data is excluded from matching, never scored 0**, and no
   output may express an admission probability.
6. Models default to `gemini-2.5-flash` — measured: search grounding
   metadata is reliably returned there. Change via env, and re-verify
   grounding (`STATE_EVIDENCE` non-empty after a research turn) if you do.
7. Greetings/identity questions are answered with **no tools**; the
   evidence rules are scoped to institutions, not the assistant itself.
8. **Alumni are the strictest slice.** `save_alumni_findings` is the only
   path into the alumni store: 26-source allowlist (unknown domain =
   discarded, no fallback), name must appear in retrieved text from that
   domain, entity resolution splits namesakes on conflicting graduation
   years. Only admitted people may be named; aggregates always carry
   denominators; alumni presence is never an employment or admission
   guarantee.

## Adding things

| Change | Where |
|---|---|
| New program fact slot | `PROGRAM_FIELDS` in `app/models/program.py` |
| New profile field | Section model in `app/models/student.py` |
| Match weights/thresholds | `app/config/settings.py` |
| New deterministic capability | `app/tools/` + a root-instruction section |
| New search surface | New leaf agent + add to `RESEARCH_TOOL_NAMES` |
| New alumni source | `ALUMNI_SOURCES` in `app/alumni/source_registry.py` (keep it at the 26 approved categories) |
| New alumni fact field | `ALUMNI_FIELDS` in `app/alumni/models.py` — professional facts only |

Run the offline suite after every change; it is fast and it pins the
constraints above.
