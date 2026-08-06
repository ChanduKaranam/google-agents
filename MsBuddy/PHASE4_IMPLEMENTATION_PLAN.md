# Phase 4 — Implementation Plan

| | |
|---|---|
| **Status** | **PLAN ONLY — no code written.** |
| **Governs** | `PHASE4_ALUMNI_ARCHITECTURE.md` |
| **Written** | 2026-07-31 |

---

## Sequencing principle

**The verification gate is built before anything can search.**

Phases 2 and 3 both taught the same lesson the expensive way. In Phase 2 the
storage path shipped before the value-in-quote check, and a real live run
stored a fabricated academic year. In Phase 3 the comparison shipped before
anyone checked whether the answer reached the student, and the suite stayed
green while the feature was refused end to end.

For a capability whose failure mode is **inventing a human being**, search
is the last thing to switch on, not the first. Stages A–C contain no
network access at all.

Each stage ends with the same gate: **unit tests pass · full existing suite
passes · lint/format/codespell/ty pass · no Phase 1–3 behaviour changed.**

---

## Stage 0 — Decide the verification model *(no code)*

**Blocking.** Open question §17.1 must be answered before Stage C.

Spec C4 requires "a resolvable public URL on which the name and affiliation
both appear." Vertex grounding does not expose publisher URLs. Decide:

- **(a)** verify name + affiliation co-occur in a grounded **segment**
  attributed to the domain; surface the redirect honestly. *Recommended —
  implementable today, consistent with C2.*
- **(b)** add a fetch/`url_context` verification stage. Needs its own design:
  ToS, robots, latency, and it must not break `google_search` isolation.

Also settle: result cap (§17.3), and whether aggregates need a minimum n
(§17.5).

**Exit:** a written decision. Everything downstream assumes (a) unless told
otherwise.

---

## Stage A — Reference data *(pure, no ADK, no network)*

**Build:** `app/reference/alumni_fields.py`, `app/reference/source_authority.py`.

- Alumni field registry (allowlist, mirroring `program_fields.py`), each
  field with its `PERSON` staleness class.
- Source classes 1–7 and the **field-scoped authority map** — which class
  may `VERIFY` which field.
- Extend `domain_trust.py` **additively** with company / professional-org /
  publication classification. Existing classification must not change; the
  Phase 1–3 domain-trust tests are the regression guard.

**Tests:** a university page verifies attendance but not employer; a company
page the reverse; classes 5–7 verify nothing; LinkedIn is link-only; every
existing `test_domain_trust.py` case still passes.

**Why first:** it is data, it is where the safety model actually lives, and
it is testable without a single moving part.

---

## Stage B — Identity and storage *(pure)*

**Build:** `app/identity.py`, `app/alumni_store.py`.

- `identity_key(name, university)` — deterministic, inspectable.
- Name normalization: case, whitespace, diacritics. **Nothing else** — no
  nickname expansion, no initial matching.
- Merge rules per §9, biased toward two records over one.
- Record/claim storage reusing C2's `apply_claim` shape (multi-source,
  conflicts retained, preferred by standing then recency).

**Tests:** all identity/dedup cases from §15 — same name different
university stays two records; conflicting graduation year blocks the merge;
Bob↔Robert never merges; key stability; corrupt-state tolerance.

**Exit gate:** this stage is where "a fabricated human" is structurally
prevented. Do not proceed until the namesake tests are green.

---

## Stage C — The verification gate *(the anti-fabrication stage)*

**Build:** `save_alumni_records` in `app/tools/alumni_tools.py`, plus
`get_alumni`.

Implements the five-point gate (§13) using the Stage 0 decision:

1. domain retrieved this turn?
2. grounded segment from that domain contains the **name**?
3. same segment supports the **claimed affiliation**?
4. source class 1–4 for origination?
5. identity resolves without an unsafe merge?

Every rejection returns a named reason. Unsourced fields come back as
`UNKNOWN`, never omitted.

**Tests:** the fabrication cases from §15, driven by stubbed grounding —
**no live model yet**. A fabricated name, a fabricated employer, and a
snippet-only person must all be rejected here, deterministically.

---

## Stage D — Query construction and privacy

**Build:** `build_alumni_query`.

Reuses C2's screening: assemble from university / program / field only, then
check the assembled string against the stored profile and refuse if any
sensitive value appears. `citizenship` and `undergrad_institution` must
never reach a query.

**Tests:** a query containing a sensitive profile value is refused with
`profile_data_in_query`; anchors remain usable locally.

---

## Stage E — The discovery agent *(first network access)*

**Build:** `app/agents/alumni_discovery.py` — `google_search` only, no
`mode`, no `output_schema`, harvest callback as in `program_research.py`.

Instruction carries the `NO_INVENTION` rules verbatim: never a person
without a source naming them; never an inferred employer or graduation year;
they/them unless the source states otherwise; an empty result is a correct
answer.

**Tests:** structural AFC isolation (extend the existing walker so exactly
two agents in the tree can reach the network); then the **first live run**.

---

## Stage F — Affinity ranking

**Build:** `app/affinity.py`, `rank_alumni_by_affinity`.

Evidenced anchor overlap, rationale strings, ties preserved, no composite
score. Pure module — same AST import-graph test as Phase 3.

**Tests:** determinism, order-independence, ties, no anchor on an
inference, `citizenship` never an anchor.

---

## Stage G — Aggregation and narration safety

**Build:** deterministic aggregate helper; root instruction section;
`EvidencePlugin` person-claim rule (§13) — **the only change to existing
code in this phase, and it is additive.**

Aggregates return counts **with denominators**. The root is required to
state the denominator and the selection-bias caveat.

**Tests:** the aggregate cannot express a placement rate; a narration
omitting the denominator fails; a person named in narration but absent from
the store is caught. Consider extending `NarrationIntegrityPlugin` from
numbers to **names** — the natural analogue, and cheap given the machinery
exists.

---

## Stage H — Evaluation

Eval datasets per §15, including the **obscure-program scenario**.

**Release gate: fabrication rate must be 0.** If a program with no public
alumni footprint produces names, C4 does not ship regardless of how well
every other scenario scores.

---

## Rules for every stage

- No new dependencies.
- No changes to Phase 1–3 behaviour. The one permitted edit is the additive
  `EvidencePlugin` person rule in Stage G.
- Run the suite **serially** — Phase 3 established that concurrent live runs
  cause skips and transient failures.
- Report failures; never weaken an assertion to get green.

---

## Recommended first step

**Stage 0**, then **Stage A**. Neither writes an agent, touches the network,
or risks existing behaviour — and Stage 0 resolves a contradiction between
the spec and what the grounding API can actually provide, which would
otherwise be discovered halfway through Stage C.
