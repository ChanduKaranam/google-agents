# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Typed models for MS Buddy.

`ClaimTier` is the full five-tier vocabulary from `.agents-cli-spec.md` §7.1.
Phase 1 only ever emits `USER_STATED` and `INFERENCE`; the retrieval tiers
(`VERIFIED`, `REPORTED`) are declared here so the vocabulary has one
definition rather than two, and are unused until C2 lands.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ClaimTier(StrEnum):
    """Provenance tier for any value MS Buddy holds (spec §7.1).

    There is deliberately no tier meaning "the model knows this".
    """

    VERIFIED = "VERIFIED"
    REPORTED = "REPORTED"
    INFERENCE = "INFERENCE"
    USER_STATED = "USER_STATED"
    UNKNOWN = "UNKNOWN"


class ProvenancedValue(BaseModel):
    """A single profile value together with where it came from.

    Every stored profile field is wrapped in one of these. A bare value can
    never enter the profile — that is what makes "zero unstated fields ever
    written" (C1 evaluation criterion a) checkable rather than aspirational.
    """

    model_config = ConfigDict(extra="forbid")

    value: str | float | int | list[str]
    tier: ClaimTier
    recorded_at: str = Field(description="ISO-8601 UTC timestamp.")
    evidence_span: str | None = Field(
        default=None,
        description="Verbatim student text this value was taken from. "
        "Required for USER_STATED, absent for INFERENCE.",
    )
    rule_id: str | None = Field(
        default=None,
        description="Versioned derivation rule id, e.g. "
        "'gpa_conv:cgpa_10_to_us_4pt:v1'. Required for INFERENCE.",
    )
    superseded: list[str] = Field(
        default_factory=list,
        description="Prior values, newest last. Kept because silent overwrite "
        "of a corrected value is a named C1 failure case.",
    )


# --- Profile extractor agent I/O (spec §4.1: mode='task' + schemas) ---------


class ExtractionInput(BaseModel):
    """Input contract for `profile_extractor_agent`."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(
        description="The student's own words to extract profile fields from."
    )


class ExtractedField(BaseModel):
    """One candidate profile field, with the text it was taken from."""

    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(description="Registry field name, e.g. 'gre_quant'.")
    value: str = Field(description="The extracted value, as a string.")
    evidence_span: str = Field(
        description="Verbatim substring of the student's text supporting this "
        "value. Must be copied exactly, not paraphrased."
    )


class ExtractionOutput(BaseModel):
    """Output contract for `profile_extractor_agent`."""

    model_config = ConfigDict(extra="forbid")

    extracted: list[ExtractedField] = Field(
        default_factory=list,
        description="Fields explicitly stated by the student. Empty if none.",
    )
    ambiguous: list[str] = Field(
        default_factory=list,
        description="Things the student mentioned that could not be resolved "
        "to a single unambiguous value, phrased as a question to ask them.",
    )


# --- C2 program research ---------------------------------------------------


class ProgramClaim(BaseModel):
    """One retrieved fact about a program, with the source that carries it.

    `source_domain` and `supporting_quote` are both required and both are
    checked against what the runtime actually retrieved. A claim naming a
    domain that was never fetched, or quoting text that was never grounded,
    is refused — so a citation cannot be invented to dress up a guess.
    """

    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(
        description="Program field name, e.g. 'application_deadline'."
    )
    value: str = Field(description="The value exactly as the source states it.")
    source_domain: str = Field(
        description="Domain of the source that states this, e.g. 'ethz.ch'. "
        "Must be one of the domains actually retrieved this turn."
    )
    supporting_quote: str = Field(
        description="Verbatim text from that source which states this value. "
        "Copied, never paraphrased."
    )


# --- C3 comparison ---------------------------------------------------------


class DimensionWeight(BaseModel):
    """How much one comparison dimension matters to the student.

    Importance is a **word**, not a number. The word-to-number mapping lives
    in `app.scoring.IMPORTANCE_WEIGHTS` and is shown to the student, so the
    model cannot invent a weight and the student is never anchored on a
    framing they did not see.
    """

    model_config = ConfigDict(extra="forbid")

    dimension: str = Field(description="One of: cost, duration, stem, test_burden.")
    importance: str = Field(
        description="One of: critical, very important, important, "
        "slightly important, not important. Use the student's own words "
        "where they map cleanly; ask them rather than guessing."
    )


# --- C4 alumni -------------------------------------------------------------


class AlumniClaimInput(BaseModel):
    """One proposed fact about a person, with the source that carries it.

    A *proposal*. Nothing here is trusted: the storage layer re-derives the
    tier from the source class, re-validates the value, and refuses anything
    the source has no standing to say. The model may propose a candidate;
    only deterministic code admits one.
    """

    model_config = ConfigDict(extra="forbid")

    field_name: str = Field(
        description="Alumni field name, e.g. 'employer' or 'graduation_year'."
    )
    value: str = Field(description="The value exactly as the source states it.")
    source_domain: str = Field(
        description="Domain of the source stating this, e.g. 'tudelft.nl'. "
        "Must be one of the domains actually retrieved this turn."
    )
    supporting_quote: str = Field(
        description="Verbatim text from that source which names the person "
        "and states this value. Copied, never paraphrased."
    )
    source_url: str | None = Field(
        default=None,
        description="The grounding redirect the quote came from, if known.",
    )


class AlumniCandidate(BaseModel):
    """A person a search proposed, before any of it has been verified.

    `university` is mandatory and load-bearing: it is half the identity key,
    and without an institutional anchor there is no way to tell one
    `John Smith` from another. A candidate without it is refused rather than
    stored under a bare name.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(description="The person's name exactly as published.")
    university: str = Field(
        description="The institution this person is claimed to have attended."
    )
    claims: list[AlumniClaimInput] = Field(
        default_factory=list,
        description="Facts proposed about this person, each with its source.",
    )
