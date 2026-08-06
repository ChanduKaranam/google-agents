# Phase 3 — Personalized University Comparison (C3)

| | |
|---|---|
| **Status** | **IMPLEMENTED** — approved 2026-07-31 and built as described. See §10 for the as-built deviations. |
| **Governs** | Capability C3 in `.agents-cli-spec.md` §2. |
| **Depends on** | C2 (shipped in Phase 2). C3 reads stored ProgramRecords; it never retrieves. |
| **Written** | 2026-07-30, after the Phase 2 architecture audit. |
| **Built** | 2026-07-31, Phase 3. `app/normalize.py`, `app/scoring.py`, `app/tools/comparison_tools.py`, `app/reference/comparison_dimensions.py`. |

---

## 1. The one rule this architecture exists to enforce

> **A number the student sees in a ranking must be traceable to a fact a source stated, through arithmetic they could redo by hand.**

Comparison is where hallucination becomes most dangerous, because a ranked list *reads* as authoritative. A model that silently guesses a missing tuition figure to complete a table produces a table that looks complete and is wrong. So the pipeline below is split so that **no LLM ever touches a number**.

```
   ProgramRecords (C2)            ← FACTS, each already tier + source + timestamp
        │
        ▼
   ① deterministic normalization  ← Python. Parses published strings into typed
        │                            quantities. Refuses rather than guesses.
        ▼
   ② deterministic scoring        ← Python. Weights in, ranking + arithmetic out.
        │                            Reproducible, unit-testable, no model.
        ▼
   ③ explanation                  ← LLM. Narrates the numbers it was given.
        │                            Adds no facts and computes nothing.
        ▼
   Student
```

Stages ① and ② are code. Stage ③ is the only LLM in the path, and it is downstream of every number.

---

## 2. What is a FACT, and what is an OPINION

The audit confirmed the C2 store already distinguishes these. Phase 3 must not blur them.

| | Origin | Tier | May affect the ranking? |
|---|---|---|---|
| **Fact** | A source stated it; quote and value both verified | `VERIFIED` / `REPORTED` | **Yes** — this is the only input to scoring |
| **Student input** | The student stated it (weights, budget, constraints) | `USER_STATED` | **Yes** — as *weights and filters*, never as data about a program |
| **Derived** | Computed by MS Buddy from the two above | `INFERENCE` | It **is** the output; always labelled |
| **Unknown** | Not found | `UNKNOWN` | **No** — never imputed, never defaulted to zero |
| **Opinion** | The model's commentary | — | **Never.** Stage ③ output is not fed back into scoring |

**The hard line:** stage ③ receives the scoring result and may only describe it. If the explanation names a number that is not in the scorer's output, that is a defect, and §7 proposes the check for it.

---

## 3. Stage ① — deterministic normalization

**Problem this solves.** C2 deliberately stores values *as published*: `"22290"`, `"24 Months"`, `"15 January (23:59 CEST)"`, `"EUR"`. That is correct for provenance — the stored string is the one the quote supports — but it is not comparable. Normalization is the bridge, and it is where the audit found the largest remaining gap (§8 below).

**Proposed module:** `app/normalize.py` — pure functions, no state, no ADK, no model.

| Normalizer | In | Out |
|---|---|---|
| `normalize_money` | `"22290"` + `"EUR"` + `"per year"` + duration | `{amount: 22290, currency: "EUR", basis: "year", annualized: 22290, total_program: 44580}` |
| `normalize_duration` | `"24 Months"` / `"2 years"` / `"120 EC"` | `{months: 24}` |
| `normalize_deadline` | `"15 January (23:59 CEST)"` + intake year | `{date: "2027-01-15", tz: "CEST", is_rolling: false}` |
| `normalize_boolean` | `"Yes, STEM designated"` | `{value: true}` |
| `normalize_test_requirement` | `"GRE not required"` | `{required: false, waivable: null}` |

**Design rules, each carried over from a control that already works in C1/C2:**

1. **Refuse, never guess.** Every normalizer returns `{"status": "ok", ...}` or `{"status": "unparsed", "reason": ...}`. An unparsed value stays `UNKNOWN` and drops out of that dimension. This is the same posture as `convert_to_us_4pt` rejecting an out-of-range GPA rather than coercing it.
2. **Provenance travels through.** A normalized quantity carries the `tier`, `source_domain`, `retrieved_at` and `staleness_class` of the fact it came from. Normalization must not be a place where a citation is lost.
3. **Normalization is `INFERENCE`, with a versioned rule id** — exactly as `gpa_conv:cgpa_10_to_us_4pt:v1` already works. A currency conversion or a per-term→per-year annualization is a derivation and is labelled one.
4. **Currency conversion needs a dated rate, and the rate is itself a fact.** Either the student supplies the rate, or it is retrieved and tiered like anything else. A hardcoded rate would be an unsourced institutional claim wearing a different hat. **Recommendation: MVP compares within a currency and reports cross-currency dimensions as not-comparable**, rather than shipping a fabricated rate.
5. **`tuition_basis` is load-bearing.** A per-year figure read as whole-program understates cost by the program length. C2 already captures the basis as its own field; if it is `UNKNOWN`, the money normalizer must refuse rather than assume "per year".

---

## 4. Stage ② — deterministic scoring

**Proposed module:** `app/scoring.py` — pure functions. Weights and normalized quantities in; ranking, per-dimension contributions and coverage out.

```
score_programs(normalized_programs, weights) -> {
    ranking: [ {program_id, total, rank} ],
    contributions: { program_id: { dimension: {raw, normalized, weight, points} } },
    coverage: { dimension: 0.0-1.0 },
    excluded_dimensions: [ {dimension, reason} ],
    ties: [ [program_id, program_id] ],
    arithmetic: "<human-checkable derivation>",
}
```

**Rules:**

1. **Missing is not zero.** A program lacking tuition does not score 0 on cost — it is *absent* from that dimension. Scoring over an incomplete set uses only the dimensions a program actually has, and reports `coverage` per dimension. Treating `UNKNOWN` as 0 would silently rank a program with no published fee as the cheapest.
2. **A dimension below a coverage floor is excluded entirely**, with a reason. Ranking on a dimension where 4 of 6 programs are unknown is noise presented as signal — a named C3 failure case.
3. **Ties are ties.** Equal totals are reported as tied, never broken arbitrarily to produce a strict order.
4. **Evidence quality is an input, not an afterthought.** A `VERIFIED` fact, a `REPORTED` one, a stale one and a *corroborated* one are not equally trustworthy. The Phase 2 audit added `source_count`, `corroborations` and `conflicts` per field precisely so this stage can use them. Proposed: a per-fact confidence weight, reported separately from the score rather than silently folded into it, so the student can see both "which is best" and "how sure are we".
5. **A field with unresolved conflicts does not silently pick a winner.** It either uses the preferred (official) value *and says a conflict exists*, or drops out of scoring — the student's call, surfaced as a choice.
6. **Stale facts are flagged, and optionally excluded.** The staleness notice must reach the ranking, not just the fact sheet.
7. **`arithmetic` is a required output.** C3 in the spec demands "a weighted ranking with the arithmetic shown". The scorer emits the derivation; stage ③ relays it.

**Weight elicitation.** The student may state weights qualitatively ("cost matters most"). The qualitative→numeric mapping is a small deterministic table, and **the mapping is shown**. That prevents the model from inventing weights and prevents anchoring the student on an unstated framing.

---

## 5. Stage ③ — explanation (the only LLM)

The root agent receives the scorer's output and narrates it. It is a **renderer with judgement**, not an analyst.

**It may:** explain why the order came out as it did, name the dimensions that decided it, point out where data is too thin to rank, surface conflicts and staleness, and note when the student's stated constraints conflict with each other.

**It may not:** compute or restate a number that is not in the scorer's output; fill a gap; assert an institutional fact (the `EvidencePlugin` already blocks that path); or present the ranking as a decision rather than a recommendation with visible reasoning.

**Instruction conditioned on data quality.** When `coverage < 0.7` on a decisive dimension, the narration is required to lead with the limitation rather than the ranking. This mirrors how the C2 root is already required to name unknowns.

---

## 6. Component classification (per spec §4.1 method)

| Component | Verdict | Why |
|---|---|---|
| Normalization | **Tool / pure module** | Parsing is deterministic and unit-testable. Every normalizer is a place a model would guess. |
| Scoring | **Tool / pure module** | Arithmetic. Principle P3. Also: reproducible across runs, which a model is not. |
| Weight elicitation | **Root agent + deterministic mapping table** | Conversation is the model's job; the number it maps to is not. |
| Explanation | **Root agent** | Genuinely a language task, and downstream of all numbers. |
| Comparison "agent" | **Does not exist** | Nothing here needs an autonomous agent. A schema-bearing comparison agent would insert generation into a computation with one correct answer. |
| Retrieval during comparison | **Forbidden** | Spec §5.2 invariant 3: comparison operates on what exists. Missing stays missing. |

**No new plugins.** `EvidencePlugin` and `UntrustedContentPlugin` already cover this path; C3 adds no new external input.

**Proposed new tools on the root:** `build_comparison_matrix`, `score_programs`, `explain_ranking_inputs` — exactly the three the spec §4.2 inventory already names. No new agents.

---

## 7. Testing strategy

| Layer | What |
|---|---|
| **Unit (the bulk)** | Every normalizer against published-string fixtures; scorer arithmetic; missing-vs-zero; coverage floors; tie detection; conflict handling; weight mapping. All deterministic, so all pytest. |
| **Property-based** | Scoring is order-independent; adding an `UNKNOWN` never changes a program's rank; scaling all weights leaves the order unchanged. |
| **Structural** | No retrieval tool reachable from the comparison path; scorer is a pure function (no `ToolContext`); provenance keys survive normalization. |
| **Explanation-integrity check** | Extract numeric tokens from the narration and assert each appears in the scorer's output. This is the C3 analogue of C2's quote verification, and it is the one new *safety* test the design needs. |
| **Eval (not pytest)** | Whether the narration is *useful*, whether coverage caveats are stated when required, whether trade-offs are read correctly. Per spec §11.1. |

---

## 8. Open issues this design must resolve first

Carried from the Phase 2 audit — these are the honest gaps, not decoration.

1. **Normalization is the weakest link and does not exist yet.** C2 stores publisher strings. Everything in stage ② assumes stage ① can parse them. Parsing `"Credits, 120 EC, 24 Months"` or `"15 January (23:59 CEST)"` reliably across institutions is the real work of Phase 3, and it should be built fixture-first against strings actually retrieved, not imagined ones.
2. **Cross-currency comparison is unresolved** (§3 rule 4). Recommend deferring rather than fabricating a rate.
3. **The intake year is not attached to a deadline.** C2 stores `application_deadline` as published, which often omits the year. Normalizing to an absolute date needs the intake from `user:profile`, and where that is ambiguous the deadline must stay unnormalized rather than be assumed into the wrong cycle.
4. **Confidence weighting needs a decision**: does evidence quality adjust the score, or ride alongside it? Recommendation: **alongside**, so score and certainty stay separable and the student can see both.
5. **`tuition_basis` coverage is unmeasured.** If sources rarely publish it, cost comparison will refuse often. Worth measuring on real retrievals before designing around it.
6. **No latency budget.** Comparison itself is fast, but it presumes several programs were researched first, each costing retrieval time.

---

## 9. What Phase 3 must not do

- Must not retrieve. C3 reads `user:shortlist` only.
- Must not write to `user:profile` beyond comparison weights under `user:preferences`.
- Must not introduce a new agent.
- Must not let the explanation stage feed anything back into scoring.
- Must not impute, default, or zero-fill a missing value under any circumstance.
- Must not add dependencies. Everything above is stdlib plus what is installed.

*All six held. No dependency was added; `normalize` and `scoring` are stdlib
only, and a test asserts they cannot transitively import ADK or any HTTP
client.*

---

## 10. As built — where the implementation differs from this proposal

Recorded so the document stays honest about what was actually shipped.

**1. A dimension registry was added** (`app/reference/comparison_dimensions.py`).
The proposal implied dimensions inline. Making them a registry keeps the
"what is orderable" decision in one reviewable place, and made §4's
`comparability_keys` (currency + basis for cost) declarative rather than a
special case inside the scorer.

**2. The deadline is normalized but never scored.** §3 lists
`normalize_deadline` and §4 never makes it a dimension; the implementation
makes that explicit via `DISPLAY_ONLY_FIELDS`, which carries the reason: an
earlier deadline is not a better one. It appears in the matrix, never in a
ranking.

**3. Per-semester and per-term fees are not annualized.** §3's table implied
a general annualization. In practice semesters-per-year is not published and
varies, so multiplying by two would be exactly the invented number this
architecture exists to prevent. Such fees normalize successfully but carry
`annual_amount: None` with the reason. They remain comparable against other
per-semester fees and non-comparable against per-year ones.

**4. Statuses are four, not two.** §3 rule 1 proposed `ok` / `unparsed`.
The implementation distinguishes `ok` / `ambiguous` / `unsupported` /
`missing`, because "the source published a range", "we cannot parse this
form" and "nobody ever said" are different things to tell a student.

**5. Weights are words, not numbers.** §4's "weight elicitation" is enforced
at the tool boundary: `DimensionWeight.importance` accepts only the five
vocabulary words, so the model cannot pass a numeric weight at all. An
attempt is refused with the vocabulary in the error.

**6. `explanation_integrity` is a shipped function, not only a test.** §7
proposed it as a test. It lives in `app/scoring.py` and is used by both unit
tests and the live agent test, so the check is available to any future
runtime enforcement without being reimplemented.

**7. Confidence weighting rides alongside** (§8 open issue 4, as
recommended). `_evidence_summary` reports verified/reported/stale/conflicted
input counts per program next to the score, never inside it.

**8. Cross-currency comparison was deferred** (§8 open issue 2, as
recommended). No FX rate exists anywhere in the codebase.

**9. A per-program coverage floor was added**, which the proposal did not
name. Renormalizing weights over "whatever a program has" would otherwise
let a program with one documented dimension beat a fully documented rival.
A program below `PROGRAM_COVERAGE_FLOOR` is returned in `unranked` with its
missing dimensions listed, rather than scored.
