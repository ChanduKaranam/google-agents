# How marking works

The evaluation engine is the educational core of this product, so it is
deterministic, inspectable and reproducible. `evaluation/scorer.py` is a pure
function: same case, same transcript, same marks, every time
(`test_scores_are_reproducible`).

## The six skills

Weights are in `evaluation/rubric.py` and can be retuned without touching the
scoring code.

| Skill | Weight | Computed from |
|---|:--:|---|
| History taking | 20% | Weighted coverage of `rubric.history` against everything the student asked, with a compounding 15% penalty per missed **critical** item |
| Communication | 10% | Open-question ratio, empathy statements, sustained interview, minus unexplained jargon and multi-barrelled questions |
| Clinical reasoning | 25% | Critical clues used, red flags addressed, substance of the discriminating plan and the final reasoning, proportion of differentials given with a reason |
| Differential diagnosis | 20% | 50% leading diagnosis, 30% must-exclude diagnoses, 20% credible alternatives; scaled down for a list under three or a list without reasons |
| Investigation selection | 15% | Coverage of `rubric.investigations`, minus low-yield or premature tests, minus a blanket-ordering penalty |
| Case synthesis | 10% | Final diagnosis correct (55), examination coverage (25), substance of the final reasoning (20); partial credit if the right answer was on the differential but not chosen |

Overall is the weighted mean, then multiplied by a support factor:

| Support used | Multiplier |
|---|:--:|
| No hints | 1.00 |
| Hint 1 | 0.94 |
| Hint 2 | 0.86 |
| Hint 3 | 0.75 |
| Answer revealed | 0.60 |

Bands: 85+ Excellent, 70+ Good, 55+ Borderline, below Borderline Needs work.

## What "asking about X" means

Every rubric item carries `keywords`. The student is credited when any keyword
appears as a phrase in their questions. So the item is only as good as its
keyword list, and the validator warns about items with no keywords or with
keywords that would match ordinary speech.

```json
{
  "id": "h_radiation",
  "label": "Radiation of the pain",
  "keywords": ["radiate", "spread", "move anywhere", "go anywhere", "arm", "jaw"],
  "weight": 3,
  "critical": true,
  "teaching_note": "Radiation to the left arm and jaw roughly doubles the likelihood of an acute coronary syndrome."
}
```

When missed, the `teaching_note` is what the student reads in "What you
missed". Write it as the sentence you would say to them at the bedside.

## The process, not the answer

A student who names the right diagnosis with no history, no examination and no
reasoning scores in the 30s: case synthesis is only 10% of the total, and
reasoning, history and investigation selection are 60% between them. A student
who reasons carefully to a defensible wrong answer scores far higher than the
lucky guesser. That is the intended behaviour, and it is what the research
means by evaluating the process.

Three signals specifically punish list-making over reasoning:

- differentials submitted without a rationale scale the differential score by
  0.85,
- a differential under three items scales it by a further 0.9,
- `submit_discriminating_plan` is worth 20 points of the reasoning score, and a
  plan under twelve words gets half.

## Communication scoring is heuristic

Open-question detection, jargon and empathy markers are word-list heuristics,
not language understanding. They are good enough to catch the common failures —
interrogating the patient with closed questions, using "diaphoresis" at the
bedside, never acknowledging the patient's discomfort — but they will not
appreciate genuinely skilful communication. Communication is weighted at 10%
for that reason. Treat the sub-score as a prompt for discussion, not a
judgement.

## What the model contributes

Nothing numeric. `prompts.EVALUATOR_INSTRUCTION` gives the evaluator agent the
scorecard and the transcript and forbids it from changing a mark, praising
generically, or citing anything the transcript does not show. Its job is to
turn the scorecard into feedback a 21-year-old will act on.
