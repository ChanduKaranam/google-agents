# MSBuddy — System Design & Agentic Architecture

| | |
|---|---|
| **Status** | Describes the system as implemented and running |
| **Written** | 2026-08-07 |
| **Verified by** | 933 offline tests, live runs where noted |

This is the design document for MSBuddy as it actually exists — every
component named here is implemented, tested, and wired. Where the design
brief sketched a different shape (eleven separate agents), this document
explains what was built instead and why, because the divergences are
load-bearing, not stylistic.

---

## 1. The one design decision everything else follows from

**LLMs propose; deterministic code decides; only decided facts reach the
student.**

Every capability in MSBuddy is split the same way:

| Role | Who plays it | Trust level |
|---|---|---|
| Understand & converse | root agent (LLM) | trusted with conversation, never with facts |
| Retrieve | search-only specialist agents (LLM + google_search) | proposals only |
| Decide | deterministic Python tools | the only writers of state |
| Screen | plugins on the way out | last line of defence |

A deadline, a fee, a requirement, or a human being can only be *stated* if a
deterministic gate admitted it with evidence. This is why the brief's core
demand — "never fabricate admission requirements, deadlines, fees, or
university information" — is an architectural property here, not a prompt
instruction hoping to hold.

## 2. Final architecture

```
                        STUDENT
                           │
                           ▼
              ┌────────────────────────┐
              │  root_agent (LLM)      │  conversation, intent, routing,
              │  gemini-3.6-flash      │  narration — computes nothing
              └───────────┬────────────┘
                          │ calls tools / delegates
     ┌────────────┬───────┼──────────────┬──────────────┐
     ▼            ▼       ▼              ▼              ▼
 PROFILE      PLANNING  RESEARCH      COMPARISON     ALUMNI
 (C1)         slice     (C2)          (C3)           (C4)
 get_profile  match_    build_program build_compar   build_alumni_query
 save_profile universi  _query        ison_matrix    alumni_discovery_agent*
 _fields      ties      program_rese  explain_rank   save_alumni_records
 profile_     get_appl  arch_agent*   ing_inputs     rank_alumni_by_affinity
 completeness ication_  save_program  score_         get_alumni
 normalize_   plan      _record       programs
 gpa          set_docu  get_shortlist
 clear_...    ment_
 profile_     status
 extractor†
                          │
                          ▼          * = search-only LLM specialist
              ┌────────────────────┐     (gemini-2.5-flash, google_search
              │ EVIDENCE LEDGER    │      only, harvests grounding)
              │ grounding harvest, │ † = task-mode sub-agent, extracts,
              │ per-session        │      cannot write state
              └─────────┬──────────┘
                        ▼
              ┌────────────────────┐
              │ PLUGINS (way out)  │  ProfileAudit → UntrustedContent →
              │                    │  Evidence → NarrationIntegrity
              └─────────┬──────────┘
                        ▼
                     STUDENT
```

## 3. The brief's eleven agents → what actually implements them

The brief's rule 15.1–15.2 ("do not make every node an independent LLM
agent; use agents only where a distinct responsibility exists") decides
this table. An LLM agent exists only where LLM judgement is the job;
everything else is a deterministic tool, which is cheaper, testable, and
cannot hallucinate.

| Brief's conceptual agent | Implemented as | Why this shape |
|---|---|---|
| Orchestrator | `root_agent` | The one conversational LLM; routes by instruction sections |
| Intent Agent | instruction routing table in `ROOT_INSTRUCTION` | Intent detection is what an LLM already does per-turn; a second LLM hop adds latency and a failure mode, not accuracy |
| Profile Agent + Extractor + Validator | `profile_extractor_agent` (extract) + `save_profile_fields` (validate/decide) + field registry | Extraction is LLM work; validation must be deterministic or it isn't validation |
| University Research Agent | `match_universities` (discovery) + C2 research (facts) | Discovery over a curated dataset needs no LLM; facts need search + verification |
| Program Research Agent | `program_research_agent` + `save_program_record` | Exists as designed — search-only proposer, deterministic gate |
| Exam & Eligibility Agent | "Exams and eligibility" instruction section + `test_requirements` registry field + C2 flow | Country-level guidance is knowledge; program-level requirements are researched facts. No new machinery needed — the registry already carried the field |
| Application Planner | `get_application_plan` next-step ladder | A priority ladder over existing state; deterministic |
| Document Agent | `get_application_plan` + `set_document_status` | A checklist is data, not judgement |
| Deadline Agent | C2 research (`application_deadline` field) + plan surfacing | Deadlines are researched facts; the plan can render them, never mint them |
| Comparison Agent | `score_programs`, `build_comparison_matrix`, `explain_ranking_inputs` | Arithmetic must be deterministic; the model narrates a result it didn't compute |
| Alumni/Outcome Agent | `alumni_discovery_agent` + `save_alumni_records` gate | The strictest slice: discovery proposes people, code decides which exist |
| Research/Source Validation | grounding harvest → evidence ledger → per-fact gates → plugins | Shared by C2 and C4, exactly as the brief's rule 15.5 asks |
| Response Builder | root narration + 4 plugins screening it | Building is LLM work; *screening* what was built is code |

**Why not eleven sub-agents?** Three measured platform constraints:
1. `AgentTool` sub-agents receive an **empty memory service** — a sub-agent
   that looks anything up in memory silently gets nothing.
2. `google_search` cannot share an agent with function tools — the Gemini
   API rejects it, sometimes only in production. Search lives in dedicated
   leaf agents or nowhere.
3. The evidence plugins screen the **root's** model output. Move narration
   into sub-agents and the last line of defence goes blind.

## 4. Orchestration and communication

- **Root ↔ specialists:** `AgentTool` (root keeps the turn) for the two
  search agents; task-mode sub-agent for the extractor. Never free-text
  relay of facts — the root passes claims to gates *verbatim*, and the gates
  re-verify them against what the runtime actually retrieved.
- **State is the only data channel** (session state via ADK): `user:profile`,
  `user:shortlist`, `user:alumni`, `user:documents`, plus the session-scoped
  evidence ledger and retrieval counters. Producer writes, reader templates —
  no second channel.
- **Budget:** every outbound search passes `enforce_retrieval_budget`
  (3/turn, 25/session), so no flow can loop the network.

## 5. Intent model

Intents are instruction sections, resolved by the root per turn — including
several in one message (profile extraction + exam question in the Lendi
case). The mapping:

| Student says | Section that answers |
|---|---|
| hello / who are you / what can you do | Talking with the student — **no tools** |
| what is an SOP / Fall vs Spring | same section, general knowledge, no search |
| my CGPA is 8.2 / I'm from Lendi | Working with the profile |
| which universities fit me | Suggesting universities |
| which exams do I need for Canada | **Exams and eligibility** |
| research TU Delft's MSc CS | Researching a program |
| compare A and B | Comparing programs |
| find alumni of X | Finding alumni |
| what documents / what's next / deadlines | Documents and progress |

## 6. Research & source validation (the heart)

1. A query is **built by a tool** (`build_program_query` /
   `build_alumni_query`), which refuses if the student's private data would
   leak into a search. The model never hand-writes a query.
2. The search agent retrieves; an `after_agent_callback` harvests the
   runtime's **grounding metadata** — domains, URIs, attributed text
   segments — into the evidence ledger. This is what the platform actually
   retrieved, not what the model says it retrieved.
3. A deterministic gate (`save_program_record` / `save_alumni_records`)
   admits each claim only if the cited domain was genuinely retrieved and
   an attributed segment supports the value (for people: name and claim in
   the *same* segment, source class with standing, safe identity
   resolution, redirect/host agreement).
4. Verified vs reported tiers per source authority (a university page
   verifies what someone studied; an employer's page where they work;
   aggregators only report). Unknowns are named, never filled.
5. Four plugins screen the way out — profile audit, untrusted-content
   marking (retrieved text is data, never instructions), the evidence
   screen (unsourced institutional claims in a fresh session are blocked),
   and narration integrity (numbers and people in the answer must exist in
   tool output).

## 7. Profile structure

A 24-field registry (`profile_fields.py`) with importance tiers
(core/recommended/optional), validation rules, value history, and an
`evidence_span` quoting the student's own words for every value. Collected
progressively — `profile_completeness` tells the root what is worth asking
next, and nothing already stored is asked again. Deletable on request,
including a full wipe behind an explicit sentinel.

## 8. The workflows the brief specified, as they actually run

**"I'm a CSE graduate at Lendi, MS in Canada — which exams?"** (the failure
this revision fixed): extractor stores degree/institution/country →
"Exams and eligibility" answers the general half directly with hedges
(English test commonly expected; GRE varies by program; scores are set per
program; never "Canada requires X") → offers the specific half: match
universities in Canada, research named ones, `test_requirements` lands with
source and quote.

**"8.2 CGPA, IELTS 7.5, MS CS Canada — suggest universities."** Profile
already knows the scores → `match_universities("Canada", "Computer
Science")` → bands with factors (converted GPA vs typical, competitiveness,
English) → offer research on the ones she likes.

**"Compare UBC, Waterloo, McGill for MS CS."** Comparison never searches:
whatever isn't researched yet gets researched first (three C2 rounds), then
`explain_ranking_inputs` → student's weights in words → `score_programs` —
deterministic, ties preserved, data limitations lead the answer.

**"What documents do I need and when?"** `get_application_plan` → checklist
+ verified deadlines only + one next step. No stored deadline → the honest
answer is "research the program", never a date from memory.

## 9. Error handling

- Every tool returns a **named refusal** (`profile_data_in_query`,
  `domain_not_retrieved`, `unknown_document`…) — the root relays what's
  needed, never retries with invented values.
- Research that finds nothing yields "couldn't verify from an authoritative
  source" — stated, not papered over.
- Fabrication is structurally prevented, not requested: the invented-
  programme release-gate test passes live (searches, widens, names nobody).
- Stack traces never reach the student; tool errors are structured dicts.

## 10. Technology stack

Python 3.11–3.13 · `google-adk` 2.5.0 · Gemini (`gemini-3.6-flash` root,
`gemini-2.5-flash` for the grounded search agents — measured grounding
regression, see `PHASE4_E2_DEMO_FINDINGS.md`) · Vertex AI grounding ·
pytest (933 offline tests, structural + unit + live invariants) · ruff, ty,
codespell · `adk web` locally · Agent Runtime + Gemini Enterprise (`AI_GE`
app) in production.

## 11. MVP status vs the brief's §16 scope

| Brief MVP item | Status |
|---|---|
| Profile, Intent, Orchestrator | ✅ shipped |
| University + Program research | ✅ shipped |
| Exam & Eligibility | ✅ this revision |
| Document + Deadline | ✅ shipped (deadlines via research) |
| Research / source validation | ✅ shipped |
| Response building/screening | ✅ shipped |
| Comparison, Alumni | ✅ shipped (beyond MVP scope) |
| Explicitly excluded (RAG, vector DBs, browser agents…) | ✅ absent, by design |

## 12. Future expansion

The seams are already cut: a new researched fact = one registry field; a
new capability = tools + an instruction section; a new search surface = one
more leaf agent inside the same budget and harvest. Next candidates, in
order of value: scholarship research (a program-registry extension), SOP/LOR
coaching (C5, pure conversation + document state), intake planning
(deadline-aware next steps), outcome aggregation over verified alumni.

Known open items are tracked in `PHASE4_E2_DEMO_FINDINGS.md` (alumni
domain-attribution fix awaiting approval) and the live-verification queue
is currently gated by a project billing denial, not by code.
