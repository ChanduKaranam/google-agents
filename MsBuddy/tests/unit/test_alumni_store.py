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

"""Deterministic alumni storage (C4 Stage B).

The storage layer is where "the LLM is never the authority for whether an
alumnus exists" stops being a principle and becomes code, so most of what
follows asserts a **refusal**.
"""

from __future__ import annotations

import copy

import pytest

from app.alumni_store import (
    URL_RESOLVED,
    URL_UNRESOLVED,
    admit_candidate,
    apply_alumni_claim,
    empty_alumni_store,
    export_alumni,
    is_compatible,
    make_alumni_evidence,
    read_alumni_store,
    records_for,
    render_alumni_store,
    render_person,
    tier_for,
    unknown_fields,
    write_alumni_store,
)
from app.config import STATE_ALUMNI
from app.reference.alumni_fields import ALL_FIELD_NAMES, PROHIBITED_FIELDS
from app.reference.source_authority import (
    AGGREGATOR,
    COMPANY_OFFICIAL,
    EXCLUDED,
    PROFESSIONAL_ORG,
    PUBLIC_PROFILE,
    REPUTABLE_PUBLICATION,
    UNIVERSITY_ALUMNI_PAGE,
    UNIVERSITY_OFFICIAL,
)
from app.schemas import AlumniCandidate, AlumniClaimInput

DELFT = "TU Delft"
OLD = "2020-01-01T00:00:00+00:00"
NEW = "2026-07-30T10:00:00+00:00"


def evidence(
    source_class: str = UNIVERSITY_OFFICIAL,
    domain: str = "tudelft.nl",
    field_name: str = "program",
    quote: str = "Ada Lovelace completed the MSc Computer Science.",
    retrieved_at: str = NEW,
    **extra: object,
) -> dict:
    return make_alumni_evidence(
        source_domain=domain,
        source_class=source_class,
        supporting_quote=quote,
        field_name=field_name,
        retrieved_at=retrieved_at,
        **extra,  # type: ignore[arg-type]
    )


def claim(field_name: str, value: str, **kwargs: object) -> dict:
    return {
        "field_name": field_name,
        "value": value,
        "evidence": evidence(field_name=field_name, **kwargs),  # type: ignore[arg-type]
    }


def affiliation(**kwargs: object) -> dict:
    """Every person needs one of these — a claim that they attended at all."""
    return claim("university_affiliation", DELFT, **kwargs)


def valid_claims() -> list[dict]:
    return [
        affiliation(),
        claim("program", "MSc Computer Science"),
        claim("graduation_year", "2021"),
    ]


# --- A valid record --------------------------------------------------------


def test_a_valid_candidate_is_admitted() -> None:
    store = empty_alumni_store()
    result = admit_candidate(store, "Ada Lovelace", DELFT, valid_claims())

    assert result["status"] == "success"
    assert result["rejected"] == []
    assert result["identity_key"] == "ada-lovelace@tu-delft"
    assert result["record"]["fields"]["program"]["value"] == "MSc Computer Science"
    assert result["record"]["fields"]["program"]["tier"] == "VERIFIED"


def test_unsourced_fields_are_named_not_omitted() -> None:
    store = empty_alumni_store()
    result = admit_candidate(store, "Ada Lovelace", DELFT, valid_claims())
    record = result["record"]
    assert set(record["fields"]) | set(record["unknown_fields"]) == set(ALL_FIELD_NAMES)
    assert "employer" in record["unknown_fields"]


def test_an_empty_store_is_a_valid_state() -> None:
    """A program with no public alumni footprint is a real answer."""
    rendered = render_alumni_store(empty_alumni_store())
    assert rendered["is_empty"] is True
    assert rendered["person_count"] == 0
    assert rendered["people"] == []


# --- Origination: only strong sources may create a person ------------------


@pytest.mark.parametrize(
    "weak", [AGGREGATOR, PUBLIC_PROFILE, REPUTABLE_PUBLICATION, EXCLUDED]
)
def test_a_weak_source_cannot_create_a_person(weak: str) -> None:
    """A search snippet must not be able to mint a human being."""
    store = empty_alumni_store()
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(source_class=weak, domain="shiksha.com")],
    )
    assert result["status"] == "error"
    # The identifier is fixed by PHASE4_STAGE0_DECISION.md §9 gate 3, which
    # is release-blocking. Stage H will assert this exact string, so it is
    # pinned here rather than left to drift.
    assert result["reason"] == "source_cannot_originate"
    assert store["people"] == {}


@pytest.mark.parametrize(
    "strong",
    [UNIVERSITY_OFFICIAL, UNIVERSITY_ALUMNI_PAGE, COMPANY_OFFICIAL, PROFESSIONAL_ORG],
)
def test_an_approved_source_may_create_a_person(strong: str) -> None:
    store = empty_alumni_store()
    result = admit_candidate(
        store, "Ada Lovelace", DELFT, [affiliation(source_class=strong)]
    )
    assert result["status"] == "success"
    assert result["record"]["originated_by"] == strong


def test_linkedin_cannot_originate_or_corroborate() -> None:
    store = empty_alumni_store()
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(source_class=EXCLUDED, domain="linkedin.com")],
    )
    assert result["status"] == "error"
    assert store["people"] == {}


# --- A person needs an anchor and an affiliation ---------------------------


def test_a_person_without_an_institution_is_not_stored() -> None:
    store = empty_alumni_store()
    result = admit_candidate(store, "Ada Lovelace", "", valid_claims())
    assert result["reason"] == "identity_unresolvable"
    assert store["people"] == {}


def test_a_person_without_a_usable_name_is_not_stored() -> None:
    store = empty_alumni_store()
    assert (
        admit_candidate(store, "!!!", DELFT, valid_claims())["reason"]
        == "identity_unresolvable"
    )
    assert store["people"] == {}


def test_a_name_near_a_university_is_not_an_alumnus() -> None:
    """Something must actually claim they attended."""
    store = empty_alumni_store()
    result = admit_candidate(
        store, "Ada Lovelace", DELFT, [claim("employer", "Booking.com")]
    )
    assert result["reason"] == "no_affiliation_claim"
    assert store["people"] == {}


# --- Field-scoped authority at the storage boundary ------------------------


def test_a_company_may_not_state_a_graduation_year() -> None:
    """The approved Stage 0 rule, enforced in storage."""
    store = empty_alumni_store()
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [
            affiliation(source_class=COMPANY_OFFICIAL, domain="booking.com"),
            claim(
                "graduation_year",
                "2021",
                source_class=COMPANY_OFFICIAL,
                domain="booking.com",
            ),
        ],
    )
    rejected = {r["field"]: r for r in result["rejected"]}
    assert rejected["graduation_year"]["reason"] == "source_lacks_authority"
    assert "graduation_year" in result["record"]["unknown_fields"]


def test_a_conference_may_not_state_a_graduation_year() -> None:
    store = empty_alumni_store()
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [
            affiliation(source_class=PROFESSIONAL_ORG, domain="acm.org"),
            claim(
                "graduation_year",
                "2021",
                source_class=PROFESSIONAL_ORG,
                domain="acm.org",
            ),
        ],
    )
    assert result["rejected"][0]["reason"] == "source_lacks_authority"


def test_tier_is_derived_from_authority_not_supplied() -> None:
    """A caller cannot assert that a claim is VERIFIED."""
    assert tier_for(UNIVERSITY_OFFICIAL, "program") == "VERIFIED"
    assert tier_for(UNIVERSITY_OFFICIAL, "employer") == "REPORTED"
    assert tier_for(COMPANY_OFFICIAL, "employer") == "VERIFIED"
    assert tier_for(COMPANY_OFFICIAL, "graduation_year") is None
    assert tier_for(AGGREGATOR, "program") == "REPORTED"


def test_a_university_employer_claim_is_reported_not_verified() -> None:
    """Its employer line is historical: true when published, unknown now."""
    store = empty_alumni_store()
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("employer", "Booking.com")],
    )
    assert result["record"]["fields"]["employer"]["tier"] == "REPORTED"


def test_applying_a_refused_claim_directly_raises() -> None:
    """The low-level helper refuses too; the guard is not only in admission."""
    store = empty_alumni_store()
    admit_candidate(store, "Ada Lovelace", DELFT, [affiliation()])
    record = next(iter(store["people"].values()))
    with pytest.raises(ValueError, match="no standing"):
        apply_alumni_claim(
            record,
            "graduation_year",
            "2021",
            evidence(source_class=COMPANY_OFFICIAL, field_name="graduation_year"),
        )


# --- Field and value validation --------------------------------------------


def test_an_unknown_field_is_refused() -> None:
    store = empty_alumni_store()
    result = admit_candidate(
        store, "Ada Lovelace", DELFT, [affiliation(), claim("favourite_colour", "blue")]
    )
    assert result["rejected"][0]["reason"] == "unknown_field"


def test_a_malformed_graduation_year_is_refused() -> None:
    store = empty_alumni_store()
    result = admit_candidate(
        store, "Ada Lovelace", DELFT, [affiliation(), claim("graduation_year", "21")]
    )
    assert result["rejected"][0]["reason"] == "not_a_four_digit_year"
    assert "graduation_year" in result["record"]["unknown_fields"]


def test_an_empty_value_is_refused() -> None:
    store = empty_alumni_store()
    result = admit_candidate(
        store, "Ada Lovelace", DELFT, [affiliation(), claim("employer", "  ")]
    )
    assert result["rejected"][0]["reason"] == "empty_value"


# --- Privacy ---------------------------------------------------------------


@pytest.mark.parametrize(
    "field", ["email", "phone", "home_address", "gender", "salary"]
)
def test_a_prohibited_field_is_refused(field: str) -> None:
    store = empty_alumni_store()
    result = admit_candidate(
        store, "Ada Lovelace", DELFT, [affiliation(), claim(field, "anything")]
    )
    assert result["rejected"][0]["reason"] == "prohibited_field"
    assert field not in result["record"]["fields"]


def test_contact_details_smuggled_into_a_permitted_field_are_refused() -> None:
    store = empty_alumni_store()
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("role", "Engineer, ada@example.com")],
    )
    assert result["rejected"][0]["reason"] == "contact_details_in_value"


def test_no_prohibited_key_can_reach_a_rendered_record() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "Ada Lovelace", DELFT, valid_claims())
    for person in render_alumni_store(store)["people"]:
        assert PROHIBITED_FIELDS.isdisjoint(set(person["fields"]))


# --- Identity: the merges that must never happen ---------------------------


def test_the_same_name_at_two_universities_stays_two_people() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "John Smith", "University A", [affiliation()])
    admit_candidate(store, "John Smith", "University B", [affiliation()])
    assert len(store["people"]) == 2


def test_bob_is_not_robert() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "Bob Smith", DELFT, [affiliation()])
    admit_candidate(store, "Robert Smith", DELFT, [affiliation()])
    assert len(store["people"]) == 2


def test_an_initial_is_not_a_first_name() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "J. Smith", DELFT, [affiliation()])
    admit_candidate(store, "John Smith", DELFT, [affiliation()])
    assert len(store["people"]) == 2


def test_the_same_person_written_differently_is_one_record() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "José Álvarez", DELFT, [affiliation()])
    admit_candidate(store, "Jose Alvarez", DELFT, [affiliation()])
    assert len(store["people"]) == 1


# --- Namesakes under one identity key --------------------------------------


def test_a_conflicting_graduation_year_splits_rather_than_merges() -> None:
    """The case where merging would fabricate a person."""
    store = empty_alumni_store()
    admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("graduation_year", "2015")]
    )
    second = admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("graduation_year", "2021")]
    )

    assert second["namesake_split"] is True
    assert len(store["people"]) == 2
    assert second["record_id"].endswith("#2")


def test_a_conflicting_program_splits() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("program", "MSc CS")]
    )
    second = admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("program", "MSc Aerospace")]
    )
    assert second["namesake_split"] is True


def test_split_records_are_cross_linked_so_ambiguity_stays_visible() -> None:
    store = empty_alumni_store()
    first = admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("graduation_year", "2015")]
    )
    second = admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("graduation_year", "2021")]
    )
    people = {p["record_id"]: p for p in render_alumni_store(store)["people"]}
    assert second["record_id"] in people[first["record_id"]]["possible_namesakes"]
    assert first["record_id"] in people[second["record_id"]]["possible_namesakes"]


def test_a_matching_discriminator_merges_into_one_record() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("graduation_year", "2021")]
    )
    second = admit_candidate(
        store,
        "John Smith",
        DELFT,
        [affiliation(), claim("graduation_year", "2021"), claim("employer", "Booking")],
    )
    assert second["namesake_split"] is False
    assert len(store["people"]) == 1


def test_absent_discriminators_never_contradict() -> None:
    """A record with no stored year is compatible with any year."""
    record = {"fields": {}}
    assert is_compatible(record, {"graduation_year": "2021"}) is True


def test_a_present_and_different_discriminator_contradicts() -> None:
    record = {"fields": {"graduation_year": {"value": "2015"}}}
    assert is_compatible(record, {"graduation_year": "2021"}) is False
    assert is_compatible(record, {"graduation_year": "2015"}) is True


def test_employer_is_not_a_discriminator() -> None:
    """People change jobs; that is not evidence of a different person."""
    store = empty_alumni_store()
    admit_candidate(store, "John Smith", DELFT, [affiliation(), claim("employer", "A")])
    second = admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("employer", "B")]
    )
    assert second["namesake_split"] is False
    assert len(store["people"]) == 1


def test_records_for_finds_every_record_under_a_key() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("graduation_year", "2015")]
    )
    admit_candidate(
        store, "John Smith", DELFT, [affiliation(), claim("graduation_year", "2021")]
    )
    assert len(records_for(store, "john-smith@tu-delft")) == 2


# --- Sources, conflicts, corroboration -------------------------------------


def test_a_second_source_agreeing_is_corroboration_not_a_duplicate() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store, "Ada Lovelace", DELFT, [affiliation(), claim("employer", "X")]
    )
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("employer", "X", domain="acm.org",
                              source_class=PROFESSIONAL_ORG)],
    )  # fmt: skip
    field = result["record"]["fields"]["employer"]
    assert field["source_count"] == 2
    assert field["corroborations"]
    assert field["conflicts"] == []


def test_restating_the_same_value_from_the_same_source_does_not_duplicate() -> None:
    store = empty_alumni_store()
    for _ in range(3):
        result = admit_candidate(
            store, "Ada Lovelace", DELFT, [affiliation(), claim("employer", "X")]
        )
    assert result["record"]["fields"]["employer"]["source_count"] == 1


def test_disagreeing_sources_are_both_kept() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store, "Ada Lovelace", DELFT, [affiliation(), claim("employer", "X")]
    )
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("employer", "Y", domain="shiksha.com",
                              source_class=AGGREGATOR)],
    )  # fmt: skip
    field = result["record"]["fields"]["employer"]
    assert field["conflicts"], "the disagreeing value was discarded"
    assert {field["value"], field["conflicts"][0]["value"]} == {"X", "Y"}


def test_a_stronger_source_is_preferred_over_a_weaker_one() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("employer", "Aggregated", domain="shiksha.com",
                              source_class=AGGREGATOR)],
    )  # fmt: skip
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("employer", "Official", domain="booking.com",
                              source_class=COMPANY_OFFICIAL)],
    )  # fmt: skip
    field = result["record"]["fields"]["employer"]
    assert field["tier"] == "VERIFIED"
    assert field["value"] == "Official"


def test_a_weaker_source_never_displaces_a_stronger_one() -> None:
    """The Phase 2 audit defect, guarded for alumni."""
    store = empty_alumni_store()
    admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("employer", "Official", domain="booking.com",
                              source_class=COMPANY_OFFICIAL)],
    )  # fmt: skip
    result = admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("employer", "Official", domain="shiksha.com",
                              source_class=AGGREGATOR)],
    )  # fmt: skip
    field = result["record"]["fields"]["employer"]
    assert field["tier"] == "VERIFIED"
    assert field["source_domain"] == "booking.com"


# --- Provenance preservation ------------------------------------------------


def test_every_provenance_key_survives_storage_and_rendering() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [
            affiliation(),
            claim(
                "program",
                "MSc Computer Science",
                source_url="https://vertexaisearch.cloud.google.com/x",
                resolved_url="https://www.tudelft.nl/alumni/ada",
                url_resolution_status=URL_RESOLVED,
            ),
        ],
    )
    field = render_alumni_store(store)["people"][0]["fields"]["program"]
    assert field["source_domain"] == "tudelft.nl"
    assert field["source_class"] == UNIVERSITY_OFFICIAL
    assert field["authority"] == "verify"
    assert field["source_url"] == "https://vertexaisearch.cloud.google.com/x"
    assert field["resolved_url"] == "https://www.tudelft.nl/alumni/ada"
    assert field["url_resolution_status"] == URL_RESOLVED
    assert field["supporting_quote"]
    assert field["retrieved_at"] == NEW
    assert field["staleness_class"] == "PERSON"
    assert field["tier"] == "VERIFIED"


def test_an_unresolved_url_is_recorded_as_such_not_hidden() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [
            affiliation(),
            claim("program", "MSc CS", url_resolution_status=URL_UNRESOLVED),
        ],
    )
    field = render_person(next(iter(store["people"].values())))["fields"]["program"]
    assert field["url_resolution_status"] == URL_UNRESOLVED
    assert field["resolved_url"] is None


def test_every_alumni_claim_carries_the_person_ttl() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "Ada Lovelace", DELFT, valid_claims())
    for field in render_alumni_store(store)["people"][0]["fields"].values():
        assert field["staleness_class"] == "PERSON"


def test_an_aged_claim_is_flagged_stale() -> None:
    store = empty_alumni_store()
    admit_candidate(
        store,
        "Ada Lovelace",
        DELFT,
        [affiliation(), claim("employer", "X", retrieved_at=OLD)],
    )
    person = render_alumni_store(store)["people"][0]
    assert "employer" in person["stale_fields"]
    assert person["fields"]["employer"]["is_stale"] is True
    assert "re-check" in person["fields"]["employer"]["staleness_notice"].lower()


def test_a_fresh_claim_is_not_stale() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "Ada Lovelace", DELFT, [affiliation()])
    person = render_alumni_store(store)["people"][0]
    assert person["stale_fields"] == []


# --- State round-trip ------------------------------------------------------


def test_state_round_trip_uses_copies() -> None:
    state: dict = {}
    store = read_alumni_store(state, STATE_ALUMNI)
    admit_candidate(store, "Ada Lovelace", DELFT, valid_claims())
    assert STATE_ALUMNI not in state, "reading must not write"

    write_alumni_store(state, STATE_ALUMNI, store)
    again = read_alumni_store(state, STATE_ALUMNI)
    again["people"]["ada-lovelace@tu-delft"]["name_as_published"] = "MUTATED"
    assert (
        state[STATE_ALUMNI]["people"]["ada-lovelace@tu-delft"]["name_as_published"]
        == "Ada Lovelace"
    )


def test_read_tolerates_corrupt_state() -> None:
    for junk in ("nonsense", 7, {"unexpected": True}, None, []):
        assert read_alumni_store({STATE_ALUMNI: junk}, STATE_ALUMNI)["people"] == {}


def test_storage_is_deterministic_across_repeated_runs() -> None:
    def build() -> dict:
        store = empty_alumni_store()
        admit_candidate(store, "Ada Lovelace", DELFT, valid_claims())
        admit_candidate(store, "Jean-Luc Picard", DELFT, [affiliation()])
        rendered = render_alumni_store(store)
        for person in rendered["people"]:
            for field in person["fields"].values():
                field.pop("retrieved_at", None)
        return rendered

    first = build()
    assert [p["record_id"] for p in first["people"]] == [
        p["record_id"] for p in build()["people"]
    ]
    assert first["person_count"] == 2


def test_rendering_is_ordered_stably() -> None:
    store = empty_alumni_store()
    for name in ("Zoe Zhang", "Ada Lovelace", "Marie Curie"):
        admit_candidate(store, name, DELFT, [affiliation()])
    ids = [p["record_id"] for p in render_alumni_store(store)["people"]]
    assert ids == sorted(ids)


def test_export_exposes_the_whole_directory() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "Ada Lovelace", DELFT, valid_claims())
    exported = export_alumni(store)
    assert exported["person_count"] == 1
    assert exported["ruleset"]
    assert exported["schema_version"]


def test_unknown_fields_covers_the_whole_registry() -> None:
    store = empty_alumni_store()
    admit_candidate(store, "Ada Lovelace", DELFT, [affiliation()])
    record = next(iter(store["people"].values()))
    assert "university_affiliation" not in unknown_fields(record)
    assert set(unknown_fields(record)) | {"university_affiliation"} == set(
        ALL_FIELD_NAMES
    )


# --- Schemas ---------------------------------------------------------------


def test_the_candidate_schema_rejects_unexpected_fields() -> None:
    """Validated from a dict, which is how a tool call will actually arrive.

    An extra key must be refused rather than quietly dropped — `email` is
    exactly the sort of thing a model might helpfully volunteer, and it must
    not be able to enter the system through a schema that shrugs.
    """
    with pytest.raises(ValueError):
        AlumniCandidate.model_validate(
            {
                "name": "Ada",
                "university": DELFT,
                "claims": [],
                "email": "ada@example.com",
            }
        )


def test_the_claim_schema_requires_a_source_and_a_quote() -> None:
    """A value with no citation is not a claim this system accepts."""
    with pytest.raises(ValueError):
        AlumniClaimInput.model_validate({"field_name": "employer", "value": "X"})


def test_a_well_formed_candidate_validates() -> None:
    candidate = AlumniCandidate(
        name="Ada Lovelace",
        university=DELFT,
        claims=[
            AlumniClaimInput(
                field_name="employer",
                value="Booking.com",
                source_domain="booking.com",
                supporting_quote="Ada Lovelace works at Booking.com.",
            )
        ],
    )
    assert candidate.claims[0].source_url is None


# --- The storage layer contains no reasoning -------------------------------


def test_the_storage_layer_cannot_reach_adk_or_the_network() -> None:
    """No LLM, no HTTP — Stage B is deterministic Python only."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path("app/alumni_store.py").read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    for name in imported:
        root = name.split(".")[0]
        assert root not in {
            "google",
            "urllib",
            "requests",
            "httpx",
            "socket",
            "http",
        }, f"alumni_store imports {name}"


def test_admission_never_mutates_the_caller_s_claims() -> None:
    store = empty_alumni_store()
    claims = valid_claims()
    before = copy.deepcopy(claims)
    admit_candidate(store, "Ada Lovelace", DELFT, claims)
    assert claims == before
