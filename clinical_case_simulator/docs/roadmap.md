# Roadmap

Against sections 17–19 of the research doc.

## V1 — shipped here

| Requirement | Status |
|---|---|
| Internal Medicine, text-based | Done |
| 10–20 expert-reviewed cases | **8 cases, none clinically reviewed.** The gap below |
| Full workflow: history → examination → investigations → differential → final → evaluation | Done |
| Clinical reasoning, history-taking and communication scores | Done |
| Missed questions, differential analysis, investigation assessment | Done |
| Strengths, weaknesses, recommended revision | Done |
| Practice Mode | Done |
| Progressive hints | Done (V2 in the doc; cheap enough to include now) |
| Metacognitive follow-up | Done (V2 in the doc; one tool) |
| Progressive difficulty, levels 1–4 | Done — one level 1, four level 2, two level 3, one level 4 |

### The V1 gap

Two things stand between this and classroom use, and neither is code:

1. **Clinical review.** All eight cases are `provenance.status: "draft"`. Each
   needs a qualified medical educator to check the clinical content, the
   differential statuses and the rubric weights, then set the field. The
   validator reports the count every run.
2. **Case count.** Eight against a target of 10–20. The bank is skewed towards
   level 2; level 1 has a single case, which is the wrong shape for a student
   meeting the tool for the first time. Two or three more level 1 cases —
   uncomplicated UTI, uncomplicated hypertension, straightforward heart failure —
   would fix that faster than anything else.

## V2

Ordered by educational value per unit of work.

1. **A scorecard datastore.** Live encounters already persist on Agent Runtime,
   so resuming a case works today. What does not exist is a record of *finished*
   encounters — scorecards written somewhere durable and keyed by student.
   Everything in V3 depends on it, and it is the single change that turns a demo
   into a product.
2. **More cases, more specialties.** The case format is specialty-agnostic
   already; `specialty` is a field and `list_available_cases` filters on
   difficulty. Nothing but content stands in the way.
3. **Patient personality and affect.** `persona` exists and is used. Extending
   it — the angry patient, the patient who minimises, the patient with a
   relative who answers for them — is content, not code, and directly trains
   the communication skills the OSCE examines.
4. **RAG over guidelines**, for post-case teaching only. See
   `gemini-enterprise.md`.
5. **Adaptive difficulty.** Needs persistence first: pick the next case from
   the skill sub-scores rather than letting the student choose.
6. **Voice.** Highest perceived value, highest cost, and it changes the
   evaluation problem — spoken history-taking is assessed differently from
   typed. Worth doing only once the text experience is proven.
7. **OSCE-style timing and structure.** A time limit changes behaviour
   markedly; it should be a per-case flag, not a global mode.

## V3

The learning-platform layer, all of which requires persistence and none of
which requires a change to the agent:

- faculty case-authoring UI over the existing JSON schema and validator;
- student dashboard from stored scorecards;
- weakness detection from skill sub-scores across encounters;
- adaptive case recommendation;
- cohort analytics for faculty;
- longitudinal competency tracking.

The validator and the case schema were written with this in mind: a faculty
authoring tool is a form over `_template.json` plus `validate.py` as the
submit-time check.

## Deliberately not planned

- **Generating cases with an LLM at scale.** Section 10 of the research doc
  rules it out and it is right. Cases are the grounding layer; a generated case
  bank would make every downstream guarantee meaningless.
- **Letting the model score.** The numbers stay in Python.
- **Any clinical-decision-support framing.** This trains students. It does not
  advise on real patients, and the moment it appears to, it acquires a
  regulatory profile nobody wants.
