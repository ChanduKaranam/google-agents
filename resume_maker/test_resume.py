"""Checks for the things that break silently in the Resume Maker agent.

No network, no LLM calls. Run with:
    .venv/bin/python -m pytest resume_maker/test_resume.py
or just:
    .venv/bin/python resume_maker/test_resume.py
"""

import asyncio
import json
import os
import tempfile

from resume_maker import analysis
from resume_maker.agent import root_agent
from resume_maker.pdf_templates import GENERATORS, normalize_resume, render
from resume_maker.tools import (
    analyze_resume,
    export_json_resume,
    generate_resume_pdf,
)

# A Gemini built-in tool cannot share an agent with custom function tools. This
# agent deliberately uses none — assert that stays true, since adding one later
# (e.g. google_search) would fail only at the Gemini API, possibly in prod.
BUILT_IN_NAMES = {"google_search", "url_context", "code_execution", "computer_use"}

SAMPLE = {
    "name": "Tilak Sharma",
    "role": "Backend Engineer",
    "email": "tilak@email.com",
    "phone": "+91 98765 43210",
    "location": "Bengaluru",
    "linkedin": "linkedin.com/in/tilak",
    "github": "github.com/tilak",
    "summary": "Backend engineer with 3 years building high-throughput APIs.",
    "skills": {
        "Technical": ["Node.js", "TypeScript", "Python", "PostgreSQL", "Redis"],
        "Tools": ["Docker", "Kubernetes", "AWS"],
        "Soft": ["Mentoring"],
    },
    "experience": [
        {
            "role": "Backend Engineer",
            "company": "XYZ Corp",
            "duration": "Jan 2023 – Present",
            "bullets": [
                "Built an ingestion service that reduced data lag by 95%.",
                "Responsible for the database.",  # deliberately weak
            ],
        }
    ],
    "education": [{"degree": "B.Tech CS", "school": "NIT Trichy", "duration": "2018 – 2022"}],
    "projects": [{"name": "OpenTrace", "tech": "Go", "bullets": ["Tracing lib, 400+ stars."]}],
    "certifications": ["AWS Certified"],
    "achievements": ["Won SIH 2021"],
}
SAMPLE_JSON = json.dumps(SAMPLE)


class _StubToolContext:
    """Captures save_artifact so the PDF tool can be tested without a service."""

    def __init__(self):
        self.saved = {}

    async def save_artifact(self, filename, artifact):
        self.saved[filename] = artifact.inline_data.data
        return len(self.saved)


def _tool_name(tool) -> str:
    return getattr(tool, "name", None) or getattr(tool, "__name__", repr(tool))


def test_no_builtin_tools_mixed_with_functions():
    names = {_tool_name(t) for t in root_agent.tools}
    assert not (names & BUILT_IN_NAMES), f"built-in tool present: {names & BUILT_IN_NAMES}"


def test_agent_has_upload_and_generate_tools():
    names = {_tool_name(t) for t in root_agent.tools}
    # load_artifacts is how uploaded resumes are read; without it the agent
    # sees a filename and may invent the contents.
    assert "load_artifacts" in names
    assert "generate_resume_pdf" in names
    assert "analyze_resume" in names


def test_identity_guard_wired():
    assert root_agent.before_agent_callback is not None
    assert root_agent.after_agent_callback is not None


def test_all_templates_render_nonempty():
    for tpl in GENERATORS:
        path = os.path.join(tempfile.gettempdir(), f"_t_{tpl}.pdf")
        render(SAMPLE, tpl, path)
        assert os.path.getsize(path) > 1000, f"{tpl} produced a suspiciously small PDF"
        os.remove(path)


def test_unknown_template_falls_back_not_crash():
    path = os.path.join(tempfile.gettempdir(), "_t_unknown.pdf")
    render(SAMPLE, "does-not-exist", path)  # must not raise
    assert os.path.getsize(path) > 1000
    os.remove(path)


def test_normalize_handles_thin_and_messy_data():
    d = normalize_resume({"name": "A", "skills": "Python, Go, Rust"})
    assert d["skills"] == ["Python", "Go", "Rust"]  # comma string coerced
    assert d["experience"] == [] and d["role"] == ""  # missing sections safe
    d2 = normalize_resume({})  # nothing at all
    assert d2["name"] == "Your Name"


def test_ats_score_is_deterministic_and_bounded():
    a = analysis.ats_score(SAMPLE, "")
    b = analysis.ats_score(SAMPLE, "")
    assert a == b, "ATS score must be reproducible"
    assert 0 <= a["ats_score"] <= 100


def test_impact_flags_weak_bullet():
    ratings = analysis.score_impact(
        ["Built X reducing latency by 40%.", "Responsible for the database."]
    )
    assert ratings[0]["rating"] == "strong"
    assert ratings[1]["rating"] == "weak"
    assert not ratings[1]["quantified"]


def test_keyword_gap_finds_real_missing_terms_only():
    jd = "Backend engineer skilled in Go, Kubernetes, gRPC, Kafka, distributed systems."
    gap = analysis.keyword_gap(SAMPLE, jd)
    assert "grpc" in gap["missing"] and "kafka" in gap["missing"]
    # Filler and punctuation must not leak into missing keywords.
    assert all("." not in m and m not in {"skilled", "need"} for m in gap["missing"])


def test_generate_pdf_saves_artifact():
    ctx = _StubToolContext()
    res = asyncio.run(generate_resume_pdf(SAMPLE_JSON, "modern", ctx))
    assert res["status"] == "generated"
    assert res["filename"] == "Tilak_Sharma_Resume_Backend_Engineer.pdf"
    assert res["filename"] in ctx.saved
    assert ctx.saved[res["filename"]][:4] == b"%PDF"  # real PDF bytes attached


def test_generate_pdf_rejects_bad_json():
    ctx = _StubToolContext()
    res = asyncio.run(generate_resume_pdf("{not json", "modern", ctx))
    assert "error" in res and not ctx.saved


def test_export_json_resume_shape():
    jr = export_json_resume(SAMPLE_JSON)["json_resume"]
    assert jr["basics"]["name"] == "Tilak Sharma"
    assert jr["work"][0]["position"] == "Backend Engineer"
    assert jr["work"][0]["highlights"]  # bullets carried over


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except Exception:  # noqa: BLE001
            failed += 1
            print(f"  FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    raise SystemExit(1 if failed else 0)
