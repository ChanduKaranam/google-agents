"""Tools the dispatcher agent uses to publish an agent and notify its sections.

Written against the API as measured on 2026-08-03, which differs from both the
OpenAPI document and the team guide: there is no `claim` and no
`PUT /faculty/agents/{id}/sections`. One `POST /faculty/agents` carries the
share link and the sections together, and a separate `notify` does the send.
"""

from google.adk.tools import ToolContext

from . import auth, config, sethu_client
from .sethu_client import SethuError

# Session-state key recording the exact agent the professor was shown a student
# count for. Sending requires an exact match, so a confirmation given for one
# agent can never be spent on another.
_QUOTED_SEND = 'quoted_send'

# The count the professor was actually shown. Kept beside the agent id because
# the instruction alone does not hold: the model has been observed quoting
# "(0 students)" and sending anyway. A send that reaches nobody is refused in
# code, where no amount of prompt drift can get past it.
_QUOTED_COUNT = 'quoted_send_count'

# Sethu stores the Gemini Enterprise share link on the agent record as `geUrl`.
_LINK_FIELD = 'geUrl'


def _error(message: str) -> dict:
    return {'status': 'error', 'error_message': message}


def _norm(text: str) -> str:
    """Reduce a section string to letters and digits, for tolerant matching.

    "Section" and "Sec" are folded together first so a professor's phrasing
    matches Sethu's label: "CSE Year 1 Section A" -> "cseyear1seca", which is
    what "CSE · Year 1 · Sec A" reduces to.
    """
    lowered = str(text).lower().replace('section', 'sec')
    return ''.join(ch for ch in lowered if ch.isalnum())


def _resolve_sections(requested: list, roster: list) -> tuple[list, list]:
    """Map what the professor said onto exact Sethu labels.

    Returns (canonical_labels, unresolved). Sethu accepts a section string it
    cannot match and publishes it to nobody rather than rejecting it, so an
    unresolved name has to be caught here — after the POST it is permanent.

    Accepts the full label, or a looser "CSE 1 A" / "CSE Year 1 Section A",
    and always returns the canonical label so what we send is what Sethu
    stores.
    """
    lookup = {}
    for entry in roster:
        label = entry.get('label')
        if not label:
            continue
        dept, year, sec = (
            entry.get('department'),
            entry.get('year'),
            entry.get('section'),
        )
        for key in (label, f'{dept}{year}{sec}', f'{dept} year {year} sec {sec}'):
            lookup.setdefault(_norm(key), label)

    canonical, unresolved = [], []
    for item in requested:
        label = lookup.get(_norm(item))
        if label is None:
            unresolved.append(item)
        elif label not in canonical:
            canonical.append(label)
    return canonical, unresolved


def _roster_count(sections: list, roster: list) -> int | None:
    """Sum the roster's own headcount for these sections.

    Sethu stores a `studentCount` on the agent record at publish time, and it
    has been observed as 0 for a section the roster reports as having 3
    students (agent 019fc850-…, 2026-08-03). The roster's per-section
    `students` has matched reality everywhere we have checked it, so it is the
    number we quote to a professor.

    Returns None if the sections cannot be matched, rather than a misleading 0.
    """
    by_label = {s.get('label'): s.get('students') for s in roster if s.get('label')}
    total, matched = 0, False
    for label in sections:
        students = by_label.get(label)
        if students is not None:
            total += students
            matched = True
    return total if matched else None


def _count_warning(count) -> str | None:
    """Flag a student count that means the send would reach nobody.

    Sethu accepts a section string it cannot resolve — a bare "A" instead of a
    full label — and publishes it `status: "live"` with `studentCount: 0`
    rather than rejecting it (measured 2026-08-03). A zero or missing count is
    therefore the only signal that the sections did not resolve, and it must
    never be quoted to a professor as if it were a real audience.
    """
    if count is None:
        return (
            'Sethu did not report a student count, so there is no way to tell '
            'the professor how many people this would reach. Do not quote a '
            'number and do not send; ask them to check the agent in Sethu.'
        )
    if count == 0:
        return (
            'This reaches zero students, which almost always means the section '
            'names did not resolve — Sethu accepts an unrecognised section and '
            'silently publishes it to nobody. Tell the professor plainly, and '
            'do not send. The sections most likely need the full label, e.g. '
            '"CSE · Year 1 · Sec A".'
        )
    return None


def _call(tool_context: ToolContext, action):
    """Run `action(token)`, re-exchanging once if Sethu rejects the token."""
    token = auth.get_session(tool_context)['token']
    try:
        return action(token)
    except SethuError as exc:
        if exc.status_code != 401:
            raise
        auth.invalidate(tool_context)
        return action(auth.get_session(tool_context)['token'])


def _same_link(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a.strip().rstrip('/') == b.strip().rstrip('/')


def _summarise(agent: dict) -> dict:
    """The fields the model needs to talk about an agent with the professor."""
    return {
        'agent_id': agent.get('id'),
        'name': agent.get('name'),
        'link': agent.get(_LINK_FIELD),
        'sections': agent.get('sections') or [],
        'semester': agent.get('semester'),
        'student_count': agent.get('studentCount'),
        'status': agent.get('status'),
    }


def list_college_sections(tool_context: ToolContext) -> dict:
    """List the sections that exist in this college.

    Professors are not assigned sections — any of them can send an agent to any
    section in the college. So this is a roster to check a stated section
    against, not a list of what the professor owns. Use it to confirm a section
    the professor named really exists before publishing, and to offer choices
    when they are vague.

    Each section is an object with 'department', 'year', 'section', 'label' and
    'students'. Match on department + year + section together: 'section' alone
    is just "A" or "B" and repeats across every department and year, so it
    identifies nothing on its own. Pass the 'label' to `publish_agent`.

    'students' is the real headcount for that section, so the sections the
    professor picked can be totalled before quoting a number.

    Returns:
        A dict with 'status'. On success, 'sections' is the list of sections.
    """
    try:
        sections = _call(tool_context, sethu_client.list_faculty_sections)
    except SethuError as exc:
        if exc.status_code == 403:
            # This route needs an `email` claim the others do not. Say which
            # side is at fault rather than leaving "permissions" to guesswork.
            token = auth.get_session(tool_context).get('token')
            if not auth.has_email_claim(token):
                return _error(
                    'Sethu minted this account a token with no email claim, '
                    'and /faculty/sections requires one — so it refuses. This '
                    'is a Sethu token-minting issue, not a problem with the '
                    "professor's account. Report it to the Sethu team."
                )
        return _error(str(exc))

    if not sections:
        return _error('Sethu lists no sections for this college.')
    return {'status': 'success', 'sections': sections}


def find_agent_by_link(agent_link: str, tool_context: ToolContext) -> dict:
    """Check whether a pasted Gemini Enterprise link is already published.

    Call this first. If the professor has already published this agent, reuse
    it rather than publishing a duplicate — Sethu has no way to delete one.

    Args:
        agent_link: The share URL of the agent the professor wants to send.

    Returns:
        A dict with 'status'. 'success' means it is already published and
        'agent' describes it, including the sections it currently goes to.
        'not_published' means it needs `publish_agent`.
    """
    link = agent_link.strip()
    if not link.startswith('https://'):
        return _error(
            'That does not look like an agent link. Ask the professor for the '
            'full https:// share URL from Gemini Enterprise.'
        )

    try:
        agents = _call(tool_context, sethu_client.list_faculty_agents)
    except SethuError as exc:
        return _error(str(exc))

    for agent in agents:
        if _same_link(agent.get(_LINK_FIELD) or '', link):
            return {'status': 'success', 'agent': _summarise(agent)}

    return {'status': 'not_published'}


def publish_agent(
    agent_link: str,
    name: str,
    semester: str,
    sections: list[str],
    tool_context: ToolContext,
) -> dict:
    """Publish the professor's agent to the sections they named.

    This registers the agent against those sections and returns how many
    students it reaches. It does **not** message anyone — only
    `send_agent_to_sections` does that.

    Sethu cannot delete or re-point a published agent, so confirm the sections
    with the professor before calling this, and never publish twice for the
    same link — check `find_agent_by_link` first.

    Args:
        agent_link: The full https:// share URL from Gemini Enterprise.
        name: What the professor calls the agent, e.g. "CS101 TA".
        semester: The semester it is for, e.g. "1".
        sections: Section labels as plain strings, exactly as they appear in
            the 'label' field from list_college_sections, e.g.
            ["CSE · Year 1 · Sec A"]. Never a bare section letter — that does
            not identify a section.

    Returns:
        A dict with 'status'. On success, 'agent_id' identifies it and 'count'
        is the number of students it would reach.
    """
    link = agent_link.strip()
    if not link.startswith('https://'):
        return _error('That is not a valid https:// share link.')
    if not sections:
        return _error('No sections were given, so there is nobody to send to.')

    # Check the sections against the roster first. Sethu publishes an
    # unrecognised section to zero students instead of rejecting it, and the
    # record cannot be deleted afterwards — so this is the last point at which
    # a typo is still recoverable.
    try:
        roster = _call(tool_context, sethu_client.list_faculty_sections)
    except SethuError:
        roster = []

    if roster:
        sections, unresolved = _resolve_sections(sections, roster)
        if unresolved:
            return _error(
                f'Sethu has no section matching {unresolved}. Publishing that '
                'would create a permanent agent that reaches nobody, so '
                'nothing was published. Use the exact labels from '
                'list_college_sections, e.g. "CSE · Year 1 · Sec A". Closest '
                f'available: {[s.get("label") for s in roster[:5]]}'
            )
        if not sections:
            return _error('None of those sections could be resolved.')

    try:
        agent = _call(
            tool_context,
            lambda token: sethu_client.publish_faculty_agent(
                token, link, name, semester, sections
            ),
        )
    except SethuError as exc:
        return _error(str(exc))

    agent_id = (agent or {}).get('id')
    if not agent_id:
        return _error('Sethu published the agent but did not return its id.')

    sethu_count = agent.get('studentCount')
    published = agent.get('sections') or sections
    count = _roster_count(published, roster)
    if count is None:
        count = sethu_count

    tool_context.state[_QUOTED_SEND] = agent_id
    tool_context.state[_QUOTED_COUNT] = count
    result = {
        'status': 'success',
        'agent_id': agent_id,
        'count': count,
        'sections': published,
    }
    if sethu_count != count:
        result['note'] = (
            f'Quoting {count} from the section roster. Sethu\'s own record says '
            f'{sethu_count}, which is a known bug on their side. Quote {count} '
            'to the professor.'
        )
    warning = _count_warning(count)
    if warning:
        result['warning'] = warning
    return result


def prepare_send(agent_id: str, tool_context: ToolContext) -> dict:
    """Re-read an already-published agent and report who it would reach.

    Use this when `find_agent_by_link` found the agent already published, so
    you can quote a student count without publishing a duplicate.

    Args:
        agent_id: The id from find_agent_by_link.

    Returns:
        A dict with 'status'. On success, 'count' is the number of students
        and 'sections' the sections it goes to.
    """
    try:
        agent = _call(
            tool_context,
            lambda token: sethu_client.get_faculty_agent(token, agent_id),
        )
    except SethuError as exc:
        return _error(str(exc))

    if not agent.get(_LINK_FIELD):
        return _error(
            'This agent has no share link in Sethu, so students would get a '
            'message with nothing to open.'
        )

    sethu_count = agent.get('studentCount')
    sections = agent.get('sections') or []

    # Prefer the roster's headcount over the agent record's stored count, for
    # the same reason as publish_agent: the stored one has been wrong.
    try:
        roster = _call(tool_context, sethu_client.list_faculty_sections)
    except SethuError:
        roster = []
    count = _roster_count(sections, roster)
    if count is None:
        count = sethu_count

    tool_context.state[_QUOTED_SEND] = agent_id
    tool_context.state[_QUOTED_COUNT] = count
    result = {
        'status': 'success',
        'count': count,
        'sections': sections,
    }
    if sethu_count != count:
        result['note'] = (
            f'Quoting {count} from the section roster. Sethu\'s own record says '
            f'{sethu_count}, which is a known bug on their side. Quote {count} '
            'to the professor.'
        )
    warning = _count_warning(count)
    if warning:
        result['warning'] = warning
    return result


def send_agent_to_sections(agent_id: str, tool_context: ToolContext) -> dict:
    """Send the agent link to its sections over WhatsApp.

    Only call this after the professor has explicitly confirmed. WhatsApp
    messages go to real students and cannot be recalled.

    Args:
        agent_id: The id from publish_agent or find_agent_by_link.

    Returns:
        A dict with 'status'. On success, 'result' is Sethu's send result.
    """
    if tool_context.state.get(_QUOTED_SEND) != agent_id:
        return _error(
            'Quote the student count for this exact agent first, then ask the '
            'professor to confirm before sending.'
        )

    quoted = tool_context.state.get(_QUOTED_COUNT)
    if not quoted:
        return _error(
            f'This agent reaches {quoted if quoted is not None else "an unknown number of"} '
            'students, so sending would message nobody. Nothing was sent. '
            'Sethu reports the count as zero even for sections that do have '
            'students, so check the agent in Sethu before trying again — and '
            'tell the professor plainly rather than reporting a successful '
            'send.'
        )

    try:
        result = _call(
            tool_context,
            lambda token: sethu_client.notify_agent_sections(token, agent_id),
        )
    except SethuError as exc:
        return _error(str(exc))

    # A send must not be replayable on a stray second "yes".
    tool_context.state[_QUOTED_SEND] = None
    tool_context.state[_QUOTED_COUNT] = None
    return {'status': 'success', 'result': result}


def diagnose_identity(tool_context: ToolContext) -> dict:
    """Report what identity information this session actually carries.

    Diagnostic only. Use it when the professor asks why sign-in is failing, or
    when asked directly to run a diagnostic. It reveals no token values.

    Returns:
        A dict describing each session-state entry, whether Gemini Enterprise
        forwarded an OAuth access token, and who Sethu resolves it to.
    """
    entries = []
    for key, value in sorted(auth.state_items(tool_context).items()):
        entry = {'key': key, 'type': type(value).__name__}
        if isinstance(value, str):
            entry['length'] = len(value)
            entry['is_google_access_token'] = auth.looks_like_access_token(value)
            if value.count('.') == 2:
                entry['jwt_issuer'] = auth._claims(value).get('iss')
        entries.append(entry)

    found = any(e.get('is_google_access_token') for e in entries)
    result = {
        'status': 'success',
        'expected_authorization_id': config.GE_AUTHORIZATION_ID,
        'google_access_token_found': found,
        'state_entries': entries,
    }

    if not found:
        result['likely_cause'] = (
            'Gemini Enterprise forwards no identity until the agent has '
            'authorizationConfig.toolAuthorizations set. If that is already '
            'set, check the authorization id matches '
            f'"{config.GE_AUTHORIZATION_ID}".'
        )
        return result

    # A token arriving is not the same as Sethu accepting it. Exchange it and
    # ask Sethu who it thinks this is — the only answer that proves the chain.
    try:
        session = auth.get_session(tool_context)
        result['sethu_exchange'] = 'ok'
        result['role'] = session.get('role')
        result['tenant_id'] = session.get('tenantId')
        # Decides whether /faculty/sections will work at all.
        result['token_has_email_claim'] = auth.has_email_claim(
            session.get('token')
        )
    except SethuError as exc:
        result['sethu_exchange'] = 'failed'
        result['sethu_error'] = str(exc)
        result['sethu_request_id'] = exc.request_id
        return result

    try:
        result['sethu_identity'] = _call(tool_context, sethu_client.get_me)
    except SethuError as exc:
        result['sethu_identity_error'] = str(exc)

    return result
