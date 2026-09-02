"""Activation and usage cards, built from the primitives in `a2ui.py`.

Four views over three endpoints, all read-only. What each one may claim is
constrained by what the API can actually back:

* Every figure is either returned by Sethu or arithmetic over figures Sethu
  returned. Nothing here is composed by the model. A tile the model writes can
  show a number no tool returned, and eventually will.
* `rank` and `pooled` come from the server. Re-deriving the pooling rule here
  would put a second implementation of it in the codebase, and the day the two
  drift the leaderboard and the dashboard start contradicting each other.
* Ambassador idleness is a proxy for *student* activity in that person's
  section, so it is worded that way everywhere. See `sethu_client.get_ambassadors`.

Two rendering constraints shape the layout, both from `A2UI-VIEWS.md`:

* The v0.8 catalog has no colour and no severity. The mockups lean on amber,
  red and a pink row background to say "this one is behind"; none of that
  survives. Emphasis has to live in the words — "3 behind", "no ambassador".
* Gemini Enterprise drops a surface over ~6KB **silently**. Every list here is
  therefore paged: rows are added until the next one would breach the ceiling,
  and the rest goes behind a "Show more" button that pages from state rather
  than re-calling an API that sleeps on Render.

The mockups draw the dashboard's four figures as a 2x2 grid of tiles. They are
rendered as lines of text instead: a Row of Columns of Cards is one nesting
level deeper than anything proven to render in GE here, and a card that fails
to render logs nothing at all. The numbers are identical either way.
"""

import json

from datetime import datetime, timedelta

from . import a2ui, config

# Which cut of the agent list is on screen. Held in session state rather than
# passed through the builder, so a "Show more" inside a filtered view pages the
# filtered list instead of silently reverting to all agents.
AGENT_FILTER = 'agent_usage_filter'

# Filter buttons on the agents card.
AGENT_VIEW = 'agent_view'
FILTER_ALL = 'all'
FILTER_MOST_USED = 'most_used'
FILTER_MOST_ACTIVATED = 'most_activated'
FILTER_NO_ACTIVATION = 'no_activation'
FILTER_NOT_SENT = 'not_sent'

# Which cut of the ambassador roster is on screen, and the button that changes
# it. Same shape as the agents card: the payload is already in state, so
# switching costs no call to Sethu.
AMBASSADOR_FILTER = 'ambassador_filter'
AMBASSADOR_VIEW = 'ambassador_view'
AMB_ALL = 'all'
AMB_LEADERBOARD = 'leaderboard'
AMB_UNCOVERED = 'uncovered'

# Paging. The offset travels in the button's action context; the rows it pages
# through are already in session state, so a page turn costs no API call.
SHOW_MORE = 'show_more_rows'

# Which list a "Show more" belongs to.
VIEW_DEPARTMENT = 'department_progress'
VIEW_LEADERBOARD = 'leaderboard'
VIEW_AMBASSADORS = 'ambassadors'
VIEW_AGENT_USAGE = 'agent_usage'

# Opening-menu buttons, and the view each one draws. A tap is answered in code
# like every other button: `before_agent` returning Content ends the invocation,
# so a click that fell through to the model would produce prose and no card.
MENU_DEPARTMENT = 'menu_department_progress'
MENU_LEADERBOARD = 'menu_leaderboard'
MENU_AMBASSADORS = 'menu_ambassadors'
MENU_AGENT_USAGE = 'menu_agent_usage'

# The one line the agent says above each card. Kept here beside the button
# labels so a menu entry and its reply cannot drift apart.
MENU_VIEWS = {
    MENU_DEPARTMENT: ('DEPT Progress', VIEW_DEPARTMENT,
                      'Here is how your department is doing.'),
    MENU_LEADERBOARD: ('Leaderboard', VIEW_LEADERBOARD,
                       'Here are your sections, ranked.'),
    MENU_AMBASSADORS: ('Ambassadors', VIEW_AMBASSADORS,
                       'Here are your ambassadors.'),
    MENU_AGENT_USAGE: ('My Agents', VIEW_AGENT_USAGE,
                       'Here are your published agents.'),
}


# The "Section List" action, which belongs to `section_ui`. It is spelled out
# here because that module imports this one and the reverse would be an import
# cycle; `section_ui` checks the two agree at import time, so a rename fails
# loudly rather than leaving a button that dispatches to nothing.
SECTION_LIST = 'show_sections'


# The activation bar the dashboard counts sections against.
_ON_TRACK_PERCENT = 75.0


def _fits(messages: list) -> bool:
    return (
        len(json.dumps(messages, ensure_ascii=False).encode())
        < a2ui.SURFACE_BYTE_CEILING
    )


def _pct(activated, total) -> str:
    """One decimal, everywhere.

    The mockups show `90%` on the leaderboard and `89.7%` on the ambassador
    card for the same person, which reads as two screens disagreeing. One
    helper, one rounding, applied to every view.
    """
    if not total:
        return 'no students'
    return f'{(activated or 0) * 100 / total:.1f}%'


def _ratio(activated, total) -> str:
    return f'{activated or 0} of {total or 0} activated'


def _bar(activated, total, width: int = 10) -> str:
    """A bar, drawn in block characters.

    The v0.8 catalog has no chart, no ProgressBar and no colour, so a real
    chart is not available at any effort. Block elements are the one thing that
    reads as a bar in a proportional font: U+2588 and U+2591 are the same
    advance width as each other, so the bars line up down the column even
    though the labels around them do not.
    """
    if not total:
        return '░' * width
    filled = round((activated or 0) * width / total)
    filled = max(0, min(width, int(filled)))
    return '█' * filled + '░' * (width - filled)


def _plural(n: int, noun: str) -> str:
    return f'{n} {noun}' if n == 1 else f'{n} {noun}s'


_MONTHS = ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
           'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec')


def _local(synced_at) -> tuple:
    """A UTC timestamp as (day, month name, "HH:MM") in the reader's zone.

    Sethu stamps these in UTC. Slicing the characters out of the string, as
    this did, showed a professor 05:38 for a sync they had just watched happen
    at 11:08. Returns None if the timestamp cannot be read at all.
    """
    text = str(synced_at)
    try:
        moment = datetime(
            int(text[0:4]), int(text[5:7]), int(text[8:10]),
            int(text[11:13]), int(text[14:16]),
        ) + timedelta(minutes=config.DISPLAY_UTC_OFFSET_MINUTES)
    except (ValueError, IndexError):
        return None
    return moment.day, _MONTHS[moment.month - 1], moment.strftime('%H:%M')


def _stamp(synced_at) -> str:
    """A timestamp a professor reads, e.g. "as of 11 Aug, 11:30 IST"."""
    local = _local(synced_at)
    if not local:
        return f'as of {str(synced_at)[:16].replace("T", " ")}'
    day, month, clock = local
    return f'as of {day} {month}, {clock} {config.DISPLAY_TZ_LABEL}'


def _synced_line(synced_at) -> str:
    """Say how fresh the numbers are, or that they have never been fresh."""
    if not synced_at:
        return 'These figures have never synced.'
    local = _local(synced_at)
    if not local:
        # An unparseable timestamp is not worth failing a card over, and a raw
        # one still tells a professor something.
        return f'Updated {str(synced_at)[:16].replace("T", " ")}'
    day, month, clock = local
    return f'Updated {day} {month}, {clock} {config.DISPLAY_TZ_LABEL}'


def _paged(state, base: str, header: list, rows: list, footer: str | None,
           view: str, offset: int, buttons: list | None = None,
           row_budget: int | None = None, row_cap: int | None = None) -> list:
    # `footer` may be a single line or several.
    """Fit what fits, page the rest behind a button.

    Each entry in `rows` is itself a list of lines — a title and its bar — and
    entries are dropped whole. Dropping by line would strand a bar under no
    heading at the bottom of a page.
    """
    prefix = a2ui.uid(state, base)
    extra = list(buttons or [])
    window = rows[offset:]
    for count in range(len(window), 0, -1):
        shown = [line for entry in window[:count] for line in entry]
        remaining = len(rows) - (offset + count)
        page_buttons = list(extra)
        if remaining > 0:
            page_buttons.append((
                f'Show {remaining} more',
                SHOW_MORE,
                {'view': view, 'offset': offset + count},
            ))
        tail = ([footer] if isinstance(footer, str) else list(footer or []))
        # Rules where the card changes subject: the rollup ends and the list
        # begins, the list ends and the footnotes begin.
        lines = (header
                 + ([a2ui.DIVIDER] if shown else [])
                 + shown
                 + ([a2ui.DIVIDER] if tail else [])
                 + tail)
        messages = a2ui.build_card(prefix, lines, page_buttons,
                                   row_budget=row_budget, row_cap=row_cap)
        if _fits(messages):
            return messages
    tail = ([footer] if isinstance(footer, str) else list(footer or []))
    # Only say there is nothing when nothing else on the card explains why.
    empty = [] if (rows or tail) else ['Nothing to show yet.']
    return a2ui.build_card(prefix, header + empty + tail, extra,
                           row_budget=row_budget, row_cap=row_cap)


def _department_buttons(data: dict, progress: dict, action: str) -> tuple[list, str | None]:
    """Buttons to look at another department, and the caveat if there are none.

    Sethu resolves the scope from the caller's email, so asking for another
    department may simply come back as your own. That is detected on the
    request and recorded, and the buttons are withdrawn rather than left there
    doing nothing.
    """
    if not config.DEPARTMENT_SWITCH_ENABLED or data.get('switch_unsupported'):
        # No caveat when the feature is simply off: a professor who was never
        # offered another department does not need telling they cannot have
        # one. The line is for the case where the buttons were there a moment
        # ago and have just been withdrawn.
        return [], (
            'Sethu scopes these figures to your own department, so the other '
            'departments cannot be shown here.'
        ) if data.get('switch_unsupported') else None
    current = progress.get('department')
    others = [d for d in (data.get('departments') or []) if d and d != current]
    if not others:
        return [], None
    # Six is already three rows of buttons; more belongs behind its own card.
    return [(d, action, {'department': d}) for d in others[:6]], None


# --- "How is my department doing?" ----------------------------------------

def _section_entry(section: dict) -> list:
    """One section as a heading and a bar beneath it."""
    who = section.get('ambassador') or 'no ambassador'
    activated, total = section.get('activated'), section.get('total')
    # `pooled` is a ranking rule and this card does not rank, so it would be a
    # word the reader has to look up for no gain. It stays on the leaderboard,
    # where it explains a section's position.
    return [
        f'{section.get("label")} — {who}',
        f'{_bar(activated, total)}  {_pct(activated, total)} · '
        f'{_ratio(activated, total)}',
    ]


def department_dashboard(state, data: dict, offset: int = 0) -> list:
    """The department rollup, worst sections first.

    Worst-first rather than by `rank`: this card is asked "how are we doing",
    and the sections that answer that are the ones behind. `rank` orders the
    leaderboard, where being ranked is the point.

    `data` carries both calls this card needs — `progress` always, and
    `ambassadors` only if that second call succeeded — so a "Show more" tap
    redraws from state with the same tiles it was first drawn with.
    """
    progress = data.get('progress') or {}
    ambassadors = data.get('ambassadors')
    sections = list(progress.get('sections') or [])
    scope = progress.get('department') or 'the college'
    activated, total = progress.get('activated'), progress.get('total')

    on_track = [
        s for s in sections
        if s.get('total') and (s.get('activated') or 0) * 100 / s['total']
        >= _ON_TRACK_PERCENT
    ]
    uncovered = [s for s in sections if not s.get('ambassador')]

    header = [
        f'How {scope} is doing',
        f'{_bar(activated, total)}  {_pct(activated, total)} — {activated} of '
        f'{total} students activated',
    ]

    # One line, and only the parts that say something. A zero here — "sections
    # with no ambassador: 0" — costs a line to report the absence of a problem,
    # and with a single section "0 of 1 behind" is arithmetic the reader can
    # already see in the bar above.
    flags = []
    behind = len(sections) - len(on_track)
    if len(sections) > 1 and behind:
        flags.append(f'{behind} of {len(sections)} sections below '
                     f'{_ON_TRACK_PERCENT:.0f}%')
    if uncovered:
        flags.append(f'{_plural(len(uncovered), "section")} with no ambassador')
    # The idle count is the one figure this card cannot get from its own
    # endpoint. If that second call failed it is dropped rather than guessed.
    if ambassadors is not None:
        idle = [a for a in (ambassadors.get('ambassadors') or [])
                if a.get('idleDays') is None or a.get('idleDays') >= 3]
        if idle:
            flags.append(f'{len(idle)} quiet for 3+ days')
    if flags:
        header.append(' · '.join(flags))

    def worst_first(section):
        total_ = section.get('total') or 0
        return ((section.get('activated') or 0) / total_ if total_ else 0,
                section.get('label') or '')

    switch_buttons, caveat = _department_buttons(data, progress, MENU_DEPARTMENT)
    if caveat:
        header.append(caveat)

    # This card is where a professor goes to look at their department, so the
    # two views that answer the follow-up questions — the ranking, and the
    # section roster — hang off it rather than off the opening menu.
    buttons = switch_buttons + [
        ('Leaderboard', MENU_LEADERBOARD, None),
        ('Section List', SECTION_LIST, None),
    ]

    # A heading between the department's own figures and the per-section list.
    # Without it the summary's last line and the first section run together —
    # both are body text, and a reader cannot tell where the rollup stops.
    rows = [[_heading('Sections')]]
    rows += [_section_entry(s) for s in sorted(sections, key=worst_first)]
    return _paged(state, 'deptprog', header, rows,
                  _synced_line(progress.get('syncedAt')),
                  VIEW_DEPARTMENT, offset, buttons)


# --- "Show the leaderboard" -----------------------------------------------

def leaderboard(state, data: dict, offset: int = 0) -> list:
    """Sections by server-assigned rank, best first."""
    progress = data.get('progress') or data
    sections = sorted(
        (progress.get('sections') or []),
        key=lambda s: (s.get('rank') is None, s.get('rank') or 0),
    )
    scope = progress.get('department') or 'the college'
    activated, total = progress.get('activated'), progress.get('total')

    single = len(sections) < 2
    header = [
        f'{scope} sections' if single else f'{scope} sections, ranked',
        f'{_bar(activated, total)}  {scope} overall {_pct(activated, total)} · '
        f'{_ratio(activated, total)}',
    ]
    rows = []
    for section in sections:
        who = section.get('ambassador') or 'no ambassador'
        activated, total = section.get('activated'), section.get('total')
        # Pooling is marked on the row, not just in the footer. A pooled
        # section can sit last on 100%, and a reader who does not connect it to
        # the footnote reads the ranking as broken. With nothing to rank
        # against, neither the position nor the pooling means anything.
        tail = '' if single or not section.get('pooled') else ' · pooled'
        rank = '' if single else f'#{section.get("rank")}  '
        rows.append([
            f'{rank}{section.get("label")} — {who}',
            f'{_bar(activated, total)}  {_pct(activated, total)} · '
            f'{_ratio(activated, total)}{tail}',
        ])

    # Nothing to explain when there is one row and no ranking happening.
    footer = None
    if not single:
        footer = 'Ranked on % activated.'
        if any(s.get('pooled') for s in sections):
            footer += ' Sections under 30 students rank last.'

    switch_buttons, caveat = _department_buttons(data, progress, MENU_LEADERBOARD)
    if caveat:
        header.append(caveat)

    # The way back. This card is reached from the department card, and without
    # these it is a dead end — the only thing under it was the opening menu,
    # which starts the professor over rather than returning them.
    buttons = switch_buttons + [
        ('DEPT Progress', MENU_DEPARTMENT, None),
        ('Section List', SECTION_LIST, None),
    ]
    return _paged(state, 'leaderb', header, rows, footer,
                  VIEW_LEADERBOARD, offset, buttons)


# --- "Who / How are my ambassadors?" --------------------------------------

def _idle_phrase(ambassador: dict) -> str:
    """Always about the section, never about the person.

    `idleDays` counts days since the last *student* activation in their cohort.
    Rendering it as "Rohit did nothing for 6 days" would be an accusation the
    data cannot support.
    """
    days = ambassador.get('idleDays')
    if ambassador.get('lastActivityAt') is None:
        return 'no activation recorded in their section'
    if days == 0:
        return 'someone in their section activated today'
    if days == 1:
        return 'last activation in their section yesterday'
    return f'no activation in their section for {days} days'


def ambassador_summary(data: dict) -> str:
    """Built here, not by the model.

    It is made entirely of counts and names. A model writing this sentence from
    a tool result will eventually get a day-count wrong, and it will read as
    authoritative.
    """
    people = list(data.get('ambassadors') or [])
    quiet = [a for a in people
             if a.get('lastActivityAt') is None or (a.get('idleDays') or 0) >= 3]
    uncovered = list(data.get('sectionsWithoutAmbassador') or [])

    if not people:
        parts = ['No ambassadors are listed for your department.']
    elif not quiet:
        parts = [
            'Every section with an ambassador has activated someone in the '
            'last 3 days.' if len(people) > 1 else
            'Their section has activated someone in the last 3 days.'
        ]
    elif len(people) == 1:
        # With one ambassador the row below says who and how long. Repeating it
        # here in a longer sentence is the whole card said twice.
        parts = ['Their section has gone quiet.']
    elif len(quiet) == len(people):
        parts = [f'All {len(people)} of your ambassadors cover sections that '
                 'have gone quiet.']
    else:
        named = ', '.join(
            f'{a.get("name")} ({a.get("section")}, {_idle_phrase(a)})'
            for a in quiet[:3]
        )
        more = f' and {len(quiet) - 3} more' if len(quiet) > 3 else ''
        parts = [
            f'{len(quiet)} of your {len(people)} ambassadors cover sections '
            f'that have gone quiet — {named}{more}.'
        ]

    if uncovered:
        labels = ', '.join(str(s.get('section')) for s in uncovered[:3])
        extra = f' and {len(uncovered) - 3} more' if len(uncovered) > 3 else ''
        parts.append(
            f'{_plural(len(uncovered), "section")} '
            f'{"has" if len(uncovered) == 1 else "have"} no ambassador at all: '
            f'{labels}{extra}.'
        )
    return ' '.join(parts)


def _amb_rate(ambassador: dict) -> float:
    total = ambassador.get('total') or 0
    return (ambassador.get('activated') or 0) / total if total else 0.0


def ambassador_roster(state, data: dict, offset: int = 0) -> list:
    """The department's ambassadors, or one cut of them.

    Three views over the same payload. The default keeps Sethu's own order —
    worst first — because the card is asked who needs attention. The
    leaderboard reverses that question, and the uncovered list answers a third
    one the ambassador list cannot: which sections have nobody at all, which is
    why Sethu returns it separately.
    """
    people = list(data.get('ambassadors') or [])
    uncovered = list(data.get('sectionsWithoutAmbassador') or [])
    where = data.get('department') or 'the college'
    chosen = (state or {}).get(AMBASSADOR_FILTER) or AMB_ALL

    if chosen == AMB_LEADERBOARD:
        shown = sorted(people, key=lambda a: (-_amb_rate(a), _agent_name(a)))
        header = [f'Ambassador Leaderboard — {where}']
        if shown:
            header.append('Ranked on % of their section activated.')
        top = _amb_rate(shown[0]) if shown else 0.0
        rows = []
        for position, a in enumerate(shown, 1):
            activated, total = a.get('activated'), a.get('total')
            bar = (_bar(round(_amb_rate(a) * 100), round(top * 100))
                   if top else _bar(0, 0))
            rows.append([
                f'#{position}  {a.get("name")} — {a.get("section")}',
                f'{bar}  {_pct(activated, total)} · {_ratio(activated, total)}',
            ])
        footer = ['No ambassadors are listed for this department.'] if not shown else []

    elif chosen == AMB_UNCOVERED:
        header = [f'Sections With No Ambassador — {where}']
        rows = [[f'·  {s.get("section")}'
                 + (f'  —  {_plural(s.get("total") or 0, "student")}'
                    if s.get('total') else '')]
                for s in uncovered]
        footer = ([] if uncovered else
                  ['Every section in this department has an ambassador.'])

    else:
        chosen = AMB_ALL
        header = [f'Ambassadors in {where}', ambassador_summary(data)]
        if len(people) > 1:
            header.append('Quietest sections are listed first.')
        rows = [
            [
                f'{a.get("name")} — {a.get("section")}',
                f'{_bar(a.get("activated"), a.get("total"))}  '
                f'{_pct(a.get("activated"), a.get("total"))} · '
                f'{_ratio(a.get("activated"), a.get("total"))} · {_idle_phrase(a)}',
            ]
            for a in people
        ]
        footer = [
            'Quiet means no student activations in that section, not the '
            "ambassador's own activity."
        ]

    buttons = [(label, AMBASSADOR_VIEW, {'filter': key}) for label, key in (
        ('Leaderboard', AMB_LEADERBOARD),
        ('Section with No Ambassador', AMB_UNCOVERED),
    ) if key != chosen]
    if chosen != AMB_ALL:
        buttons.append(('All Ambassadors', AMBASSADOR_VIEW, {'filter': AMB_ALL}))

    return _paged(state, 'ambass', header, rows, footer,
                  VIEW_AMBASSADORS, offset, buttons,
                  row_budget=70, row_cap=5)


# --- "How are my agents used?" --------------------------------------------

def _where(sections: list) -> str:
    """Where an agent went, without repeating a long label list."""
    if not sections:
        return 'not sent to anyone'
    if len(sections) == 1:
        return str(sections[0])
    if len(sections) == 2:
        return f'{sections[0]} and {sections[1]}'
    return f'{len(sections)} sections'


def _chats(agent: dict):
    """Conversations this week, or None if nothing has measured them.

    `statsSyncedAt` is the gate. A count without it is a value nobody wrote,
    and `0` from an unsynced record would be reported as a measured silence.
    """
    if not agent.get('statsSyncedAt'):
        return None
    return (agent.get('stats') or {}).get('questionsThisWeek')


def _has_usage(agent: dict) -> bool:
    """Whether anything has actually been measured for this agent.

    An agent can be used without ever having been sent to a section — a
    professor's own Gemini Enterprise agent gets opened directly, so it has
    conversations and no Sethu audience. Measured 2026-08-11: one such agent
    had 100 conversations while every section-published agent had none.
    """
    if not agent.get('statsSyncedAt'):
        return False
    stats = agent.get('stats') or {}
    return any(stats.get(f) is not None
               for f in ('questionsThisWeek', 'usedBy'))


def _agent_name(agent: dict) -> str:
    """What to call an agent, preferring the name the professor gave it.

    `name` is whatever `publish_agent` sent, so for anything a professor
    published it is already their own wording. A record Sethu's GE sync
    discovered was never published by anyone, so it carries the Gemini
    Enterprise name — there is no publish-time name to prefer. `subject` is the
    only other human label on the record and is used when `name` is missing.
    """
    for field in ('name', 'subject'):
        value = str(agent.get(field) or '').strip()
        if value:
            return value
    return 'Untitled agent'


def _heading(title: str) -> tuple:
    """A section heading inside a card.

    Rendered with the same usage hint as the card's own title, which is the
    strongest visual break the v0.8 catalog allows. There is no non-clickable
    button in it, and a real Button dispatches an action when tapped — a
    professor pressing a decorative one would send the agent a message.
    """
    return (title, 'h3')


def _signins(agent: dict) -> int:
    return (agent.get('stats') or {}).get('signInsCaused') or 0


def agent_usage(state, agents: list, offset: int = 0) -> list:
    """The professor's agents, or one cut of them.

    Every cut but one is about agents that were actually sent to sections. An
    agent nobody has been given cannot have activation or conversations, so
    listing it beside agents that do is a row of blanks that pushes the real
    ones off the card. Those live behind "Not Sent Yet", which is a to-do list
    rather than a measurement.

    The current cut lives in session state so paging stays inside it.
    """
    agents = list(agents or [])
    sent = [a for a in agents if a.get('sections')]
    unsent = [a for a in agents if not a.get('sections')]
    chosen = (state or {}).get(AGENT_FILTER) or FILTER_ALL

    if chosen == FILTER_MOST_USED:
        shown = sorted([a for a in sent if (_chats(a) or 0) > 0],
                       key=lambda a: (-(_chats(a) or 0), _agent_name(a)))
        title, empty = 'Most Used', 'No sent agent has conversations yet.'
    elif chosen == FILTER_MOST_ACTIVATED:
        shown = sorted([a for a in sent if _signins(a) > 0],
                       key=lambda a: (-_signins(a), _agent_name(a)))
        title, empty = 'Most Successful Activation', 'No sent agent has an activation yet.'
    elif chosen == FILTER_NO_ACTIVATION:
        shown = sorted([a for a in sent if _signins(a) == 0], key=_agent_name)
        title, empty = 'No Activation', 'Every sent agent has at least one activation.'
    elif chosen == FILTER_NOT_SENT:
        shown = sorted(unsent, key=_agent_name)
        title, empty = 'Not Sent Yet', 'Every agent has been sent.'
    else:
        chosen = FILTER_ALL
        # Ranked by conversations, which is also what the bar measures. Sends
        # of the same agent are kept together so their shared chat total reads
        # as one group.
        shown = sorted(
            sent,
            key=lambda a: (-(_chats(a) or 0),
                           a.get('agentName') or _agent_name(a),
                           -_signins(a),
                           _agent_name(a)),
        )
        title, empty = 'Your agents', 'No agent has been sent to a section yet.'

    def volume(agent):
        chats = _chats(agent)
        return (_plural(chats, 'chat') + ' this week' if chats is not None
                else 'chat volume not synced')

    rows = []
    if chosen == FILTER_MOST_USED:
        top = _chats(shown[0]) or 0 if shown else 0
        rows = [[_agent_name(a),
                 f'{_bar(_chats(a) or 0, top)}  '
                 f'{_plural(_chats(a) or 0, "chat")} this week'] for a in shown]
    elif chosen == FILTER_MOST_ACTIVATED:
        top = _signins(shown[0]) if shown else 0
        rows = [[_agent_name(a),
                 f'{_bar(_signins(a), top)}  {_plural(_signins(a), "activation")}']
                for a in shown]
    elif chosen == FILTER_NOT_SENT:
        rows = [[f'·  {_agent_name(a)}'] for a in shown]
    elif chosen == FILTER_NO_ACTIVATION:
        # Every row here has zero activations, so printing that is a column of
        # identical noise. Conversations are the one thing that varies — an
        # agent used without a single activation is worth seeing — so it is
        # shown when there is one and left off entirely when there is not.
        for a in shown:
            chats = _chats(a) or 0
            rows.append([f'·  {_agent_name(a)}' + (
                f'  —  {_plural(chats, "chat")} this week' if chats else '')])
    else:
        # The bar measures conversations, which is what the list is ordered by.
        # With nothing measured anywhere there is no scale, so no bar is drawn.
        top = max((_chats(a) or 0 for a in shown), default=0)
        # A conversation total belongs to the Gemini Enterprise agent, not to
        # any one send of it, so it is printed once per agent rather than
        # repeated beside every send as if each had earned it.
        seen_chats = set()
        for a in shown:
            chats = _chats(a)
            detail = _plural(_signins(a), 'activation')
            key = a.get('agentName') or _agent_name(a)
            shared = (a.get('sendCount') or 0) > 1
            # The bar is drawn once per agent, beside the figure it measures.
            # Repeated on every send it read as each send having earned the
            # whole agent's conversations.
            first = key not in seen_chats
            if top and first:
                detail = f'{_bar(chats or 0, top)}  {detail}'
            line = [_agent_name(a), detail]

            if first:
                seen_chats.add(key)
                if shared:
                    line.append(
                        f'   {key} · {volume(a)} across '
                        f'{_plural(a["sendCount"], "send")}'
                    )
                else:
                    line[1] = f'{detail} · {volume(a)}'
            rows.append(line)

    header = [title]
    if chosen == FILTER_ALL:
        # Sends, then how many distinct agents they came from. Counting rows
        # would say "3 agents sent" for one agent sent to three departments.
        names = {a.get('agentName') or _agent_name(a) for a in sent}
        summary = f'{_plural(len(names), "agent")} sent'
        if len(sent) > len(names):
            summary = f'{summary} · {_plural(len(sent), "send")}'
        if unsent:
            summary += f', {len(unsent)} not sent yet'
        header.append(summary)

    buttons = [(label, AGENT_VIEW, {'filter': key}) for label, key in (
        ('Most Used', FILTER_MOST_USED),
        ('Top Activation', FILTER_MOST_ACTIVATED),
        ('No Activation', FILTER_NO_ACTIVATION),
        ('Not Sent Yet', FILTER_NOT_SENT),
    ) if key != chosen]
    if chosen != FILTER_ALL:
        buttons.append(('All Agents', AGENT_VIEW, {'filter': FILTER_ALL}))

    footer = []
    if not shown:
        footer.append(empty)
    stamps = [a.get('statsSyncedAt') for a in agents if a.get('statsSyncedAt')]
    if stamps:
        footer.append(f'Usage figures {_stamp(max(stamps))}.')
    # One row of buttons. The four labels total 48 characters; the measured
    # pane fitted about 65 before Gemini Enterprise clipped one, so this stays
    # inside that with room to spare while the conservative default would wrap
    # them onto two lines.
    return _paged(state, 'agentuse', header, rows, footer,
                  VIEW_AGENT_USAGE, offset, buttons,
                  row_budget=70, row_cap=5)


# Which builder a paged view re-enters, so a "Show more" tap redraws the same
# card from the payload already in session state.
BUILDERS = {
    VIEW_DEPARTMENT: department_dashboard,
    VIEW_LEADERBOARD: leaderboard,
    VIEW_AMBASSADORS: ambassador_roster,
    VIEW_AGENT_USAGE: agent_usage,
}
