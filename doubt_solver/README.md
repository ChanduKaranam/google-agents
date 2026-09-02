# Doubt Solver — MRU Multi-Department Study Agent

A Google ADK agent for Malla Reddy University (MRU) students. A **coordinator**
identifies which department a student's question belongs to and delegates to one
of **14 specialist sub-agents**, which answer in their domain and can export
styled PDF notes.

## Architecture

```
Student question
   │
 root_agent  (mru_doubt_solver_coordinator, gemini-2.5-flash)
   • identifies the department; asks ONE clarifying question if ambiguous
   • handles greetings / "what can you do" itself; never answers subject content
   │  transfer_to_agent(...)
   ▼
 one of 14 specialists (each gemini-2.5-flash, each with the generate_pdf tool)
```

Sub-agents (`sub_agents/`):

- **Engineering / tech:** `cse`, `it`, `ece`, `eee`, `mech`, `civil`, `mca_bca`
- **Other schools:** `management`, `agriculture`, `arts`, `healthcare` (applied
  allied-health technician programs)
- **Medical sciences:** `preclinical` (Anatomy/Physiology/Biochemistry),
  `paraclinical` (Pathology/Pharmacology/Microbiology), `clinical`
  (Medicine/Surgery/Pediatrics/OB-GYN)

The coordinator's instruction includes a routing rule that maps medical
disciplines to the three medical agents and applied allied-health programs to
`healthcare`.

## Files

| File | Role |
|---|---|
| `agent.py` | `root_agent` coordinator — routing instruction + `sub_agents=[...]` |
| `sub_agents/` | the 14 specialist agents + `__init__.py` exporting them |
| `tools/pdf_tool.py` | `generate_pdf` — Markdown → styled A4 PDF (headings, tables, syntax-highlighted code) delivered as an artifact |

## Design notes

- **Router pattern, not `AgentTool`.** The coordinator uses `sub_agents=[...]`
  (transfer), so a specialist replies to the user directly and shares the session.
- **Plain text, Agent Engine path.** This agent is deployed via
  `adk deploy agent_engine` (`adkAgentDefinition`); it does not use A2UI. The
  PDF is the one rich artifact, delivered via `tool_context.save_artifact`.
- **Per-domain instructions are explicit per file** so each specialist's scope
  and answer style can be tuned independently.

## Run it locally

```bash
# from the repo root, with the project venv (Python 3.12 + all deps)
cp doubt_solver/.env.example doubt_solver/.env   # set your project id
PYTHONPATH=. .venv/bin/adk web                    # local chat UI
```

## Deploy

```bash
.venv/bin/adk deploy agent_engine \
  --project=<project> --region=us-central1 \
  --display_name="Doubt Solver" \
  --description="Routes a student's doubt to the right department specialist." \
  doubt_solver
```

Then register the printed `reasoningEngines/...` path in your Gemini Enterprise
app (Agents → Add agent → Custom agent via Agent Runtime) and **share** it.
