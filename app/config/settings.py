"""Environment-based configuration — the only file that reads the env.

No API keys live here or anywhere in the repo; the google-genai client
reads its own credentials from the environment (`.env.example` documents
the two options).
"""

from __future__ import annotations

import os

from app.models.matching import DEFAULT_CATEGORY_THRESHOLDS, MatchWeights

# Both default to gemini-2.5-flash: measured on this stack, search grounding
# metadata is reliably returned there, and an agent whose evidence depends
# on grounding must not silently run on a model that returns none.
MODEL = os.environ.get("MSBUDDY_MODEL", "gemini-2.5-flash")
SEARCH_MODEL = os.environ.get("MSBUDDY_SEARCH_MODEL", "gemini-2.5-flash")

MATCH_WEIGHTS = MatchWeights()
CATEGORY_THRESHOLDS = DEFAULT_CATEGORY_THRESHOLDS

# --- Session state keys -----------------------------------------------------
# `user:` prefix = persistent per-user in ADK; bare = session-scoped.
STATE_PROFILE = "user:student_profile"
# Per-field provenance: {path: {source, status, confidence}} plus the
# unconfirmed domain inferences a resume produced. Separate key so the
# profile stays the plain value shape every consumer already reads.
STATE_PROFILE_META = "user:profile_meta"
STATE_KNOWLEDGE = "user:program_knowledge"
# Resolved alumni entities with per-claim evidence, entity-keyed.
STATE_ALUMNI = "user:alumni_signals"
# Financial facts that belong to a city, country, provider or market rather
# than one program (living costs, work rules, visa funds, loan terms) —
# scope-keyed so a city figure can never masquerade as a program figure.
STATE_FINANCE = "user:finance_facts"
# The application tracker: per-program status + document states, mutated
# only through validated tracker functions.
STATE_APPLICATIONS = "user:applications"
STATE_EVIDENCE = "evidence_ledger"

# Outbound research is budgeted so no flow can loop the network.
MAX_SEARCHES_PER_TURN = 3
MAX_SEARCHES_PER_SESSION = 20
STATE_SEARCH_COUNT = "search_calls"
