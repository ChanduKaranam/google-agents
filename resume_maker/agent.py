"""Resume Maker Agent — ResumeAI, a guided A2UI resume builder on Google ADK.

Rich UI is real A2UI, not prose. The agent carries a custom ``show_card`` tool
(``ui_tools.py``): the model calls it with tiny args (heading, body, button
labels) and the server assembles the native ``Card -> Column -> [Text, Row of
Buttons]`` A2UI that Gemini Enterprise renders. This replaces the A2UI SDK's
``send_a2ui_json_to_client`` toolset, which required the model to emit a large
A2UI JSON string — Gemini malformed that on big cards. The A2UI system prompt
and catalog come from ``a2ui_setup.py``.

This renders as native UI ONLY when the agent is served over A2A and registered
in Gemini Enterprise via the ``a2aAgentDefinition`` path (see ``a2a_server.py``
+ ``Dockerfile`` + README). Registered via the managed Agent Engine path
(``adkAgentDefinition``), Gemini Enterprise does not render A2UI and the agent
degrades to plain text — that is a platform limitation, not a code one.

One agent, not an orchestrator. The whole feature is a single conversational
flow (intake → context → analysis → rewrite → design → PDF → refine), and every
capability that needs real code is a plain function tool the root calls
directly. That means none of the multi-agent traps apply here — there are no
Gemini built-in tools to isolate (``google_search`` etc.), so custom tools and
the model coexist in one agent safely.

Two production rules from ``DEPLOYING_ADK_AGENTS.md`` are wired in below:

* Uploaded files arrive as artifacts with an empty marker, not as text, so the
  root holds ``load_artifacts_tool`` and is told to call it before reading a
  resume — otherwise it sees a filename and may invent the contents.
* A turn that ends on a tool call with no text is a blank screen. The
  instruction forces a text/Card reply plus next-step chips after every tool
  call.

The model runs on ``gemini-2.5-pro``: the rewriting quality (strong verbs,
quantified impact, tone shifts) and the reliability of "always answer after a
tool call" both measurably favour pro over flash for this kind of multi-step,
text-heavy single agent.
"""

from google.adk.agents.llm_agent import Agent
from google.adk.tools.load_artifacts_tool import load_artifacts_tool
from google.adk.tools.preload_memory_tool import preload_memory_tool

from .a2ui_setup import A2UI_INSTRUCTION
from .callbacks import remember_session, require_real_user
from .tools import analyze_resume, export_json_resume, generate_resume_pdf
from .ui_tools import show_card

MODEL = "gemini-2.5-pro"

root_agent = Agent(
    model=MODEL,
    name="resume_maker",
    description=(
        "ResumeAI — a guided resume builder and career coach. Parses an uploaded"
        " or pasted resume, scores it for ATS and keyword fit, rewrites bullets"
        " with quantified impact, and generates a polished PDF in one of five"
        " designs (Classic, Modern, Minimal, Creative, ATS-Safe). Also exports"
        " jsonresume.org JSON. Invoke for anything about building, improving,"
        " analyzing, or formatting a resume/CV."
    ),
    instruction=A2UI_INSTRUCTION,
    tools=[
        # A2UI: the model calls show_card(heading, body, buttons) with tiny args
        # and the server builds the faculty-style Card + tappable Buttons. This
        # replaces the SDK's send_a2ui_json_to_client tool, which required the
        # model to emit a large A2UI JSON string — Gemini malformed that on big
        # cards (the "print(default_api...)" broken-escaping error).
        show_card,
        load_artifacts_tool,
        generate_resume_pdf,
        analyze_resume,
        export_json_resume,
        preload_memory_tool,
    ],
    before_agent_callback=require_real_user,
    after_agent_callback=remember_session,
)
