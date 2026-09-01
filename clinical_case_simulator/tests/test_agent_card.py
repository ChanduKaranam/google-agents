"""The agent card is the contract Gemini Enterprise registers against."""

from clinical_simulator.agent_card import SKILLS, build

URL = "https://clinical-case-simulator-abc.a.run.app"

# Fields Gemini Enterprise's A2A registration form documents as required.
REQUIRED_V03 = {
    "protocolVersion", "name", "description", "url", "version",
    "defaultInputModes", "defaultOutputModes", "capabilities", "skills",
}


def test_v03_card_has_every_required_field():
    card = build(URL)
    assert REQUIRED_V03 <= set(card)
    assert card["url"] == URL
    assert card["protocolVersion"].startswith("0.3")


def test_v1_card_advertises_the_url_as_an_interface():
    card = build(URL, v1_shape=True)
    interfaces = card["supportedInterfaces"]
    assert interfaces[0]["url"] == URL
    assert "url" not in card, "the v1.0 shape carries the URL in supportedInterfaces"


def test_trailing_slash_is_normalised():
    assert build(URL + "/")["url"] == URL


def test_skills_describe_student_intents_not_internal_tools():
    ids = {s["id"] for s in SKILLS}
    # Tool names must not leak into the card as if they were user-facing skills.
    for internal in ("reveal_answer", "submit_differential", "record_metacognition"):
        assert internal not in ids
    for skill in SKILLS:
        assert skill["examples"], f"{skill['id']} has no examples for routing"
        assert skill["tags"]


def test_card_states_it_is_educational_only():
    text = build(URL)["description"].lower()
    assert "educational" in text or "simulation" in text
    assert "not clinical advice" in text or "not a diagnostic tool" in text
