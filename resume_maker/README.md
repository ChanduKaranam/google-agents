# Resume Maker Agent — ResumeAI

A guided, conversational resume builder on Google ADK, built to deploy into a
Gemini Enterprise app. It takes a user from an uploaded/pasted resume to a
polished, ATS-optimized PDF through a seven-stage guided flow: intake → context →
analysis → rewrite → design → PDF → refine.

**Rich UI is real A2UI.** At every decision point the agent renders native,
tappable UI in Gemini Enterprise — `Card`s with `Button` rows for suggested
replies and next steps — via a custom `show_card` tool (`ui_tools.py`) that
assembles the A2UI component tree server-side against the `a2ui-agent-sdk` v0.8
basic catalog. This requires serving the agent over **A2A** and registering it
via the `a2aAgentDefinition` path (see [Deploy](#deploy-to-gemini-enterprise));
on the managed Agent Engine path Gemini Enterprise does not render A2UI and the
agent degrades to plain text.

## What it does

- **Intake** — reads an uploaded PDF/DOCX (via `load_artifacts`), pasted text,
  or builds from scratch; extracts name, contact, skills, experience,
  education, projects, certifications, achievements.
- **Analysis** — a *deterministic* ATS score (0–100 with a breakdown), a
  keyword gap against a pasted job description, and per-bullet impact ratings
  (weak/moderate/strong on action verb + quantification). These are real
  computed numbers, not model estimates — see `analysis.py`.
- **Rewrite** — strong action verbs, quantified impact (only where the user
  gave numbers — it never fabricates), a tailored 3-sentence summary, grouped
  skills.
- **Five PDF designs** rendered with ReportLab (`pdf_templates.py`):
  Classic (ATS ~95), Modern sidebar (~80), Minimal (~90), Creative gradient
  (~70), ATS-Safe (~99). The PDF is delivered as a downloadable **artifact**.
- **Export** — jsonresume.org JSON, or a plain-text version.
- **Refinement loop** — "more concise", "add my internship", "change the tone"
  → updates in place and re-exports the PDF.

## Files

| File | Role |
|---|---|
| `agent.py` | `root_agent` — single ADK agent with the A2UI system prompt + the `show_card` tool |
| `a2ui_setup.py` | A2UI wiring: v0.8 catalog, the `show_card` system prompt, and the A2A part converter |
| `ui_tools.py` | `show_card` — builds the `Card -> Column -> [Text, Row of Buttons]` A2UI server-side |
| `a2a_server.py` | Serves the agent over A2A (the endpoint GE's A2UI path registers) — `uvicorn resume_maker.a2a_server:app` |
| `Dockerfile` | Cloud Run image for the A2A server |
| `pdf_templates.py` | Five ReportLab renderers + `normalize_resume` |
| `analysis.py` | Deterministic ATS score, keyword gap, impact scoring |
| `tools.py` | ADK function tools: `generate_resume_pdf`, `analyze_resume`, `export_json_resume` |
| `callbacks.py` | Identity guard + Memory Bank persistence |
| `test_resume.py` | Offline checks (no network, no LLM) |

## Design decisions worth knowing

- **One agent, no orchestrator.** The whole feature is one conversational flow,
  and there are no Gemini built-in tools (`google_search` etc.), so custom
  function tools and the model coexist safely in a single agent. `test_resume.py`
  asserts no built-in ever sneaks in.
- **`resume_json` is a JSON string, not a nested object.** ADK's
  automatic-function-calling doesn't round-trip deep nested schemas reliably;
  the model emits JSON well, and we parse and validate it in `tools.py`.
- **No external font files.** Every template uses the 14 standard PDF fonts, so
  nothing fails at render time in production over a missing `.ttf`.
- **ATS numbers come from code, not the model.** Users act on the score, so it
  has to be reproducible and defensible.
- **Identity guard.** A resume is personal data; the agent refuses a turn that
  arrives without a real `user_id` rather than risk cross-user leakage.

## Run it locally

```bash
# from the repo root, with the project venv
cp resume_maker/.env.example resume_maker/.env   # edit project id if needed
PYTHONPATH=. .venv/bin/python resume_maker/test_resume.py   # offline checks
.venv/bin/adk web        # local chat UI at http://localhost:8000
```

> Local success is not proof it works deployed — file upload and artifact
> download behave differently in Gemini Enterprise. Test the deployed agent.

## A2UI rendering: which components, and the one platform constraint

The agent emits UI from the **A2UI v0.8 basic catalog** (the only version Gemini
Enterprise renders today). The `show_card` tool builds a `Card -> Column ->
[Text, Row of Button]` tree; the v0.8 catalog also offers `MultipleChoice`,
`List`, `Divider`, `Image`, etc. There is **no `ChoicePicker`** in v0.8 — that
name only exists in later drafts.

> **Platform constraint (confirmed in Google Cloud docs):** Gemini Enterprise
> renders A2UI only for agents registered via the **A2A path**
> (`a2aAgentDefinition`) — i.e. a self-hosted A2A endpoint. Managed agents
> deployed to Vertex AI Agent Engine and registered via `adkAgentDefinition` do
> **not** render A2UI today. A2UI in GE is currently **Public Preview**.
> Sources: [Register agents using A2UI and A2A](https://docs.cloud.google.com/gemini/enterprise/docs/a2ui-agents/register-and-manage-an-a2ui-agent),
> [Host an A2UI agent with Cloud Run](https://docs.cloud.google.com/gemini/enterprise/docs/a2ui-agents/tutorial-host-agent-cloud-run).

## Deploy to Gemini Enterprise

To get native A2UI chips/cards, serve the agent over A2A (Cloud Run) and register
it via the **A2A path** — not the Agent Engine path.

```bash
# 1. Build & deploy the A2A server to Cloud Run.
gcloud run deploy resume-maker-a2ui \
  --source resume_maker --region us-central1 --allow-unauthenticated

# 2. Re-point the advertised URL at the Cloud Run URL from step 1, then redeploy.
gcloud run services update resume-maker-a2ui --region us-central1 \
  --set-env-vars A2A_PUBLIC_URL=https://<your-cloud-run-url>

# 3. Sanity-check the agent card (should list the A2UI extension).
curl -s https://<your-cloud-run-url>/.well-known/agent-card.json | jq .capabilities.extensions
```

Then register it in your Gemini Enterprise app via the **A2A** option (Agents →
Add agent → the A2A / `a2aAgentDefinition` path → paste the Cloud Run URL) and
**share** it under User permissions — registering alone does not make it visible.

> **Fallback (plain text only):** if you must use the managed Agent Engine path
> (`adk deploy agent_engine` → register as *Custom agent via Agent Runtime*), the
> agent still runs, but Gemini Enterprise will **not** render A2UI — the model's
> UI intents collapse to text. Use the A2A path above whenever you want the chips.

## Run the A2UI server locally

```bash
.venv/bin/pip install -r resume_maker/requirements.txt
PYTHONPATH=. .venv/bin/uvicorn resume_maker.a2a_server:app --host 0.0.0.0 --port 8080
curl -s http://localhost:8080/.well-known/agent-card.json | jq .capabilities.extensions
```
