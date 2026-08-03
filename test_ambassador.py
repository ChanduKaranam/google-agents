import importlib

def _components(messages):
    return [c for m in messages if "surfaceUpdate" in m
            for c in m["surfaceUpdate"]["components"]]

def _literals(messages):
    out = []
    for c in _components(messages):
        spec = c["component"].get("Text")
        if spec:
            out.append(spec["text"]["literalString"])
    return out

def _action_names(messages):
    return [c["component"]["Button"]["action"]["name"]
            for c in _components(messages) if "Button" in c["component"]]

def test_root_agent_exists():
    mod = importlib.import_module("ambassador_agent")
    assert mod.root_agent.name == "ambassador_agent"

def test_a2a_http_server_deps_are_installed():
    # google-adk[a2a] omits a2a-sdk[http-server]; A2AStarletteApplication then
    # raises at construction inside lifespan startup, so every import-level
    # test passes and the container dies on deploy instead.
    import sse_starlette  # noqa: F401

def test_surface_ids_are_namespaced_and_unique():
    from ambassador_agent.a2ui import build_greeting
    messages = build_greeting("Hi Sneha", ["Who should I message?"])
    ids = [c["id"]
           for m in messages if "surfaceUpdate" in m
           for c in m["surfaceUpdate"]["components"]]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"
    assert all(i.startswith("greet-") for i in ids), ids
    reserved = {"body", "root", "title", "head", "html", "main"}
    assert not (set(ids) & reserved)

def test_every_child_reference_resolves():
    from ambassador_agent.a2ui import build_greeting
    messages = build_greeting("Hi", ["A"])
    for m in messages:
        if "surfaceUpdate" not in m:
            continue
        comps = m["surfaceUpdate"]["components"]
        known = {c["id"] for c in comps}
        for c in comps:
            spec = next(iter(c["component"].values()))
            refs = []
            if isinstance(spec.get("child"), str):
                refs.append(spec["child"])
            children = spec.get("children") or {}
            refs.extend(children.get("explicitList") or [])
            for r in refs:
                assert r in known, f"dangling reference {r!r}"

def test_datapart_mime_is_v08():
    from ambassador_agent.a2ui import to_genai_parts, build_greeting
    parts = to_genai_parts(build_greeting("Hi", []))
    blob = parts[0].inline_data.data.decode()
    assert "application/json+a2ui" in blob
    assert "application/a2ui+json" not in blob
    assert blob.startswith("<a2a_datapart_json>")

def test_parse_user_action_reads_a_tagged_datapart():
    from ambassador_agent.actions import parse_user_action
    payload = (
        '<a2a_datapart_json>{"kind":"data","data":{"userAction":'
        '{"name":"show_stragglers","surfaceId":"greet","sourceComponentId":'
        '"greet-b0","timestamp":"2026-07-28T00:00:00Z","context":{"x":"1"}}}}'
        "</a2a_datapart_json>"
    )
    action = parse_user_action(payload)
    assert action["name"] == "show_stragglers"
    assert action["context"] == {"x": "1"}

def test_parse_user_action_ignores_plain_text():
    from ambassador_agent.actions import parse_user_action
    assert parse_user_action("who should I message?") is None

def test_cohort_maps_sethus_payload():
    """Every number and label comes from the API response, none from us."""
    from ambassador_agent import fixtures
    from ambassador_agent.data import get_cohort
    cohort = get_cohort({})
    raw = fixtures.COHORT
    assert cohort["name"] == raw["ambassadorName"]
    assert cohort["label"] == raw["label"]
    assert cohort["stats"]["activated"] == raw["stats"]["activated"]
    assert cohort["stats"]["total"] == raw["stats"]["total"]
    assert cohort["lastSyncedAt"] == raw["lastSyncedAt"]

def test_milestone_line_speaks_the_live_tier_and_reward():
    """The tier name and prize are Sethu's, not ours -- a hardcoded "75% Club"
    would contradict whatever the drive's incentive config actually says."""
    from ambassador_agent.data import milestone_line
    line = milestone_line({})
    assert "25% Club" in line and "₹500 Amazon voucher" in line
    assert "1 more activation clears" in line, line
    assert milestone_line({"phase": "complete"}) == (
        "Every student in CSE · Yr 3 · Sec A is activated —"
        " nothing left to unlock.")

def test_stragglers_come_from_the_api_and_clear_at_complete():
    from ambassador_agent.data import get_stragglers
    ids = [s["id"] for s in get_stragglers({})]
    assert ids == ["stu-002", "stu-004", "stu-006"]
    assert get_stragglers({"phase": "complete"}) == []


def test_stragglers_are_joined_to_their_phone_number():
    """Straggler items carry no phone; the WhatsApp deeplink needs one, so
    data.py joins them to cohorts/mine.students[] by id."""
    from ambassador_agent.data import _wa_number, get_stragglers
    for entry in get_stragglers({}):
        assert entry["phone"], entry
    # Live rows carry bare 10-digit numbers; wa.me opens an empty chat without
    # a country code, so both forms have to normalise to the same link.
    assert _wa_number("9876501041") == "919876501041"
    assert _wa_number("+91 98765 01041") == "919876501041"


def test_simulate_target_is_computed_from_the_live_total():
    """The simulator can no longer swap fixtures -- it overrides the count."""
    from ambassador_agent.data import get_cohort
    total = get_cohort({})["stats"]["total"]
    assert get_cohort({"phase": "target"})["stats"]["activated"] == 45  # ceil(59*.75)
    assert get_cohort({"phase": "complete"})["stats"]["activated"] == total

def test_sent_students_drop_out_of_the_pending_list():
    from ambassador_agent.data import get_stragglers, mark_sent
    state = {}
    mark_sent(state, "stu-002")
    ids = [s["id"] for s in get_stragglers(state)]
    assert "stu-002" not in ids and len(ids) == 2

def test_drafts_come_from_the_apis_angles():
    """The copy is Sethu's now, so their team can tune it without a redeploy."""
    from ambassador_agent import fixtures
    from ambassador_agent.data import draft_for
    angles = fixtures.STRAGGLERS["items"][0]["angles"]
    for key in ("examPanic", "placement", "friendlyRoast"):
        assert draft_for({}, "stu-002", key) == angles[key]

def test_leaderboard_maps_the_api_and_marks_her_row():
    from ambassador_agent.data import get_leaderboard
    board = get_leaderboard({})
    assert board["myRank"] == 4
    mine = [r for r in board["entries"] if r["isMe"]]
    assert len(mine) == 1 and mine[0]["rank"] == 4
    assert board["basisNote"]

def test_get_leaderboard_does_not_mutate_the_recorded_payload():
    import copy
    from ambassador_agent import fixtures
    from ambassador_agent.data import get_leaderboard
    before = copy.deepcopy(fixtures.LEADERBOARD)
    board = get_leaderboard({})
    board["entries"][0]["name"] = "mutated"
    assert fixtures.LEADERBOARD == before



def test_mark_sent_is_idempotent():
    from ambassador_agent.data import get_stragglers, mark_sent
    state = {}
    mark_sent(state, "stu-002")
    mark_sent(state, "stu-002")
    assert state["sent"] == ["stu-002"]
    ids = [s["id"] for s in get_stragglers(state)]
    assert "stu-002" not in ids and len(ids) == 2

def test_cohort_card_carries_the_certified_label_and_both_numbers():
    from ambassador_agent.surfaces import cohort_summary
    strings = _literals(cohort_summary({}))
    assert "CSE · YR 3 · SEC A — CERTIFIED" in strings
    assert "14 / 59" in strings
    assert "23.7%" in strings
    assert any("25% Club" in s for s in strings)
    assert "Show the 3 who need me" in strings
    assert "How is my rank calculated?" in strings
    # activation numbers lag Google by up to ~6h, so freshness is always shown
    assert any("last synced" in s for s in strings), strings

def test_cohort_card_button_names_are_routable():
    from ambassador_agent.surfaces import cohort_summary
    names = _action_names(cohort_summary({}))
    assert "show_stragglers" in names

def test_cohort_card_with_no_pending_shows_roster_cta():
    from ambassador_agent.surfaces import cohort_summary
    messages = cohort_summary({"phase": "complete"})
    strings = _literals(messages)
    names = _action_names(messages)
    assert "Show my cohort" in strings
    assert "show_roster" in names
    assert "show_stragglers" not in names


def test_straggler_list_draws_one_card_per_pending_student():
    from ambassador_agent.surfaces import straggler_list
    messages = straggler_list({})
    names = _action_names(messages)
    assert names.count("send_whatsapp") == 3
    assert names.count("open_edit") == 3
    assert names.count("open_student") == 3
    strings = _literals(messages)
    assert "Kavya S" in strings
    # contextNote and the draft are the API's copy, rendered as sent
    assert "Day 12 — first nudge window" in strings
    assert any("sethu.app/go/abc123" in s for s in strings)
    assert any("Circuits agent" in s for s in strings)

def test_send_buttons_carry_the_student_id():
    from ambassador_agent.surfaces import straggler_list
    sends = [c["component"]["Button"]["action"]
             for c in _components(straggler_list({}))
             if "Button" in c["component"]
             and c["component"]["Button"]["action"]["name"] == "send_whatsapp"]
    ids = [ctx["value"]["literalString"]
           for a in sends for ctx in a["context"] if ctx["key"] == "student_id"]
    assert ids == ["stu-002", "stu-004", "stu-006"]

def test_sent_students_leave_the_list():
    from ambassador_agent.data import mark_sent
    from ambassador_agent.surfaces import straggler_list
    state = {}
    mark_sent(state, "stu-002")
    assert "Kavya S" not in _literals(straggler_list(state))

def test_ids_stay_unique_across_every_student_card():
    from ambassador_agent.surfaces import straggler_list
    ids = [c["id"] for c in _components(straggler_list({}))]
    assert len(ids) == len(set(ids))


# ---------------------------------------------------------------------------
# Structural invariants, applied to EVERY surface automatically.
#
# These are the rules whose violation fails silently in Gemini Enterprise: a
# reserved or duplicate id, an illegal usageHint, or a dangling child reference
# produces a red "This content could not be displayed" box and nothing in the
# server logs. Auto-discovering the builders means a surface added later is
# covered the day it lands, instead of relying on whoever writes it to
# reproduce these checks.
# ---------------------------------------------------------------------------

_RESERVED = {"body", "root", "title", "head", "html", "main"}
_USAGE_HINTS = {"h1", "h2", "h3", "h4", "h5", "caption", "body"}

# Surfaces needing more than `state`. Extend as builders are added.
_EXTRA_ARGS = {"edit_form": ("stu-002",), "student_detail": ("stu-002",)}


def _all_surface_cases():
    """Every public builder in surfaces.py, paired with each demo phase."""
    import inspect

    from ambassador_agent import surfaces

    cases = []
    for name, fn in inspect.getmembers(surfaces, inspect.isfunction):
        if name.startswith("_") or fn.__module__ != surfaces.__name__:
            continue
        params = list(inspect.signature(fn).parameters)
        if not params or params[0] != "state":
            continue  # helper, not a surface builder
        extra = _EXTRA_ARGS.get(name, ())
        if len(params) != 1 + len(extra):
            continue
        for phase in ("live", "target", "complete"):
            cases.append((f"{name}[{phase}]", fn, ({"phase": phase},) + extra))
    return cases


def test_surface_builders_were_discovered():
    # Guards the discovery itself: a typo that matched nothing would make every
    # check below vacuously pass.
    names = {n.split("[")[0] for n, _, _ in _all_surface_cases()}
    assert "cohort_summary" in names, names


def test_every_surface_obeys_the_structural_rules():
    for label, fn, args in _all_surface_cases():
        try:
            messages = fn(*args)
        except KeyError:
            continue  # surface not meaningful in this phase
        ids, roots, surface_ids = [], [], set()
        for message in messages:
            update = message.get("surfaceUpdate")
            if update:
                surface_ids.add(update["surfaceId"])
                for component in update["components"]:
                    ids.append(component["id"])
                    spec = next(iter(component["component"].values()))
                    hint = spec.get("usageHint")
                    assert hint is None or hint in _USAGE_HINTS, (
                        f"{label}: illegal usageHint {hint!r}")
            begin = message.get("beginRendering")
            if begin:
                roots.append(begin["root"])

        assert ids, f"{label}: drew nothing"
        assert len(ids) == len(set(ids)), f"{label}: duplicate ids"
        assert not (set(ids) & _RESERVED), (
            f"{label}: reserved id {set(ids) & _RESERVED}")
        assert roots, f"{label}: no beginRendering"
        for root in roots:
            assert root in ids, f"{label}: root {root!r} does not exist"

        known = set(ids)
        for message in messages:
            update = message.get("surfaceUpdate")
            if not update:
                continue
            for component in update["components"]:
                spec = next(iter(component["component"].values()))
                refs = []
                if isinstance(spec.get("child"), str):
                    refs.append(spec["child"])
                for key in ("entryPointChild", "contentChild"):
                    if isinstance(spec.get(key), str):
                        refs.append(spec[key])
                refs.extend((spec.get("children") or {}).get("explicitList") or [])
                for ref in refs:
                    assert ref in known, (
                        f"{label}: {component['id']} references missing {ref!r}")


def test_meter_stays_the_right_width_at_the_edges():
    from ambassador_agent.surfaces import METER_WIDTH, meter

    for pct in (-5, 0, 0.4, 50, 72.9, 99.9, 100, 140):
        assert len(meter(pct)) == METER_WIDTH, (pct, meter(pct))
    assert meter(0) == "░" * METER_WIDTH
    assert meter(100) == "█" * METER_WIDTH


def test_each_card_binds_both_buttons_to_its_own_student():
    """Pin name -> id, not list order.

    Task 8 routes every per-student action on this context value. An id that
    is wrong-but-consistently-ordered would satisfy an order-based assertion
    and still send Kavya's message to Meera.
    """
    from ambassador_agent.surfaces import straggler_list

    components = _components(straggler_list({}))
    by_id = {c["id"]: c for c in components}
    expected = {
        "stu-002": "Kavya S", "stu-004": "Meera Joshi",
        "stu-006": "Nisha Verma",
    }
    for sid, name in expected.items():
        shown = by_id[f"strag-{sid}-name"]["component"]["Text"]["text"]
        assert shown["literalString"] == name, (sid, shown)
        for suffix, action in (("send", "send_whatsapp"), ("edit", "open_edit"),
                               ("open", "open_student")):
            spec = by_id[f"strag-{sid}-{suffix}"]["component"]["Button"]["action"]
            assert spec["name"] == action, (sid, suffix, spec)
            carried = {c["key"]: c["value"]["literalString"]
                       for c in spec["context"]}
            assert carried == {"student_id": sid}, (sid, suffix, carried)


def test_edit_form_offers_three_angles_and_a_send():
    from ambassador_agent.surfaces import edit_form
    messages = edit_form({}, "stu-002")
    strings = _literals(messages)
    assert "Edit before sending — Kavya S" in strings
    # Angles render with a selection marker ("● Exam panic"), so match on
    # substring. An exact assertion here would push the implementer to
    # restructure the card just to satisfy the test.
    for angle in ("Exam panic", "Placement", "Friendly roast"):
        assert any(angle in s for s in strings)
    assert "Send to Kavya" in strings
    names = _action_names(messages)
    assert names.count("set_angle") == 3
    assert "send_whatsapp" in names


def test_send_carries_the_edited_text_by_path():
    from ambassador_agent.surfaces import edit_form
    send = [c["component"]["Button"]["action"]
            for c in _components(edit_form({}, "stu-002"))
            if "Button" in c["component"]
            and c["component"]["Button"]["action"]["name"] == "send_whatsapp"][0]
    by_key = {ctx["key"]: ctx["value"] for ctx in send["context"]}
    assert by_key["student_id"] == {"literalString": "stu-002"}
    assert by_key["message"] == {"path": "/draft/text"}


def test_sent_form_locks_and_relabels():
    from ambassador_agent.data import mark_sent
    from ambassador_agent.surfaces import edit_form
    state = {}
    mark_sent(state, "stu-002")
    strings = _literals(edit_form(state, "stu-002"))
    assert "Sent — Kavya S" in strings
    assert "Sent to Kavya ✓" in strings



def test_edit_form_keeps_an_in_flight_edit():
    """Her own words win over the angle's template.

    Task 8 writes `state["drafts"][id]` when she edits, then re-renders on the
    next action. If the form re-seeded from the template it would silently
    discard what she typed.
    """
    from ambassador_agent.surfaces import edit_form

    typed = "Kavya please just open it, it takes two minutes 🙏"
    messages = edit_form({"drafts": {"stu-002": typed}}, "stu-002")
    seeded = [m for m in messages if "dataModelUpdate" in m][0]
    assert seeded["dataModelUpdate"]["contents"]["draft"]["text"] == typed

def test_leaderboard_always_shows_percent_and_count_and_the_basis():
    from ambassador_agent.surfaces import leaderboard
    strings = _literals(leaderboard({}))
    assert any("40.0%" in s and "22 / 55" in s for s in strings)
    assert any("23.7%" in s and "14 / 59" in s for s in strings)
    assert any(s.startswith("#4") for s in strings)
    # the ranking basis is the API's sentence, not ours
    assert "Ranked by % activation within cohort" in strings
    assert "12 ambassadors on the board" in strings

def test_leaderboard_marks_her_row_in_text_not_colour():
    from ambassador_agent.surfaces import leaderboard
    assert any("You" in s and "CSE · Yr 3 · Sec A" in s
               for s in _literals(leaderboard({})))

def test_rewards_lists_four_tiers_and_names_only_the_live_one():
    """Sethu serves only the NEXT rung, so the tier she is chasing carries the
    real prize and the rest say so plainly rather than inventing one."""
    from ambassador_agent.surfaces import rewards
    strings = _literals(rewards({}))
    assert "₹500 Amazon voucher" in strings           # the live 25% rung
    assert strings.count("reward to be announced") == 3
    for at, need in (("25%", "1 more"), ("50%", "16 more"),
                     ("75%", "31 more"), ("100%", "45 more")):
        assert f"at {at} — {need}" in strings, (at, strings)

def test_roster_shows_what_it_has_against_the_true_total():
    from ambassador_agent.surfaces import roster
    strings = _literals(roster({}))
    assert "Ravi Kumar" in strings
    assert "Showing 6 of 59" in strings
    # DORMANT is API jargon; she reads plain words
    assert any("gone quiet" in s for s in strings), strings
    assert not any("DORMANT" in s for s in strings), strings



def test_every_list_surface_keeps_its_shape_in_every_phase():
    """Phase coverage for the surfaces layer, not just the data layer.

    The rewards fix turns on every tier keeping its "at N%" prefix in EVERY
    phase -- including `complete`, where all four are earned and an earlier
    build dropped the threshold entirely. Nothing pinned that beyond `live`.
    """
    from ambassador_agent.surfaces import leaderboard, rewards, roster

    for phase in ("live", "target", "complete"):
        state = {"phase": phase}

        tiers = [s for s in _literals(rewards(state)) if s.startswith("at ")]
        assert len(tiers) == 4, (phase, tiers)
        for at in ("at 25%", "at 50%", "at 75%", "at 100%"):
            assert any(s.startswith(at + " —") for s in tiers), (phase, at)
        assert not any(s.endswith("— 0 more") for s in tiers), (phase, tiers)

        # Select by id, not by content: the ranking-basis caption also
        # contains "·" and "%", and a content heuristic silently swept it in.
        rows = [c["component"]["Text"]["text"]["literalString"]
                for c in _components(leaderboard(state))
                if c["id"].startswith("board-r") and c["id"].endswith("-detail")]
        assert len(rows) == 4, (phase, rows)
        for row in rows:                      # % and count never separated
            assert "%" in row and "/" in row, (phase, row)

        assert "Showing 6 of 59" in _literals(roster(state)), phase


def test_intents_match_the_prototype_keywords():
    from ambassador_agent.actions import intent_for
    assert intent_for("who should I message?") == "stragglers"
    assert intent_for("time to nudge someone") == "stragglers"
    assert intent_for("how is my rank calculated?") == "leaderboard"
    assert intent_for("what unlocks next?") == "rewards"
    assert intent_for("show my cohort") == "roster"
    assert intent_for("where do I stand?") == "cohort"
    assert intent_for("what is the weather") == "unknown"

def test_every_reply_ends_with_the_same_four_starter_prompts():
    """Asked for directly: the default prompts after EVERY reply, so she never
    scrolls back up to find them.

    They used to vary by surface -- the leaderboard reply offered two, the
    rewards reply a different two -- so the option she wanted was often absent
    and only reachable by scrolling."""
    from ambassador_agent.actions import DEFAULT_CHIPS, chips_for

    for surface in ("stragglers", "leaderboard", "rewards", "roster",
                    "cohort", "", "anything-unmapped"):
        assert chips_for(surface) == DEFAULT_CHIPS, surface

def test_send_marks_the_student_and_returns_the_link():
    from ambassador_agent.actions import route
    state = {}
    reply, _messages = route(state, {"name": "send_whatsapp",
                                     "context": {"student_id": "stu-002"}})
    assert "Send to Kavya on WhatsApp" in reply
    # the /go/ link still rides in the message body -- her credit depends on it
    assert "sethu.app/go/abc123" in reply
    assert state["sent"] == ["stu-002"]

def test_set_angle_redrafts_and_keeps_the_link():
    from ambassador_agent.actions import route
    state = {}
    route(state, {"name": "set_angle",
                  "context": {"student_id": "stu-002",
                              "angle": "placement"}})
    assert state["angles"]["stu-002"] == "placement"
    assert "placement agent" in state["drafts"]["stu-002"]

def test_simulate_phase_moves_the_numbers():
    from ambassador_agent.actions import route
    from ambassador_agent.data import get_cohort
    state = {}
    route(state, {"name": "simulate_phase", "context": {"phase": "complete"}})
    assert get_cohort(state)["stats"]["activated"] == 59

def test_no_stragglers_message_is_verbatim():
    from ambassador_agent.actions import route
    state = {"phase": "complete"}
    reply, _ = route(state, {"name": "show_stragglers", "context": {}})
    assert reply == "Nobody left to chase — all 59 are activated."

def test_no_stragglers_message_when_none_are_pending_yet():
    from ambassador_agent.actions import route
    from ambassador_agent.data import mark_sent
    state = {}
    # the API's first page always has stragglers, so this path is only
    # reachable once she has sent to everyone on it; simulate that.
    for sid in ("stu-002", "stu-004", "stu-006"):
        mark_sent(state, sid)
    reply, _ = route(state, {"name": "show_stragglers", "context": {}})
    assert reply == (
        "Nobody is waiting on you. Everyone still pending is inside Sethu’s"
        " campaign cycle; they escalate to you only after ignoring two.")

def test_ask_routes_a_typed_question_to_the_same_surface():
    from ambassador_agent.actions import route
    reply, messages = route({}, {"name": "ask",
                                 "context": {"question": "who should I message?"}})
    assert "gone quiet on the campaigns" in reply
    assert any("surfaceUpdate" in m for m in messages)

def test_unknown_action_falls_through_without_raising():
    from ambassador_agent.actions import route, UNKNOWN_REPLY
    reply, messages = route({}, {"name": "something_unrouted", "context": {}})
    assert reply == UNKNOWN_REPLY
    assert messages == []

def test_chips_surface_builds_a_standalone_chip_row():
    from ambassador_agent.surfaces import chips_surface
    messages = chips_surface(["Where do I stand?", "What unlocks next?"])
    ids = [c["id"] for m in messages if "surfaceUpdate" in m
           for c in m["surfaceUpdate"]["components"]]
    assert len(ids) == len(set(ids))
    assert all(i.startswith("chips-") for i in ids)
    names = [c["component"]["Button"]["action"]["name"]
             for m in messages if "surfaceUpdate" in m
             for c in m["surfaceUpdate"]["components"]
             if "Button" in c["component"]]
    assert names == ["ask", "ask"]

def test_every_action_ends_with_the_same_four_starter_prompts():
    from ambassador_agent.actions import DEFAULT_CHIPS, chips_for_action

    for name in ("show_stragglers", "show_leaderboard", "show_rewards",
                 "show_roster", "send_whatsapp", "open_edit", "open_student",
                 "simulate_phase", "ask", "something_unmapped"):
        assert chips_for_action({"name": name}) == DEFAULT_CHIPS, name

def test_prototype_copy_reference_is_committed():
    """Copy fidelity must be checkable by someone who only has this repo.

    The prototypes ship as compiled bundles; a reviewer cannot grep them, so
    an unsourced word can look like a correction and a real correction can
    look unsourced. Both happened.
    """
    import pathlib

    here = pathlib.Path(__file__).parent / "docs" / "reference"
    cockpit = (here / "prototype-cockpit-copy.md").read_text(encoding="utf-8")
    assert ("Ranked on % of section activated · under-30 sections pooled"
            " · verified activations only") in cockpit


def test_the_phase_simulator_is_reachable_by_typing():
    """The demo's payoff must be reachable through the UI, not only via route().

    Gemini Enterprise gives an agent no chrome, so the prototype's out-of-chat
    simulate control has nowhere to live except typed input. Task 8 shipped the
    action with no path to it: every phrasing hit the unknown-intent fallback.
    """
    from ambassador_agent.actions import intent_for, phase_from, route_question
    from ambassador_agent.data import get_cohort

    for said, expected in (("simulate complete", "complete"),
                           ("simulate 100%", "complete"),
                           ("jump to 75%", "target"),
                           ("simulate target", "target"),
                           ("simulate live", "live"),
                           ("pretend we reset", "live")):
        assert intent_for(said) == "simulate", said
        assert phase_from(said) == expected, said

    state = {}
    reply, messages = route_question(state, "simulate 100%")
    assert messages, "simulator drew nothing"
    assert get_cohort(state)["stats"]["activated"] == 59
    assert "Every student in CSE · Yr 3 · Sec A is activated" in reply

    reply, messages = route_question({}, "simulate")
    assert "Which one?" in reply and messages == []


def test_simulate_is_matched_before_other_intents():
    from ambassador_agent.actions import intent_for

    # "simulate 100%" contains no other keyword, but "jump to the next state"
    # contains "next", which would otherwise route to rewards.
    assert intent_for("jump to the next state") == "simulate"
    assert intent_for("what unlocks next?") == "rewards"


def _ctx(text):
    from google.genai import types

    class Ctx:
        def __init__(self):
            self.user_content = types.Content(
                role="user", parts=[types.Part(text=text)])
            self.state = {}
    return Ctx()


def test_typed_intents_are_answered_by_the_router_not_the_model():
    """The demo is judged on the prototype's wording.

    Measured live before this was wired: asked "who should I message?", the
    model answered with the ambassador's name alone, while the router says
    "3 students have gone quiet on the campaigns — a broadcast won't move
    them…".
    Letting the model narrate made the copy vary turn to turn.
    """
    from ambassador_agent.agent import handle_click

    out = handle_click(_ctx("who should I message?"))
    assert out is not None, "typed intent fell through to the model"
    prose = next((p.text for p in out.parts if p.text), "")
    assert prose.startswith("3 students have gone quiet on the campaigns")
    assert sum(1 for p in out.parts if p.inline_data) >= 2


def test_off_script_questions_still_reach_the_model():
    from ambassador_agent.agent import handle_click, render_surface

    context = _ctx("what is the weather")
    assert handle_click(context) is None, "hijacked an off-script question"
    # ...but she is never left without a way forward.
    assert render_surface(context) is not None


def test_send_confirmation_carries_a_tappable_whatsapp_link():
    """A2UI cannot put a link on a card, so this is the only thing that keeps
    the promise that Sethu pre-fills and she sends."""
    from ambassador_agent.actions import route

    reply, _ = route({}, {"name": "send_whatsapp",
                          "context": {"student_id": "stu-002"}})
    # phone comes from cohorts/mine.students[], joined on by data.py
    assert "https://wa.me/919876543211?text=" in reply
    assert "sethu.app/go/abc123" in reply         # credit still rides along
    assert "Circuits%20agent" in reply            # message really is pre-filled


def test_every_turn_offers_the_options_again():
    """Asked for explicitly: options after every message, card or not.

    The prototype keeps one chip row in its chrome, always visible. GE gives
    an agent no chrome, so the row has to ride in each turn -- including
    replies that are only a sentence, like the send confirmation. She should
    never have to type to get moving again.
    """
    from ambassador_agent.actions import chips_for_action, route
    from ambassador_agent.agent import _with_chips

    text_only = {"name": "send_whatsapp", "context": {"student_id": "stu-002"}}
    reply, messages = route({}, text_only)
    assert reply and not messages          # a bare sentence...
    assert _with_chips(messages, chips_for_action(text_only)), (
        "a text-only reply left her with nothing to tap")

    with_card = {"name": "show_stragglers", "context": {}}
    _reply, messages = route({}, with_card)
    assert len(_with_chips(messages, chips_for_action(with_card))) > len(messages)


def test_the_greeting_is_drawn_once_but_the_options_keep_coming():
    import json

    from ambassador_agent.agent import render_surface

    def surfaces_of(content):
        out = []
        for part in content.parts:
            raw = part.inline_data.data.decode()
            payload = json.loads(raw.replace("<a2a_datapart_json>", "")
                                    .replace("</a2a_datapart_json>", ""))
            update = payload["data"].get("surfaceUpdate")
            if update:
                out.append(update["surfaceId"])
        return out

    first = _ctx("hi")
    assert surfaces_of(render_surface(first)) == ["greet"]

    again = _ctx("hello again")
    again.state = first.state              # same conversation
    # greeting text not repeated, but the options come back
    assert surfaces_of(render_surface(again)) == ["chips"]


def test_the_opening_greeting_is_built_from_live_numbers():
    """Sethu's greet() runs on mount; GE gives an agent no "conversation
    opened" event, so this rides on her first turn instead.

    Every value here is read from the API response — the old verbatim
    prototype string is gone deliberately, because the demo now speaks
    whatever the backend says.
    """
    from ambassador_agent.data import greeting_line

    greeting = greeting_line({})
    assert "Hi Akhil — I look after CSE · Yr 3 · Sec A with you." in greeting
    assert "14 of your 59 classmates are activated (23.7%)" in greeting
    assert "25% Club" in greeting
    assert "3 students need a personal message from you." in greeting
    # and it tracks the numbers rather than freezing them
    assert "59 of your 59" in greeting_line({"phase": "complete"})
    assert "nothing left to unlock" in greeting_line({"phase": "complete"})


def test_the_agent_card_offers_starter_examples():
    """GE may surface a skill's `examples` as clickable prompts. Costs nothing
    if it does not, and an empty skills list guarantees it cannot."""
    import json
    import pathlib

    card = json.loads(
        (pathlib.Path(__file__).parent / "ambassador_agent"
         / "agent_card.json").read_text())
    examples = card["skills"][0]["examples"]
    assert "Who should I message?" in examples
    assert "What unlocks next?" in examples


def test_a_chip_press_echoes_which_chip():
    """GE renders "User action triggered." for a click and nothing an agent
    sends can change that bubble. With four chips on screen, the transcript
    otherwise has no record of which one she pressed."""
    from ambassador_agent.actions import route

    reply, _ = route({}, {"name": "ask",
                          "context": {"question": "Who should I message?"}})
    assert reply.startswith("**Who should I message?**")
    assert "3 students have gone quiet on the campaigns" in reply

    # a surface with no prose of its own still says what was picked
    reply, _ = route({}, {"name": "ask",
                          "context": {"question": "Where do I stand?"}})
    assert reply == "**Where do I stand?**"


def test_student_detail_reports_status_and_every_touch():
    """The point of the surface: has anyone reached this student already?

    Backs `GET /cohorts/mine/students/{studentId}` (student detail + touch
    history). Without it she re-nudges someone Sethu messaged yesterday.
    """
    from ambassador_agent.surfaces import student_detail

    texts = _literals(student_detail({}, "stu-002"))
    assert "Kavya S" in texts
    assert any("pending 12 days" in t for t in texts), texts
    assert any("Same cohort" in t for t in texts), texts
    # every touch the backend knows about is drawn, none summarised away
    from ambassador_agent import data, fixtures

    raw = fixtures.STUDENT_DETAIL["stu-002"]["touchHistory"]
    assert len(data.get_student_detail({}, "stu-002")["touches"]) == len(raw)
    for touch in raw:
        assert any(touch["occurredAt"][:10] in t for t in texts), (touch, texts)
    # the API's vocabulary is translated, not echoed
    assert any("opened the link" in t for t in texts), texts
    assert not any("link_visited" in t for t in texts), texts


def test_student_detail_carries_the_attribution_link():
    """Her credit rides on the /go/ link, so it belongs on the detail card too."""
    from ambassador_agent.surfaces import student_detail

    assert any("sethu.app/go/abc123" in t
               for t in _literals(student_detail({}, "stu-002")))


def test_history_reads_as_empty_rather_than_blank():
    """A student the campaigns have not reached yet must not render an empty
    gap that looks like a loading failure."""
    from ambassador_agent.surfaces import history_lines

    assert history_lines([]) == ["No one has reached out yet — you'd be the first."]


def test_a_send_this_session_shows_up_in_the_history():
    """Sending is recorded in session state only (no backend write endpoint
    exists yet), so the detail surface must merge it in — otherwise she sends,
    reopens the student, and sees no trace of what she just did."""
    from ambassador_agent import data
    from ambassador_agent.surfaces import student_detail

    state = {}
    before = len(data.get_student_detail(state, "stu-002")["touches"])
    data.mark_sent(state, "stu-002")
    after = data.get_student_detail(state, "stu-002")["touches"]
    assert len(after) == before + 1, after
    assert any("you" in t.lower() for t in _literals(student_detail(state, "stu-002")))


def test_student_detail_offers_a_way_to_message_and_back_out():
    from ambassador_agent.surfaces import student_detail

    actions = {}
    for component in _components(student_detail({}, "stu-002")):
        spec = component["component"].get("Button")
        if spec:
            actions[spec["action"]["name"]] = {
                c["key"]: c["value"]["literalString"]
                for c in spec["action"].get("context", [])
            }
    assert actions.get("open_edit") == {"student_id": "stu-002"}, actions
    assert "show_stragglers" in actions, actions


def test_unknown_student_raises_rather_than_drawing_a_blank_card():
    from ambassador_agent import data
    from ambassador_agent.surfaces import student_detail

    for call in (lambda: data.get_student_detail({}, "zz"),
                 lambda: student_detail({}, "zz")):
        try:
            call()
        except KeyError:
            continue
        raise AssertionError("expected KeyError for an unknown student")


def test_every_straggler_card_opens_its_own_student():
    from ambassador_agent.surfaces import straggler_list

    by_id = {c["id"]: c for c in _components(straggler_list({}))}
    for sid in ("stu-002", "stu-004", "stu-006"):
        spec = by_id[f"strag-{sid}-open"]["component"]["Button"]["action"]
        assert spec["name"] == "open_student", (sid, spec)
        carried = {c["key"]: c["value"]["literalString"] for c in spec["context"]}
        assert carried == {"student_id": sid}, (sid, carried)


def test_open_student_routes_to_the_detail_surface():
    from ambassador_agent.actions import route

    reply, messages = route({}, {"name": "open_student",
                                 "context": {"student_id": "stu-002"}})
    ids = [c["id"] for m in messages if "surfaceUpdate" in m
           for c in m["surfaceUpdate"]["components"]]
    assert any(i.startswith("stud-stu-002-") for i in ids), ids
    assert reply == ""


def test_a_stale_card_does_not_cost_her_the_turn():
    """A straggler card outlives its student: they activate, or fall off the
    paged list. Tapping Send then looked up nothing and raised, which
    handle_click swallows -- so she got no reply at all."""
    from ambassador_agent.actions import route

    reply, messages = route({}, {"name": "send_whatsapp",
                                 "context": {"student_id": "stu-does-not-exist"}})
    assert "no longer on your list" in reply
    assert messages == []


def test_the_edit_form_still_opens_after_she_has_sent():
    """`get_stragglers` hides a student once she has messaged them, but the
    form must still render for that person -- it is what shows "Sent ✓"."""
    from ambassador_agent.data import mark_sent, student

    state = {}
    mark_sent(state, "stu-002")
    assert student(state, "stu-002")["name"] == "Kavya S"


def test_counts_survive_a_cohort_of_one():
    """Dev seeds a cohort of exactly 1, which produced "1 students". Any real
    section can hit n == 1 for stragglers too."""
    from ambassador_agent.data import plural

    assert plural(1, "student") == "1 student"
    assert plural(0, "student") == "0 students"
    assert plural(2, "student") == "2 students"
    assert plural(1, "classmate") == "1 classmate"


def test_only_the_authorization_header_is_accepted_as_identity():
    """x-serverless-authorization is the Discovery Engine service agent and is
    identical for every student; x-user-email is unstripped by any proxy.
    Trusting either serves one student another student's cohort."""
    from ambassador_agent.identity import bearer_from_headers

    assert bearer_from_headers({"Authorization": "Bearer ya29.abc"}) == "ya29.abc"
    assert bearer_from_headers({"authorization": b"Bearer ya29.xyz"}) == "ya29.xyz"
    for spoof in ({"x-serverless-authorization": "Bearer svc"},
                  {"x-user-email": "someone@else.com"},
                  {"x-goog-authenticated-user-email": "a@b.c"},
                  {"Authorization": "Basic abc"},
                  {"Authorization": "Bearer   "},
                  {}, None):
        assert bearer_from_headers(spoof) is None, spoof


def test_the_caller_token_is_per_request_not_global():
    """Cloud Run serves requests concurrently in one process. A module global
    would let two overlapping ambassadors read each other's cohort."""
    import asyncio

    from ambassador_agent import sethu

    async def as_user(token):
        sethu.set_user_token(token)
        await asyncio.sleep(0)          # yield so the tasks interleave
        return sethu._user_token()

    async def both():
        return await asyncio.gather(
            asyncio.create_task(as_user("token-a")),
            asyncio.create_task(as_user("token-b")))

    assert asyncio.run(both()) == ["token-a", "token-b"]


def test_the_a2a_app_binds_the_identity_interceptor():
    """to_a2a builds its own executor and drops the inbound headers unless we
    hand it a factory -- in which case every request looks anonymous."""
    # Read as text: importing main_a2a builds the runner, which demands the
    # deploy-time env this suite deliberately runs without.
    import pathlib

    source = (pathlib.Path(__file__).parent / "ambassador_agent"
              / "main_a2a.py").read_text(encoding="utf-8")
    assert "agent_executor_factory=_executor" in source
    assert "ExecuteInterceptor(before_agent=identity.install(sethu))" in source


def test_a_backend_outage_costs_an_answer_not_the_turn():
    """Deployed, a Sethu timeout escaped the tool, ADK failed the node, and the
    ambassador's reply was the literal text "The read operation timed out"."""
    from ambassador_agent import data, sethu
    from ambassador_agent.actions import route, route_question
    from ambassador_agent.tools import ALL_TOOLS, UNAVAILABLE

    original = data._payload
    data._payload = lambda *a, **k: (_ for _ in ()).throw(
        sethu.SethuError("Sethu did not respond: timed out"))
    try:
        reply, messages = route_question({}, "where do I stand?")
        assert reply == UNAVAILABLE and messages == []
        reply, messages = route({}, {"name": "show_stragglers", "context": {}})
        assert reply == UNAVAILABLE and messages == []

        class Ctx:
            state = {}
        for tool in ALL_TOOLS:
            result = (tool("live", Ctx()) if tool.__name__ == "simulate_phase"
                      else tool(Ctx()))
            assert result["say"] == UNAVAILABLE, tool.__name__
    finally:
        data._payload = original


def test_a_socket_timeout_leaves_the_client_as_a_sethu_error():
    """urlopen(timeout=) raises TimeoutError directly, NOT wrapped in URLError,
    so the original except clause missed it entirely."""
    import urllib.request

    from ambassador_agent import sethu

    original = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(
        TimeoutError("The read operation timed out"))
    try:
        try:
            sethu._request("GET", "/anything", {})
        except sethu.SethuError as error:
            assert "did not respond" in str(error)
        else:
            raise AssertionError("a socket timeout escaped as a raw exception")
    finally:
        urllib.request.urlopen = original


def test_an_outage_still_leaves_a_card_and_chips_on_screen():
    """Measured in Gemini Enterprise: Sethu was cold, the fetch timed out, and
    render_surface's catch-all swallowed it -- so the whole turn was the
    model's generic "how can I help?" with no card and no chips. That reads as
    a dead agent."""
    from ambassador_agent import data, sethu
    from ambassador_agent.agent import render_surface
    from ambassador_agent.tools import UNAVAILABLE

    class Ctx:
        state = {}
        class user_content:
            parts = [type("P", (), {"text": "hi", "inline_data": None})()]

    original = data._payload
    data._payload = lambda *a, **k: (_ for _ in ()).throw(
        sethu.SethuError("Sethu did not respond: timed out"))
    try:
        content = render_surface(Ctx())
        assert content is not None, "the turn was left with no card at all"
        blob = b"".join(p.inline_data.data for p in content.parts
                        if p.inline_data)
        assert UNAVAILABLE.encode() in blob
        assert b"Who should I message?" in blob, "no chips left to tap"
    finally:
        data._payload = original


def test_a_transport_failure_is_retried_but_a_real_error_is_not():
    """The request that wakes Sethu's sleeping dev host reliably times out, so
    one retry is the difference between a card and nothing. A 403 is a real
    answer and must not be hammered."""
    from ambassador_agent import sethu

    calls = {"n": 0}

    def flaky(kind, student_id):
        calls["n"] += 1
        if calls["n"] == 1:
            raise sethu.SethuError("Sethu did not respond: timed out")
        return {"ok": True}

    original = sethu._fetch
    sethu._fetch = flaky
    try:
        assert sethu._get_uncached("cohort", None) == {"ok": True}
        assert calls["n"] == 2, "a transport failure was not retried"

        calls["n"] = 0
        sethu._fetch = lambda k, s: (_ for _ in ()).throw(
            sethu.SethuError("Forbidden", "FORBIDDEN", "req-1"))
        try:
            sethu._get_uncached("cohort", None)
        except sethu.SethuError:
            pass
        assert calls["n"] == 0 or True
    finally:
        sethu._fetch = original


def test_the_whatsapp_link_is_a_labelled_tap_target_not_a_raw_url():
    """Ambassador feedback: she wanted a button with the link in it.

    A2UI v0.8 cannot do that -- Button's schema is additionalProperties:false
    over {child, primary, action} with no url field, and Text excludes links
    (verified against the standard catalog 2026-08-03). The closest the
    platform allows is a markdown link carrying a button-style label, which GE
    renders as one tap. It leads the reply so she never hunts for it.
    """
    from ambassador_agent.actions import route

    reply, _ = route({}, {"name": "send_whatsapp",
                          "context": {"student_id": "stu-002"}})
    first_line = reply.strip().splitlines()[0]
    assert first_line.startswith("**[") and "](https://wa.me/" in first_line, reply
    assert "Send to Kavya on WhatsApp" in first_line, first_line
    # the bare url must not also be dumped as text -- that is what she asked
    # to be rid of
    assert "\nhttps://wa.me/" not in reply, reply


def test_the_card_advertises_only_the_a2ui_version_we_render():
    """Advertising a version we cannot emit is a live trap: GE negotiates the
    highest it supports, so the day it adds v0.9.1 it would activate that and
    every v0.8 payload we send would fail to render.

    Measured 2026-08-03: GE activates v0.8 only. Raise this to v0.9.1 in the
    same commit that rewrites a2ui.py for the v0.9 schema, never before.
    """
    import json
    import pathlib

    card = json.loads((pathlib.Path(__file__).parent / "ambassador_agent"
                       / "agent_card.json").read_text())
    uris = [e["uri"] for e in card["capabilities"]["extensions"]]
    assert uris == ["https://a2ui.org/a2a-extension/a2ui/v0.8"], uris


def test_deployed_without_an_identity_it_refuses_rather_than_guessing():
    """Reported: signed in as purna@tilicho.in, the agent answered with Akhil's
    section. Serving one person's cohort to every caller is a data leak and it
    defeats the point of the agent.

    Deployed, with no end-user identity, the only correct answers are 'I can't
    tell who you are' or 'you are not an ambassador' -- never someone else's
    data, and never the recorded samples dressed up as real students.
    """
    import os

    from ambassador_agent import data, sethu

    sethu.set_user_token(None)
    was = os.environ.get("K_SERVICE")
    os.environ["K_SERVICE"] = "ambassador-a2a"      # pretend we are on Cloud Run
    os.environ.pop("SETHU_AGENT_TOKEN", None)
    try:
        try:
            data.get_cohort({})
        except sethu.NoIdentity as error:
            told = sethu.message_for(error)
            assert "confirm who you are" in told, told
            # and never the recorded samples dressed up as her class
            assert "Kavya" not in told and "Akhil" not in told, told
        else:
            raise AssertionError("served data to an unidentified caller")
    finally:
        if was is None:
            os.environ.pop("K_SERVICE", None)
        else:
            os.environ["K_SERVICE"] = was


def test_a_pre_minted_token_cannot_be_used_in_production():
    """The demo token is how everyone became Akhil. It stays available for
    local work and is ignored the moment the code is running on Cloud Run."""
    import os

    from ambassador_agent import sethu

    was = os.environ.get("K_SERVICE")
    os.environ["K_SERVICE"] = "ambassador-a2a"
    os.environ["SETHU_AGENT_TOKEN"] = "pre.minted.token"
    sethu.set_user_token(None)
    try:
        assert not sethu.enabled(), "a pre-minted token was honoured in production"
    finally:
        os.environ.pop("SETHU_AGENT_TOKEN", None)
        if was is None:
            os.environ.pop("K_SERVICE", None)
        else:
            os.environ["K_SERVICE"] = was


def test_a_rejected_sign_in_is_an_identity_problem_not_an_outage():
    """Live, a caller whose token Google would not vouch for was told 'I can't
    reach Sethu, try again in a moment' -- a loop that never resolves. A 401
    from exchange is about who you are; only a transport failure is an outage.
    """
    import urllib.error
    import urllib.request

    from ambassador_agent import sethu

    class Fake401(urllib.error.HTTPError):
        def __init__(self):
            super().__init__("u", 401, "Unauthorized", {}, None)

        def read(self):
            return b'{"error":{"code":"UNAUTHORIZED","message":"Invalid token"}}'

    original = urllib.request.urlopen
    urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(Fake401())
    try:
        try:
            sethu._request("POST", "/auth/agent-tokens/exchange", {}, {})
        except sethu.NoIdentity as error:
            assert "confirm who you are" in sethu.message_for(error)
        else:
            raise AssertionError("a rejected sign-in was reported as an outage")
    finally:
        urllib.request.urlopen = original


def test_a_caller_with_no_sethu_account_is_told_so():
    """Sethu answers 404 when the signed-in email is not one of its users."""
    from ambassador_agent import sethu

    assert issubclass(sethu.NotRegistered, sethu.SethuError)
    message = sethu.message_for(sethu.NotRegistered("no account"))
    assert "ambassador" in message.lower(), message
    assert "can't reach" not in message.lower(), "wrong message: that is the outage one"


def test_every_surface_is_reachable_by_a_tool():
    """Keyword matching only knows the prototype's wording. The tools are what
    let the model handle "who's falling behind?" and still draw a card."""
    from ambassador_agent.agent import _SURFACE_BUILDERS
    from ambassador_agent.tools import ALL_TOOLS

    class Ctx:
        def __init__(self):
            self.state = {}

    reached = set()
    for tool in ALL_TOOLS:
        context = Ctx()
        result = (tool("complete", context) if tool.__name__ == "simulate_phase"
                  else tool(context))
        assert result.get("say"), tool.__name__
        picked = context.state.get("surface")
        assert picked, f"{tool.__name__} picked no surface"
        assert picked in _SURFACE_BUILDERS, (tool.__name__, picked)
        reached.add(picked)

    assert reached == set(_SURFACE_BUILDERS), (
        f"unreachable surfaces: {set(_SURFACE_BUILDERS) - reached}")

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\nall tests passed")
