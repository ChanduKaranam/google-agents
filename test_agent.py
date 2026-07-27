"""Checks for the things that break silently.

No network, no LLM calls. Run with: .venv/bin/python -m pytest test_agent.py
or just: .venv/bin/python test_agent.py
"""

import asyncio
import io
import os
import tempfile

from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

from Job_Helper_agent.agent import SPECIALISTS, root_agent
from Job_Helper_agent.tools import list_applications, track_application
from placement_agent.agent import root_agent as placement_root_agent
from placement_agent.resume_parser import parse_resume

# Built-in Gemini tools, which cannot share an agent with function tools.
BUILT_IN_NAMES = {"google_search", "url_context", "code_execution", "computer_use"}

EXPECTED_OUTPUT_KEYS = {
    "profile_agent": "profile",
    "company_agent": "companies",
    "alumni_agent": "alumni",
    "matching_agent": "matches",
    "verification_agent": None,
    "resume_gap_agent": "gaps",
    "outreach_agent": None,
    "tracker_agent": None,
    "coach_agent": None,
}


def _tool_name(tool) -> str:
    if isinstance(tool, AgentTool):
        return tool.agent.name
    return getattr(tool, "name", None) or getattr(tool, "__name__", repr(tool))


def _is_built_in(tool) -> bool:
    return _tool_name(tool) in BUILT_IN_NAMES


def _is_function_tool(tool) -> bool:
    # A plain python function passed to `tools=` is wrapped by ADK, so accept
    # both shapes.
    return callable(tool) and not isinstance(tool, BaseTool) or isinstance(
        tool, (FunctionTool, AgentTool)
    )


def test_root_has_all_specialists_plus_infrastructure_tools():
    names = [_tool_name(t) for t in root_agent.tools]
    for agent in SPECIALISTS:
        assert agent.name in names, f"{agent.name} not wired into root"

    # These two are easy to drop in a refactor and their absence is silent:
    # without load_artifacts the agent can never read an uploaded resume and
    # will likely invent one; without preload_memory a returning student's
    # application history never comes back.
    assert "load_artifacts" in names, "root cannot read uploaded resumes"
    assert "preload_memory" in names, "root cannot recall application history"
    assert "alumni_search_links" in names, "no fallback when alumni search is empty"
    assert len(root_agent.tools) == len(SPECIALISTS) + 3


def test_output_keys_match_the_spec():
    for agent in SPECIALISTS:
        expected = EXPECTED_OUTPUT_KEYS[agent.name]
        assert agent.output_key == expected, (
            f"{agent.name} output_key is {agent.output_key!r}, expected"
            f" {expected!r} -- downstream agents read this via {{key?}}"
        )


def test_no_agent_can_fetch_linkedin():
    """url_context would fetch any URL a student pasted, including LinkedIn.

    robots.txt is `User-agent: * / Disallow: /`, so that would be prohibited
    automated access originating from our production agent. Job descriptions
    now go through fetch_job_description, which blocklists such domains in
    code -- instructions alone have already failed us twice.
    """
    for agent in [root_agent, *SPECIALISTS]:
        assert "url_context" not in [_tool_name(t) for t in (agent.tools or [])], (
            f"{agent.name} holds url_context, which will fetch any URL given to it"
        )


def test_no_agent_mixes_builtin_and_function_tools():
    """The constraint ADK will not enforce for us.

    A Gemini built-in cannot share an LlmAgent with custom function tools. ADK
    raises nothing (llm_agent.py:139-176 silently rewrites instead), and the
    auto-wrap workaround defaults to off, so this fails at the Gemini API --
    potentially only once deployed.
    """
    for agent in [root_agent, *SPECIALISTS]:
        tools = list(agent.tools or [])
        built_ins = [t for t in tools if _is_built_in(t)]
        if not built_ins:
            continue
        assert len(tools) == 1, (
            f"{agent.name} holds built-in {_tool_name(built_ins[0])!r} alongside"
            f" {[_tool_name(t) for t in tools if not _is_built_in(t)]}."
            " Gemini rejects this at request time."
        )


class _FakeContext:
    """Minimal stand-in for ToolContext: the tools only touch .state."""

    def __init__(self):
        self.state = {}


def test_track_application_appends_then_updates():
    ctx = _FakeContext()

    first = track_application("Google", "SWE Intern", "Applied", "via careers page", ctx)
    assert first["total"] == 1
    assert ctx.state["applications"][0]["company"] == "Google"

    track_application("Atlassian", "Backend Intern", "Applied", "", ctx)
    listed = list_applications(ctx)
    assert listed["total"] == 2

    # Same company + role must update in place, not duplicate -- otherwise the
    # coach agent double-counts the pipeline.
    moved = track_application("google", "swe intern", "Interview", "onsite Aug 3", ctx)
    assert "updated" in moved
    assert moved["total"] == 2
    assert ctx.state["applications"][0]["status"] == "Interview"
    assert ctx.state["applications"][0]["notes"] == "onsite Aug 3"


def test_track_application_rejects_unknown_status():
    ctx = _FakeContext()
    result = track_application("Google", "SWE", "Ghosted", "", ctx)
    assert "error" in result
    assert ctx.state.get("applications") in (None, [])


# ---------------------------------------------------------------------------
# placement_agent -- reading the file the user uploaded in Gemini Enterprise
#
# GE never gives a custom agent a file path. It announces the upload as a text
# marker ("<start_of_user_uploaded_file: resume.pdf>", empty between markers)
# and puts the bytes in the artifact service. Measured against a live deployed
# agent 2026-07-22; see .claude/skills/gemini-enterprise-agents. A parser that
# only stats the filesystem can never succeed in the deployed container, and
# the model then invents the resume contents instead of erroring.
# ---------------------------------------------------------------------------

DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class _FakeUploadContext:
    """Stand-in for ToolContext: only the artifact methods are touched."""

    def __init__(self, artifacts=None, has_artifact_service=True):
        self._artifacts = dict(artifacts or {})
        self._has_service = has_artifact_service
        self.state = {}

    async def list_artifacts(self):
        if not self._has_service:
            raise ValueError("Artifact service is not initialized.")
        return list(self._artifacts)

    async def load_artifact(self, filename, version=None):
        if not self._has_service:
            raise ValueError("Artifact service is not initialized.")
        return self._artifacts.get(filename)


def _docx_bytes(paragraphs) -> bytes:
    from docx import Document

    doc = Document()
    for line in paragraphs:
        doc.add_paragraph(line)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _upload(data: bytes, mime_type: str):
    return types.Part.from_bytes(data=data, mime_type=mime_type)


def _pdf_bytes(line: str) -> bytes:
    """A minimal one-page PDF with a real text layer -- no extra dependency."""
    stream = f"BT /F1 12 Tf 72 720 Td ({line}) Tj ET".encode()
    objects = [
        b"<</Type/Catalog/Pages 2 0 R>>",
        b"<</Type/Pages/Kids[3 0 R]/Count 1>>",
        b"<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]"
        b"/Resources<</Font<</F1 5 0 R>>>>/Contents 4 0 R>>",
        b"<</Length " + str(len(stream)).encode() + b">>\nstream\n" + stream + b"\nendstream\n",
        b"<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>",
    ]
    buf, offsets = io.BytesIO(), []
    buf.write(b"%PDF-1.4\n")
    for i, obj in enumerate(objects, 1):
        offsets.append(buf.tell())
        buf.write(str(i).encode() + b" 0 obj\n" + obj + b"\nendobj\n")
    xref = buf.tell()
    buf.write(b"xref\n0 " + str(len(objects) + 1).encode() + b"\n0000000000 65535 f \n")
    for off in offsets:
        buf.write(b"%010d 00000 n \n" % off)
    buf.write(
        b"trailer<</Size " + str(len(objects) + 1).encode() + b"/Root 1 0 R>>\nstartxref\n"
        + str(xref).encode() + b"\n%%EOF\n"
    )
    return buf.getvalue()


def test_parse_resume_reads_an_uploaded_pdf_artifact():
    """PDF is the format users actually upload; extraction runs off bytes."""
    ctx = _FakeUploadContext(
        {"resume.pdf": _upload(_pdf_bytes("Priya Raman Backend Intern Python"), "application/pdf")}
    )
    out = asyncio.run(parse_resume(ctx, "resume.pdf"))

    assert out["success"], out
    assert "Priya Raman" in out["text"]
    assert out["source"] == "uploaded_file"


def test_parse_resume_reads_an_uploaded_docx_artifact():
    """The deployed path: bytes come from the artifact service, not from disk."""
    ctx = _FakeUploadContext(
        {"resume.docx": _upload(_docx_bytes(["Priya Raman", "Backend Intern"]), DOCX_MIME)}
    )
    out = asyncio.run(parse_resume(ctx, "resume.docx"))

    assert out["success"], out
    assert "Priya Raman" in out["text"]
    assert out["source"] == "uploaded_file"
    assert out["word_count"] > 0


def test_parse_resume_reads_docx_table_cells():
    """Resumes are routinely laid out in tables -- paragraphs alone drop them."""
    from docx import Document

    doc = Document()
    doc.add_paragraph("Priya Raman")
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "Skills"
    table.cell(0, 1).text = "Python, Kubernetes"
    buf = io.BytesIO()
    doc.save(buf)

    ctx = _FakeUploadContext({"resume.docx": _upload(buf.getvalue(), DOCX_MIME)})
    out = asyncio.run(parse_resume(ctx, "resume.docx"))

    assert out["success"], out
    assert "Kubernetes" in out["text"], "table cell content was silently dropped"


def test_parse_resume_accepts_the_ge_upload_marker_verbatim():
    """The model sees the marker, not a bare name -- both must resolve."""
    ctx = _FakeUploadContext({"resume.txt": _upload(b"Priya Raman\nBackend Intern", "text/plain")})
    out = asyncio.run(parse_resume(ctx, "<start_of_user_uploaded_file: resume.txt>"))

    assert out["success"], out
    assert "Priya Raman" in out["text"]


def test_parse_resume_finds_the_only_upload_without_being_told_its_name():
    ctx = _FakeUploadContext({"my cv.txt": _upload(b"Priya Raman", "text/plain")})
    out = asyncio.run(parse_resume(ctx))

    assert out["success"], out
    assert out["file_name"] == "my cv.txt"


def test_parse_resume_reports_what_is_attached_when_the_name_is_wrong():
    ctx = _FakeUploadContext({"resume.txt": _upload(b"Priya Raman", "text/plain")})
    out = asyncio.run(parse_resume(ctx, "not-the-file.pdf"))

    assert out["success"] is False
    assert out["available_files"] == ["resume.txt"]


def test_parse_resume_says_nothing_was_uploaded_rather_than_returning_blank():
    """A blank success would let the model hallucinate a resume."""
    ctx = _FakeUploadContext({})
    out = asyncio.run(parse_resume(ctx))

    assert out["success"] is False
    assert out["text"] == ""
    assert "upload" in out["error"].lower()


def test_parse_resume_still_reads_a_local_path_for_adk_web():
    """Local `adk web` runs have no artifact service; a path must still work."""
    fd, path = tempfile.mkstemp(suffix=".txt")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write("Priya Raman\nBackend Intern")
    try:
        out = asyncio.run(parse_resume(_FakeUploadContext(has_artifact_service=False), path))
    finally:
        os.unlink(path)

    assert out["success"], out
    assert out["source"] == "local_path"
    assert "Priya Raman" in out["text"]


def test_parse_resume_flags_a_pdf_with_no_text_layer():
    """A scanned resume must be reported, not returned as an empty success."""
    empty_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
        b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
        b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
        b"trailer<</Root 1 0 R>>\n%%EOF\n"
    )
    ctx = _FakeUploadContext({"scan.pdf": _upload(empty_pdf, "application/pdf")})
    out = asyncio.run(parse_resume(ctx, "scan.pdf"))

    assert out["success"] is False
    assert out["text"] == ""


def test_placement_root_is_told_the_upload_marker_protocol():
    """Guardrail: lose the marker instruction and the model invents resumes."""
    instruction = placement_root_agent.instruction
    assert "<start_of_user_uploaded_file:" in instruction
    assert "parse_resume" in instruction


def test_placement_agents_do_not_mix_builtin_and_function_tools():
    agents = [placement_root_agent, *(placement_root_agent.sub_agents or [])]
    for agent in agents:
        tools = list(agent.tools or [])
        built_ins = [t for t in tools if _is_built_in(t)]
        if built_ins:
            assert len(tools) == 1, (
                f"{agent.name} holds built-in {_tool_name(built_ins[0])!r} alongside"
                " function tools. Gemini rejects this at request time."
            )


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nall checks passed")
