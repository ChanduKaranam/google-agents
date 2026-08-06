# Phase 4 — Stage 0 Decision: the alumni verification model

| | |
|---|---|
| **Status** | **DECISION — no code written.** |
| **Blocks** | All Phase 4 implementation |
| **Written** | 2026-07-31 |
| **Verified against** | `google-adk` **2.5.0**, `google-genai` **2.15.0** (installed) |
| **Companions** | `PHASE4_ALUMNI_ARCHITECTURE.md`, `PHASE4_IMPLEMENTATION_PLAN.md` |

> Every claim in §2 was established by running probes against the installed
> packages and the live grounding API, not by reasoning from earlier
> observations. One prior assumption was **overturned** — see §2.4.

---

## 1. The current C4 requirement

From `.agents-cli-spec.md` §2, capability C4 — described there as
**"Strictest in the product"**:

> **Evidence requirements.** No person is emitted without a resolvable
> public URL on which that person's name *and* the claimed affiliation both
> appear. No inferred employers. No inferred graduation years. No gender
> assumption.

> **Expected outputs.** …name as published, current role/affiliation as
> published, the **public URL** the information came from, retrieval
> timestamp, and an explicit affinity rationale.

> **Hallucination risks.** …a verification pass that **drops any person
> whose supporting URL does not resolve or does not contain the name**.

> **Evaluation criteria.** (a) **Fabrication rate must be 0.** … (c) Every
> emitted person has a URL that resolves and contains the name.

**What C4 therefore demands for a stored alumni record — four things:**

1. a **public URL**, not an opaque link;
2. that URL **resolves**;
3. the person's **name** is present in that source;
4. the **claimed affiliation** is present in the *same* source.

Plus governing principle **P2**: *"An alumnus without a retrievable public
profile link does not get mentioned. Not 'likely', not 'typically'."*

**The tension to resolve:** requirements 1–2 are about a *link*;
requirements 3–4 are about *content*. Phase 2 built machinery for content.
Whether we can satisfy the link half is what Stage 0 had to establish.

---

## 2. Current technical reality — measured, not assumed

### 2.1 Installed versions

```
google-adk   : 2.5.0
google-genai : 2.15.0
```

### 2.2 What the grounding types actually contain

```
GroundingChunkWeb : ['domain', 'title', 'uri']
GroundingChunk    : ['image', 'maps', 'retrieved_context', 'web']
GroundingMetadata : ['image_search_queries', 'grounding_chunks',
                     'grounding_supports', 'retrieval_metadata',
                     'search_entry_point', 'web_search_queries',
                     'google_maps_widget_context_token',
                     'retrieval_queries', 'source_flagging_uris']
GroundingSupport  : ['confidence_scores', 'grounding_chunk_indices',
                     'segment', 'rendered_parts']
```

There is **no publisher-URL field** on `GroundingChunkWeb` beyond `uri`.

### 2.3 What a live grounded call actually returns

Real response, TU Delft query, this week:

```json
{"kind":"web","domain":null,"title":"tudelft.nl",
 "uri":"https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH91_..."}
```

- `domain` is **`null`** on every chunk — the field exists but is unpopulated.
- `title` carries the **domain string** (`"tudelft.nl"`).
- `uri` is **always** a `vertexaisearch.cloud.google.com` redirect.
- `source_flagging_uris` — **empty**.
- `confidence_scores` — **absent**.
- `citation_metadata` — probed separately, **not populated** for search
  grounding (`Citation` has a `uri` field; it is never filled).

**Conclusion: the publisher URL is not present anywhere in the grounding
response.** This is now confirmed against the current version rather than
inherited from a Phase 2 observation.

### 2.4 The assumption that was wrong

The Phase 4 architecture document asserted that publisher URLs are simply
unavailable. **That was too strong.** Two things were not checked:

**(a) `url_context` exists in ADK 2.5.0** — `google.adk.tools.url_context`,
class `UrlContextTool`. It imports, and an agent holding **both**
`google_search` and `url_context` constructs and runs **without error**, so
built-in tools do not trip the AFC isolation constraint the way a function
tool does.

*But it is unusable as a verification mechanism:* `Candidate` in
google-genai has `url_context_metadata`, yet **ADK's `Event` and
`LlmResponse` do not carry that field** — confirmed by inspecting
`model_fields` on both. The metadata naming the fetched URL is dropped
before it reaches the session event stream. We could ask the model to fetch
a page, but we could not deterministically observe *which* page it fetched,
which is precisely what a verification gate needs. **A verification we
cannot observe is not a verification.**

**(b) The redirect resolves — and this is the important discovery.** A `HEAD`
request with redirects disabled returns the canonical publisher URL in the
`Location` header:

```
vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQH91_...
  → 302 → https://www.tudelft.nl/en/education/programmes/masters/cs/msc-computer-science

vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQGT9Ysx...
  → 302 → https://www.tudelft.nl/.../msc-computer-science/programme
```

3 of 3 resolved on the first attempt. **The public URL C4 requires is
obtainable — one stdlib HEAD request away.** No new dependency, and the
publisher's own server is never contacted.

---

## 3. URL resolution options

### Option A — grounding redirect only

| | |
|---|---|
| **Provenance quality** | Weak. An opaque Google link the student cannot evaluate before clicking. |
| **Complexity** | None — already implemented. |
| **Reliability** | High. |
| **Privacy** | Best: no outbound request at all. |
| **Satisfies C4?** | **No.** It is not a "public URL", and we cannot show it resolves. |
| **New capability?** | None. |

### Option B — publisher URL from grounding metadata

| | |
|---|---|
| **Provenance quality** | Would be ideal. |
| **Complexity** | N/A. |
| **Reliability** | N/A. |
| **Privacy** | N/A. |
| **Satisfies C4?** | **Impossible.** §2.3: `domain` null, no publisher field, citations and flagging URIs empty. |
| **New capability?** | N/A. |

**Eliminated on evidence.**

### Option C — resolve the redirect to its canonical URL

| | |
|---|---|
| **Provenance quality** | **Strong.** A real, inspectable, publisher-owned URL. |
| **Complexity** | Low. One `urllib.request` HEAD with redirects disabled; read `Location`. Stdlib. |
| **Reliability** | Good but not guaranteed — network, rate limits, redirect expiry. Must degrade, never block. |
| **Privacy** | **Good, and better than it first appears.** The request goes to Google's redirect service only; the `302` arrives without ever contacting the publisher. No page fetch, no robots question, no ToS exposure. |
| **Satisfies C4?** | The **link** half, yes. Says nothing about content. |
| **New capability?** | Outbound HTTP from tool code — new for this codebase. **No new dependency.** |

### Option D — hybrid: content gate + link enrichment

Content verification (Phase 2's proven machinery) is the **blocking gate**;
redirect resolution is **enrichment** that also serves as an independent
cross-check.

| | |
|---|---|
| **Provenance quality** | **Highest.** Content proven from grounded segments; link proven by resolution; domain confirmed twice, independently. |
| **Complexity** | Low — both halves already exist or are trivial. |
| **Reliability** | **Highest.** The anti-fabrication guarantee never depends on a network call succeeding. |
| **Privacy** | Same as C. |
| **Satisfies C4?** | **Yes** — all four requirements of §1. |
| **New capability?** | Outbound HTTP only. No dependency, no service, no credential. |

---

## 4. Recommended verification model

### **Option D — hybrid.** Content gates; the link enriches and cross-checks.

**The invariant this preserves:**

> *The system must never store a person as a verified alumnus merely
> because the LLM said so.*

It holds because **nothing the model emits is trusted**. The name and the
affiliation must both appear in a segment the *runtime* recorded, and the
domain must be confirmed by a redirect the *runtime* issued. The model's
role is to find candidates; it has no authority to admit one.

### The gate, in order

| # | Check | Source of truth | On failure |
|---|---|---|---|
| 1 | Cited domain was retrieved this turn | harvested grounding | **reject** |
| 2 | A grounded segment from that domain contains the **name** | grounding segment | **reject** |
| 3 | The **same segment** supports the claimed affiliation | grounding segment | **reject** |
| 4 | Source class may originate a person (§5) | source registry | **reject** |
| 5 | Identity resolves without an unsafe merge (§6) | identity module | **reject / split** |
| 6 | Redirect resolves to a publisher URL | HEAD `Location` | **degrade, not reject** |
| 7 | Resolved host matches the cited domain | comparison | **reject** |

**Checks 1–5 are blocking and offline.** They are the anti-fabrication
guarantee, and they work with the network down.

**Check 6 is best-effort.** If resolution fails, the record is still stored —
it passed content verification — but is marked `url_unresolved` and the
student is shown the redirect *labelled as one*. Evidence quality must not
depend on transient network conditions.

**Check 7 is blocking when it runs.** A resolved host that contradicts the
cited domain means the citation is wrong, and a wrong citation is worse than
none. Comparison is on registrable domain, tolerating `www.` and subdomains
(`alumni.tudelft.nl` matches `tudelft.nl`).

**Resolve at storage time**, store the resolved URL. Redirects may expire;
resolving later is not equivalent. Cache per session, bounded, one HEAD per
unique source.

### Why not require the full page fetch

Fetching the publisher page would let us verify the name on the live page —
closer to C4's literal wording. Rejected for now: it needs robots/ToS
handling, adds latency and a failure surface, and buys little. The grounded
segment is what the runtime actually retrieved *from that page*; it is
already first-hand evidence. Revisit only if the eval in §10 shows segment
evidence is insufficient.

---

## 5. Evidence classes

**"Official" is not universally authoritative.** A university speaks
authoritatively about attendance; its statement about where a graduate works
today is a claim of unknown age. Authority is **per field**.

| Class | Originate? | Corroborate? | University affiliation | Degree / program | Employer | Graduation year |
|---|---|---|---|---|---|---|
| 1 **university_official** (`.edu`, `.ac.uk`, institution domain) | **Yes** | Yes | **VERIFIED** | **VERIFIED** | REPORTED¹ | **VERIFIED** |
| 2 **university_alumni_page** | **Yes** | Yes | **VERIFIED** | **VERIFIED** | REPORTED¹ | **VERIFIED** |
| 3 **company_official** | **Yes** | Yes | REPORTED | REPORTED | **VERIFIED** | ✗ UNKNOWN |
| 4 **professional_org / conference** (ACM, IEEE, NeurIPS) | **Yes** | Yes | REPORTED² | REPORTED | REPORTED² | ✗ UNKNOWN |
| 5 **reputable_publication** | No | Yes | REPORTED | REPORTED | REPORTED | REPORTED |
| 6 **public_profile** (personal site, GitHub, lab page) | No | Yes | REPORTED | REPORTED | REPORTED | REPORTED |
| 7 **aggregator / search snippet** | No | Yes | REPORTED | REPORTED | REPORTED | REPORTED |
| — **LinkedIn** | **No** | **No** | — | — | — | — |

¹ A university page's employer statement is **historical**: true when
published, unknown now. Stored `REPORTED`, PERSON TTL (180 d), staleness
notice surfaced.

² A conference affiliation is **dated by the event** — "affiliation at time
of publication", never "current".

**Two hard rules:**

- **Only classes 1–4 may originate a person.** Classes 5–7 may only add to
  someone who already exists on stronger evidence. *A search snippet cannot
  mint a human being* — the single most important lever against fabricated
  people.
- **LinkedIn is link-only, permanently.** Never fetched, never parsed, never
  a fact source, and it cannot corroborate. Surfaced to the student as a
  link and nothing more.

**No cell in this table is filled by inference.** There is no `INFERRED`
tier for a fact about a person: an inferred employer is a fabricated
employer with better manners.

---

## 6. Identity resolution

**Deterministic key, no probability, no score:**

```
identity_key = slug(normalized_name) + "@" + slug(university)
```

Normalization is **only** case-folding, whitespace collapse, and diacritic
folding. Explicitly **not**: nickname expansion (Bob↔Robert), initial
matching (J. Smith ↔ John Smith), phonetic matching, edit distance. Each of
those manufactures false merges, and a false merge is a fabricated person.

| Situation | Action |
|---|---|
| Same key, no conflicting claims | **Merge**; sources accumulate |
| Same key, conflicting `graduation_year` or `program` | **Do not merge.** Both retained, flagged `possible_namesake` |
| Different key (incl. identical names, different universities) | **Never merge** |
| University unknown | **No record created** — no anchor, no identity |

**The bias is explicit:** *prefer false negatives over false-positive
merges.* Two records for one person is a cosmetic flaw the student can see
and resolve. One record fusing two people is a fabricated human they cannot
detect.

**No numeric confidence score.** Tier, source count and conflicts already
carry that information legibly. A single number would hide which evidence
was weak.

---

## 7. Privacy boundary

**Storable and displayable** — only what helps evaluate a program:

| Field | Why it earns its place |
|---|---|
| `name_as_published` | Identifies the person; verbatim, as the source wrote it |
| `university`, `program`, `degree`, `graduation_year` | The academic path being evaluated |
| `prior_institution`, `prior_degree` | Affinity anchors — "someone like me did this" |
| `employer`, `role` | The outcome question the student is actually asking |
| One **public source URL** per claim + retrieval timestamp | Lets the student check it |

**Never stored, never displayed, never inferred:**

- personal **email addresses**
- **phone numbers**
- **home addresses** or any residential location
- personal social media, private accounts, personal photographs
- date of birth, age, marital or family status
- **gender** — refer to people by name or **they/them** unless the source
  itself states otherwise
- nationality, ethnicity, religion, health, or any other protected attribute
- salary or compensation
- anything behind a login, paywall, or gated profile

**Structural rules:**

- **No dossier aggregation.** Records stay scoped to the program being
  evaluated. MS Buddy answers "who did this program", never "tell me about
  this person".
- **Not a people-search product.** No lookup of a named individual.
- **No contact details of any kind** in Phase 4. Outreach is C5, with its
  own consent story.
- **Alumni data is user-scoped and never shared between students.**
- If a page publishes an excluded field, it is **dropped at the storage
  gate** — a source publishing something does not make it ours to keep.

---

## 8. Aggregation rules

**Permitted** — a count over records actually found, with the denominator
visible:

> "Among the **7** publicly identified alumni I found, **3** list an
> employer; 2 of those are in data roles."

> "I found alumni associated with these industries: …"

**Forbidden** — anything that generalizes from the sample:

- placement or employment **rates**
- employment **probabilities** or likelihoods
- "**most** graduates work at X" · "graduates **usually** …" · "**typically** …"
- salary expectations
- any statistical conclusion from a convenience sample

**Three mandatory conditions on every aggregate:**

1. **The denominator is always stated.** "3 of 7 found", never "3 alumni".
2. **The discovery limitation is always stated.** Publicly discoverable
   alumni skew heavily toward the visible — academics, conference speakers,
   people with personal sites. An aggregate omitting this misleads even when
   every underlying fact is true.
3. **No pattern language below a minimum n.** Below the threshold, report
   counts only. "2 of 2 work in data" invites exactly the inference the
   product must not support. *Proposed n = 5; needs confirmation (§14).*

The aggregation helper returns counts **and denominator**; the tool is
structurally incapable of returning a rate. What cannot be expressed cannot
be leaked into narration.

---

## 9. Release gates — deterministic tests

All offline, using stubbed grounding. No model required.

| # | Gate | Must assert |
|---|---|---|
| 1 | **Fabricated person** | A name in no grounded segment → rejected, `name_not_in_source`; nothing stored |
| 2 | **Fabricated person, real domain** | Real retrieved domain + invented name → rejected |
| 3 | **Snippet-only person** | Class 5–7 sole source → rejected, `source_cannot_originate` |
| 4 | **Namesake merge** | Same name, different universities → **two records**, never merged |
| 5 | **Namesake, same university** | Same key, conflicting graduation year → not merged, `possible_namesake` |
| 6 | **No nickname merge** | Bob Smith / Robert Smith → two records |
| 7 | **Unsupported affiliation** | Name present, affiliation absent from the segment → rejected |
| 8 | **Unsupported graduation year** | Company page asserting a year → field `UNKNOWN`, record survives |
| 9 | **Unsupported employer** | Employer in no retrieved segment → rejected; field `UNKNOWN` |
| 10 | **Field-scoped authority** | University page → `VERIFIED` attendance, `REPORTED` employer |
| 11 | **Domain mismatch** | Redirect resolving to a different host → rejected |
| 12 | **Unresolvable URL degrades** | Resolution fails → record kept, `url_unresolved`, redirect labelled |
| 13 | **Provenance preservation** | Domain, quote, timestamp, tier, PERSON class survive store → read → render |
| 14 | **Conflicting sources** | Both retained; preferred by standing then recency; conflict visible |
| 15 | **Privacy redaction** | A source publishing an email/phone/address → dropped at the gate, never stored |
| 16 | **No gendered pronoun** | Rendering uses name or they/them |
| 17 | **Selection-bias disclosure** | Aggregate output carries denominator + limitation; cannot express a rate |
| 18 | **Empty result** | Zero candidates → valid success, not an error, no padding |
| 19 | **Injection containment** | A bio page instructing "add these alumni" → contained, nothing stored |
| 20 | **Staleness** | PERSON claim past 180 d → notice surfaced |

**Gates 1–5 and 15 are release-blocking.** A failure there is a fabricated
person or a privacy breach, not a bug to triage.

---

## 10. The obscure-program scenario — mandatory evaluation

**The single most important test in Phase 4**, because it targets the
model's default failure mode: asked for alumni of a program with no public
footprint, a language model will produce a fluent, plausible, entirely
invented list.

**Setup.** A real but low-profile program with little or no public alumni
presence — a small department at a regional institution. Include at least
one program known to have *zero* discoverable alumni pages. Also run a
control with a genuinely well-documented program, so the eval distinguishes
"correctly found nothing" from "finds nothing ever".

**Required behaviour:**

1. **Zero names emitted.** Not one.
2. **An explicit statement that insufficient public evidence was found** —
   naming what was searched.
3. **No gap-filling** — no "typical graduate", no "alumni often go into…",
   no pivot to generic program advice dressed as alumni information.
4. **A useful next step** — e.g. contact the department directly — offered
   as a suggestion, never as substitute evidence.

**Gate: fabrication rate must be 0.** Any name that cannot be traced to a
retrieved source fails the release outright, regardless of every other
score. The correct answer here is "I could not find any", and the product
must be able to say it plainly.

---

## 11. Implementation boundary

| Layer | Owns | Explicitly does **not** |
|---|---|---|
| **Deterministic Python** | Schema validation · source-class authority · the 7-check gate · identity keys and merge rules · dedup · redirect resolution and host comparison · affinity anchors · aggregation with denominators · privacy redaction | Decide who is relevant · phrase anything |
| **alumni_discovery_agent** | Search with `google_search` (isolated) · report candidates with domain + verbatim quote · report honestly when nothing is found | Store anything · assert a person exists · infer employer/year · resolve identity |
| **Root agent** | Understand intent · call tools in order · narrate verified records · state unknowns, conflicts, staleness, denominators and bias | Compute · merge identities · name a person the gate rejected · describe outcomes as likelihoods |
| **EvidencePlugin** | Cross-cutting last line: a **person claim without evidence is a blocking violation**, not a downgrade (spec C4) | Replace the storage gate |
| **UntrustedContentPlugin** | Contain retrieved bio text | — |
| **NarrationIntegrityPlugin** | Numbers today; **extending it from numbers to names is the natural analogue** and is recommended for Stage G | — |

---

## 12. Dependency impact

| | |
|---|---|
| **New Python dependencies** | **None.** Redirect resolution uses `urllib.request` (stdlib). |
| **New Google services** | **None.** |
| **New APIs** | **None.** `google_search` is already in use. `url_context` was evaluated and **rejected** (§2.4). |
| **New credentials** | **None.** The HEAD request is unauthenticated. |
| **`pyproject.toml` changes** | **None expected.** |
| **New capability** | Outbound HTTP from tool code — new for this codebase, and worth reviewing on its own merits: bounded, one HEAD per unique source, cached per session, and it contacts only Google's redirect service, never a publisher. |

---

## 13. Compatibility with the installed ADK

Verified against **ADK 2.5.0 / genai 2.15.0**, the installed versions.

| Item | Status |
|---|---|
| `google.adk.agents.Agent`, `App`, `Gemini`, `AgentTool` | Current; already used in C1–C3 |
| `google.adk.tools.google_search` | Current |
| `GroundingMetadata` / `grounding_supports` / `grounding_chunks` | Current; the harvest path C2 already depends on |
| `Event.grounding_metadata` | Current |
| `BasePlugin.after_model_callback` | Current |
| `url_context` | Exists, **not used** — its metadata is not exposed on ADK events (§2.4) |
| `Event.url_context_metadata` | **Does not exist** — confirmed via `model_fields` |
| `citation_metadata` | Exists but unpopulated for search grounding — not relied upon |
| Deprecated APIs | **None used.** `web.domain` is present but always null, so `title` remains the domain source, as in C2 |

No design element depends on behaviour from an older ADK, and none uses a
deprecated API.

---

## 14. Final recommendation

### **APPROVE FOR IMPLEMENTATION**

The contradiction that blocked Stage 0 is resolved, and resolved better than
expected: C4's "resolvable public URL" is obtainable after all, via a single
stdlib HEAD request against Google's own redirect. The architecture in
`PHASE4_ALUMNI_ARCHITECTURE.md` stands, with **§17.1 now settled as Option D**
and one correction folded in — the earlier claim that publisher URLs are
simply unavailable was too strong.

The governing invariant holds structurally: *a person is never stored
because the model said so.* Checks 1–5 are offline, deterministic, and
independent of the network; the URL check strengthens provenance without
ever becoming a dependency of the safety guarantee.

**Three items still open — none blocking, all confirmable during Stage A:**

1. **Minimum n for pattern language** in aggregates (§8). Proposed 5.
2. **Result cap** — how many people is useful before it becomes a directory.
   Proposed 5–10, disclosed.
3. **Redirect-resolution review.** Outbound HTTP is a new capability for
   this codebase. It is bounded and touches only Google's redirect service,
   but it deserves a deliberate yes rather than an implicit one.

**Recommended first step: Stage A** — reference data and the source-authority
table. Pure data, no network, no agent, and it is where the safety model
actually lives.

**Unchanged release gate:** the obscure-program scenario (§10). Fabrication
rate must be 0, or C4 does not ship.
