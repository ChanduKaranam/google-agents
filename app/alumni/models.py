"""Alumni intelligence contracts.

Privacy is structural: an `AlumniFinding` can only carry the professional
fields below. There is no field for contact details, and no field where a
sensitive attribute (religion, health, politics, ethnicity, orientation,
finances) could legally land — a claim outside the registry is a validation
error, not a moderation decision (§31).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EvidenceStrength = Literal["strong", "moderate", "weak"]

# The only things MSBuddy may know about an alumnus. All professional, all
# the kind of information people publish about themselves professionally.
ALUMNI_FIELDS: frozenset[str] = frozenset(
    {
        "program",
        "graduation_year",
        "company",
        "role",
        "location",
        "skills",
        "research_area",
        "publication",
        "phd_institution",
        "startup",
    }
)

_CONTACT_MARKERS = ("@", "phone", "tel:", "mailto:", "whatsapp")


class AlumniClaim(BaseModel):
    """One professional fact about one person, from one approved source."""

    model_config = ConfigDict(extra="forbid")

    field: str
    value: str
    source_domain: str

    @field_validator("field")
    @classmethod
    def _known_field(cls, v: str) -> str:
        if v not in ALUMNI_FIELDS:
            raise ValueError(
                f"'{v}' is not an allowed alumni field; allowed: "
                f"{sorted(ALUMNI_FIELDS)}"
            )
        return v

    @field_validator("value")
    @classmethod
    def _no_contact_details(cls, v: str) -> str:
        lowered = v.casefold()
        if any(marker in lowered for marker in _CONTACT_MARKERS):
            raise ValueError("contact details are never stored")
        return v


class AlumniFinding(BaseModel):
    """One person the alumni agent proposes, with per-fact sourcing."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2)
    university: str = Field(min_length=2)
    claims: list[AlumniClaim] = Field(default_factory=list)


class StoredEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_key: str
    source_label: str
    source_domain: str
    tier: int
    url: str = ""
    retrieved_at: str = ""


class StoredClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str
    evidence: StoredEvidence
    # Conflicting values for mutable facts (company/role) are retained side
    # by side, never silently resolved (§41).
    conflicts: list[dict] = Field(default_factory=list)


class AlumniRecord(BaseModel):
    """One resolved alumni entity in state, with everything that admitted it."""

    model_config = ConfigDict(extra="forbid")

    name: str
    university: str
    claims: dict[str, StoredClaim] = Field(default_factory=dict)
    source_keys: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = "weak"
    possible_namesake_of: list[str] = Field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.name.strip().casefold()}::{self.university.strip().casefold()}"
