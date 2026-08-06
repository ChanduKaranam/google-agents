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

"""Constants for MS Buddy.

State keys mirror the classification table in `.agents-cli-spec.md` §6.1.
Only the keys used by Phase 1 (C1 — Student Profile Intelligence) are defined
here; the remainder arrive with the capability that owns them.
"""

from __future__ import annotations

# Model. Preserved from the scaffold — see the code-preservation rule in
# /google-agents-cli-workflow. Do not change without an eval comparison
# (spec §15 open question 2).
MODEL = "gemini-3.6-flash"

# The two grounded agents run a different model, and this split is a bug fix
# rather than a preference. Measured 2026-08-06, identical instruction and
# query: `gemini-3.6-flash` returned `web_search_queries` but **zero**
# `grounding_chunks`/`grounding_supports` in 0/6 runs; `gemini-2.5-flash`
# returned chunks in 3/3.
#
# Zero chunks means `evidence.harvest_metadata` yields no segments, so the
# evidence ledger is empty — `save_alumni_records` then refuses every
# candidate for `name_not_in_source` and `save_program_record` stores nothing.
# The failure is silent and looks like a broken verification gate; it is the
# gate working correctly on evidence that never arrived.
#
# Scoped to the search agents rather than changed globally: only grounded
# calls are affected, and the root's conversation model is not to move
# without the eval comparison above. See `PHASE4_E2_DEMO_FINDINGS.md`.
SEARCH_MODEL = "gemini-2.5-flash"

# --- State keys (spec §6.1) -------------------------------------------------
# Persistent, user-scoped.
STATE_PROFILE = "user:profile"
STATE_SHORTLIST = "user:shortlist"

# Session-scoped.
STATE_EVIDENCE_LEDGER = "evidence_ledger"
STATE_RETRIEVAL_COUNT = "retrieval_calls"

# Ephemeral, single-invocation. Anything untrusted or unverified lives under
# `temp:` by construction (spec §6.2) so that it cannot outlive the turn.
STATE_EXTRACTION_SOURCE = "temp:extraction_source"

# --- Retrieval budget (spec §8.4) -------------------------------------------
# Hard ceilings. Exceeding one returns partial results *and says so*; it never
# fails silently and never loops.
MAX_RETRIEVALS_PER_TURN = 3
MAX_RETRIEVALS_PER_SESSION = 25

# Retrieved text is truncated before it can enter a prompt (spec §8.3).
MAX_RETRIEVED_SEGMENT_CHARS = 2000

# --- C4 alumni (Phase 4) -----------------------------------------------------
# Persistent, user-scoped. Alumni records are never shared between students.
STATE_ALUMNI = "user:alumni"

# Session-scoped cache of resolved grounding redirects, so a redirect is
# resolved at most once per conversation (Stage 0: one HEAD per unique URL).
STATE_URL_RESOLUTION_CACHE = "url_resolution_cache"

# Session-scoped record of what the current alumni search is scoped to, set
# by `build_alumni_query`. Session rather than `user:` because the scope
# belongs to the question being asked, not to the student.
STATE_ALUMNI_ANCHOR = "alumni_anchor"

# How many alumni may be returned. A cap, not a target: MS Buddy answers
# "who did this program", and beyond a handful it would start to read as a
# directory of people. Disclosed to the student when it bites.
MAX_ALUMNI_RESULTS = 10

# Below this many discovered alumni, MS Buddy reports counts only and must
# not use pattern language. "2 of 2 work in data" invites precisely the
# generalisation a convenience sample cannot support.
MIN_PATTERN_N = 5

# Bounded redirect resolution (Stage 0 option D). stdlib urllib only, HEAD
# only, and the publisher's own server is never contacted — the 302 comes
# from Google's redirect service.
URL_RESOLUTION_TIMEOUT_SECONDS = 10
MAX_URL_RESOLUTIONS_PER_TURN = 20

# --- Profile record ---------------------------------------------------------
PROFILE_SCHEMA_VERSION = 1

# How many superseded values to retain per field. Bounded so a long
# conversation cannot grow state without limit. Retained at all because
# "silent overwrite of a corrected value" is a named C1 failure case.
MAX_VALUE_HISTORY = 5

# Sentinel accepted by `clear_profile_fields` to erase the whole profile.
# Deletion is a spec requirement (C1 privacy: "must be exportable and
# deletable on request"); the sentinel exists so that a full wipe is always
# explicit and can never result from an empty or malformed field list.
CLEAR_ALL_SENTINEL = "__all__"
