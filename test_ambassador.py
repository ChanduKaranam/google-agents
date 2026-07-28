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

def test_live_phase_matches_the_prototype():
    from ambassador_agent.data import get_cohort
    cohort = get_cohort({})
    assert cohort["stats"] == {"activated": 43, "size": 59, "pct": 72.9}
    assert cohort["ambassador"] == {"name": "Sneha Reddy",
                                    "section": "EEE Sem 3 · Sec B"}

def test_milestone_line_is_verbatim():
    from ambassador_agent.data import milestone_line
    assert milestone_line({}) == (
        "2 more activations clear your 75% milestone.")
    assert milestone_line({"phase": "target"}) == (
        "Your 75% milestone is earned. 5 more makes Full House, "
        "the 100% badge.")
    assert milestone_line({"phase": "complete"}) == (
        "Every student in Sec B is activated — nothing left to unlock.")

def test_target_phase_leaves_two_stragglers():
    from ambassador_agent.data import get_stragglers
    assert len(get_stragglers({})["data"]) == 6
    ids = [s["studentId"] for s in get_stragglers({"phase": "target"})["data"]]
    assert ids == ["dg", "rt"]
    assert get_stragglers({"phase": "complete"})["data"] == []

def test_sent_students_drop_out_of_the_pending_list():
    from ambassador_agent.data import get_stragglers, mark_sent
    state = {}
    mark_sent(state, "pn")
    ids = [s["studentId"] for s in get_stragglers(state)["data"]]
    assert "pn" not in ids and len(ids) == 5

def test_drafts_change_with_the_angle():
    from ambassador_agent.data import draft_for
    assert draft_for("pn", "Exam panic").startswith(
        "Hey Priya — internals Tuesday.")
    assert draft_for("pn", "Placement").startswith(
        "Hey Priya — the placement agent")
    assert draft_for("pn", "Plain").startswith(
        "Hey Priya — your college study agents are ready.")

def test_leaderboard_shows_percent_and_count_together():
    from ambassador_agent.data import get_leaderboard
    board = get_leaderboard({})
    assert board["myRank"] == 19
    me = [r for r in board["data"] if r["name"] == "You"][0]
    assert me["pct"] == 72.9 and me["activated"] == 43 and me["size"] == 59
    assert [r["rank"] for r in board["data"]] == [1, 2, 3, 19]

def test_get_leaderboard_does_not_mutate_fixtures():
    from ambassador_agent import fixtures
    from ambassador_agent.data import get_leaderboard
    get_leaderboard({})
    assert all("rank" not in p for p in fixtures.PEERS)

def test_leaderboard_at_complete_puts_sneha_first():
    from ambassador_agent.data import get_leaderboard
    board = get_leaderboard({"phase": "complete"})
    assert board["myRank"] == 1
    me = [r for r in board["data"] if r["name"] == "You"][0]
    assert me["rank"] == 1 and me["pct"] == 100.0
    assert [r["rank"] for r in board["data"]] == [1, 2, 3, 4]

def test_mark_sent_is_idempotent():
    from ambassador_agent.data import get_stragglers, mark_sent
    state = {}
    mark_sent(state, "pn")
    mark_sent(state, "pn")
    assert state["sent"] == ["pn"]
    ids = [s["studentId"] for s in get_stragglers(state)["data"]]
    assert "pn" not in ids and len(ids) == 5

def test_cohort_card_carries_the_certified_label_and_both_numbers():
    from ambassador_agent.surfaces import cohort_summary
    strings = _literals(cohort_summary({}))
    assert "EEE SEM 3 · SEC B — CERTIFIED" in strings
    assert "43 / 59" in strings
    assert "72.9%" in strings
    assert any("2 more activations clear your 75% milestone." in s
               for s in strings)
    assert "Show the 6 who need me" in strings
    assert "How is my rank calculated?" in strings

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
    assert names.count("send_whatsapp") == 6
    assert names.count("open_edit") == 6
    strings = _literals(messages)
    assert "Priya Nandakumar" in strings
    assert "ignored 2 campaigns · 11 days" in strings
    assert any("sethu.app/go/pn8x2" in s for s in strings)

def test_send_buttons_carry_the_student_id():
    from ambassador_agent.surfaces import straggler_list
    sends = [c["component"]["Button"]["action"]
             for c in _components(straggler_list({}))
             if "Button" in c["component"]
             and c["component"]["Button"]["action"]["name"] == "send_whatsapp"]
    ids = [ctx["value"]["literalString"]
           for a in sends for ctx in a["context"] if ctx["key"] == "student_id"]
    assert ids == ["pn", "sk", "ar", "vm", "dg", "rt"]

def test_sent_students_leave_the_list():
    from ambassador_agent.data import mark_sent
    from ambassador_agent.surfaces import straggler_list
    state = {}
    mark_sent(state, "pn")
    assert "Priya Nandakumar" not in _literals(straggler_list(state))

def test_ids_stay_unique_across_six_student_cards():
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
_EXTRA_ARGS = {"edit_form": ("pn",)}


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
    and still send Priya's message to Rahul.
    """
    from ambassador_agent.surfaces import straggler_list

    components = _components(straggler_list({}))
    by_id = {c["id"]: c for c in components}
    expected = {
        "pn": "Priya Nandakumar", "sk": "Suresh Kumar", "ar": "Anjali Rao",
        "vm": "Vikram Mehta", "dg": "Deepa Gowda", "rt": "Rahul Tiwari",
    }
    for sid, name in expected.items():
        shown = by_id[f"strag-{sid}-name"]["component"]["Text"]["text"]
        assert shown["literalString"] == name, (sid, shown)
        for suffix, action in (("send", "send_whatsapp"), ("edit", "open_edit")):
            spec = by_id[f"strag-{sid}-{suffix}"]["component"]["Button"]["action"]
            assert spec["name"] == action, (sid, suffix, spec)
            carried = {c["key"]: c["value"]["literalString"]
                       for c in spec["context"]}
            assert carried == {"student_id": sid}, (sid, suffix, carried)


def test_edit_form_offers_three_angles_and_a_send():
    from ambassador_agent.surfaces import edit_form
    messages = edit_form({}, "pn")
    strings = _literals(messages)
    assert "Edit before sending — Priya Nandakumar" in strings
    # Angles render with a selection marker ("● Exam panic"), so match on
    # substring. An exact assertion here would push the implementer to
    # restructure the card just to satisfy the test.
    for angle in ("Exam panic", "Placement", "Plain"):
        assert any(angle in s for s in strings)
    assert "Send to Priya" in strings
    names = _action_names(messages)
    assert names.count("set_angle") == 3
    assert "send_whatsapp" in names


def test_send_carries_the_edited_text_by_path():
    from ambassador_agent.surfaces import edit_form
    send = [c["component"]["Button"]["action"]
            for c in _components(edit_form({}, "pn"))
            if "Button" in c["component"]
            and c["component"]["Button"]["action"]["name"] == "send_whatsapp"][0]
    by_key = {ctx["key"]: ctx["value"] for ctx in send["context"]}
    assert by_key["student_id"] == {"literalString": "pn"}
    assert by_key["message"] == {"path": "/draft/text"}


def test_sent_form_locks_and_relabels():
    from ambassador_agent.data import mark_sent
    from ambassador_agent.surfaces import edit_form
    state = {}
    mark_sent(state, "pn")
    strings = _literals(edit_form(state, "pn"))
    assert "Sent — Priya Nandakumar" in strings
    assert "Sent to Priya ✓" in strings



def test_edit_form_keeps_an_in_flight_edit():
    """Her own words win over the angle's template.

    Task 8 writes `state["drafts"][id]` when she edits, then re-renders on the
    next action. If the form re-seeded from the template it would silently
    discard what she typed.
    """
    from ambassador_agent.surfaces import edit_form

    typed = "Priya please just open it, it takes two minutes 🙏"
    messages = edit_form({"drafts": {"pn": typed}}, "pn")
    seeded = [m for m in messages if "dataModelUpdate" in m][0]
    assert seeded["dataModelUpdate"]["contents"]["draft"]["text"] == typed

def test_leaderboard_always_shows_percent_and_count_and_the_basis():
    from ambassador_agent.surfaces import leaderboard
    strings = _literals(leaderboard({}))
    assert any("96.7%" in s and "58 / 60" in s for s in strings)
    assert any("72.9%" in s and "43 / 59" in s for s in strings)
    assert any(s.startswith("#19") for s in strings)
    assert "178 qualifying sections · under-30 pooled" in strings

def test_leaderboard_marks_her_row_in_text_not_colour():
    from ambassador_agent.surfaces import leaderboard
    assert any("You" in s and "EEE Sem 3 · Sec B" in s
               for s in _literals(leaderboard({})))

def test_rewards_lists_four_tiers_with_status():
    from ambassador_agent.surfaces import rewards
    strings = _literals(rewards({}))
    assert "75% Club — tee + certificate" in strings
    assert "Full House — the 100% badge" in strings
    assert any("2 more" in s for s in strings)  # renders as "at 75% — 2 more"
    # Count the rows whose status is earned, not bare occurrences of the word
    # -- an exact-count assertion pushed an earlier build to drop "at 25%"
    # from those rows entirely just to make the number come out right.
    assert len([s for s in strings if s.endswith("— earned")]) == 2
    assert "at 25% — earned" in strings and "at 50% — earned" in strings

def test_roster_shows_six_of_fiftynine():
    from ambassador_agent.surfaces import roster
    strings = _literals(roster({}))
    assert "Aarti Sharma" in strings
    assert "Showing 6 of 59" in strings



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

def test_chips_change_with_the_surface():
    from ambassador_agent.actions import chips_for
    assert chips_for("stragglers") == [
        "Where do I stand?", "What unlocks next?", "Show my cohort"]
    assert chips_for("leaderboard") == [
        "Who should I message?", "What unlocks next?"]
    assert chips_for("rewards") == [
        "Who should I message?", "Where do I stand?"]
    assert len(chips_for("cohort")) == 4

def test_send_marks_the_student_and_returns_the_link():
    from ambassador_agent.actions import route
    state = {}
    reply, _messages = route(state, {"name": "send_whatsapp",
                                     "context": {"student_id": "pn"}})
    assert "Opened WhatsApp with the message for Priya." in reply
    assert "sethu.app/go/pn8x2" in reply
    assert state["sent"] == ["pn"]

def test_set_angle_redrafts_and_keeps_the_link():
    from ambassador_agent.actions import route
    state = {}
    route(state, {"name": "set_angle",
                  "context": {"student_id": "pn", "angle": "Placement"}})
    assert state["angles"]["pn"] == "Placement"
    assert "placement agent" in state["drafts"]["pn"]

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
    # live phase always has 6 stragglers in fixtures, so this path is only
    # reachable once everyone in the pool has been sent to; simulate that.
    for sid in ("pn", "sk", "ar", "vm", "dg", "rt"):
        mark_sent(state, sid)
    reply, _ = route(state, {"name": "show_stragglers", "context": {}})
    assert reply == (
        "Nobody is waiting on you. Everyone still pending is inside Sethu’s"
        " campaign cycle; they escalate to you only after ignoring two.")

def test_ask_routes_a_typed_question_to_the_same_surface():
    from ambassador_agent.actions import route
    reply, messages = route({}, {"name": "ask",
                                 "context": {"question": "who should I message?"}})
    assert "ignored two campaigns" in reply
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

def test_chips_for_action_maps_the_action_name_to_its_surface():
    from ambassador_agent.actions import chips_for_action
    assert chips_for_action({"name": "show_stragglers"}) == [
        "Where do I stand?", "What unlocks next?", "Show my cohort"]
    assert chips_for_action({"name": "show_leaderboard"}) == [
        "Who should I message?", "What unlocks next?"]
    assert chips_for_action({"name": "show_rewards"}) == [
        "Who should I message?", "Where do I stand?"]
    assert len(chips_for_action({"name": "send_whatsapp"})) == 4

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
    assert "Every student in Sec B is activated" in reply

    reply, messages = route_question({}, "simulate")
    assert "Which one?" in reply and messages == []


def test_simulate_is_matched_before_other_intents():
    from ambassador_agent.actions import intent_for

    # "simulate 100%" contains no other keyword, but "jump to the next state"
    # contains "next", which would otherwise route to rewards.
    assert intent_for("jump to the next state") == "simulate"
    assert intent_for("what unlocks next?") == "rewards"

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\nall tests passed")
