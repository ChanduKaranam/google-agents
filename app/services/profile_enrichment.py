"""Deterministic skill and project enrichment — derived, based, bounded.

A keyword canon, not a model: every derived skill names the exact text
evidence that produced it, and nothing outside the canon can ever be
derived. The canon maps surface forms to canonical skills and, where a
technology *implies* a domain (CNN → Computer Vision), the implication is
explicit here — inspectable and testable, never guessed at runtime.

Derived skills are enrichment metadata. They never enter the stated
profile: `technical.skills` holds only what the student or their resume
actually listed.
"""

from __future__ import annotations

import re
from typing import Any

# surface form (matched as a word) → (canonical skill, implied domains)
_CANON: dict[str, tuple[str, tuple[str, ...]]] = {
    "python": ("Python", ()),
    "java": ("Java", ()),
    "c++": ("C++", ()),
    "javascript": ("JavaScript", ()),
    "typescript": ("TypeScript", ()),
    "sql": ("SQL", ()),
    "postgres": ("PostgreSQL", ()),
    "mysql": ("MySQL", ()),
    "mongodb": ("MongoDB", ()),
    "tensorflow": ("TensorFlow", ("Deep Learning",)),
    "pytorch": ("PyTorch", ("Deep Learning",)),
    "keras": ("Keras", ("Deep Learning",)),
    "scikit-learn": ("scikit-learn", ("Machine Learning",)),
    "sklearn": ("scikit-learn", ("Machine Learning",)),
    "machine learning": ("Machine Learning", ()),
    "deep learning": ("Deep Learning", ()),
    "cnn": ("CNN", ("Computer Vision", "Deep Learning")),
    "cnns": ("CNN", ("Computer Vision", "Deep Learning")),
    "computer vision": ("Computer Vision", ()),
    "opencv": ("OpenCV", ("Computer Vision",)),
    "nlp": ("NLP", ()),
    "llm": ("LLMs", ("NLP",)),
    "llms": ("LLMs", ("NLP",)),
    "transformer": ("Transformers", ("NLP", "Deep Learning")),
    "transformers": ("Transformers", ("NLP", "Deep Learning")),
    "react": ("React", ("Web Development",)),
    "node": ("Node.js", ("Web Development",)),
    "django": ("Django", ("Web Development",)),
    "flask": ("Flask", ("Web Development",)),
    "html": ("HTML", ("Web Development",)),
    "css": ("CSS", ("Web Development",)),
    "aws": ("AWS", ("Cloud",)),
    "azure": ("Azure", ("Cloud",)),
    "gcp": ("GCP", ("Cloud",)),
    "docker": ("Docker", ("DevOps",)),
    "kubernetes": ("Kubernetes", ("DevOps",)),
    "spark": ("Apache Spark", ("Data Engineering",)),
    "hadoop": ("Hadoop", ("Data Engineering",)),
    "pandas": ("pandas", ("Data Analysis",)),
    "numpy": ("NumPy", ("Data Analysis",)),
    "data science": ("Data Science", ()),
    "cybersecurity": ("Cybersecurity", ()),
}

_AI_ML_DOMAINS = frozenset(
    {"Machine Learning", "Deep Learning", "Computer Vision", "NLP"}
)
_RESEARCH_MARKERS = (
    "research",
    "paper",
    "publication",
    "published",
    "conference",
    "thesis",
    "journal",
)

# Longest surface forms first, so "machine learning" beats "learning", and
# hard boundaries so "react" never matches inside "reaction".
_PATTERN = re.compile(
    r"(?<![\w+])("
    + "|".join(re.escape(form) for form in sorted(_CANON, key=len, reverse=True))
    + r")(?![\w+])",
    re.IGNORECASE,
)


def derive_skills(text: str) -> list[dict[str, Any]]:
    """Canonical skills the text actually supports, each with its basis."""
    found: dict[str, set[str]] = {}
    for match in _PATTERN.finditer(str(text or "")):
        surface = match.group(0)
        skill, implied = _CANON[surface.casefold()]
        found.setdefault(skill, set()).add(surface)
        for domain in implied:
            found.setdefault(domain, set()).add(surface)
    return [
        {"skill": skill, "basis": sorted(bases)}
        for skill, bases in sorted(found.items())
    ]


def analyze_projects(projects: list[str]) -> list[dict[str, Any]]:
    """Per-project structured signals, only where the description supports
    them. No description marker → the signal is False, never guessed."""
    analyses = []
    for description in projects:
        derived = derive_skills(description)
        skills = {d["skill"] for d in derived}
        domains = sorted(
            skills
            & set().union(
                _AI_ML_DOMAINS,
                {
                    "Web Development",
                    "Cloud",
                    "Data Engineering",
                    "Data Science",
                    "Cybersecurity",
                    "DevOps",
                },
            )
        )
        lowered = str(description).casefold()
        analyses.append(
            {
                "project": description,
                "technologies": sorted(s for s in skills if s not in domains),
                "domains": domains,
                "ai_ml_relevant": bool(skills & _AI_ML_DOMAINS),
                "research_relevant": any(
                    marker in lowered for marker in _RESEARCH_MARKERS
                ),
            }
        )
    return analyses
