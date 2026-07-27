"""Checks for the things that break silently.

No network, no LLM calls. Run with: .venv/bin/python -m pytest test_agent.py
or just: .venv/bin/python test_agent.py
"""

import json
import os
import pathlib

from google.adk.memory.vertex_ai_memory_bank_service import VertexAiMemoryBankService
from google.adk.sessions.vertex_ai_session_service import VertexAiSessionService
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.function_tool import FunctionTool

from Job_Helper_agent.agent import SPECIALISTS, root_agent
from Job_Helper_agent.callbacks import require_real_user
from Job_Helper_agent.runtime import REQUIRED_ENV, build_runner
from Job_Helper_agent.tools import list_applications, track_application

# Built-in Gemini tools, which cannot share an agent with function tools.
BUILT_IN_NAMES = {"google_search", "url_context", "code_execution", "computer_use"}

EXPECTED_OUTPUT_KEYS = {
    "profile_agent": "profile",
    "company_agent": "companies",
    "alumni_agent": "alumni",
    "matching_agent": "matches",
    "verification_agent": None,
    "resume_gap_agent": "gaps",
    "outreach_agent": None,
    "tracker_agent": None,
    "coach_agent": None,
}


def _tool_name(tool) -> str:
    if isinstance(tool, AgentTool):
        return tool.agent.name
    return getattr(tool, "name", None) or getattr(tool, "__name__", repr(tool))


def _is_built_in(tool) -> bool:
    return _tool_name(tool) in BUILT_IN_NAMES


def _is_function_tool(tool) -> bool:
    # A plain python function passed to `tools=` is wrapped by ADK, so accept
    # both shapes.
    return callable(tool) and not isinstance(tool, BaseTool) or isinstance(
        tool, (FunctionTool, AgentTool)
    )


def test_root_has_all_specialists_plus_infrastructure_tools():
    names = [_tool_name(t) for t in root_agent.tools]
    for agent in SPECIALISTS:
        assert agent.name in names, f"{agent.name} not wired into root"

    # These two are easy to drop in a refactor and their absence is silent:
    # without load_artifacts the agent can never read an uploaded resume and
    # will likely invent one; without preload_memory a returning student's
    # application history never comes back.
    assert "load_artifacts" in names, "root cannot read uploaded resumes"
    assert "preload_memory" in names, "root cannot recall application history"
    assert "alumni_search_links" in names, "no fallback when alumni search is empty"
    assert len(root_agent.tools) == len(SPECIALISTS) + 3


def test_output_keys_match_the_spec():
    for agent in SPECIALISTS:
        expected = EXPECTED_OUTPUT_KEYS[agent.name]
        assert agent.output_key == expected, (
            f"{agent.name} output_key is {agent.output_key!r}, expected"
            f" {expected!r} -- downstream agents read this via {{key?}}"
        )


def test_no_agent_can_fetch_linkedin():
    """url_context would fetch any URL a student pasted, including LinkedIn.

    robots.txt is `User-agent: * / Disallow: /`, so that would be prohibited
    automated access originating from our production agent. Job descriptions
    now go through fetch_job_description, which blocklists such domains in
    code -- instructions alone have already failed us twice.
    """
    for agent in [root_agent, *SPECIALISTS]:
        assert "url_context" not in [_tool_name(t) for t in (agent.tools or [])], (
            f"{agent.name} holds url_context, which will fetch any URL given to it"
        )


def test_no_agent_mixes_builtin_and_function_tools():
    """The constraint ADK will not enforce for us.

    A Gemini built-in cannot share an LlmAgent with custom function tools. ADK
    raises nothing (llm_agent.py:139-176 silently rewrites instead), and the
    auto-wrap workaround defaults to off, so this fails at the Gemini API --
    potentially only once deployed.
    """
    for agent in [root_agent, *SPECIALISTS]:
        tools = list(agent.tools or [])
        built_ins = [t for t in tools if _is_built_in(t)]
        if not built_ins:
            continue
        assert len(tools) == 1, (
            f"{agent.name} holds built-in {_tool_name(built_ins[0])!r} alongside"
            f" {[_tool_name(t) for t in tools if not _is_built_in(t)]}."
            " Gemini rejects this at request time."
        )


class _FakeCallbackContext:
    def __init__(self, user_id):
        self.user_id = user_id


def test_identity_guard_rejects_untrustworthy_user_ids():
    # Agent Engine's silent fallback.
    assert require_real_user(_FakeCallbackContext("default-user-id")) is not None

    # ADK's A2A fallback when auth is off. Per-conversation, not per-student:
    # letting this through means Memory Bank scopes history to a single chat
    # and the privacy guard is effectively disabled.
    assert require_real_user(_FakeCallbackContext("A2A_USER_ctx-abc123")) is not None
    assert require_real_user(_FakeCallbackContext("A2A_USER_")) is not None

    # A real signed-in student must still get through.
    assert require_real_user(_FakeCallbackContext("student@example.com")) is None


class _FakeContext:
    """Minimal stand-in for ToolContext: the tools only touch .state."""

    def __init__(self):
        self.state = {}


def test_track_application_appends_then_updates():
    ctx = _FakeContext()

    first = track_application("Google", "SWE Intern", "Applied", "via careers page", ctx)
    assert first["total"] == 1
    assert ctx.state["applications"][0]["company"] == "Google"

    track_application("Atlassian", "Backend Intern", "Applied", "", ctx)
    listed = list_applications(ctx)
    assert listed["total"] == 2

    # Same company + role must update in place, not duplicate -- otherwise the
    # coach agent double-counts the pipeline.
    moved = track_application("google", "swe intern", "Interview", "onsite Aug 3", ctx)
    assert "updated" in moved
    assert moved["total"] == 2
    assert ctx.state["applications"][0]["status"] == "Interview"
    assert ctx.state["applications"][0]["notes"] == "onsite Aug 3"


def test_track_application_rejects_unknown_status():
    ctx = _FakeContext()
    result = track_application("Google", "SWE", "Ghosted", "", ctx)
    assert "error" in result
    assert ctx.state.get("applications") in (None, [])


def test_build_runner_refuses_to_start_without_backing_store_config():
    # Fail loudly at boot rather than silently serving from memory: an
    # in-memory session service on Cloud Run loses a student's tracked
    # applications the moment the instance recycles.
    saved = {k: os.environ.pop(k, None) for k in REQUIRED_ENV}
    try:
        raised = None
        try:
            build_runner()
        except RuntimeError as e:
            raised = e
        assert raised is not None, "build_runner started with no configuration"
        assert "AGENT_ENGINE_ID" in str(raised)

        # Partial config is the likelier deploy mistake than none at all, and
        # the message has to name everything still missing or the operator
        # fixes one variable per redeploy.
        os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
        raised = None
        try:
            build_runner()
        except RuntimeError as e:
            raised = e
        assert raised is not None, "build_runner started with partial configuration"
        assert "GOOGLE_CLOUD_LOCATION" in str(raised)
        assert "AGENT_ENGINE_ID" in str(raised)
        assert "GOOGLE_CLOUD_PROJECT" not in str(raised)
    finally:
        for k in REQUIRED_ENV:
            os.environ.pop(k, None)
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_build_runner_uses_persistent_services_not_in_memory_defaults():
    saved = {k: os.environ.get(k) for k in REQUIRED_ENV}
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    os.environ["GOOGLE_CLOUD_LOCATION"] = "us-central1"
    os.environ["AGENT_ENGINE_ID"] = "1234567890"
    try:
        runner = build_runner()
        # These three are the regression guard for the migration. Each default
        # is a silent data-loss path, not a performance nicety.
        assert isinstance(runner.session_service, VertexAiSessionService)
        assert isinstance(runner.memory_service, VertexAiMemoryBankService)
        assert runner.agent is not None
        # app_name is the Memory Bank retrieval scope. The Agent Engine
        # template this replaces scoped memories to the engine id, so anything
        # else here orphans every memory already written.
        assert runner.app_name == os.environ["AGENT_ENGINE_ID"]
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def test_a2a_extra_is_installed():
    # main_a2a.py imports this. Without the [a2a] extra it raises
    # ModuleNotFoundError, and the container dies on startup rather than at
    # any point a test would otherwise notice.
    import google.adk.a2a.utils.agent_to_a2a  # noqa: F401


def test_agent_card_is_schema_valid_and_names_an_endpoint():
    from a2a.types import AgentCard

    # Imported from card.py, never from main_a2a: importing main_a2a would
    # call build_runner() and take the whole offline suite down.
    from Job_Helper_agent.card import CARD_PATH, load_agent_card

    # Parses as a real AgentCard, not just as JSON. A card that fails schema
    # validation takes the whole server down at import.
    raw = json.loads(CARD_PATH.read_text())
    AgentCard(**raw)

    # The url is what Gemini Enterprise calls back on. Passing a static card to
    # to_a2a() means ADK never fills this in (agent_to_a2a.py:203-205), so an
    # unresolved url is a silently unreachable agent.
    card = load_agent_card("job-helper-a2a-xyz.a.run.app", "https")
    assert card.url == "https://job-helper-a2a-xyz.a.run.app/"


def test_agent_card_declares_a2ui_and_streaming():
    card = json.loads(
        (pathlib.Path(__file__).parent / "Job_Helper_agent" / "agent_card.json").read_text()
    )
    caps = card["capabilities"]
    # Without streaming, progress updates cannot be painted incrementally.
    assert caps["streaming"] is True

    exts = caps["extensions"]
    a2ui = [e for e in exts if "a2ui" in e["uri"]]
    assert len(a2ui) == 1, "agent card must declare exactly one A2UI extension"

    # Gemini Enterprise supports A2UI v0.8 only. A version bump here silently
    # stops rendering in GE.
    assert a2ui[0]["uri"] == "https://a2ui.org/a2a-extension/a2ui/v0.8"

    # Must stay false: it is what lets the agent fall back to plain text for
    # any client that does not negotiate A2UI.
    assert a2ui[0]["required"] is False


def test_extract_user_id_reads_every_candidate_header_case_insensitively():
    # WHICH header Gemini Enterprise actually sends is UNCONFIRMED and must be
    # verified against a live GE call. Until then the lookup is deliberately
    # tolerant of several plausible names, and refuses rather than guessing
    # when none of them match -- see the module docstring in identity.py.
    from Job_Helper_agent.identity import IDENTITY_HEADERS, extract_user_id

    for header in IDENTITY_HEADERS:
        assert extract_user_id({header: "student@example.edu"}) == "student@example.edu"
        assert extract_user_id({header.upper(): "student@example.edu"}) == (
            "student@example.edu"
        )
        assert extract_user_id({header.title(): "student@example.edu"}) == (
            "student@example.edu"
        )


def test_extract_user_id_strips_the_google_issuer_prefix():
    # Google identity headers carry the issuer inline. Left on, it becomes part
    # of the user_id and silently forks every session and memory scope.
    from Job_Helper_agent.identity import extract_user_id

    assert (
        extract_user_id(
            {"x-goog-authenticated-user-email": "accounts.google.com:student@example.edu"}
        )
        == "student@example.edu"
    )


def test_extract_user_id_returns_none_rather_than_guessing():
    from Job_Helper_agent.identity import extract_user_id

    assert extract_user_id({}) is None
    assert extract_user_id({"x-user-email": ""}) is None
    assert extract_user_id({"x-user-email": "   "}) is None
    assert extract_user_id({"x-goog-authenticated-user-email": "accounts.google.com:"}) is None
    assert extract_user_id({"user-agent": "curl/8.0", "host": "example.com"}) is None


def test_request_converter_only_overrides_user_id_on_a_real_find():
    # No identity in the headers must leave the A2A_USER_* sentinel in place so
    # require_real_user still refuses the turn. Falling back to anything else
    # would hand one student's session to whoever calls next.
    from Job_Helper_agent.callbacks import require_real_user
    from Job_Helper_agent.identity import build_request_converter

    convert = build_request_converter()

    class _FakeRunRequest:
        user_id = "A2A_USER_ctx-abc123"

    class _FakeCallContext:
        def __init__(self, headers):
            self.state = {"headers": headers}

    class _FakeRequest:
        def __init__(self, headers):
            self.call_context = _FakeCallContext(headers)

    import Job_Helper_agent.identity as identity_module

    original = identity_module.convert_a2a_request_to_agent_run_request
    try:
        identity_module.convert_a2a_request_to_agent_run_request = (
            lambda request, part_converter: _FakeRunRequest()
        )

        found = convert(_FakeRequest({"x-user-email": "student@example.edu"}))
        assert found.user_id == "student@example.edu"
        assert require_real_user(_FakeCallbackContext("student@example.edu")) is None

        missing = convert(_FakeRequest({"user-agent": "curl/8.0"}))
        assert missing.user_id == "A2A_USER_ctx-abc123"
        assert require_real_user(_FakeCallbackContext(missing.user_id)) is not None
    finally:
        identity_module.convert_a2a_request_to_agent_run_request = original


def test_require_public_host_refuses_the_localhost_default_on_cloud_run():
    # A deploy that forgets PUBLIC_HOST otherwise boots green while serving a
    # card pointing at https://localhost:8080/ -- a dead agent that looks
    # healthy. Cloud Run always sets K_SERVICE.
    from Job_Helper_agent.card import LOCAL_HOST_DEFAULT, require_public_host

    raised = None
    try:
        require_public_host(None, "job-helper-a2a")
    except RuntimeError as e:
        raised = e
    assert raised is not None, "boot succeeded on Cloud Run with no PUBLIC_HOST"
    assert "PUBLIC_HOST" in str(raised)

    assert (
        require_public_host("job-helper-a2a-xyz.a.run.app", "job-helper-a2a")
        == "job-helper-a2a-xyz.a.run.app"
    )

    # Local development keeps working with no environment at all.
    assert require_public_host(None, None) == LOCAL_HOST_DEFAULT


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("\nall checks passed")
