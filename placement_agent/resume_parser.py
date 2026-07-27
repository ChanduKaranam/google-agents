"""
resume_parser.py
Tools for extracting raw text from uploaded resume files (PDF or DOCX).
"""

import os
import re
from typing import Optional


def _extract_text_from_pdf(file_path: str) -> str:
    """Extract text from a PDF file using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        return "ERROR: pdfplumber is not installed. Run: pip install pdfplumber"

    text_chunks = []
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_chunks.append(page_text)
        return "\n".join(text_chunks).strip()
    except Exception as e:
        return f"ERROR reading PDF: {e}"


def _extract_text_from_docx(file_path: str) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document
    except ImportError:
        return "ERROR: python-docx is not installed. Run: pip install python-docx"

    try:
        doc = Document(file_path)
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs).strip()
    except Exception as e:
        return f"ERROR reading DOCX: {e}"


# ---------------------------------------------------------------------------
# Public ADK tool functions
# ---------------------------------------------------------------------------

def parse_resume(file_path: str) -> dict:
    """
    Parse a resume file (PDF or DOCX) and return its plain text content.

    Args:
        file_path: Absolute or relative path to the resume file.
                   Supported formats: .pdf, .docx

    Returns:
        A dict with keys:
          - success (bool)
          - text (str): extracted resume text on success
          - error (str): error message on failure
          - file_name (str): base name of the file
          - word_count (int): approximate word count
    """
    if not os.path.exists(file_path):
        return {
            "success": False,
            "text": "",
            "error": f"File not found: {file_path}",
            "file_name": os.path.basename(file_path),
            "word_count": 0,
        }

    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        text = _extract_text_from_pdf(file_path)
    elif ext in (".docx", ".doc"):
        text = _extract_text_from_docx(file_path)
    else:
        return {
            "success": False,
            "text": "",
            "error": f"Unsupported file format '{ext}'. Please upload a PDF or DOCX.",
            "file_name": os.path.basename(file_path),
            "word_count": 0,
        }

    if text.startswith("ERROR"):
        return {
            "success": False,
            "text": "",
            "error": text,
            "file_name": os.path.basename(file_path),
            "word_count": 0,
        }

    word_count = len(text.split())
    return {
        "success": True,
        "text": text,
        "error": "",
        "file_name": os.path.basename(file_path),
        "word_count": word_count,
    }


def get_resume_sections(resume_text: str) -> dict:
    """
    Identify and extract standard resume sections from plain text.

    Args:
        resume_text: The raw text content of a resume.

    Returns:
        A dict mapping section names to their extracted content.
        Sections attempted: contact, summary, experience, education,
        skills, certifications, projects, awards.
    """
    # Common section header patterns (case-insensitive)
    section_patterns = {
        "contact": r"(contact\s*(information|details)?)",
        "summary": r"(summary|objective|profile|about\s*me)",
        "experience": r"(experience|work\s*(history|experience)|employment)",
        "education": r"(education|academic|qualification)",
        "skills": r"(skills|technical\s*skills|core\s*competencies|competencies)",
        "certifications": r"(certifications?|licenses?|credentials?)",
        "projects": r"(projects?|portfolio)",
        "awards": r"(awards?|honors?|achievements?|accomplishments?)",
    }

    lines = resume_text.splitlines()
    found_sections: dict[str, str] = {}
    current_section: Optional[str] = None
    buffer: list[str] = []

    for line in lines:
        stripped = line.strip()
        matched_section = None
        for section_name, pattern in section_patterns.items():
            if re.fullmatch(pattern, stripped, re.IGNORECASE):
                matched_section = section_name
                break
        if matched_section:
            # Save previous buffer
            if current_section and buffer:
                found_sections[current_section] = "\n".join(buffer).strip()
            current_section = matched_section
            buffer = []
        elif current_section:
            buffer.append(line)

    # Save last section
    if current_section and buffer:
        found_sections[current_section] = "\n".join(buffer).strip()

    # If no sections were detected at all, return the full text as "body"
    if not found_sections:
        found_sections["body"] = resume_text

    return {
        "sections_found": list(found_sections.keys()),
        "sections": found_sections,
        "total_sections": len(found_sections),
    }
