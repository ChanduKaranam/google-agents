# MSBuddy — Master Architecture Migration Analysis

| | |
|---|---|
| **Status** | Analysis only — no code changed |
| **Written** | 2026-08-10 |
| **Baseline** | 100 offline tests green · live flows verified · commits through `8ad178e` |

## A. Current architecture discovered (ahead of the brief's assumption)

The brief describes V1 (52 tests). The repository is at **V2 + Alumni
Intelligence** (100 tests). What actually runs:

```
root_agent (ADK, gemini-2.5-flash)
├── task sub-agents (extract, cannot write): profile_agent · resume_agent
├── search leafs (google_search only, grounding-harvested, budgeted):
│     research_agent · alumni_agent
└── deterministic tools:
      get_profile · update_profile(provenance) · get_interview_state ·
      convert_gpa · clear_profile · save_research(authority gate) ·
      get_programs · match_programs(8 components) · get_next_steps ·
      save_alumni_findings(26-source gate) · get_alumni_signals
```

Infrastructure already proven live: evidence ledger from grounding
metadata; source-authority gating; per-field profile provenance
(user_explicit / resume / user_confirmed) with an unconfirmed-inference
channel; deterministic question-priority engine with intent reordering and
readiness tiers; entity resolution with namesake splitting; denominator-
gated aggregates; search budget; 26-source alumni allowlist.

## B. Proposed architecture — hierarchical in code, flat at runtime

The target diagram's nine domains are right as *organization*. As an ADK
runtime shape, a tree of LLM sub-agents each owning LLM sub-sub-agents is
wrong for this platform, for measured reasons (this session, this stack):

1. `google_search` cannot share an agent with function tools → search
   lives in dedicated leafs, period.
2. AgentTool children receive an **empty memory service** and forwarded
   state only — deep nesting multiplies silent-blindness points.
3. Task-mode agents cannot write state — extraction quality does not
   improve by nesting it deeper.
4. Every LLM hop adds latency, cost, and a place to hallucinate. A
   "Calculation Agent" that is an LLM calling a calculator is strictly
   worse than the calculator.

So each **domain = a module**: deterministic services + gated tools + an
instruction section on the root + (only where a distinct retrieval
contract exists) one search leaf. `app/alumni/` is the proven template.
The user experiences nine specialist domains; the runtime stays one
orchestrator, two extractors, and few search leafs.

## C. Current → new mapping, domain by domain

| Target domain | Already exists (tested) | Missing |
|---|---|---|
| **PROFILE** | extractor + resume agent w/ inference channel · provenance · merge · gap detection · progressive questions · career/financial fields | live file-upload path exercised end-to-end; deterministic skill/project analyzers; `backlogs` field |
| **EXAMS** | `test_requirements` researched per program · IELTS/TOEFL/GRE/GMAT/PTE/Duolingo profile fields · exam-guidance carve-out pattern (sister repo) | exam reference module (structure/validity/scoring — static knowledge) · requirement-matching tool (profile scores vs researched requirements) |
| **CALCULATION** | `convert_gpa` (linear, caveated) · match engine · financial-fit comparison | cost aggregation, loan/EMI, ROI (needs salary evidence rules), score-band tables; university-specific GPA methodology override |
| **UNIVERSITY** | research_agent · PROGRAM_FIELDS incl. deadlines/requirements/structure/scholarships · authority gate · knowledge store · comparison via matching | faculty/lab research slot(s); deadline freshness surfacing; per-program comparison renderer |
| **PLACEMENT** | `career_signals` slot · alumni career/role/company/location analysis with denominators | official **outcomes-report** research path (university career services as first-class facts); salary evidence rules (authoritative sources only) |
| **ALUMNI** | complete: 26-source registry, gate, entity resolution, similarity, career paths — live-verified (12 real admitted alumni) | API clients (scaffolded); program-level filtering nudge |
| **FINANCE** | budget/funding/scholarship profile fields · financial_fit · tuition facts | living-cost fact slot · cost-breakdown calculator · scholarship finder flow (slot exists, flow untested) |
| **VISA** | nothing | new: gov-source allowlist (registry pattern), visa fact slots, instruction section; reuses research_agent |
| **APPLICATION** | `get_next_steps` ladder | document checklist/tracker (port from sister repo, tested pattern exists) · SOP/LOR guidance sections (conversation, not tools) |

## D. Proposed repository structure

```
app/
  agent.py                     # root orchestrator (sections per domain)
  agents/                      # profile · resume · research · alumni leafs
  alumni/                      # (existing — the domain-module template)
  exams/    reference.py, matching.py
  finance/  calculators.py     # cost, loan, ROI — pure
  visa/     sources.py         # gov-source registry
  models/   student.py, program.py, evidence.py, matching.py, exams.py
  services/                    # profile, research, matching, question
  tools/    <domain>_tools.py  # every store-writer is a gate
  config/settings.py           # state keys, budgets, weights
tests/ unit/ integration/ eval/
```

No placeholder folders: a domain package is created in the phase that
implements it.

## E. State/model changes

- `StudentProfile` stays the single source of truth. Add: `education.backlogs`;
  nothing else until a phase needs it.
- New state keys per phase, `user:`-scoped: `user:exam_readiness`,
  `user:financial_plan`, `user:visa_info`, `user:applications`.
- `PROGRAM_FIELDS` grows per phase (`living_cost_estimate`,
  `faculty_research`, `visa_*` live in their own store, not program facts).
- New Pydantic contracts per phase (ExamRequirementMatch, CostBreakdown,
  LoanPlan, VisaChecklist) — same extra="forbid" discipline.

## F. Tool architecture rules (already in force; keep)

1. Every tool that writes a store is a **gate**: allowlist → evidence →
   entity/merge rules → provenance + freshness.
2. Every aggregate carries its **denominator**; pattern language is gated.
3. Every number the student sees comes from deterministic code.
4. High-stakes fields (deadlines, tuition, requirements — extend to
   **salaries** and **visa facts**) demand authoritative sources; community
   sources are refused for them by the gate, not by hope.

## G. Agent/sub-agent hierarchy (runtime)

Now: root + profile_agent + resume_agent (task) + research_agent +
alumni_agent (search leafs). Planned additions: **none for Exams/
Calculation/Finance/Application** (tools + instruction sections);
**Visa reuses research_agent** (gov-source instruction + gate);
**Placement reuses both leafs**. A new leaf is justified only by a
distinct retrieval contract, as alumni was.

## H. Roadmap (brief's phases, re-baselined)

- **Phase 0** — this document. ✅
- **Phase 1 — Profile + Resume Analyzer** (first milestone): live
  file-upload resume test through the UI artifact path; deterministic
  skill/project analyzers feeding domain-inference bases; `backlogs`;
  instruction: program-level qualification when presenting people.
  *Mostly built; the milestone is closing the file-ingestion gap and
  hardening.*
- **Phase 2 — Exams**: reference module + `match_exam_requirements` tool.
- **Phase 3 — Calculation**: finance calculators + score tables; GPA
  methodology overrides.
- **Phase 4 — University**: faculty/labs slot, comparison renderer,
  deadline freshness.
- **Phase 5 — Placement**: outcomes-report facts, salary evidence rules.
- **Phase 6 — Alumni**: ✅ shipped; API clients optional.
- **Phase 7 — Finance**: living-cost slot, cost breakdown, scholarship flow.
- **Phase 8 — Visa**: gov registry + checklist.
- **Phase 9 — Application**: document tracker (port), SOP/LOR sections.
- **Phase 10-11 — Integration & eval**: cross-domain flows, new matching
  signals (only then — per §18, weights stay put until signals are real).

## I. Risks and architectural conflicts

1. **The sub-agent-tree expectation vs ADK reality** — the main conflict;
   resolved by §B (modules, not agent trees). If the UI graph must *look*
   hierarchical, that is presentation, not runtime.
2. **Root instruction growth**: 9 domain sections will strain routing.
   Mitigations: keep sections terse; measure; only if routing degrades,
   split conversational domains behind an AgentTool router (accepting the
   forwarded-state constraints consciously).
3. **Search-budget contention** across domains in one turn — budgets are
   configurable; deep modes raise them explicitly (§29 of alumni brief).
4. **GPA conversion** (§6): current linear conversion is honest but
   generic; university-specific methodology needs a per-university
   override table sourced from official evaluators — Phase 3.
5. **Salary/visa facts are liability-grade**: they enter only through the
   authority gate with government/official-only standing.
6. **Model sensitivity**: grounding reliability is model-dependent
   (measured); any model change requires re-verifying `STATE_EVIDENCE`
   is populated post-research.
```
