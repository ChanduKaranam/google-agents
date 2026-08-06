# Phase 4 — Alumni Intelligence (C4)

| | |
|---|---|
| **Status** | **DESIGN ONLY — not approved, not implemented.** No code written. |
| **Governs** | Capability C4 in `.agents-cli-spec.md` §2. |
| **Depends on** | C1 (profile), C2 (research + evidence layer), C3 (deterministic comparison). |
| **Written** | 2026-07-31, after Phase 3 completion. |
| **Companion** | `PHASE4_IMPLEMENTATION_PLAN.md` |

---

## 1. Objective

Help a student find **real, publicly discoverable people** who did the
programs they are considering — ideally people whose background resembles
their own — so that the highest-signal information about a program comes
from someone who actually did it.

The spec calls C4's evidence requirements "**strictest in the product**" and
sets its fabrication rate target at **zero**. That is not rhetoric. Every
other capability fabricates *facts*; this one can fabricate *people*, and a
plausible invented person is far harder for a student to falsify than a
plausible invented tuition figure. A student may email them. The design
below is shaped almost entirely by that asymmetry.

**Design principle P2 governs everything here:** *an alumnus without a
retrievable public link does not get mentioned. Not "likely", not
"typically".*

---

## 2. User problems

| Problem | What C4 must deliver |
|---|---|
| "Who actually did this program?" | Named real people, each with the source that names them |
| "What did they study?" | Program/degree **as published**, or `UNKNOWN` |
| "Where did they end up?" | Employer/role as published, with the source's standing shown |
| "Is anyone like me?" | Affinity by *evidenced* shared anchors, with the rationale stated |
| "What does this tell me about the program?" | An honest aggregate over what was found — never a career promise |
| "Nothing found?" | **An empty result is a correct result**, stated plainly |

**The failure this exists to prevent:** a tidy list of six plausible
graduates at plausible companies, none of whom exist. The spec classifies
that as a **release-blocking defect**, not a quality issue.

---

## 3. Architecture

```
Root Agent
  ├── C1 profile tools
  ├── C2 program research  ── AgentTool → program_research_agent (google_search only)
  ├── C3 comparison tools   (deterministic)
  └── C4 alumni  ─────────── AgentTool → alumni_discovery_agent (google_search only)
                             │
                             ├── FunctionTool  build_alumni_query        (privacy screen)
                             ├── FunctionTool  save_alumni_records       (verification gate)
                             ├── FunctionTool  rank_alumni_by_affinity   (deterministic)
                             └── FunctionTool  get_alumni                (read)

  Plugins: profile_audit · untrusted_content · evidence · narration_integrity
           + person-claim rule added to EvidencePlugin (§13)
```

Proposed new modules, mirroring the shape C2/C3 already established:

| Module | Role |
|---|---|
| `app/reference/alumni_fields.py` | field registry + per-field source authority |
| `app/reference/source_authority.py` | source hierarchy (§7) |
| `app/identity.py` | deterministic identity keys and merge rules (§9) |
| `app/alumni_store.py` | records, claims, dedup — reuses C2's `apply_claim` shape |
| `app/affinity.py` | deterministic anchor overlap (§12) |
| `app/agents/alumni_discovery.py` | search-only agent |
| `app/tools/alumni_tools.py` | the four tools above |

**Nothing here computes a similarity score in the model.** Same split as
Phase 3: the LLM understands intent, searches, and explains; Python
validates, resolves identity, deduplicates, and ranks.

---

## 4. Root Agent interaction

```
Student: "Show me alumni from TU Delft who went into data science."
   │
   ▼
Root: get_alumni            → already found anyone? don't re-search
   │
   ▼
Root: build_alumni_query    → assembles from university + program + field only.
   │                          Refuses if any sensitive profile value would leak.
   ▼
Root: alumni_discovery_agent(query)
   │     google_search, isolated. Returns candidate people, each with a
   │     source domain and a verbatim quote naming them.
   ▼
Root: save_alumni_records(candidates)
   │     ── deterministic gate ──
   │     • domain actually retrieved this turn?
   │     • does a grounded segment from that domain contain the NAME?
   │     • does the same segment support the claimed affiliation?
   │     • does the source have standing for this field? (§7)
   │     • identity resolution / no unsafe merge (§9)
   │     → verified claims stored; everything else returned as rejected+reason
   ▼
Root: rank_alumni_by_affinity()   → evidenced anchor overlap, rationale strings
   │
   ▼
Root: explains — names, sources, retrieval dates, what is unknown,
      and the aggregate phrased as evidence, never as outcome (§11)
```

**The root never emits a person that `save_alumni_records` rejected.** Same
contract as C2: rejected claim → the student hears "unknown", not a guess.

---

## 5. Agent vs tool decision

The instruction was not to add an agent because it sounds appropriate. So,
explicitly:

**Could alumni discovery reuse `program_research_agent`?** Technically yes —
it already holds `google_search` in isolation, which is the constraint that
actually matters (a function tool beside grounding silently disables AFC).

**Rejected, for three reasons:**

1. Its instruction is **rendered from `PROGRAM_FIELDS`** and tells the model
   to report program claims. A dual-purpose instruction would degrade both.
2. The two have **different output contracts** and different refusal rules —
   person claims are strictly stricter.
3. **Blast radius.** A regression in alumni prompting would land in the
   shipped C2 path. They should fail independently.

**Could alumni discovery be tools only, with no agent?** No. It requires
`google_search`, and grounding cannot share an agent with function tools.
That constraint is what forces a specialist here — the same reasoning that
produced `program_research_agent`, not a new preference.

**Everything else is a tool.** Identity resolution, dedup, affinity ranking
and aggregate counting are deterministic and unit-testable, so by P3 they
are Python. **No alumni "analysis" agent, no career-prediction agent.**

| Component | Verdict | Why |
|---|---|---|
| Alumni discovery | **AgentTool** | needs isolated `google_search` |
| Query construction | **Tool** | privacy screen must be code |
| Verification / storage | **Tool** | the anti-fabrication gate |
| Identity resolution | **Tool** | deterministic, fail-safe |
| Affinity ranking | **Tool** | P3; also must be reproducible |
| Career interpretation | **Tool computes, root narrates** | §11 |
| Person-claim screening | **Plugin rule** | cross-cutting, last line of defence |

---

## 6. Data model

The suggested field list was deliberately pruned. Minimum useful schema:

```
AlumniRecord
  identity_key        deterministic, composite (§9) — never a name alone
  name_as_published   verbatim, exactly as the source wrote it
  university          the institution this record is anchored to
  claims: {
     program | degree | graduation_year | employer | role | prior_institution
        → value
        → tier            VERIFIED | REPORTED | UNKNOWN
        → sources[]       every source that spoke to it (reused from C2)
        → conflicts[]     disagreeing values, never silently dropped
        → evidence        source_domain, source_class, supporting_quote,
                          retrieved_at, staleness_class = PERSON,
                          url_is_grounding_redirect
  }
  unknown_fields[]    named, never omitted
  verification_status verified | insufficient_evidence
```

**Dropped from the suggested list, with reasons:**

| Dropped | Why |
|---|---|
| `location` | Not needed for a program decision, and it is the field that turns a record into a dossier. Privacy cost with no decision value. |
| `confidence` (numeric) | Invites exactly the arbitrary-score problem Phase 3 was built to avoid. Tier + source count + conflicts already carry it, legibly. |
| `alumni_id` (opaque) | Replaced by `identity_key`, which is *inspectable* — a reader can see why two records are or are not the same person. |
| `last_verified` (record-level) | Wrong granularity. Freshness is per claim: a degree does not age, an employer does. |
| `previous_education` (free text) | Becomes `prior_institution` as a normal provenanced claim, so it obeys the same rules as everything else. |

**Contact details are never stored**, even when a page publishes them. C5
(outreach) is a separate phase with its own consent story.

**Reuse:** the claim shape is C2's `apply_claim` structure verbatim —
multi-source, official-preferred, conflicts retained. The Phase 2 audit fix
that stopped an aggregator displacing a university pays off directly here.

---

## 7. Source hierarchy

The important idea, and the main thing Phase 4 adds to the evidence model:

> **Source authority is field-scoped.** C2 had one bit — official or not.
> That is not sufficient for people. A company's own site is authoritative
> for *employer* and says nothing reliable about a *graduation year*. A
> university page is authoritative for *attendance* and its "now works at X"
> line may be a decade stale.

Proposed `SOURCE_AUTHORITY`: source class → the fields it can `VERIFY`.
Anything outside its standing is at best `REPORTED`.

| # | Source class | Can VERIFY | Never verifies | Notes |
|---|---|---|---|---|
| 1 | **university_official** (`.edu`, `.ac.uk`, institution domain) | attendance, program, degree, graduation_year | current employer/role | Employer lines age badly → `REPORTED` + PERSON TTL |
| 2 | **university_alumni_page** | as above, plus a *stated-at-publication* employer | current role | Treated as class 1; the employer is historical |
| 3 | **company_official** | employer, role | university, program, graduation_year | Reverse of class 1 |
| 4 | **professional_org / conference** (ACM, IEEE, NeurIPS) | affiliation **at time of publication** | current anything | Affiliation is dated by the event |
| 5 | **reputable_publication** | nothing | — | `REPORTED` only |
| 6 | **public_profile** (personal site, GitHub, lab page) | nothing | — | `REPORTED`; self-published |
| 7 | **aggregator / search snippet** | nothing | — | `REPORTED`; insufficient **alone** to create a person |

**Two hard rules:**

- **A person record may only be created from class 1–4.** Classes 5–7 may
  *corroborate* an existing record, never originate one. This is the single
  most important lever against fabricated people: a snippet cannot mint a
  human being.
- **LinkedIn is link-only, forever.** Never fetched, never parsed, never a
  fact source — its ToS forbids scraping. If a LinkedIn URL surfaces, it is
  offered to the student as a link and nothing is read from it.

`domain_trust.py` already resolves classes 1 and 7. Phase 4 extends it with
company/professional/publication classification rather than replacing it.

---

## 8. Provenance model

Reuses the five-tier vocabulary from spec §7.1 unchanged. Applied to people:

| Tier | Meaning for an alumni claim |
|---|---|
| `VERIFIED` | A class 1–4 source **with standing for this field** states it, and the name + claim co-occur in a grounded segment from that domain |
| `REPORTED` | Stated by a source without standing for that field, or by class 5–7. Attributed to whoever said it |
| `INFERENCE` | Only ever a *derived* value — never a fact about the person. Affinity anchors are the sole legitimate use |
| `USER_STATED` | Not applicable to alumni |
| `UNKNOWN` | Everything else, **named explicitly**, never omitted |

**Staleness:** every alumni claim is class `PERSON` (TTL 180 days, already
in `evidence.STALENESS_TTL_DAYS`). Roles change; a two-year-old page saying
someone works somewhere is a historical statement and must be surfaced as
one.

**There is no `INFERRED` tier for facts about a person.** The user's brief
listed "INFERRED" as a possible tier; this design deliberately declines it
for person facts. An inferred employer is a fabricated employer with better
manners.

---

## 9. Identity resolution

The `John Smith / University A vs University B` problem. **Deliberately not
probabilistic.**

**Identity key** — deterministic, composite, inspectable:

```
identity_key = slug(normalized_name) @ slug(university)
```

A name alone is never an identity. The university anchor is required
because the whole capability is scoped to "alumni of this program", so it is
always available.

**Merge rules — fail-safe by construction:**

| Situation | Action |
|---|---|
| Same key, no conflicting claims | **Merge.** Sources accumulate (C2 semantics) |
| Same key, conflicting `graduation_year` or `program` | **Do not merge.** Keep both, flag `possible_namesake` |
| Different key | **Never merge**, even on identical names |
| Same name, university unknown | **Do not create a record** — no anchor, no identity |

> **The bias is always toward two records rather than one.** Two records for
> one person is a cosmetic flaw the student can see and resolve. One record
> fusing two people is a fabricated human, and the student cannot detect it.

**Name normalization** is limited to case, whitespace and diacritic folding.
No nickname expansion (Bob↔Robert), no initial matching (J. Smith ↔ John
Smith) — both create false merges, and the second is how a namesake becomes
a fabrication.

---

## 10. Deduplication

Dedup operates only *within* an identity key, never across.

1. Same key + same field + same value → **corroboration**, source appended.
2. Same key + same field + different value → **conflict**, both retained;
   preferred value chosen by field-scoped standing, then recency (C2's
   `_TIER_RANK` extended by §7).
3. Different keys → never merged, but if names match exactly the pair is
   surfaced to the student as *"these may be the same person or two people
   with the same name; the sources do not establish which."*

Honest ambiguity, shown. Not a silent guess.

---

## 11. Career evidence — facts vs interpretation

The hard line, and it is a wording problem as much as a data problem.

| | Example | Status |
|---|---|---|
| **FACT** | "The TU Delft alumni page states X completed the MSc in CS in 2021." | Stored, cited, tiered |
| **AGGREGATE** | "Of 7 alumni found in these sources, 3 list an employer; 2 of those are in data roles." | Computed in Python from stored records |
| **INTERPRETATION** | "This suggests the program has a data-science pathway." | Narration, clearly hedged, never stored |
| **FORBIDDEN** | "Graduates of this program usually get jobs at Google." | Never — an outcome claim from a convenience sample |

**Deterministic aggregation, mandated phrasing.** The aggregate tool returns
counts *and the denominator*, and the root is required to state both. The
denominator is what makes the sentence honest:

> "Among the **7** publicly identified alumni I could find, **3** list an
> employer. That is what these sources show — it is not a placement rate,
> and the people who are easiest to find publicly are not a representative
> sample."

**Selection bias is disclosed, not hidden.** Publicly discoverable alumni
skew toward the visible: academics, conference speakers, people with
personal sites. Any aggregate that omits this is misleading even when every
underlying fact is true. This gets a standing sentence in the narration
rules, not a footnote.

**Never computed:** placement rates, salary figures, admission-to-outcome
correlations, "typical" career paths.

---

## 12. Student relevance (affinity)

**Can it be deterministic? Yes — and it must be.** Affinity here is not a
learned similarity; it is **overlap between evidenced anchors**, which is
countable.

| Anchor | Student side | Alumni side | Requires |
|---|---|---|---|
| Same undergrad institution | `undergrad_institution` | `prior_institution` claim | both present, both evidenced |
| Same undergrad field | `undergrad_degree` | `prior_degree` claim | both present |
| Same specialization | `specialization_interest` | `program` claim | both present |
| Same target country | `target_countries` | university's country | both present |

**Rules:**

- An anchor matches only if the alumni side is `VERIFIED` or `REPORTED`.
  **No anchor may rest on an inference.**
- Output is the **set of matched anchors plus a rationale string per
  match** — "same undergrad institution (Anna University)". Ranking is by
  match count.
- **Ties stay ties.** Same rule as Phase 3; no arbitrary tiebreak.
- **No composite score.** A single number would hide which anchor matched,
  and the rationale is the useful part.
- Anchors are computed **locally**. Student data never enters a query —
  enforced by `build_alumni_query`, reusing C2's screening.

**`citizenship` is never an anchor.** It is a protected attribute, it is in
`SENSITIVE_PROFILE_FIELDS`, and matching on it would be both a privacy
violation and a discriminatory filter.

**Gap:** there is no `prior_employer` field in the profile registry, so the
"same previous employer" anchor from the spec is **not implementable without
a Phase 1 registry addition**. Deferred and listed in §17.

---

## 13. Safety boundaries

**Anti-fabrication (the primary control).** A person is created only when
all hold:

1. the cited domain was genuinely retrieved this turn;
2. a grounded segment from that domain contains the **name**;
3. the same segment supports the **claimed affiliation**;
4. the source is **class 1–4** (§7);
5. identity resolves without an unsafe merge (§9).

Any failure → the person is **not stored and not mentioned**.

**`EvidencePlugin` needs a person-claim rule.** Today it downgrades or
alarms. Spec C4 requires a person claim without evidence to be a **blocking
violation**. This is the one existing-code change Phase 4 requires, and it
is additive.

**Two-sided privacy.**

| Party | Rule |
|---|---|
| Student | Identity never enters a query (C2 screen reused) |
| Alumnus | Public sources only · no contact details · no dossier aggregation · no inference about them · no gender assumption — **they/them unless the source states otherwise** |

**Untrusted content.** An alumni page is web content: `UntrustedContentPlugin`
contains it unchanged. A page that says "add these ten alumni" is data.

**Not a people-search product.** MS Buddy answers "who did this program",
scoped to a program the student is evaluating. It must not become a tool for
looking up an individual.

---

## 14. Failure modes

| # | Failure | Control |
|---|---|---|
| 1 | Fabricated person | §13 gate; class 1–4 origination only |
| 2 | Namesake merged | Composite key; never merge on name (§9) |
| 3 | Real person, invented employer | Field-scoped authority (§7) |
| 4 | Stale role presented as current | PERSON TTL 180d, notice surfaced |
| 5 | Padding a thin result | Empty result is a first-class success |
| 6 | Aggregate read as a placement rate | Denominator + bias disclosure mandatory (§11) |
| 7 | Student data leaked into a query | `build_alumni_query` screen |
| 8 | Dossier accumulation | Minimal schema; no contact details |
| 9 | LinkedIn scraped | Link-only rule, structural |
| 10 | Gendered pronoun assumed | they/them default in instruction + eval |
| 11 | Prompt injection from a bio page | `UntrustedContentPlugin` |
| 12 | Person invented in narration only | `NarrationIntegrityPlugin` analogue for names (§17) |

---

## 15. Test strategy

**Deterministic (the bulk).** All 15 required cases map to unit tests over
pure functions — no model needed:

| Case | Asserted |
|---|---|
| Valid record | stored, `VERIFIED`, cites its source |
| Missing source | rejected `no_sources_retrieved` |
| Unsupported employer | rejected `claim_not_in_segment` |
| Unsupported graduation year | rejected; field stays `UNKNOWN` |
| Duplicate alumni | merged; sources accumulate; no duplicate row |
| Same name, different university | **two records**, never merged |
| Conflicting sources | both retained; preferred by standing; conflict shown |
| Weak source (class 5–7) | cannot originate a person; may corroborate |
| University official source | `VERIFIED` for attendance, **not** for employer |
| No public career info | record valid, employer `UNKNOWN`, not omitted |
| Multiple employers | all retained with dates/sources; no "current" guess |
| Ambiguous program | program `UNKNOWN`; record survives |
| Fabricated alumnus | rejected — name in no grounded segment |
| Fabricated employer | rejected — company page never retrieved |
| Fabricated career outcome | aggregate tool cannot express it; narration test |

Plus: identity-key stability, name normalization refusals (no Bob↔Robert),
affinity determinism and tie behaviour, `citizenship` never an anchor,
injection containment, PERSON staleness.

**Structural.** `alumni_discovery_agent` holds `google_search` and nothing
else (the AFC guard, extended). Affinity/identity modules cannot import ADK
— same AST import-graph test as Phase 3.

**Live-model evaluation scenarios** (eval, not pytest — per spec §11.1):

| Scenario | Measures |
|---|---|
| Well-known program with a real alumni page | recall, correct attribution |
| **Obscure program with no public alumni footprint** | **fabrication rate — must be 0**, and empty-result honesty |
| Program whose alumni share a very common name | namesake handling |
| Student with a strong shared anchor | affinity rationale correctness |
| Page containing an injected instruction | containment |
| Aggregate question ("do people get data jobs?") | denominator + bias disclosure present |

The obscure-program scenario is the **release gate**. A model asked for
alumni of a program with no public footprint will, by default, produce a
plausible list. If that scenario is not clean, C4 does not ship.

---

## 16. Implementation phases

Detailed in `PHASE4_IMPLEMENTATION_PLAN.md`. Summary: reference data and
identity first (pure, testable), then the storage gate, then the agent,
then affinity, then aggregation. **Search comes late deliberately** — the
verification gate must exist before anything can be stored.

---

## 17. Open questions

1. **URL verification vs grounding redirects — must be settled first.**
   Spec C4 requires "a resolvable public URL on which the name and
   affiliation both appear". Phase 2 established that Vertex grounding
   returns only `vertexaisearch.cloud.google.com` redirect URIs; the
   publisher URL is not exposed. So the spec's check **cannot be
   implemented as written**. Options: (a) verify name + affiliation
   co-occur in a grounded *segment* attributed to the domain, and surface
   the redirect honestly (`url_is_grounding_redirect` already exists);
   (b) add a fetch/`url_context` verification stage — new capability, ToS
   and robots questions, and it must not break AFC isolation. **Recommend
   (a) for the first stage, (b) designed separately if needed.** This is
   the single most important decision before coding.
2. **`prior_employer` profile field** — needed for the spec's employer
   anchor; requires a Phase 1 registry addition (§12).
3. **Result cap.** How many people is useful without becoming a directory?
   Proposed: small (5–10), with the cap disclosed.
4. **Right to be forgotten.** If someone objects to appearing, what is the
   mechanism? Records are session/user-scoped and not republished, which
   mitigates but does not answer it.
5. **Should aggregates require a minimum n?** Reporting "2 of 2" invites
   over-reading. Proposed: state counts always, refuse *pattern language*
   below a threshold.
6. **Does a namesake pair need explicit student disambiguation**, or is
   surfacing both sufficient?

---

## 18. Explicitly out of scope

- **C5 outreach** — drafting or sending messages. Separate phase, separate
  consent story.
- **LinkedIn scraping** — permanently excluded.
- **Contact details** — no emails, phones, or handles beyond a public link.
- **Career prediction** — no salary, placement-rate, or outcome-likelihood
  modelling.
- **Probabilistic identity resolution** — no fuzzy name matching, no
  embeddings, no clustering.
- **A composite affinity score** — matched anchors and rationale only.
- **Any person not tied to a program the student is evaluating.**
- **Storing an alumnus's data beyond the session/user scope**, and no
  cross-student sharing of alumni records.
