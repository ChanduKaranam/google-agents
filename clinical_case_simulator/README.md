# Clinical Case Simulator

A grounded AI virtual patient that lets medical students practise history-taking
and clinical reasoning, then evaluates **how they thought** — not just whether
they got the diagnosis right.

Built as a Google ADK agent, runnable locally and deployable to Cloud Run for
use through Gemini Enterprise. Implements the V1 MVP described in
`Clinical_Case_Simulator_Research.md`: Internal Medicine, text-based, expert-
reviewable case bank, deterministic scoring.

```
Start case → History → Examination → Investigations → Differential
          → Discriminating plan → Final diagnosis → Performance report
```

---

## Quick start

```bash
cp .env.example .env          # add a Gemini API key, or switch to Vertex AI
./run_local.sh                # ADK dev UI at http://localhost:8000
```

Pick **clinical_simulator** in the agent dropdown and type *"list the beginner
cases"*.

No browser:

```bash
.venv/bin/python -m clinical_simulator.console          # play in the terminal
.venv/bin/python -m clinical_simulator.console --smoke  # scripted end-to-end run
```

Checks:

```bash
.venv/bin/python -m pytest -q                  # 37 tests
.venv/bin/python -m clinical_simulator.validate  # case-bank linter
```

---

## The design decision everything rests on

The research flags clinical inaccuracy and answer-dumping as the two failure
modes that sink AI virtual patients. Both are addressed structurally rather
than by asking the model nicely.

**No component that talks to the student knows the diagnosis.**

| Component | Sees | Never sees |
|---|---|---|
| Simulator agent (the preceptor) | nothing but tool results | the case file, any diagnosis |
| Patient agent | `case.patient_view()` — lay-language history only | examination findings, results, differentials, rubric, hints |
| Tools | the full case file | — |
| Evaluator agent | a scorecard Python already computed, plus the transcript | authority to change a mark |

The simulator cannot leak an answer it was never given, and the patient cannot
describe a test result it has never seen. `tests/test_prompt_isolation.py`
asserts this against every case in the bank, and
`python -m clinical_simulator.validate` fails the build if a case file lets the
patient say the diagnosis out loud.

Scores are computed in `evaluation/scorer.py` — a pure function of the case
rubric and the transcript. The model writes the prose around numbers it cannot
alter. That is what stops the "overly agreeable AI" problem from turning into
grade inflation.

---

## What the student can do

| Action | Tool | Behaviour |
|---|---|---|
| Ask the patient anything | `ask_patient` | Replies in character, in lay language, answering only what was asked |
| Examine | `perform_examination` | Returns the authored finding, or refuses. Handles "auscultate the chest and percuss it" |
| Order tests | `order_investigation` | Returns the authored result, or says it is unavailable. Handles "CBC, CRP and blood culture" |
| Commit a differential | `submit_differential` | Records diagnoses *and* the reason for each. No feedback on correctness |
| Say how they would discriminate | `submit_discriminating_plan` | The step that separates reasoning from list-making |
| Commit an answer | `submit_final_diagnosis` | Still no correctness feedback |
| Ask for help | `give_hint` | Three authored levels, each costing marks |
| Give up | `reveal_answer` | Requires explicit confirmation; caps the score at 60% |
| Be marked | `clinical_evaluator` | Full performance report |
| Explain themselves | `record_metacognition` | "You asked about smoking — why?" |

Practice Mode is on by default: the agent will not confirm, deny or hint at the
diagnosis mid-case, however the question is phrased.

---

## The case bank

Eight expert-reviewable Internal Medicine cases across the four difficulty
levels, in `clinical_simulator/cases/data/*.json`.

| ID | Level | Presentation | Teaches |
|---|:--:|---|---|
| IM-001 | 1 | Fever and cough, 42M | Signs of consolidation; excluding TB in an endemic setting |
| IM-002 | 2 | Central chest discomfort, 54M | Structured chest-pain assessment; ECG and serial troponin |
| IM-003 | 2 | Severe epigastric pain, 38M | Pancreatitis criteria; the surgical and cardiac mimics |
| IM-007 | 2 | Thirst, weight loss, vomiting, 19M | DKA; bedside glucose in every unwell patient |
| IM-008 | 2 | Tiredness with Hb 7.8, 58M | Anaemia is a finding, not a diagnosis; when a plausible cause is a trap |
| IM-004 | 3 | Chest tightness in an anxious 29F | Anchoring and premature closure; PE in a patient who says it's panic |
| IM-005 | 3 | Eight days of fever, 24F | Undifferentiated tropical fever; why the Widal test is not an answer |
| IM-006 | 4 | Confusion and falls, 76F | Incomplete history, evolving case, collateral-seeking, hyponatraemia |

Every case carries a rubric with per-item weights, criticality flags and a
teaching note that becomes the student's feedback when the item is missed.

**All eight are marked `provenance.status: "draft"`.** They were written for
this build and have not been reviewed by a clinician. The validator reports
`0/8 cleared for student assessment` by design, and will keep saying so until a
qualified medical educator reviews each case and sets the field. Do not put
these in front of students for assessment before that happens.

Adding a case is a JSON file — see `docs/case-authoring.md` and
`clinical_simulator/cases/data/_template.json`.

---

## Deploying to Gemini Enterprise

Gemini Enterprise does not register an arbitrary HTTP endpoint — a raw
`adk api_server` URL is not a registerable agent. There are two supported
routes and both are wired up here.

```bash
# A — Agent Runtime (simpler): register by resource path, no agent card
PROJECT=your-project ./deploy_agent_engine.sh

# B — A2A on Cloud Run: serves /.well-known/agent-card.json, register the card
PROJECT=your-project ./deploy.sh
python -m clinical_simulator.agent_card https://<service-url>
```

Both scripts validate the case bank before deploying. The A2A interface
(`clinical_simulator/a2a_app.py`) has been verified locally end to end —
the card serves, and a JSON-RPC `message/send` drives a real encounter.
The scripts themselves have not been run against a live project, and no
Gemini Enterprise registration has been performed. `docs/gemini-enterprise.md`
sets out exactly what was verified and what was not.

---

## Layout

```
clinical_simulator/
├── agent.py            root agent — knows no case content
├── agents.py           patient and evaluator sub-agents, wrapped as tools
├── prompts.py          the two prompts, built from different slices of the case
├── session.py          encounter state
├── console.py          terminal client and smoke test
├── validate.py         case-bank linter (leakage, markability, provenance)
├── a2a_app.py          A2A interface — what Gemini Enterprise talks to
├── agent_card.py       curated agent card for registration
├── cases/
│   ├── schema.py       the hidden case state, and patient_view()
│   ├── matching.py     deterministic request matching
│   └── data/*.json     the case bank
├── evaluation/
│   ├── rubric.py       weights and heuristics
│   └── scorer.py       the deterministic scorer
└── tools/              what the student can actually do
docs/                   architecture, authoring, scoring, deployment, roadmap
tests/                  32 tests, including the prompt-isolation guarantees
```

---

## Educational use only

This is a simulation for training clinical reasoning. It is not a diagnostic
tool, and nothing it produces is clinical advice about a real person.
