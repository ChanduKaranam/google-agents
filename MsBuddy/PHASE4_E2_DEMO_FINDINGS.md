# Phase 4 — E2 demo readiness: what was found, and what it blocks

| | |
|---|---|
| **Status** | Vertical slice complete; grounding regression diagnosed and worked around |
| **Written** | 2026-08-06 |
| **Governs** | `PHASE4_ALUMNI_ARCHITECTURE.md`, `PHASE4_STAGE0_DECISION.md` |

---

## 1. What was already built

Stages E2, F and G were already implemented and wired before this session
started — the earlier session got further than its own notes recorded. On disk:

* `alumni_discovery_agent` attached to `root_agent` as an `AgentTool`, and
  covered by the retrieval budget (`callbacks.RESEARCH_TOOL_NAMES`).
* `build_alumni_query`, `save_alumni_records`, `rank_alumni_by_affinity` and
  `get_alumni` all attached as root tools.
* Stage F affinity ranking (`app/affinity.py`) — deterministic, no composite
  score, ties preserved.
* Stage G aggregation and narration safety — `summary` with denominators,
  `MIN_PATTERN_N`, and the person-level `NarrationIntegrityPlugin` rule.
* The offline end-to-end path test, `tests/integration/test_alumni_path.py`.

Offline the whole slice is green: **859 tests pass**, `ruff check`,
`ruff format --check`, `codespell` and `ty` all clean.

## 2. The blocking finding

**Live alumni discovery admits nobody, on every run.** Not because the
verification gate is wrong — because the gate is being starved of the evidence
it checks against.

`save_alumni_records` verifies a claim by locating a *grounded segment*: text
the search runtime attributed to the cited domain, containing both the
person's name and the claimed value (`alumni_tools.find_supporting_segment`).
Those segments come from `grounding_supports[].segment.text`, mapped to
domains through `grounding_chunk_indices` (`evidence.harvest_metadata`).

On `gemini-3.6-flash`, calls carrying MS Buddy's system instructions come back
with `web_search_queries` populated but **`grounding_chunks: 0` and
`grounding_supports: 0`**. The evidence ledger is therefore empty, every
candidate is refused for `no_sources_retrieved` / `name_not_in_source`, and
the correct, honest answer MS Buddy gives is that it found nobody.

Measured 2026-08-06, same model, same query, only the system instruction
differing:

| System instruction | queries | chunks | supports |
|---|---|---|---|
| none | 4 | 13 | 22 |
| short rules + prose format | 15 | 5 | 5 |
| short rules + prose-then-template | 8 | 4 | 7 |
| short rules + template only | 16 | **0** | **0** |
| full discovery `INSTRUCTION` (3 runs) | 8–20 | **0** | **0** |

**This is not alumni-specific.** `tests/integration/test_program_research_live.py`
— C2, shipped and previously working — now skips all 8 invariants for the same
reason: no grounding reached the caller. The evidence layer as a whole is inert
on this model, which is why this is written up as a finding rather than fixed
in the alumni prompt.

`app/config.py` last changed 2026-08-03; `PHASE4_STAGE0_DECISION.md` recorded
its measurements on 2026-07-31 against a different model. The regression sits
in that window.

## 3. What was fixed here

Two genuine defects in the discovery agent's *reporting contract* were found
and fixed. Both were absolute blockers independent of the grounding
regression, and neither touches the gate, provenance, identity resolution,
source authority or the privacy screen.

**3.1 A template-only answer produces no attribution at all.** Vertex derives
`grounding_supports` from the answer's prose and returns a `grounding_chunk`
only where some support cites it. An answer made entirely of `PERSON:/FIELD:`
lines gives the attribution pass nothing to work on. The agent now answers in
prose first, then `---`, then the machine-readable block. Measured effect with
short rules: 0 chunks → 4 chunks / 7 supports.

**3.2 The quote could never be matched.** The instruction demanded a quote
"copied from the retrieved page text, character for character", but the gate
looks for that quote inside a grounded segment — a span of the model's own
attributed answer, never raw page text. So even on runs where chunks did come
back, every claim failed `claim_not_in_same_segment`. The quote is now
specified as the sentence the agent wrote about that person, which is the
thing Vertex actually attributes to a domain.

This concedes nothing. The model does not decide attribution — the search
runtime does, and it will not attribute a sentence no source supports. A
fabricated person or fact matches no segment and is refused exactly as before.
It is Stage 0 option (a) — name and claim co-occurring in a segment attributed
to the domain — restated in terms the runtime can satisfy.

**3.3 The value was paraphrased out of matchability.** With grounding
restored, the first live run refused a real, well-sourced person for
`claim_not_in_same_segment`: `tudelft.nl` named Sreevidya Iyer, but the
reported value `"Master's program in Computer Science"` appeared nowhere in
the attributed sentence, which said it differently. `value_supported_by` is a
text match on top of the quote match, so tidying the wording between the
sentence and the value refuses a person who is genuinely evidenced. The
instruction now requires the value to be copied out of its own sentence,
spelled as that sentence spells it.

The same run refused `Jacobus Henricus van 't Hoff` for `name_not_in_source`
— a famous historical chemist arriving from model recall, which is exactly
failure mode 1 from architecture §14, caught by the gate as designed.

All three are pinned by tests in `tests/integration/test_alumni_structure.py`:
`test_discovery_instruction_asks_for_prose_before_the_machine_readable_block`
and `test_the_quote_is_specified_as_the_attributed_sentence`.

A third change, "one fact per sentence", was tried and **reverted**: it made
the prose robotic ("X studied Y at Z. X obtained an MSc from Z.") and dropped
chunk yield to 0/3. Information-dense natural sentences are both better for
attribution and better for the gate, since one sentence naming the person,
the degree and the employer can support all three claims — which is exactly
the shape of the `ANNA_DELFT` fixture in `test_alumni_path.py`.

## 3b. The remaining blocker — and why it needs a decision

With grounding restored, the pipeline runs correctly end to end and refuses
everybody. The root tries hard: five `save_alumni_records` calls in one turn,
widening from program to institution, retrying across `tudelft.nl`,
`edurank.org` and `wikipedia.org`. Every claim is refused, and the reasons
are exact.

The decisive one, observed live 2026-08-06. `edurank.org` was retrieved, and
the model reported:

> QUOTE: "Ben van Beurden joined Shell in 1983, after earning a master's
> degree in chemical engineering from Delft University of Technology,
> Netherlands."
> VALUE: master's degree in chemical engineering

That quote contains the name *and* the value. The gate still refused it:

> `claim_not_in_same_segment` — 'edurank.org' names Ben van Beurden, but no
> single passage there states 'master's degree in chemical engineering'
> alongside the name.

So the name **was** found in an attributed segment from that domain, but the
segment is not the sentence the model wrote. That is the whole problem:
`grounding_supports` mark whichever spans of the answer Vertex chose to
attribute, and **the model has no way to know which of its own sentences
those were.** It cannot reliably echo back a segment it cannot see. No
amount of prompting fixes an unobservable target.

**Proposed change — a decision, not applied.** `find_supporting_segment`
already returns the segment it matched (`{"ok": True, "segment": ...}`), but
`_admit` stores `claim.supporting_quote` — the model's text — as provenance,
and uses the model's quote as an extra filter (`alumni_tools.py:558, 606`).
The proposal is to stop filtering on the model's quote and store the matched
segment instead.

What that removes is only "did the model correctly guess which of its own
sentences got attributed", which is not a safety property. Every real check
is untouched and still deterministic: the domain was retrieved this turn, the
name appears in a segment attributed to it, the value appears in *the same*
segment, the source class may originate or verify that field, the redirect
resolves and the hosts agree, and identity resolves without an unsafe merge.
Stored provenance gets strictly more accurate, because it becomes the text
the runtime actually attributed rather than the model's restatement of it.

It is written up rather than applied because it edits the deterministic
admission path, which is the one place this work was told not to touch
without asking.

## 3c. The pattern behind all of it

Three separate blockers, one shape. Each time, the discovery agent was asked
to predict something about **attribution** — a decision made by the search
runtime *after* the agent has written its answer, and never shown to it:

| Asked to predict | Refusal it caused | Status |
|---|---|---|
| which of its sentences would be attributed | `claim_not_in_same_segment` | fixed — quote no longer matched |
| how the value would be spelled in that sentence | `claim_not_in_same_segment` | fixed — value copied from the sentence |
| **which domains would be attributed** | `domain_not_retrieved` | **open** |

The third, measured twice on 2026-08-06 with identical results (3
`domain_not_retrieved`, 2 `no_verifiable_claim`):

> `'utwente.nl' was not retrieved this turn. Domains actually retrieved:
> github.io, tudelft.nl.`

The agent cited a domain it genuinely saw in search results. Vertex attributed
two. The agent cannot tell which two, so it will keep guessing wrong.

**The principled fix is to stop asking it to predict anything.** Provenance
would be *derived* from the harvest rather than asserted by the model: given
a name and a value, the gate finds which harvested domain has a segment
carrying both, and applies source authority to **that** domain. The model
proposes the person and the fact; the code decides where the evidence is.

Source authority is unaffected — it is applied to the derived domain, so a
university page still cannot verify an employer. It is arguably stricter
than today, since a domain the model asserts is no longer taken on trust.
The cost is that checks 6 and 7 (redirect resolution and host agreement)
would need their URL from the harvest entry rather than from `claim.source_url`.

Not applied, because it is a third change to the deterministic admission path.

## 4. What safety still guarantees

Nothing was weakened, and the guarantees were verified live, not asserted:

* The Phase 4 release gate passes. `test_an_invented_programme_produces_no_people`
  and `test_the_obscure_answer_does_not_offer_a_consolation_list` **pass live**
  against a real model — asked for alumni of an invented programme, MS Buddy
  stores nobody and offers no consolation list.
* Discovery remains a proposer: `google_search` only, no storage tool, no
  profile access.
* `save_alumni_records` remains the sole admission gate; the root cannot name
  anyone it did not admit.
* C1/C2/C3 behaviour is unchanged. The only edits were to the discovery
  agent's instruction, one paragraph of the root instruction describing how to
  read that agent's output, and the tests pinning both.

## 5. The resolution: a model split, scoped to grounded calls

Same full instruction, same query, three runs each:

| Model | runs returning grounding chunks |
|---|---|
| `gemini-3.6-flash` | **0 / 3** (0/6 including the search-cap probe) |
| `gemini-2.5-flash` | **3 / 3** — (6q→3 chunks), (3q→1), (6q→3) |

So `app/config.py` now carries a second constant, `SEARCH_MODEL =
"gemini-2.5-flash"`, used by `program_research_agent` and
`alumni_discovery_agent` only. `MODEL` is untouched: the root and the profile
extractor still run `gemini-3.6-flash`, because only grounded calls are
affected and the conversation model is not to move without the eval
comparison `config.py` calls for.

Pinned by `test_the_grounded_agents_run_the_model_whose_grounding_works`.

## 6. POST-DEMO REFINEMENT

* Re-run `PHASE4_STAGE0_DECISION.md` §2 probes against both models; its
  measurements predate this regression and are stale.
* Revisit the split once `gemini-3.6-flash` grounding is fixed upstream —
  it is a workaround for a platform behaviour, not a design preference.
* Two models in one tree is a cost and latency asymmetry worth an eval pass.
* Stage 0 option (b) — `url_context` verification — becomes worth revisiting
  if grounding attribution stays unreliable, since it does not depend on it.
* The discovery agent logs to C2's `msbuddy.program_research` logger
  (`ponytail:` note in `alumni_discovery.py`).
* Affinity has three anchors, not the architecture's four; "same target
  country" needs a fact no alumni record holds.
* Stage H evaluation, deliberately not started.
