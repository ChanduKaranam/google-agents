# Architecture

## The shape of it

```
                        Student
                           │
                           ▼
              ┌────────────────────────┐
              │  clinical_case_simulator│   root LlmAgent — the preceptor.
              │        (root agent)     │   Knows NO case content.
              └────────────┬───────────┘
                           │ tools
        ┌──────────────────┼──────────────────┬─────────────────┐
        ▼                  ▼                  ▼                 ▼
   ask_patient      perform_examination   submit_*        clinical_evaluator
  (AgentTool)        order_investigation  give_hint        (AgentTool)
        │                  │              reveal_answer          │
        ▼                  ▼                  │                  ▼
  patient LlmAgent    case file lookup    session state    scorer.py (pure Python)
  sees patient_view() (gated, no          (ADK state)      then LlmAgent narrates
  only                 invention)                          a scorecard it cannot change
                           │
                           ▼
              clinical_simulator/cases/data/*.json
              (the approved case bank — the grounding layer)
```

The research doc's MVP prescription was *"1 ADK agent + structured case data +
RAG + evaluation logic"*. This is that, with two narrow sub-agents where a
single agent would have had to hold contradictory knowledge in one context.

## Why the patient is a separate agent

A single agent playing both preceptor and patient would need the whole case in
its context to answer history questions — including the diagnosis, the
examination findings and the rubric. Every instruction telling it not to reveal
those would be a request, not a guarantee, and would be one clever student
prompt away from failing.

Splitting them makes the guarantee structural:

- `patient_agent`'s instruction is built by `prompts.patient_instruction()`
  from `Case.patient_view()`, which returns lay-language history only.
- The root agent's instruction (`prompts.SIMULATOR_INSTRUCTION`) contains no
  case content whatsoever. Everything it can say about the case came back from
  a tool call in this session.

`tests/test_prompt_isolation.py` asserts both properties over the whole bank.

## Conversational memory

`AgentTool` runs its sub-agent in a fresh child session on every call, so the
patient would otherwise have amnesia between questions — one of the specific
failure modes the research flags. `PatientTool` (in `agents.py`) subclasses it:
it appends the question to `state["enc"]["questions_asked"]` before delegating,
and the reply to `patient_replies` afterwards. The patient's instruction then
carries the last 25 exchanges verbatim, so it stays consistent with what it has
already said.

## Where the numbers come from

`EvaluatorTool` computes the scorecard with `score_encounter()` — a pure
function of the case rubric and the encounter state — stores it in session
state, and only then invokes the evaluator agent, whose instruction contains
that scorecard and the transcript and whose first rule is that the numbers are
fixed.

So the model:

- cannot award a mark the rubric does not support,
- cannot cite evidence the transcript does not contain,
- and cannot be talked into a better grade.

It is doing the one job LLMs are genuinely good at here: turning a structured
assessment into readable, specific, human feedback.

## Session state

One key, `enc`, in ADK session state. Visible in the ADK dev UI state
inspector, which makes debugging an encounter straightforward.

```
enc = {
  case_id, phase, turn,
  questions_asked[], patient_replies[],
  exams_requested[], investigations_ordered[],
  differential_submitted[], distinguishing_plan, final_diagnosis, final_reasoning,
  hints_used, revealed, metacognition[], evolution_fired[], scorecard
}
```

`phase` advances monotonically through `not_started → history → examination →
investigations → differential → final → evaluated`. It never moves backwards,
because a student may legitimately examine again after seeing a blood result.

## Request matching is deterministic

`cases/matching.py` resolves "sputum for AFB" to the AFB test and not to the
Gram stain, by scoring how much of the *request* each finding accounts for
rather than which alias matches first. Compound requests ("CBC, CRP and blood
culture") are split on conjunctions, but only when every fragment resolves
confidently on its own — so "sputum Gram stain and culture" is not torn in
half. Genuinely ambiguous requests return suggestions instead of a guess.

This is deliberately not an LLM call. Marks have to be reproducible and a
faculty reviewer has to be able to predict them from the case JSON alone.

## What is not here yet

- **RAG.** The research doc's architecture puts a retrieval layer between the
  approved sources and the agent. The case bank is currently the whole
  grounding layer: structured, reviewed JSON rather than retrieved text. That
  is the right MVP trade — retrieval adds a hallucination surface that
  structured case state does not have. RAG belongs at V2, over guidelines and
  faculty material, to support post-case teaching rather than the encounter.
- **Performance history.** Individual encounters persist (Agent Engine
  provides a managed session store, so a student can close the tab and resume),
  but nothing aggregates *across* encounters. There is still no student
  dashboard, weakness detection or cohort analytics — those are V3, and they
  need a datastore of scorecards, not just live sessions.
- **Authentication and per-student identity.** Cloud Run deploys with
  `--no-allow-unauthenticated`; identity currently comes from whatever calls
  it.
