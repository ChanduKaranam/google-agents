"""Tools the dispatcher agent uses to publish an agent and notify its sections.

Written against the API as measured on 2026-08-03, which differs from both the
OpenAPI document and the team guide: there is no `claim` and no
`PUT /faculty/agents/{id}/sections`. One `POST /faculty/agents` carries the
share link and the sections together, and a separate `notify` does the send.
"""

import logging
import uuid
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from google.adk.tools import ToolContext

from . import auth, config, progress_ui, sethu_client
from .sethu_client import SethuError

# Set by `show_section_picker`, read by the after-agent callback that draws the
# card. The payload never travels through the model: it is thousands of
# characters of JSON, and a model asked to echo it will eventually corrupt it
# into a card that silently fails to render.
PENDING_UI = 'pending_a2ui'

# The roster the picker was built from, so a click can be resolved without
# re-fetching, and the sections the professor has chosen so far.
ROSTER_CACHE = 'roster_cache'
CHOSEN_SECTIONS = 'chosen_sections'

# How widely this send goes, chosen on the Send Agent card. It decides what a
# later department tap means: pick every section in that department, or drill
# down to one.
SEND_SCOPE = 'send_scope'

# The department whose sections are currently on screen, so a pick can redraw
# the same card instead of sending the professor back to the department list
# after every section.
PICKING_DEPARTMENT = 'picking_department'

# The name of the agent chosen from the picker. Gemini Enterprise already
# named it, so the professor is not asked to name it again.
PICKED_NAME = 'picked_agent_name'

# The link the professor pasted into the card's text field.
PENDING_LINK = 'pending_agent_link'

# Session-state key recording the exact agent the professor was shown a student
# count for. Sending requires an exact match, so a confirmation given for one
# agent can never be spent on another.
_QUOTED_SEND = 'quoted_send'

# The count the professor was actually shown. Kept beside the agent id because
# the instruction alone does not hold: the model has been observed quoting
# "(0 students)" and sending anyway. A send that reaches nobody is refused in
# code, where no amount of prompt drift can get past it.
_QUOTED_COUNT = 'quoted_send_count'

# Agents this session has already sent. The confirmation card stays on screen
# after the send, so a professor can tap "Yes, send it" a second time — and
# nothing about the card says it has been spent. Sending again would put a
# duplicate WhatsApp message in front of every student, so a repeat tap is
# answered rather than acted on.
SENT_AGENTS = 'sent_agents'

# The Idempotency-Key for the send in flight, kept per agent so a retry, a
# re-click, or a second attempt after a timeout is the SAME send to Sethu
# rather than a second blast at the same students.
SEND_KEY = 'send_idempotency_key'

# Said when Sethu stops answering mid-send. It deliberately does not claim the
# send failed: a read timeout means the request may well have been processed,
# and telling a professor "nothing was sent" when 60 students already have the
# message is the worse of the two wrong answers.
SEND_UNCONFIRMED_MESSAGE = (
    'Sethu did not answer in time, so I cannot tell you whether the messages '
    'went out. They may have. Check the agent in Sethu before trying again — '
    'if you do try again, students who already received it will not be '
    'messaged twice.'
)

# Cancel, pressed on a send that has already gone out. Saying "nothing was
# sent" here would be false in the one direction that matters: the professor
# walks away believing their students were not messaged when they were.
SENT_CANNOT_CANCEL_MESSAGE = (
    'This agent has already been sent, and WhatsApp messages cannot be '
    'recalled — so cancelling now changes nothing. The students in those '
    'sections have the link.'
)

# What a repeat confirmation is answered with, in code rather than by the
# model, so the professor gets the same sentence every time.
ALREADY_SENT_MESSAGE = (
    'Already sent — this agent went out to those sections earlier, so nothing '
    'was sent again.'
)

# A confirmation card that can no longer be acted on. Distinct from
# ALREADY_SENT_MESSAGE because we genuinely cannot tell the two apart: a card
# left from before this session — or from before the send guard existed — has
# no recorded state either way. It says what is certain (nothing went out just
# now) and nothing it cannot back up.
STALE_CONFIRMATION_MESSAGE = (
    'That confirmation is no longer current, so nothing was sent just now. If '
    'this agent has not gone out yet, start again from Send Agent.'
)

# Sethu stores the Gemini Enterprise share link on the agent record as `geUrl`.
_LINK_FIELD = 'geUrl'


def confirmation_status(state, agent_id: str) -> str:
    """Whether a tapped "Yes, send it" can still be acted on.

    The card stays on screen for the rest of the conversation, long after the
    state that produced it is gone, so a tap has to be classified before it is
    obeyed.

        'sent'  this agent already went out in this session.
        'stale' the quoted count no longer belongs to this agent — the send was
                spent, the session was cleared, or a later publish replaced it.
        'live'  the count the professor is looking at is still this agent's.
    """
    if agent_id in (state.get(SENT_AGENTS) or []):
        return 'sent'
    if state.get(_QUOTED_SEND) != agent_id:
        return 'stale'
    return 'live'


logger = logging.getLogger(__name__)


# Gemini Enterprise's web host. Share links are addresses in this app, not
# tokens it mints — GE's API has no share-URL field at all, so a professor's
# only source is the browser bar, and what is there describes their session as
# much as it describes the agent.
_GE_HOST = 'vertexaisearch.cloud.google.com'

# Query parameters that describe the person who copied the link rather than
# what it points at.
# `_gl` is Google Analytics' cross-domain linker. Decoded, it carries the
# copier's GA client id and session count — a pseudonymous fingerprint of the
# person who copied the link, which would then travel to every student in the
# section. It expires in about two minutes so the tracking is inert by the time
# anyone clicks, but it identifies a person and has no reason to be in a link
# we store and send on.
_PERSONAL_QUERY = frozenset({'hl', 'authuser', '_gl'})


def normalise_agent_link(link: str) -> str:
    """Reduce a copied browser URL to the part that identifies the agent.

    Measured 2026-08-11 against real records. The shape is:

        /u/{account index}/home/cid/{client id}/r/agent/{agent id}/session/{id}

    Three pieces of it belong to whoever did the copying, not to the agent:

    * `/u/2/` is their position in Google's account switcher. A student whose
      accounts are ordered differently lands on the wrong one, or on none.
    * a numeric `session` is one of their conversations. `-` is the form GE
      itself uses for "start a new session", and one of the observed links
      already had it.
    * `hl` / `authuser` carry their locale and account.

    Anything not recognisable as a GE link is returned untouched. A link this
    function does not understand is one it must not rewrite: `publish_agent`
    creates a record Sethu cannot delete, so a mangled URL is permanent.
    """
    link = (link or '').strip()
    try:
        parts = urlsplit(link)
    except ValueError:
        return link
    if parts.netloc != _GE_HOST:
        return link

    segments = parts.path.split('/')
    # ['', 'u', '2', 'home', ...] -> ['', 'home', ...]
    if len(segments) > 3 and segments[1] == 'u' and segments[2].isdigit():
        segments = [segments[0]] + segments[3:]
    if 'session' in segments:
        index = segments.index('session')
        if index + 1 < len(segments):
            segments[index + 1] = '-'
        else:
            segments.append('-')

    query = '&'.join(
        f'{k}={v}' for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k not in _PERSONAL_QUERY
    )
    return urlunsplit((parts.scheme, parts.netloc, '/'.join(segments), query, ''))


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
    """Whether two links point at the same agent.

    Compared after normalising, so a professor pasting their own `/u/2/…`
    address matches the canonical link already stored against the agent —
    otherwise `find_agent_by_link` misses it and they publish a duplicate.
    """
    a, b = normalise_agent_link(a).rstrip('/'), normalise_agent_link(b).rstrip('/')
    return bool(a) and bool(b) and a == b


def show_main_menu(tool_context: ToolContext) -> dict:
    """Offer the professor the things this agent can do, as buttons.

    Call this when they greet you, ask what you can do, or open the
    conversation without a request. Reply with one short line — the buttons
    appear underneath it — and do not list the options in words.

    Returns:
        A dict with 'status'.
    """
    tool_context.state[PENDING_UI] = 'menu'
    logger.info('show_main_menu: staged')
    return {
        'status': 'success',
        'note': 'The menu is displayed. Wait for the professor to choose.',
    }


def show_section_picker(tool_context: ToolContext) -> dict:
    """Show the professor a searchable list of sections to tick.

    Prefer this over asking them to type a section whenever they have not named
    one precisely, or when they want several. Typing is where sections go
    wrong: "Sec A" is ambiguous across 7 departments and 4 years, and a section
    string Sethu cannot resolve is published to zero students rather than
    refused.

    The list renders after your reply, so say something brief first — "here are
    the sections" — and do not describe the list or repeat its contents.

    Returns:
        A dict with 'status'. On success, 'section_count' is how many were
        offered. The professor's choices arrive in their next message.
    """
    try:
        roster = _call(tool_context, sethu_client.list_faculty_sections)
    except SethuError as exc:
        return _error(str(exc))

    if not roster:
        return _error('Sethu lists no sections for this college.')

    tool_context.state[ROSTER_CACHE] = roster
    tool_context.state[PENDING_UI] = 'departments'
    logger.info('show_section_picker: staged %d sections', len(roster))
    return {
        'status': 'success',
        'section_count': len(roster),
        'note': 'The picker is displayed. Wait for the professor to choose.',
    }


# Set once Sethu has been observed ignoring a `department` request, so the
# switcher stops being offered rather than handing a professor buttons that
# silently return their own department every time.
DEPT_SWITCH_UNSUPPORTED = 'department_switch_unsupported'

# The payload a progress card is drawn from. Held in state for the same reason
# as the roster: it is kilobytes of JSON, the model has no use for it, and a
# model asked to carry numbers through a turn will eventually change one.
VIEW_DATA = 'view_payload'

# Which view `VIEW_DATA` currently holds. Only one payload is kept, so a card
# further up the transcript can outlive the data it was drawn from — and the
# builders take different shapes (a dict here, a list of agents there). Paging
# an older card without this check hands a builder the wrong shape.
VIEW_NAME = 'view_payload_name'


def _staged(tool_context: ToolContext, view: str, payload) -> None:
    tool_context.state[VIEW_DATA] = payload
    tool_context.state[VIEW_NAME] = view
    tool_context.state[PENDING_UI] = view
    logger.info('%s: staged', view)


def show_department_progress(tool_context: ToolContext,
                             department: str = '') -> dict:
    """Show how the professor's department is doing on student activation.

    Call this for "how is my department doing", "how are my sections doing",
    "how many students have activated", or any question about activation
    progress across sections.

    The card carries every figure — the activated total, which sections are
    behind, and the per-section breakdown. Say one short sentence and stop:
    do not repeat the numbers, and do not describe the card. Quoting a figure
    yourself risks quoting one the tool never returned.

    Returns:
        A dict with 'status'. On success, 'section_count' is how many sections
        the card covers.
    """
    try:
        progress = _progress(tool_context, department)
    except SethuError as exc:
        return _error(str(exc))
    if not progress or not progress.get('sections'):
        return _error('Sethu returned no activation data for this department.')
    _log_scope(tool_context, progress)
    progress = _narrow_progress(progress, _own_department(tool_context))

    # The idle-sections figure lives on a different endpoint. It is worth one
    # extra call on an already-woken API, but not worth failing the whole card
    # for: if it errors, the dashboard simply drops that line.
    ambassadors = None
    if config.AMBASSADOR_VIEW_ENABLED:
        try:
            ambassadors = _narrow_ambassadors(
                _call(tool_context, sethu_client.get_ambassadors),
                _own_department(tool_context),
                _departments_roster(tool_context),
            )
        except SethuError:
            logger.info('ambassadors unavailable; dashboard drops the idle count')

    _staged(
        tool_context,
        progress_ui.VIEW_DEPARTMENT,
        {
            'progress': progress,
            'ambassadors': ambassadors,
            'departments': _departments(tool_context),
            'switch_unsupported': bool(
                tool_context.state.get(DEPT_SWITCH_UNSUPPORTED)
            ),
        },
    )
    return {
        'status': 'success',
        'section_count': len(progress.get('sections') or []),
        'note': 'The card shows the figures. Do not repeat them.',
    }


# The department Sethu resolves this professor to, cached per session. Empty
# for an admin or non-roster email, which is the case that must not be narrowed
# — there is no "own department" to narrow to.
OWN_DEPARTMENT = 'own_department'


def _departments_roster(tool_context: ToolContext) -> list:
    """The full college roster, fetched once per session."""
    roster = tool_context.state.get(ROSTER_CACHE)
    if not roster:
        try:
            department, roster = _call(
                tool_context, sethu_client.list_faculty_scope
            )
        except SethuError:
            return []
        tool_context.state[ROSTER_CACHE] = roster
        tool_context.state[OWN_DEPARTMENT] = department
        logger.info('scope: Sethu resolves this caller to department %r',
                    department or '(none — admin or non-roster)')
    return roster or []


def _own_department(tool_context: ToolContext) -> str:
    """This professor's department, or "" if Sethu does not give them one."""
    if tool_context.state.get(OWN_DEPARTMENT) is None:
        _departments_roster(tool_context)
    return tool_context.state.get(OWN_DEPARTMENT) or ''


def _narrow_progress(progress: dict, department: str) -> dict:
    """Cut a whole-college progress response down to one department.

    Sethu already scopes this per caller; this only bites when it hands back
    the whole college (`department: ""`) for someone who does have a
    department. Faculty are meant to see their own progress, while still being
    able to send an agent anywhere in the college.

    The server's ordering is kept exactly as given — pooling included — and
    only the printed positions are renumbered, so a filtered list still reads
    #1, #2, #3 without this code ever deciding who outranks whom.
    """
    if not department or (progress.get('department') or ''):
        return progress
    sections = [s for s in (progress.get('sections') or [])
                if s.get('department') == department]
    if not sections:
        return progress

    sections = sorted(sections,
                      key=lambda s: (s.get('rank') is None, s.get('rank') or 0))
    renumbered = [{**s, 'rank': i} for i, s in enumerate(sections, 1)]
    return {
        **progress,
        'department': department,
        'sections': renumbered,
        # Recomputed, never inherited: the college totals would describe an
        # audience this card is no longer showing.
        'activated': sum(s.get('activated') or 0 for s in renumbered),
        'total': sum(s.get('total') or 0 for s in renumbered),
    }


def _narrow_ambassadors(data: dict, department: str, roster: list) -> dict:
    """The same narrowing for the ambassador roster.

    Ambassadors carry a section label rather than a department, so the roster
    supplies which labels belong to this department.
    """
    if not department or (data.get('department') or ''):
        return data
    labels = {str(s.get('label')) for s in roster
              if s.get('department') == department and s.get('label')}
    if not labels:
        return data
    return {
        **data,
        'department': department,
        'ambassadors': [a for a in (data.get('ambassadors') or [])
                        if str(a.get('section')) in labels],
        'sectionsWithoutAmbassador': [
            s for s in (data.get('sectionsWithoutAmbassador') or [])
            if str(s.get('section')) in labels
        ],
    }


def _departments(tool_context: ToolContext) -> list:
    """Every department in the college, from the roster already cached.

    The roster is the only list of departments there is — the progress endpoint
    returns one department, so it cannot name the others. Fetched only if this
    session has not already loaded it for the section picker.
    """
    seen = []
    for section in _departments_roster(tool_context):
        name = section.get('department')
        if name and name not in seen:
            seen.append(name)
    return seen


def _log_scope(tool_context: ToolContext, progress: dict) -> None:
    """Record how much of the college a progress response actually covered.

    The endpoint returns one department while `GET /faculty/sections` returns
    the whole roster, so the only way to tell "all of this department" from
    "some of it" is to count both and compare. Logged rather than shown: it is
    a question about the API, not something a professor asked.
    """
    try:
        sections = progress.get('sections') or []
        scope = progress.get('department') or ''
        roster = _departments_roster(tool_context)
        # An admin or non-roster email gets `department: ""` and the whole
        # college, so filtering by that empty name would compare against
        # nothing and pass vacuously.
        same_dept = ([s for s in roster if s.get('department') == scope]
                     if scope else list(roster))
        logger.info(
            'scope: progress returned %d sections for %r (students %s of %s); '
            'roster holds %d sections for %r, %d in all across %d departments',
            len(sections), scope or '(whole college)',
            progress.get('activated'), progress.get('total'),
            len(same_dept), scope or '(n/a)', len(roster),
            len({s.get('department') for s in roster if s.get('department')}),
        )
        missing = ({str(s.get('label')) for s in same_dept}
                   - {str(s.get('label')) for s in sections})
        if missing:
            logger.warning(
                'scope: %d section(s) on the roster are absent from '
                'department-progress: %s',
                len(missing), sorted(missing)[:10],
            )
    except Exception:  # Diagnostics must never cost a professor their card.
        logger.exception('scope logging failed')


def _progress(tool_context: ToolContext, department: str | None):
    """Fetch progress, and notice if Sethu refused to change department."""
    progress = _call(
        tool_context,
        lambda token: sethu_client.get_department_progress(token, department),
    )
    if department and progress:
        returned = progress.get('department')
        if returned and returned != department:
            # Asked for one department, given another: the scope is fixed to
            # the caller's own. Recorded so the buttons stop being offered.
            tool_context.state[DEPT_SWITCH_UNSUPPORTED] = True
            logger.info(
                'department switch ignored: asked %r, got %r', department,
                returned,
            )
    return progress


def show_leaderboard(tool_context: ToolContext,
                     department: str = '') -> dict:
    """Show the sections ranked by how much of each has activated.

    Call this for "show the leaderboard", "which sections are doing best", or
    "rank my sections".

    The ranking and the pooling of small sections are decided by Sethu and
    shown as given. Never re-order the list in your reply or describe a section
    as first or last yourself — say one short sentence and stop.

    Returns:
        A dict with 'status' and 'section_count'.
    """
    try:
        progress = _progress(tool_context, department)
    except SethuError as exc:
        return _error(str(exc))
    if not progress or not progress.get('sections'):
        return _error('Sethu returned no activation data for this department.')
    _log_scope(tool_context, progress)
    progress = _narrow_progress(progress, _own_department(tool_context))

    _staged(tool_context, progress_ui.VIEW_LEADERBOARD, {
        'progress': progress,
        'departments': _departments(tool_context),
        'switch_unsupported': bool(
            tool_context.state.get(DEPT_SWITCH_UNSUPPORTED)
        ),
    })
    return {
        'status': 'success',
        'section_count': len(progress.get('sections') or []),
        'note': 'The card shows the ranking. Do not repeat or re-order it.',
    }


def show_ambassadors(tool_context: ToolContext) -> dict:
    """Show the department's student ambassadors and which sections are quiet.

    Call this for "who are my ambassadors", "how are my ambassadors", "are my
    ambassadors active", or "ambassador status".

    What the card calls quiet is the absence of *student* activations in that
    ambassador's section — Sethu does not record what an ambassador personally
    did. Never restate it as the ambassador having done nothing: that is an
    accusation about a named person the data cannot support.

    Returns:
        A dict with 'status' and 'ambassador_count'.
    """
    if not config.AMBASSADOR_VIEW_ENABLED:
        return _error(
            'The ambassador view is switched off for this deployment. Tell the '
            'professor it is not available, and offer the department progress '
            'card instead.'
        )
    try:
        data = _call(tool_context, sethu_client.get_ambassadors)
    except SethuError as exc:
        return _error(str(exc))
    if not data:
        return _error('Sethu returned no ambassador data for this department.')
    data = _narrow_ambassadors(
        data, _own_department(tool_context), _departments_roster(tool_context)
    )

    logger.info(
        'scope: ambassadors returned %d for %r, %d section(s) with none',
        len(data.get('ambassadors') or []), data.get('department'),
        len(data.get('sectionsWithoutAmbassador') or []),
    )
    # Opening the card starts from the full roster, whatever cut was last
    # chosen in this session.
    tool_context.state[progress_ui.AMBASSADOR_FILTER] = None
    _staged(tool_context, progress_ui.VIEW_AMBASSADORS, data)
    return {
        'status': 'success',
        'ambassador_count': len(data.get('ambassadors') or []),
        'note': 'The card shows the roster and the summary. Do not repeat them.',
    }


def show_agent_usage(tool_context: ToolContext) -> dict:
    """Show the professor's published agents and how much they are used.

    Call this for "how are my agents used", "which of my agents is working", or
    "show my agents".

    Chat volume, return rate and unanswered topics are not populated yet — a
    sync that would fill them does not run. The card says so where it applies.
    Do not fill the gap with a number of your own, and do not report a missing
    figure as zero: an agent nobody has measured is not an agent nobody uses.

    Returns:
        A dict with 'status' and 'agent_count'.
    """
    try:
        agents = _call(tool_context, sethu_client.list_faculty_agents)
    except SethuError as exc:
        return _error(str(exc))
    if not agents:
        return _error('This professor has no published agents yet.')

    # Which usage fields Sethu is actually populating. `statsSyncedAt` is the
    # gate the card renders on, so a value present without it is as good as
    # absent — worth seeing both counts separately rather than inferring.
    synced = [a for a in agents if a.get('statsSyncedAt')]
    def _have(field):
        return sum(1 for a in agents
                   if (a.get('stats') or {}).get(field) is not None)
    logger.info(
        'scope: agents returned %d, %d sent to sections, %d with '
        'statsSyncedAt; populated: questionsThisWeek=%d usedBy=%d '
        'signInsCaused=%d topUnanswered=%d',
        len(agents), sum(1 for a in agents if a.get('sections')), len(synced),
        _have('questionsThisWeek'), _have('usedBy'),
        _have('signInsCaused'), _have('topUnanswered'),
    )
    # What a Gemini Enterprise share link actually looks like. GE's own API has
    # no share-URL field — `sharingConfig` carries only a scope enum — so the
    # only way to learn the format is to read one Sethu has stored. If the ids
    # in these are the agent ids, the link is derivable and nobody needs to
    # copy it out of a browser bar.
    for a in [x for x in agents if x.get(_LINK_FIELD)][:3]:
        logger.info('geUrl sample: id=%s name=%r unclaimed=%s url=%s',
                    a.get('id'), a.get('name'), a.get('unclaimed'),
                    a.get(_LINK_FIELD))
    logger.info('geUrl coverage: %d of %d agents carry a link, %d unclaimed',
                sum(1 for a in agents if a.get(_LINK_FIELD)), len(agents),
                sum(1 for a in agents if a.get('unclaimed')))

    newest = sorted(agents, key=lambda a: str(a.get('publishedAt') or ''),
                    reverse=True)[:3]
    for a in newest:
        logger.info('newest row: %s',
                    {k: v for k, v in a.items() if k != 'shareToken'})

    # Whether a picker is buildable turns entirely on the unclaimed records —
    # the ones Sethu's GE sync found on its own, which is what a no-code agent
    # built in Gemini Enterprise looks like before anyone pastes a link. A
    # picker needs them to (a) belong to this professor and (b) carry a usable
    # link. Every field is logged rather than just the counts, because it is
    # not yet known which of them the sync fills in.
    unclaimed = [a for a in agents if a.get('unclaimed')]
    logger.info('unclaimed: %d of %d agents; %d carry a link',
                len(unclaimed), len(agents),
                sum(1 for a in unclaimed if a.get(_LINK_FIELD)))
    for a in unclaimed[:8]:
        # Everything except the share token, which is a bearer value for the
        # /go link and has no business in a log.
        redacted = {k: v for k, v in a.items() if k != 'shareToken'}
        logger.info('unclaimed record: %s', redacted)
    # Which of the URL-ish fields is actually filled in, across every row.
    for field in ('geUrl', 'openUrl', 'geAgentId', 'createdByEmail',
                  'createdByYou'):
        present = sum(1 for a in agents if a.get(field))
        if present or any(field in a for a in agents):
            logger.info('field %s: present on %d of %d rows, %d on unclaimed',
                        field, present, len(agents),
                        sum(1 for a in unclaimed if a.get(field)))

    if synced:
        sample = synced[0]
        logger.info('scope: sample synced agent %r stats=%s syncedAt=%s',
                    sample.get('name'), sample.get('stats'),
                    sample.get('statsSyncedAt'))
    # Opening the card starts from the whole list, whatever cut was last
    # chosen in this session.
    tool_context.state[progress_ui.AGENT_FILTER] = None
    _staged(tool_context, progress_ui.VIEW_AGENT_USAGE, agents)
    return {
        'status': 'success',
        'agent_count': len(agents),
        'note': 'The card shows each agent. Do not repeat the figures.',
    }


# Where the picker keeps the agents it offered, so a choice can be resolved to
# a link without asking Sethu again.
AGENT_CHOICES = 'agent_choices'

# The composed Gemini Enterprise link Sethu now returns on every row, including
# ones no professor has pasted a link for.
_OPEN_LINK_FIELD = 'openUrl'


def ge_agent_id(link: str) -> str:
    """The GE agent id inside a share link, or "" if it is not one."""
    parts = [p for p in str(link or '').split('/') if p]
    if 'agent' in parts:
        index = parts.index('agent')
        if index + 1 < len(parts):
            return parts[index + 1].split('?')[0]
    return ''


def choosable_agents(agents: list) -> list:
    """The agents worth offering a professor, newest first.

    One entry per Gemini Enterprise agent, under the name it has in GE.

    `/faculty/agents` returns a row per *send*, not per agent: publishing to a
    second set of sections creates another row, renamed for that send. Listing
    those back is listing a professor's own past sends as if they were things
    to send — "Hackashop", "Hackashop — already sent to 1 sections" and
    "DOC CIVIL 3 SEC" were three rows over the same underlying agent.

    So rows are grouped by the GE agent id inside their link, and the row that
    represents the agent itself wins: the one the sync created, which carries
    the GE name. Only if the sync never saw it — an agent known solely from a
    pasted link — does the earliest send stand in for it.

    Excludes anything with no link to send, and the dispatcher agents Sethu's
    sync ingests as if a professor had made them.
    """
    best = {}
    for agent in agents or []:
        link = agent.get(_OPEN_LINK_FIELD) or agent.get(_LINK_FIELD)
        if not link:
            continue
        ge_id = ge_agent_id(link)
        if ge_id in config.HIDDEN_GE_AGENT_IDS:
            continue
        entry = {
            'id': str(agent.get('id')),
            'name': str(agent.get('name') or 'Untitled agent'),
            'link': normalise_agent_link(link),
            'sections': list(agent.get('sections') or []),
            'unclaimed': bool(agent.get('unclaimed')),
            'publishedAt': str(agent.get('publishedAt') or ''),
        }
        # Rows with no id in their link cannot be grouped, so each keeps itself.
        key = ge_id or f'row:{entry["id"]}'
        current = best.get(key)
        if current is None:
            best[key] = entry
        elif entry['unclaimed'] and not current['unclaimed']:
            best[key] = entry
        elif entry['unclaimed'] == current['unclaimed'] and (
            entry['publishedAt'] < current['publishedAt']
        ):
            best[key] = entry

    offered = sorted(best.values(), key=lambda a: a['publishedAt'], reverse=True)
    return offered


# Set once a sync has been asked for in this session, so a professor typing
# "hi" five times does not queue five enumerations of the whole engine.
SYNC_REQUESTED = 'sync_requested'


def request_agent_sync(tool_context: ToolContext) -> bool:
    """Ask Sethu to re-read Gemini Enterprise. Best effort, never raises.

    Returns True if Sethu accepted the request. A failure is logged and
    swallowed: the greeting must not fail because a background job could not be
    started, and the professor is told the list may lag regardless.
    """
    if tool_context.state.get(SYNC_REQUESTED):
        return False
    tool_context.state[SYNC_REQUESTED] = True
    try:
        result = _call(tool_context, sethu_client.trigger_agent_sync)
        logger.info('agent sync requested: %s', result)
        return True
    except SethuError as exc:
        logger.warning('could not request an agent sync: %s', exc)
        return False
    except Exception:
        logger.exception('could not request an agent sync')
        return False


def list_agent_choices(tool_context: ToolContext) -> dict:
    """Fetch the professor's agents and remember what was offered.

    Returns:
        A dict with 'status'. On success, 'agents' is the offered list.
    """
    try:
        agents = _call(tool_context, sethu_client.list_faculty_agents)
    except SethuError as exc:
        return _error(str(exc))
    offered = choosable_agents(agents)
    tool_context.state[AGENT_CHOICES] = offered
    logger.info('agent picker: offering %d of %d rows', len(offered),
                len(agents or []))
    if not offered:
        return _error('No agents to choose from yet.')
    return {'status': 'success', 'agents': offered}


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
    link = normalise_agent_link(agent_link)
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
        sections: Section labels as plain strings, exactly as they appear in
            the 'label' field from list_college_sections, e.g.
            ["CSE · Year 1 · Sec A"]. Never a bare section letter — that does
            not identify a section.

    Returns:
        A dict with 'status'. On success, 'agent_id' identifies it and 'count'
        is the number of students it would reach.
    """
    # Normalised before anything is written. Publishing is irreversible, so a
    # link carrying someone's account index and chat session would be stored
    # against students permanently.
    link = normalise_agent_link(agent_link)
    if link != agent_link.strip():
        logger.info('normalised agent link before publishing')
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
                token, link, name, sections
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
        'already_sent' means this agent has gone out already and nothing was
        done — tell the professor exactly what 'message' says.
    """
    already = list(tool_context.state.get(SENT_AGENTS) or [])
    if agent_id in already:
        # Checked before the quoted-count guard: both refuse the send, but only
        # this one knows why, and the other's wording would send the model
        # hunting for a count that is not the problem.
        return {'status': 'already_sent', 'message': ALREADY_SENT_MESSAGE}

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

    # One key per send, minted on the first attempt and reused afterwards.
    keys = dict(tool_context.state.get(SEND_KEY) or {})
    key = keys.get(agent_id)
    if not key:
        key = str(uuid.uuid4())
        keys[agent_id] = key
        tool_context.state[SEND_KEY] = keys

    logger.info('notify: agent %s, %s students, key %s', agent_id, quoted, key)
    try:
        result = _call(
            tool_context,
            lambda token: sethu_client.notify_agent_sections(
                token, agent_id, key
            ),
        )
    except SethuError as exc:
        logger.warning('notify failed for agent %s: %s', agent_id, exc)
        if exc.status_code is None:
            # No HTTP status means we never got an answer — a timeout or a
            # dropped connection. Whether Sethu acted on it is unknowable from
            # here, so say exactly that.
            return {'status': 'unconfirmed',
                    'error_message': SEND_UNCONFIRMED_MESSAGE}
        return _error(str(exc))

    logger.info('notify: agent %s accepted by Sethu', agent_id)
    # A send must not be replayable on a stray second "yes".
    tool_context.state[SENT_AGENTS] = already + [agent_id]
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
