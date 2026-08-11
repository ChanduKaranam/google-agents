# MSBuddy — Tree Architecture

The logical tree, and what each node physically is. Three node kinds:

- **LLM agent** — an actual ADK `Agent` (reasoning/extraction/search).
- **Deterministic service** — plain Python in `app/**`; all classification,
  validation, arithmetic, state mutation and ranking live here.
- **Tool** — the validated boundary the root calls; wraps services.

Two measured ADK constraints shape the physical layout: a Gemini built-in
tool (`google_search`) cannot share an agent with function tools, so
search lives in dedicated leaf agents; and `AgentTool` children get a
private session with forwarded state, so evidence is harvested by
callback into the shared ledger. **The tree below is logical** — nodes
are not made into LLM agents just to deepen it (refactor §11).

```
MSBuddy Orchestrator (root LLM agent — app/agent.py)
│
├── Conversation Intelligence
│   ├── Intent Analyzer ............... service: finance/planner intents; strategy routing in instruction
│   ├── Context Resolver .............. service: services/context_service.py + tool interpret_reply
│   ├── Turn Fact Extractor ........... LLM agent: agents/profile_agent.py (task mode, writes nothing)
│   ├── Session State Manager ......... service: tools/profile_tools.py precedence merge + STATE_SESSION_FACTS
│   ├── Missing Information Analyzer .. service: services/question_service.py (one question, intent-reordered)
│   └── Response Planner .............. root instruction (act-over-ask, §12 pipeline)
│
├── Profile
│   ├── Resume Analyzer ............... LLM agent: agents/resume_agent.py (stated/ambiguous/inferred channels)
│   │   ├── Education/Experience/Skills/Projects/Research/Certification
│   │   │   Analyzers ................. services: profile_enrichment.py (derive_skills, analyze_projects)
│   ├── Academic Profile Analyzer ..... service: matching_service academic components
│   ├── Interest Analyzer ............. inferred_domains channel (needs_confirmation, never auto-fact)
│   ├── Preference/Financial Profile .. StudentProfile.preferences (+ finance planner profile gaps)
│   └── Profile State Manager ......... tools/profile_tools.py (only writer; precedence §2; provenance+history)
│
├── Exams
│   ├── Requirement Analyzer .......... service: exams/requirements.py (6 statuses; absence = unknown)
│   ├── English/GRE Analyzers ......... exams/reference.py + compare_score
│   ├── Exam Comparison ............... exams/conversions.py (linking table, never official equivalence)
│   ├── Discovery ..................... research flow (english/gre requirement slots)
│   └── Exam Recommendation ........... strategy/engine.recommend_exams (shortlist-specific)
│
├── Calculation (the ONLY arithmetic engine)
│   ├── GPA / Score Conversion ........ calc/academic.py
│   ├── English Score Comparison ...... exams/conversions.py
│   ├── Tuition/Living Cost inputs .... finance/analysis.build_cost_model (prepares; never sums)
│   ├── Loan / Budget Fit / ROI ....... calc/finance.py (EMI, budget_fit, payback, convert_currency)
│   └── exposed via tools/calc_tools.py
│
├── University
│   ├── Discovery / Program Research .. research agent flow → save_research gate
│   ├── Requirement Analyzer .......... exams interpreter + application interpreter
│   ├── Deadline Analyzer ............. university/analysis.assess_deadline_freshness
│   ├── Faculty/Lab Research .......... find_faculty_matches (token overlap, named basis)
│   ├── Scholarship Research .......... scholarships/funding_evidence slots
│   └── University Comparison ......... compare_programs (unknown stays unknown; no composite score)
│
├── Placement
│   ├── Research ...................... career fact slots via research flow
│   ├── Career Outcome / Scope ........ placement/analysis.classify_scope (never upgraded)
│   ├── Salary Research ............... extract_salary_attributes (literal text only)
│   └── Career Fit Analyzer ........... analyze_career_fit (deterministic alignment, no probabilities)
│
├── Alumni
│   ├── Discovery ..................... LLM agent: agents/alumni_agent.py (search-only, 26-source allowlist)
│   ├── Verification .................. alumni gate: name-in-retrieved-text, contact markers refused
│   ├── Similarity / Career Path ...... alumni/entity_resolution.py + analysis.py (MIN_PATTERN_N denominators)
│   └── Inspiration ................... get_alumni_signals (examples, never statistics)
│
├── Finance
│   ├── Research Planner .............. finance/planner.py (21 intents → requirements)
│   ├── Tuition/Living/Housing ........ program money slots + scoped FinanceRecords (city/country/provider)
│   ├── Scholarship/Assistantship ..... funding slots + get_funding_options (eligibility, never promises)
│   ├── Loan / Part-Time .............. loan_terms/interest_rate; work rules government-only
│   └── Source registry ............... finance/sources.py (digit-free by structural test)
│
├── Application
│   ├── Requirement Tracker ........... application requirement slots via save_research (authoritative)
│   ├── Readiness Analyzer ............ application/analysis.application_readiness
│   ├── Document Analyzer ............. tracker document states (closed vocabularies)
│   ├── Deadline Planner .............. deadline_urgency (passed is passed, never rolled forward)
│   ├── Gap Analyzer .................. readiness rows + strategy profile_gaps
│   └── Application Strategy .......... tracker next_action ladder
│
└── Strategy
    ├── Profile Strength .............. matching_service.calculate_match_score (weighted components)
    ├── Exam Recommendation ........... strategy/engine.recommend_exams
    ├── University Recommendation ..... synthesize_program (weighted, kind-tagged dimensions)
    ├── Financial Recommendation ...... financial_fit dimension (through app.calc)
    ├── Career / Risk / Opportunity ... career_evidence + match risks + coverage research needs
    └── Plan Generator ................ build_plan (§26 sections, evidence-gated; next best action)

SHARED SERVICES
├── Research Agent .................... LLM agent: agents/research_agent.py
│   └── Google Search Leaf ............ google_search only (ADK isolation constraint)
├── Evidence Ledger ................... STATE_EVIDENCE via harvest_grounding callback
├── Source Authority .................. research_service.classify_source + finance/alumni registries
├── Provenance Manager ................ Evidence model + profile meta (source/status/history)
├── Freshness Manager ................. deadline/money freshness (stated year vs target intake)
└── Calculation Services .............. app/calc (see Calculation above)
```

## Information precedence (refactor §2)

```
1. Student, this turn/session (user_explicit / user_confirmed)
3. Resume analyzed this session
4. Student, previous sessions (user: state, no session-facts entry)
5. Historical resume
6. Inference (never becomes a field without confirmation)
```

Applied silently in `update_profile`: stronger incoming supersedes
(`auto_resolved`, old value → history); weaker incoming is kept as
history (`retained`); equal authority = correction, newest wins. The
session line is `STATE_SESSION_FACTS` (session-scoped key) vs the
persistent `user:` profile. **No path through the code can ask the
student to reconcile a precedence-resolvable difference.**
```
