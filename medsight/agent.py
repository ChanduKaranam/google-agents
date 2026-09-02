"""MedSight — an A2UI-native medical image + medicine study assistant on Google ADK.

MedSight helps medical / allied-health students interpret medical images and
understand medicine topics as an ACADEMIC exercise. It renders native, tappable
A2UI in Gemini Enterprise (via the `show_card` tool) and can export a PDF
summary. Image understanding is native to the Gemini 2.5 models — an uploaded image is
pulled into context with `load_artifacts` and read directly; there is no separate
vision model/endpoint to call.

One agent, not an orchestrator. Every capability that needs real code is a plain
function tool the root calls directly. There are NO Gemini built-in tools here
(no google_search / code_execution), so the "a built-in can't share an agent
with custom tools" rule does not apply.

Rich UI is real A2UI and renders ONLY over the A2A registration path
(`a2aAgentDefinition`) — see `a2a_server.py` + `Dockerfile` + README. On the
managed Agent Engine path (`adkAgentDefinition`) Gemini Enterprise does not
render A2UI and the agent degrades to plain text.

Safety: MedSight uses general Gemini, not a certified medical model, so the
disclaimer / non-diagnosis / refuse-real-patient-data rules in the system prompt
(a2ui_setup.py) are load-bearing. It is a study aid, not a clinical tool.
"""

from google.adk.agents.llm_agent import Agent
from google.adk.tools.load_artifacts_tool import load_artifacts_tool
from google.adk.tools.preload_memory_tool import preload_memory_tool

from .a2ui_setup import A2UI_INSTRUCTION
from .callbacks import remember_session, require_real_user
from .tools import generate_summary_pdf
from .ui_tools import show_card, show_comparison, show_finding_card

# gemini-2.5-flash: chosen for responsiveness — Pro made substantive turns
# (image reads, medicine explainers) take ~10s, too slow for interactive chat.
# Flash is still multimodal (reads images) and is the repo default for most
# agents (incl. the doubt_solver medical specialists). Swap back to
# "gemini-2.5-pro" if you need deeper reasoning at the cost of latency.
MODEL = "gemini-2.5-flash"

root_agent = Agent(
    model=MODEL,
    name="medsight",
    description=(
        "MedSight — a medical image and medicine study assistant. Analyzes "
        "uploaded medical images (X-rays, CT/MRI scans, dermatology photos, "
        "pathology slides, lab reports) and explains medicines, always as an "
        "academic study aid with a consult-a-clinician disclaimer, and can "
        "export a PDF summary. Invoke for interpreting a medical image or a "
        "medicine/medical-study question."
    ),
    instruction=A2UI_INSTRUCTION,
    tools=[
        show_card,
        show_finding_card,
        show_comparison,
        load_artifacts_tool,
        generate_summary_pdf,
        preload_memory_tool,
    ],
    before_agent_callback=require_real_user,
    after_agent_callback=remember_session,
)
