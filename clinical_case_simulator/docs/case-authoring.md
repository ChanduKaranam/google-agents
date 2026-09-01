# Writing a case

A case is one JSON file in `clinical_simulator/cases/data/`. No Python. Copy
`_template.json`, rename it `IM-0NN.json`, and run the validator as you go:

```bash
python -m clinical_simulator.validate
```

It fails the build on leakage and on unmarkable rubrics, and warns about
everything else.

## The one rule

**The patient may know only what a patient would know.**

`Case.patient_view()` hands the patient agent exactly these fields:

- `patient`, `persona`, `chief_complaint`
- `history.*` — present illness, past medical, medications, allergies, family,
  social, review of systems

Everything else — `examination`, `investigations`, `differentials`,
`final_diagnosis`, `critical_clues`, `red_flags`, `rubric`, `hints`,
`teaching_points` — is invisible to the patient and reachable only through a
tool.

So write the history in the patient's voice, not the examiner's:

| Don't | Do |
|---|---|
| "Retrosternal chest pain radiating to the left arm" | "A heaviness in the middle of my chest. Sometimes it goes into my left arm." |
| "Not vaccinated against typhoid" | "Hasn't had any vaccinations since childhood that she remembers" |
| "No known diabetes" | "Nobody has ever told him he has a sugar problem" |

The validator catches diagnosis words that reach the patient's mouth, but it
cannot catch a history written in doctor-speak. That is what
`persona.speech_style` and a read-through are for.

## Fill in the negatives

`review_of_systems_negative` is the field new authors skip and then wonder why
the patient improvises. Students ask about things you did not anticipate; an
explicit negative gives the patient something true to say. List the negatives
that matter for every diagnosis on your differential, not just the correct one.

`persona.knows_not` does the same job for facts a patient genuinely could not
have: their own creatinine, the name of their tablet, whether they hit their
head.

## Aliases decide whether the student gets a result

Every examination and investigation needs an `aliases` list covering every way
a student might phrase the request — abbreviations, British and American
spellings, Indian usage.

```json
{
  "id": "cbc",
  "label": "Complete blood count",
  "aliases": ["cbc", "complete blood count", "full blood count", "fbc",
              "hemogram", "haemogram", "wbc", "blood counts"],
  "tier": "first-line",
  "result": "Hb 13.4 g/dL. Total WBC 18,600/uL with 86% neutrophils. Platelets 265,000/uL."
}
```

Write `result` the way a report reads. Never interpret it — no "consistent
with pneumonia". Interpretation is the student's job and the report is where
they get told whether they did it well.

Set `appropriate: false` with a `note` for tests that are low-yield or
premature. The student still gets the result — real life gives you the result —
but investigation selection is marked down and the `note` explains why. This is
how the simulator teaches ordering discipline rather than just retrieval.

## The rubric is the marking scheme

Each item is one thing a competent student would have done.

```json
{
  "id": "h_alcohol",
  "label": "Alcohol history, quantified",
  "keywords": ["alcohol", "drink", "drinking", "how much", "how often", "binge"],
  "weight": 4,
  "critical": true,
  "teaching_note": "Alcohol and gallstones cause 80% of acute pancreatitis. Asking 'do you drink?' is not enough — quantity, frequency and duration all matter."
}
```

- `weight` — relative importance within its section. Use 1 to 5.
- `critical` — missing it compounds a 15% penalty on that skill. Reserve it for
  omissions that would be unsafe, not merely incomplete. Three or four per case.
- `keywords` — phrases that count as having asked. Include the colloquial forms
  ("does it spread anywhere" as well as "radiate"). Avoid words that appear in
  ordinary conversation; the validator warns about those.
- `teaching_note` — what the student reads when they miss it. Say why it
  mattered *in this case*, in one sentence.

Every investigation rubric item should correspond to an investigation the case
can actually result — otherwise the student is being marked on something they
cannot do. The validator warns when it does not.

## Differentials

```json
{"dx": "Aortic dissection", "status": "must-exclude", "aliases": ["dissection"], "why": "..."}
```

- `correct` — the answer. At least one is required. Multiple when the full
  answer has two parts, e.g. iron deficiency anaemia **and** the colorectal
  cancer causing it.
- `must-exclude` — dangerous alternatives that a safe student names even when
  they are unlikely. Worth 30% of the differential score. **These require an
  `excluded_by` list**: the ids of examinations or investigations in this case
  that let a student actually act on the diagnosis.

  ```json
  {"dx": "Pulmonary embolism", "status": "must-exclude",
   "aliases": ["pe", "embolus"],
   "excluded_by": ["legs", "abg", "ddimer"],
   "why": "..."}
  ```

  The validator fails the build if a must-exclude has no `excluded_by`, or if it
  names a finding the case does not define. This exists because IM-001 shipped
  asking students to exclude pulmonary embolism while defining no lower-limb
  examination — so a student doing exactly what the case asked lost marks for the
  author's omission. If you cannot give the student a way to act on a diagnosis,
  downgrade it to `plausible`.
- `plausible` — reasonable alternatives that earn credit.
- `incorrect` — common wrong answers, so the report can address them by name.

## Critical clues

`critical_clues` are matched against the student's own reasoning text, so use
short lowercase **stems**: `"radiat"` catches radiates, radiating and
radiation; `"radiating"` would not catch "radiates". Keep them to findings that
genuinely discriminate.

## Hints must not name the answer

Three levels, each more directive, none containing the diagnosis. The validator
fails the build if a hint contains a diagnosis term that is not already in the
opening brief.

1. Point at an area of the case. *"Compare her pulse rate with her temperature."*
2. Name the pattern or mechanism. *"What produces dullness, bronchial breathing and increased vocal resonance together?"*
3. Name the topic to go and read. *"Review the approach to acute undifferentiated fever in the tropics."*

## Level 4: evolving cases

`evolution` entries fire on a turn count or after a specific examination or
investigation, and hand the preceptor an event to relay.

```json
{"id": "daughter_arrives", "after_turn": 12,
 "update": "EVENT: The patient's daughter arrives with a bag of medicines..."}
```

Note that evolution *delivers* information; it does not gate it. In IM-006 the
collateral history is reachable from the start for a student who thinks to ask
for it, and arrives unprompted at turn 12 for one who does not. That is
deliberate — seeking collateral history in a confused patient is the correct
behaviour and should be rewarded, not blocked.

## Provenance

```json
"provenance": {
  "author": "Dr X",
  "reviewed_by": "Dr Y, Professor of Medicine",
  "review_date": "2026-08-20",
  "status": "expert-reviewed",
  "references": ["Guideline the content is grounded in"]
}
```

`status` stays `draft` until a qualified medical educator has read the case and
the rubric. The validator reports how many cases are cleared, and every case
shipped in this repository is currently `draft`.

## Before you commit

```bash
python -m clinical_simulator.validate   # must exit 0
python -m pytest tests -q               # must pass
python -m clinical_simulator.console    # then actually play the case
```

Playing it is not optional. Ask the awkward questions a student would, and see
whether the patient stays in character and stays consistent.
