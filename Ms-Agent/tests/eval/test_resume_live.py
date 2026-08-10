"""Live resume-upload test — a real PDF through the real attachment path.

The dev UI delivers an uploaded file to the root agent as an inline-data
part on the user's message; this test does exactly that with an actual PDF
(built byte-by-byte here — tiny, valid, deterministic, and obviously
synthetic). What must hold on any correct run:

* facts printed in the PDF reach the StudentProfile,
* their provenance says `resume`,
* nothing absent from the PDF (English scores) is invented.
"""

from __future__ import annotations

from typing import Any

import pytest
from google.adk.runners import InMemoryRunner
from google.genai import types

from app.agent import root_agent
from app.config.settings import STATE_PROFILE, STATE_PROFILE_META

APP_NAME = "msbuddy"

RESUME_LINES = [
    "Test Student Resume (synthetic fixture)",
    "Education: B.Tech Computer Science and Engineering",
    "Institution: Lendi Institute of Engineering",
    "CGPA: 8.2 out of 10",
    "Graduation year: 2026",
    "Skills: Python, Java, SQL, Machine Learning, TensorFlow",
    "Project: Crop Recommendation using machine learning",
    "Project: Medical Image Classification with CNNs",
    "Internship: Software Developer Intern at ExampleSoft",
    "Certification: TensorFlow Developer Certificate",
]


def make_resume_pdf() -> bytes:
    """A minimal, valid, single-page PDF with the fixture text."""
    text_ops = ["BT", "/F1 11 Tf", "50 780 Td", "14 TL"]
    for line in RESUME_LINES:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        text_ops.append(f"({escaped}) Tj T*")
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode()

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def test_the_fixture_is_a_valid_looking_pdf() -> None:
    """Offline sanity: header, xref, EOF, and the text is embedded."""
    pdf = make_resume_pdf()
    assert pdf.startswith(b"%PDF-1.4")
    assert b"startxref" in pdf and pdf.rstrip().endswith(b"%%EOF")
    assert b"CGPA: 8.2 out of 10" in pdf


@pytest.fixture(scope="module")
def uploaded(live_model: None) -> dict[str, Any]:
    runner = InMemoryRunner(agent=root_agent, app_name=APP_NAME)
    session = runner.session_service.create_session_sync(
        app_name=APP_NAME, user_id="live-resume"
    )
    # One prior conversational fact, to prove merge survival (§5).
    for message in [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text="I want to do my MS in Canada.")],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(
                    text="Here's my resume — please build my profile from it."
                ),
                types.Part.from_bytes(
                    data=make_resume_pdf(), mime_type="application/pdf"
                ),
            ],
        ),
    ]:
        for _ in runner.run(
            user_id="live-resume", session_id=session.id, new_message=message
        ):
            pass
    refreshed = runner.session_service.get_session_sync(
        app_name=APP_NAME, user_id="live-resume", session_id=session.id
    )
    return dict(refreshed.state or {})


def test_pdf_facts_reach_the_profile(uploaded: dict[str, Any]) -> None:
    education = (uploaded.get(STATE_PROFILE) or {}).get("education") or {}
    assert education.get("cgpa") == 8.2
    assert "lendi" in (education.get("institution") or "").lower()
    assert education.get("graduation_year") == 2026


def test_conversation_facts_survive_the_resume(uploaded: dict[str, Any]) -> None:
    target = (uploaded.get(STATE_PROFILE) or {}).get("target") or {}
    assert (target.get("country") or "").lower() == "canada"


def test_resume_facts_carry_resume_provenance(uploaded: dict[str, Any]) -> None:
    fields = (uploaded.get(STATE_PROFILE_META) or {}).get("fields") or {}
    assert fields.get("education.cgpa", {}).get("source") == "resume"
    assert fields.get("target.country", {}).get("source") == "user_explicit"


def test_nothing_absent_from_the_pdf_is_invented(uploaded: dict[str, Any]) -> None:
    scores = (uploaded.get(STATE_PROFILE) or {}).get("test_scores") or {}
    assert scores.get("ielts") is None
    assert scores.get("toefl") is None
    assert scores.get("gre") is None
