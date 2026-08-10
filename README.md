# MSBuddy (V2)

An AI application advisor for students planning a Master's degree abroad,
built on **Google ADK**. V2 is a conversational advisor — an adaptive
one-question-at-a-time interview, resume intelligence with provenance,
authority-gated research, and deterministic matching with financial and
career fit — on top of V1's core loop:

> tell MSBuddy about yourself → it builds your profile → researches real
> programs with sources → scores how well each fits you, deterministically.

## Architecture (V1)

```
                 root_agent (orchestrator, Gemini)
                 conversation · intent · narration
        ┌───────────────┼──────────────────────┐
        ▼               ▼                      ▼
  profile_agent      research_agent      deterministic tools
  resume_agent       (google_search      get/update_profile · get_interview_state
  (task-mode         only, harvests      convert_gpa · clear_profile
   extractors,        grounding)          save_research · get_programs
   write nothing)                         match_programs · get_next_steps
                          │
                          ▼
                  evidence ledger  ← what search ACTUALLY retrieved
                          │
                          ▼
              every claim graded: verified /
              partially_verified / unverified
```

Three rules carry the design:

1. **LLMs propose; code decides.** The extractor can't write state; the
   researcher can't store facts; the match score is pure Python.
2. **Evidence-first.** Every researched fact is graded against the search
   runtime's own record of what was retrieved, and stored with source
   domain, URL, type and timestamp. Unverified stays labeled unverified.
3. **Missing data is excluded, never punished** — and never invented.

## Install

Prereqs: Python 3.11–3.13 and [uv](https://docs.astral.sh/uv/).

```bash
cd Ms-Agent
uv sync --all-groups
```

## Configure

```bash
cp .env.example .env   # then edit
```

Either Vertex AI (`GOOGLE_GENAI_USE_ENTERPRISE=true` + `GOOGLE_CLOUD_PROJECT`
+ `GOOGLE_CLOUD_LOCATION=global`) or a `GEMINI_API_KEY`. On WSL with the
Windows gcloud, also export the ADC path in your shell:

```bash
export GOOGLE_APPLICATION_CREDENTIALS=/mnt/c/Users/<you>/AppData/Roaming/gcloud/application_default_credentials.json
```

## Run

```bash
uv run adk web . --port 8001
```

Open http://127.0.0.1:8001, pick **app**, and talk:

```
I'm a CSE graduate from Lendi with 8.2 CGPA. I want MS in Canada.
What do you know about my profile?
Research the MSc Computer Science at the University of Toronto.
How well do I fit it?
```

## Test

```bash
uv run pytest tests/unit tests/integration -q   # offline — always runs
uv run pytest tests/eval -q                     # live — needs a model backend
uv run ruff check . && uv run ruff format --check .
```

## Extend

- **New researched fact** → add the slot to `PROGRAM_FIELDS`
  (`app/models/program.py`); grading, storage and rendering follow.
- **New profile field** → add it to the section model in
  `app/models/student.py`; extraction, merge and gap-ranking follow.
- **Tune matching** → `MATCH_WEIGHTS` / thresholds in
  `app/config/settings.py`; the engine is `app/services/matching_service.py`.
- **New capability** → deterministic tool + a section in the root
  instruction. Add another LLM agent only if judgement is genuinely the job.

## Layout

```
app/
  agent.py            root orchestrator + search budget
  agents/             profile extractor · web researcher
  tools/              profile · university/research · matching tools
  models/             StudentProfile · Program/Evidence · MatchResult
  services/           merge/gaps · grounding/verification · match engine
  config/settings.py  models, weights, state keys, budgets
tests/
  unit/               models, services, engine (offline)
  integration/        structure + end-to-end tool flows (offline)
  eval/               live scenarios (skip without a backend)
```
