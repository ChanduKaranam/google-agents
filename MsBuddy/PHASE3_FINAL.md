# Phase 3 — Final Report

| | |
|---|---|
| **Capability** | C3 — University Comparison (`.agents-cli-spec.md` §2) |
| **Status** | **COMPLETE** — full suite green; the IAM prerequisite (§13) was resolved during the audit |
| **Audited** | 2026-07-31 |
| **Design of record** | `PHASE3_COMPARISON_ARCHITECTURE.md` |

---

## 1. Objective

Let a student compare researched MS programs against *their own* priorities,
where every number is traceable to a fact a source stated, through
arithmetic they could redo by hand.

Comparison is where hallucination does the most damage, because a ranked
list *reads* as authoritative. A model that quietly fills a missing tuition
figure to complete a table produces a table that looks complete and is
wrong. Phase 3 is built so that **no LLM ever touches a number**.

---

## 2. Architecture

```
Root Agent  (the only conversational component)
  ├── C1  Student Profile          function tools
  ├── C2  Program Research         function tools + Program Research Agent
  ├── C3  Program Comparison       function tools only  ← Phase 3
  ├── Profile Extractor Agent      task-mode sub-agent
  └── Program Research Agent       AgentTool, google_search only
```

**Phase 3 introduced no new agent.** Comparison is arithmetic with one
correct answer; inserting a generative component into it would only create
a place for the answer to drift. This is asserted structurally — a test
fails if any agent beyond the two pre-existing specialists appears.

Three tools were added to the root, exactly the three the spec §4.2
inventory already named: `build_comparison_matrix`, `score_programs`,
`explain_ranking_inputs`.

Four plugins run cross-cutting: `profile_audit`, `untrusted_content`,
`evidence`, and `narration_integrity` — the last added by this audit to
enforce the C3 number boundary at runtime (§10).

---

## 3. Data flow

```
ProgramRecords in user:shortlist       ← FACTS, each with tier + source + timestamp
        │                                (written by C2, never by C3)
        ▼
① app/normalize.py                    ← Python. Parses published strings into
        │                                typed quantities. Refuses rather than guesses.
        ▼
② app/scoring.py                      ← Python. Weights in; ranking + arithmetic out.
        │                                No ADK import, no ToolContext, no clock, no RNG.
        ▼
③ Root agent narration                ← LLM. Describes the numbers it was handed.
        │                                Adds no facts and computes nothing.
        ▼
    Student
```

C3 **never retrieves**. It compares what C2 already found; a gap stays a
gap. The student's `target_intake_year` is read from `user:profile` for one
purpose only — resolving deadlines that name no year.

---

## 4. Normalization strategy

C2 deliberately stores values *as published*, because the stored string is
the one the supporting quote verifies. That is right for provenance and
useless for comparison. Stage ① is the bridge.

Parsers were written **fixture-first against strings C2 actually
retrieved**, not formats invented because they seemed plausible. The
corpus, each marked REAL in `tests/unit/test_normalize.py`:

| String | Source |
|---|---|
| `$15,605.` `$15,590.` | gatech.edu, live harvest |
| `EUR 17.310` `EUR 22.290` | tudelft.nl, Phase 2 audit run |
| `22,290` | mastersportal.com |
| `CHF 1460 per semester` | ethz.ch |
| `2025/2026` | tudelft.nl |
| `If provided, GRE scores will be considered.` | gatech.edu |
| `A minimum overall score of 7.5 is required…` | gatech.edu (IELTS, not GRE) |
| `24 Months`, `15 January (23:59 CEST)`, `15 December 2026` | fixtures |

**Four statuses, not two.** `ok` is the only comparable outcome.
`ambiguous`, `unsupported` and `missing` are distinct because "the source
published a range", "we cannot parse this form" and "nobody ever said" are
different things to tell a student.

**The separator rule** is the crux. `$15,605.` and `EUR 17.310` use
opposite conventions and both mean five figures:

- both `.` and `,` present → the **last** is the decimal separator
- one separator, repeated → thousands (`1.234.567`)
- one separator, followed by exactly **3** digits → thousands
- one separator, followed by 1–2 digits → decimal (`1460.50`)
- spaces / apostrophes between digits → thousands (`CHF 1'460`)
- anything else → refused

Notable refusals, each with a stated reason: duration ranges
(`1.5 – 2 years`), semesters and ECTS credits as durations, word-numbers,
numeric dates (`15/12/2026` — day-month order is undecidable and being
months out is a real harm), rolling admissions, `$` alone (six currencies
use it), and English-test requirements read as GRE rules.

---

## 5. Scoring strategy

Four dimensions: `cost`, `duration`, `stem`, `test_burden`. Deadlines are
normalized and **displayed but never scored** — an earlier deadline is not a
better one.

1. Resolve weights from importance **words** (§10).
2. Per dimension: collect programs with an `ok` value; exclude on weight
   zero, too few values, coverage floor, or non-comparability.
3. Scale each included dimension 0–1 across its participants (best = 1).
4. Each program's total is the weighted mean **over the dimensions it
   actually has**.
5. Rank with competition ranking; equal totals share a rank.
6. Emit `arithmetic` — a derivation the student can redo by hand.

Determinism is empirical, not assumed: 200 identical runs produce exactly
one distinct output, and the ranking is invariant to input order.

---

## 6. Missing-data policy

**Missing is never zero.** A program with no published fee is *absent* from
cost, not worst at it. Scoring `UNKNOWN` as zero would rank a program with
no published fee as the cheapest available.

**Renormalizing is not a free pass.** Averaging over "whatever a program
happens to have" would let a one-dimension program beat a fully documented
rival. A program participating in under `PROGRAM_COVERAGE_FLOOR` (0.5) of
included dimensions is returned in `unranked` with its missing dimensions
named — it gets no score at all.

**Nothing is ever imputed, defaulted, or zero-filled.**

---

## 7. Coverage policy

| Constant | Value | Effect |
|---|---|---|
| `MIN_PROGRAMS_PER_DIMENSION` | 2 | fewer cannot be ranked |
| `COVERAGE_FLOOR` | 0.5 | thinner dimensions excluded entirely |
| `PROGRAM_COVERAGE_FLOOR` | 0.5 | sparser programs go unranked |
| `NARRATION_COVERAGE_THRESHOLD` | 0.7 | below this the narration must lead with the limitation |

Every exclusion carries a `reason`, a human-readable `message`, and the
counts behind it. Ranking a dimension where 4 of 6 programs are unknown is
noise presented as signal — a named C3 failure case.

---

## 8. Currency policy

**There is no exchange rate anywhere in this codebase**, verified by grep.

Programs quoted in different currencies — or on different bases — make cost
non-comparable. The dimension is excluded with the reason stated in words a
student can act on. An unsourced FX rate is an unsourced institutional claim
wearing a different hat.

**Per-semester and per-term fees are never annualized.** Semesters per year
varies by institution and is not published; multiplying by two would be
precisely the invented number this design exists to prevent. Such fees
normalize successfully, carry `annual_amount: None` with the reason, and
remain comparable against other per-semester fees.

---

## 9. Provenance policy

Every normalized value — **including every refusal** — carries:

- `published_value`: the source's own string, verbatim
- `tier`, `source_domain`, `source_is_official`, `source_url`
- `retrieved_at`, `staleness_class`, `is_stale`, `staleness_notice`
- `has_conflict`, `conflicting_values`, `source_count`, `corroboration_count`

Provenance survives the whole chain: retrieval → evidence → stored record →
normalization → scoring contribution → final answer. A value that could not
be normalized still has a source worth citing.

**Derived is never dressed up as stated.** A normalized value is tier
`INFERENCE` with a versioned `rule_id` (`norm:money:v1`,
`norm:duration:v1`, …), exactly as GPA conversion already worked. A refusal
is tier `UNKNOWN` and asserts nothing.

---

## 10. LLM vs deterministic-code boundary

**Code-enforced (structural):**

| Guarantee | How |
|---|---|
| Arithmetic is Python | `normalize`/`scoring` cannot transitively import `google.*`, `httpx`, `urllib` — asserted against the AST import graph |
| Scorer takes no `ToolContext` | signature test |
| Comparison cannot mutate state | state compared before/after; no `user:` key written |
| Comparison cannot retrieve | no ledger written, no retrieval symbol reachable |
| Model cannot invent a weight | `DimensionWeight.importance` accepts only five words; a numeric weight is refused |
| Missing ≠ zero | absent dimensions are skipped, not defaulted |
| Unsupported values cannot score | only `status == "ok"` participates |
| Ties stay tied | competition ranking |
| No currency conversion | no FX rate exists to apply |
| Narration states no number the turn did not produce | `NarrationIntegrityPlugin` blocks the answer at `after_model_callback` |

**The narration boundary was the one gap, and it is now closed in code.**

The audit originally flagged it as prompt-plus-test only: the *computed*
score was immutable, but nothing stopped the model **restating** it wrongly
or adding a figure the scorer never produced.
`app/plugins/narration_integrity.py` now screens the answer at runtime.
When a C3 tool has run in the turn, every number in the reply must appear in
that turn's tool results or in the student's own message; otherwise the
answer is replaced with a message naming the offending figures.

**Why this one is allowed to block when `EvidencePlugin` mostly does not.**
`EvidencePlugin` judges prose claims, where detection is heuristic and a
false positive would mangle a correct answer (spec §16.4). Here the check is
arithmetic against a closed set — the turn's tool outputs are known exactly
— so "this number came from nowhere" is determinable rather than guessed.

**Scope is deliberately narrow.** The plugin is inert unless a comparison
tool ran. Profile, research and ordinary conversation are untouched, so the
blast radius is confined to the capability whose value rests entirely on its
numbers being trustworthy. It also fails **open**: a screening error leaves
the deterministic scorer, the actual source of the numbers, unaffected.

**False-positive rate measured, not assumed.** Four consecutive live runs
against the real model passed the canary in
`test_comparison_live.py::test_narration_integrity_did_not_block_a_correct_answer`,
which asserts a legitimate answer survives the screen. A screen that blocks
good answers would be worse than none, so that canary is the test that
justifies blocking rather than merely alarming.

---

## 11. Test results

All figures from a single run on 2026-07-31, after the fixes in §16.

| Class | Result |
|---|---|
| **Deterministic** — unit (`tests/unit`) | **431 passed** |
| **Deterministic** — structural integration | **39 passed** |
| **Live-model** (4 modules, run serially) | **21 passed, 0 skipped** |
| **Environment-dependent** (`test_server_e2e`) | **4 passed** |
| `ruff check` · `ruff format --check` · `codespell` · `ty` | **all pass** |

**Complete suite: 495 passed, 0 failed, 0 skipped.**

Run-to-run variance is real and worth recording rather than hiding. Three
complete-suite runs after the hardening:

| Run | Result | Conditions |
|---|---|---|
| 1 | **495 passed, 0 failed, 0 skipped** | serial, nothing else running |
| 2 | 487 passed, 0 failed, 8 skipped | a second suite running concurrently |
| 3 | 487 passed, 0 failed, 8 skipped | a second suite running concurrently |

487 + 8 = 495 in both degraded runs, so the entire difference is the
research-live module skipping as a block. **No run produced a failure.**
The variance is in whether live tests execute at all, never in whether they
pass — and it appears only under concurrency (§14). Both degraded runs were
caused by the author starting an overlapping suite, which is how the effect
came to be measured in the first place.

---

## 12. Known limitations

1. **The narration screen's error rates are measured on a small sample.**
   Four consecutive live runs, not a statistical estimate. The two failure
   modes are not symmetric and both matter:
   - a **false positive** blocks a correct answer, which is a real UX harm
     — 0 of 4 live runs, and the canary test exists to keep watching it;
   - a **false negative** lets a fabricated figure reach the student, which
     is the harm the whole design exists to prevent.

   Separately, a screening *exception* fails **open** (the answer passes) so
   that a bug in the screen can never take the agent down. That is a
   deliberate trade: availability over a guarantee that is already backed by
   the instruction and by the scorer being the only producer of numbers.
   Re-measure both rates as answer shapes change.
2. **The fixture corpus is small.** One live harvest succeeded; a second
   returned no grounding. Forms not yet seen will surface as *refusals*,
   not wrong numbers — the right failure direction, but coverage is thinner
   than it should be.
3. **Only four scoring dimensions.** Curriculum fit and outcome data are
   named in the C3 spec but are not retrieved by C2.
4. **Per-program renormalization remains structurally generous** to sparse
   programs; the coverage floor plus reported coverage is a mitigation, not
   a cure.
5. **Institutional-claim detection is heuristic** (spec §16.4, unchanged
   since Phase 2). The guarantee that a *stored* fact is sourced does not
   rest on it.
6. **`user:profile` and `user:shortlist` are not durably persistent** under
   `InMemorySessionService`.
7. **Live coverage is probabilistic.** The C2 live invariants only run when
   the model chooses to search. Mitigated (§14), not eliminated.

---

## 13. Environment / IAM issue — RESOLVED

`tests/integration/test_server_e2e.py::test_collect_feedback` —
**now passing.** Recorded in full because it was a real blocker for most of
this audit and the diagnosis is worth keeping.

**The symptom.** `POST /feedback` calls `logger.log_struct(...)` → a Cloud
Logging write. Throughout the audit the ADC principal
(`varshith@tilicho.in`) was denied **`logging.logEntries.create`** on
project **`supadha-dev`**, so the endpoint returned 500. The same principal
could not read the project IAM policy either, so the developer could not
self-remediate: granting the role needs `setIamPolicy`, and `getIamPolicy`
was already denied.

**The resolution.** The permission was granted externally while this audit
was running. Verified directly rather than inferred from a passing test:

```
logging.logEntries.create : GRANTED (write succeeded)
```

`test_collect_feedback` then passed 3/3 in isolation and in every
subsequent full-suite run.

**Application code was never modified to make this test pass.** The endpoint
was correct throughout; the environment was not provisioned. That is the
right outcome — the failing test was reporting a real deployment gap, and
bypassing it in code would have hidden a service that genuinely could not
write its audit log.

**If it recurs** (a new principal, a fresh project), the grant is:

```bash
gcloud projects add-iam-policy-binding supadha-dev   --member="user:<principal>"   --role="roles/logging.logWriter"
```

`roles/logging.logWriter` is the predefined role containing
`logging.logEntries.create`. It must be run by a project owner or IAM
admin.

---

## 14. Live-test rate-limit issue

**Investigated; the original diagnosis was incomplete.**

Two distinct effects were conflated:

**(a) Transient errors under back-to-back live calls.** Five Phase 1 live
tests errored in one full-suite run, passed alone (6/6), and passed on
re-run with zero errors. Consistent with API rate limiting from many
sequential live calls in one process. Not test ordering, not session reuse
— each live module builds its own `InMemoryRunner` and session. **No change
made:** the effect is transient, weakening assertions to hide it would be
worse, and the model client already retries (`HttpRetryOptions(attempts=3)`).

**(b) Silent skipping — the more serious one.** All 8 skips in the
pre-audit run came from **one** module-scoped fixture in
`test_program_research_live.py`: the agent did not choose to search, so
every C2 live invariant was skipped while the suite still reported green.
A suite that is green because it did not run is worse than a red one.

**Fix:** a bounded retry (two additional plausible student follow-ups)
before skipping. **No assertion was weakened** — a retry only affects
whether the assertions get to run.

**It reduces the problem; it does not solve it.** Measured on the same
commit: running the live modules alone gave 20 passed / 0 skipped, but one
full-suite run still skipped all 8 after three attempts. That run was
executing concurrently with another live suite, which points at a third
effect worth recording:

**(c) Concurrent live runs make the miss worse.** Two live suites against
the same project contend for the same quota; retries then land in a
degraded window rather than a fresh one. **Do not run live suites in
parallel.**

**Standing recommendation:** run the deterministic suite (`tests/unit`,
~2.4 s) on every change, and the live suite deliberately and serially.
The classes are already separable by path; a `live` pytest marker would
make that explicit and is worth adding when live coverage grows. Treat
search rate itself as an eval metric (spec §11.1) — it is the honest place
for it, and it is why the live skip is loud rather than silent.

---

## 15. Files and modules

**Phase 3 implementation:**

| File | Role |
|---|---|
| `app/normalize.py` | Stage ① — parsers, refusals, provenance carry-through |
| `app/scoring.py` | Stage ② — weights, ranking, arithmetic, integrity check |
| `app/reference/comparison_dimensions.py` | dimension registry; display-only fields |
| `app/tools/comparison_tools.py` | the three C3 tools (state shell only) |
| `app/plugins/narration_integrity.py` | runtime screen on comparison answers |

**Modified:** `app/agent.py` (tools, narration boundary, plugin) ·
`app/plugins/__init__.py` ·
`app/schemas.py` (`DimensionWeight`) · `app/tools/__init__.py` ·
`app/plugins/evidence.py` (audit fixes) · `pyproject.toml` (codespell
allowlist).

**Tests:** `tests/unit/test_normalize.py` · `test_scoring.py` ·
`test_comparison_tools.py` · `test_narration_integrity.py` ·
`tests/integration/test_comparison_live.py`,
plus additions to `tests/unit/test_plugins.py` and a retry in
`tests/integration/test_program_research_live.py`.

**No dependency was added in Phase 3.**

---

## 16. Fixes made during this audit

Three defects, all found by verifying the repository rather than trusting
the implementation report.

**1. Comparison was refused outright across sessions.** `EvidencePlugin`
blocked any answer containing an institutional claim when nothing was
retrieved *that session*. C3 retrieves nothing by design, so every
comparison answer was replaced with "I can't answer that from memory" —
despite every fact being stored with a verified C2 citation. Reproduced
end-to-end before the fix.

*Fix:* evidence now means retrieved **or** stored. A stored ProgramRecord
field is not a model prior — it only exists because `save_program_record`
verified the domain, the quote, and the value. The cold-start guarantee is
untouched: nothing retrieved *and* nothing stored still refuses.

**2. The live test could not have caught defect 1.** A refusal contains no
numbers, so "invented no numbers" passed trivially. The suite was green
while the feature was unusable.

*Fix:* `test_the_comparison_was_not_refused` asserts the negative directly.

**3. The integrity checker mishandled thousands separators.** With defect 1
fixed, the first real comparison answer was flagged as fabricated: the
model wrote the stored `22290` as `22,290` and the checker read it as 22.29.
Correct answer, buggy checker.

*Fix:* each token is read every defensible way, reusing `parse_amount`'s
separator convention. Strict about provenance, relaxed about formatting —
`43000` still fails under every reading.

**Also:** `NUMERIC_CLAIM` was `\d{2,4}`, so the attribution alarm was blind
to every five-figure tuition (`22290`, `15605` are both real values) — the
most common numeric institutional claim there is. Widened to `\d{2,}`.
Two dead symbols removed (`NON_COMPARABLE`, `is_dimension`).

---

## 16b. Narration-integrity hardening

Closing the one guarantee the audit found resting on prompt text (§10).

`app/plugins/narration_integrity.py` screens the root's answer whenever a
C3 tool has run in the turn. Every number in the reply must appear in that
turn's tool results or in the student's own message; otherwise the answer is
replaced with a message naming the offending figures. Provenance is read
from `session.events`, so the plugin keeps no state of its own and cannot
leak between turns, and it is scoped by `invocation_id` — a figure the
scorer produced in an earlier turn is not evidence for the answer being
written now.

It catches recomputed totals, invented fees and converted currencies. It
tolerates the things a good answer legitimately does: thousands separators,
rounding, percentages, relayed arithmetic, and repeating a number the
student themselves supplied.

**Blocking rather than alarming was justified empirically, not assumed.**
The canary in `test_comparison_live.py` asserts a legitimate real-model
answer survives the screen, and it passed on four consecutive live runs.
The plugin also fails **open**: a screening error leaves the deterministic
scorer untouched.

22 unit tests cover it, weighted towards the false-positive direction —
a screen that mangles correct answers would be worse than none.

---

## 17. Final status

### PHASE 3 COMPLETE

The C3 capability is implemented, tested and architecturally sound. The
FACTS → deterministic normalization → deterministic scoring → explanation
boundary holds, and now holds **structurally at every step including the
narration** — the gap this audit flagged was closed in code by
`NarrationIntegrityPlugin` (§16b), so no comparison guarantee rests on
prompt text alone.

**Complete suite: 495 passed, 0 failed, 0 skipped.** Lint, format,
codespell and type checking all pass. The IAM prerequisite that blocked
`test_collect_feedback` for most of this audit was resolved externally and
verified directly (§13); no application code was changed to accommodate it.

Two caveats an engineering lead should carry forward rather than assume
away:

1. **Green requires running the suite serially.** Concurrent live runs
   contend for model quota and produce skips or transient failures (§14).
   This is a property of the tests, not of the code.
2. **Live coverage is probabilistic.** The C2 invariants only execute when
   the model chooses to search. Mitigated by a bounded retry, not
   eliminated. Search rate belongs in eval, per spec §11.1.

Phase 4 (Alumni Intelligence) has not been started.
