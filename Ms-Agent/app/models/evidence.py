"""Evidence — the unit of trust for every researched claim.

MSBuddy deals with admissions facts, so a claim without a source is not a
fact, it is a liability. Every important researched value carries one
`Evidence` and one verification status:

* ``verified``            — the source domain was genuinely retrieved this
                            session AND the value appears in text the search
                            runtime attributed to that domain.
* ``partially_verified``  — the domain was retrieved, but the exact value
                            could not be located in attributed text.
* ``unverified``          — neither; reported by the model only.

Source types rank official pages above aggregators; the ranking is data
here and policy in the research service.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VerificationStatus = Literal["verified", "partially_verified", "unverified"]

SourceType = Literal["official", "government", "aggregator", "other"]

# Domains are classified by suffix match against the program's university
# website when known; these keywords are the fallback signal for "official".
OFFICIAL_HINTS = (".edu", ".ac.", "admissions", "graduate")


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_title: str = ""
    source_domain: str
    url: str = ""
    source_type: SourceType = "other"
    quote: str = Field("", description="Verbatim supporting text, when available")
    retrieved_at: str = ""

    @classmethod
    def now_iso(cls) -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()
