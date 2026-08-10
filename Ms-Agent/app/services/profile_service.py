"""Profile service — deterministic merge, gap detection, and rendering.

The Profile Agent *proposes* a `ProfileUpdate`; this service *decides* what
the stored profile becomes. Merging is code, not prompting, so "existing
information must remain intact" is a property, not a hope.
"""

from __future__ import annotations

from typing import Any

from app.models.student import ProfileUpdate, StudentProfile

# What to ask for next, in value order. The first missing entry is "the
# highest-value missing information" — the one question worth asking.
IMPORTANT_FIELDS: tuple[tuple[str, str], ...] = (
    ("education.cgpa", "Needed to evaluate academic fit for any program."),
    ("education.grading_scale", "A CGPA means nothing without its scale."),
    ("target.country", "Scopes every search and recommendation."),
    ("target.degree", "MS vs other degrees changes the program set."),
    ("target.specialization", "Decides which programs are even relevant."),
    ("target.intake", "Deadlines and planning hang off the intake."),
    ("education.major", "Programs state required academic backgrounds."),
    ("test_scores.ielts", "Most programs require an English test score."),
    ("preferences.budget", "Filters programs the student would never take."),
)


def _get_path(profile: StudentProfile, path: str) -> Any:
    section, field = path.split(".")
    return getattr(getattr(profile, section), field)


def merge_update(
    profile: StudentProfile, update: StudentProfile
) -> tuple[StudentProfile, list[str]]:
    """Merge `update` into `profile`; return the result and changed paths.

    Rules, all deterministic:
    * None / empty in the update never erases a stored value.
    * A conflicting new value wins (the student corrected themselves) and
      the path is reported so the answer can acknowledge the change.
    * Lists union, preserving order, deduplicating case-insensitively.
    """
    merged = profile.model_copy(deep=True)
    changed: list[str] = []

    for section_name in StudentProfile.model_fields:
        current_section = getattr(merged, section_name)
        update_section = getattr(update, section_name)
        for field_name in type(current_section).model_fields:
            new = getattr(update_section, field_name)
            if new is None or new == [] or new == {}:
                continue
            old = getattr(current_section, field_name)
            if isinstance(old, list):
                seen = {str(v).casefold() for v in old}
                additions = [v for v in new if str(v).casefold() not in seen]
                if additions:
                    setattr(current_section, field_name, [*old, *additions])
                    changed.append(f"{section_name}.{field_name}")
            elif old != new:
                setattr(current_section, field_name, new)
                changed.append(f"{section_name}.{field_name}")

    return merged, changed


def missing_important_fields(profile: StudentProfile) -> list[dict[str, str]]:
    """Important fields not yet known, most valuable first."""
    missing = []
    for path, why in IMPORTANT_FIELDS:
        if _get_path(profile, path) is None:
            # An English score on either test satisfies the IELTS slot.
            if path == "test_scores.ielts" and profile.test_scores.toefl is not None:
                continue
            missing.append({"field": path, "why": why})
    return missing


def apply_update(
    profile: StudentProfile, update: ProfileUpdate
) -> tuple[StudentProfile, list[str]]:
    return merge_update(profile, update.profile)
