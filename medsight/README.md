# MedSight — A2UI Medical Image & Medicine Study Agent

A single multimodal Google ADK agent that helps medical / allied-health students
**as an academic study aid**: it interprets uploaded medical images (X-rays,
CT/MRI, dermatology photos, pathology slides, lab reports) and explains medicines,
then renders native, tappable A2UI in Gemini Enterprise and can export a PDF
summary.

> **MedSight is an informational study aid, not a diagnostic tool and not a
> medical device.** Every result carries a consult-a-clinician disclaimer; it
> refuses personal-symptom questions and suspected real-patient images, and never
> fabricates findings.

**Rich UI is real A2UI.** The model calls custom card tools (`ui_tools.py`) with
tiny args and the server assembles the A2UI component tree against the
`a2ui-agent-sdk` v0.8 basic catalog. This renders natively **only** when the
agent is served over **A2A** and registered via the `a2aAgentDefinition` path
(see [Deploy](#deploy-to-gemini-enterprise)); on the managed Agent Engine path
Gemini Enterprise does not render A2UI and it degrades to plain text.

## What it does

- **Image analysis** — reads an uploaded image (via `load_artifacts`) and, in a
  viva-style flow, invites the student to attempt their own read first, then
  presents a structured **Findings → Impression → Recommendation** report with a
  confidence line and the echoed image thumbnail.
- **Medicine explainer** — terse exam-answer format: class → mechanism →
  indications → key side effects (never dosing/prescribing).
- **Academic case reasoning** — presentation → differentials → distinguishing
  features → investigations.
- **PDF summary** — a downloadable A4 summary delivered as an artifact.

## Files

| File | Role |
|---|---|
| `agent.py` | `root_agent` — single ADK agent (`gemini-2.5-flash`, multimodal) + tools |
| `a2ui_setup.py` | A2UI wiring: v0.8 catalog, the medical system prompt, the A2A part converter |
| `ui_tools.py` | `show_card` (navigation), `show_finding_card` (image echo + confidence + disclaimer footer), `show_comparison` (side-by-side) |
| `tools.py` | `generate_summary_pdf` — Markdown → styled A4 PDF artifact |
| `a2a_server.py` | Serves the agent over A2A — `uvicorn medsight.a2a_server:app` |
| `callbacks.py` | Identity guard (`require_real_user`) + Memory Bank persistence |
| `Dockerfile` | Cloud Run image for the A2A server |

## Design decisions worth knowing

- **One agent, no orchestrator.** Image understanding is native to Gemini 2.5, so
  there is no separate vision model/endpoint. There are no Gemini built-in tools,
  so custom function tools and the model coexist safely in one agent.
- **`gemini-2.5-flash`** for responsiveness (Pro made substantive turns ~10s);
  still multimodal. Swap to `gemini-2.5-pro` in `agent.py` for deeper reasoning at
  the cost of latency.
- **Safety is UI, not just prose.** The consult-a-clinician disclaimer is a fixed
  footer baked into every result card from a single constant, so it can't drift.
- **Vertex `global` endpoint** (`GOOGLE_CLOUD_LOCATION=global`) uses dynamic
  shared quota to avoid `429 RESOURCE_EXHAUSTED` on image-heavy turns.

## Run it locally

```bash
# from the repo root, with the project venv
cp medsight/.env.example medsight/.env      # set your project id
PYTHONPATH=. .venv/bin/adk web              # local chat UI at http://localhost:8000
```

> Local `adk web` renders **plain text only** — the native A2UI cards appear only
> in Gemini Enterprise over the A2A path. Test the deployed agent.

## Deploy to Gemini Enterprise

Serve over A2A (Cloud Run) and register via the **A2A path** — not Agent Engine.

```bash
# 1. Build & deploy the A2A server to Cloud Run.
gcloud run deploy medsight-a2ui \
  --source medsight --region us-central1 --allow-unauthenticated \
  --set-env-vars GOOGLE_GENAI_USE_VERTEXAI=1,GOOGLE_CLOUD_PROJECT=<project>,GOOGLE_CLOUD_LOCATION=global

# 2. Re-point the advertised URL at the Cloud Run URL from step 1.
gcloud run services update medsight-a2ui --region us-central1 \
  --update-env-vars A2A_PUBLIC_URL=https://<your-cloud-run-url>

# 3. Sanity-check the agent card (should list the A2UI extension).
curl -s https://<your-cloud-run-url>/.well-known/agent-card.json | jq .capabilities.extensions
```

Then register it in your Gemini Enterprise app via the **A2A** option (Agents →
Add agent → the `a2aAgentDefinition` path → paste the Cloud Run URL) and **share**
it under User permissions — registering alone does not make it visible.
