import importlib

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

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("\nall tests passed")
