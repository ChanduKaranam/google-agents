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

from . import a2ui, config

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


def _synced_line(synced_at) -> str:
    """Say how fresh the numbers are, or that they have never been fresh."""
    if not synced_at:
        return 'These figures have never synced.'
    stamp = str(synced_at)
    try:
        month = _MONTHS[int(stamp[5:7]) - 1]
        return f'Updated {int(stamp[8:10])} {month}, {stamp[11:16]}'
    except (ValueError, IndexError):
        # An unparseable timestamp is not worth failing a card over, and a raw
        # one still tells a professor something.
        return f'Updated {stamp[:16].replace("T", " ")}'


def _paged(state, base: str, header: list, rows: list, footer: str | None,
           view: str, offset: int, buttons: list | None = None) -> list:
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
        lines = header + shown + tail
        messages = a2ui.build_card(prefix, lines, page_buttons)
        if _fits(messages):
            return messages
    tail = ([footer] if isinstance(footer, str) else list(footer or []))
    # Only say there is nothing when nothing else on the card explains why.
    empty = [] if (rows or tail) else ['Nothing to show yet.']
    return a2ui.build_card(prefix, header + empty + tail, extra)


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

    rows = [_section_entry(s) for s in sorted(sections, key=worst_first)]
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

    buttons, caveat = _department_buttons(data, progress, MENU_LEADERBOARD)
    if caveat:
        header.append(caveat)
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


def ambassador_roster(state, data: dict, offset: int = 0) -> list:
    """The roster in the order Sethu returned it — worst first."""
    people = list(data.get('ambassadors') or [])
    header = [
        f'Ambassadors in {data.get("department") or "the college"}',
        ambassador_summary(data),
    ]
    # Pointless above a single row, and it is the ordering that needs
    # explaining, not the list.
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
    # Kept, but to one line. The rows already say "no activation in their
    # section", so this only has to stop "quiet" being read as an accusation
    # about the person — it does not need to explain Sethu's data model.
    footer = (
        'Quiet means no student activations in that section, not the '
        'ambassador\'s own activity.'
    )
    return _paged(state, 'ambass', header, rows, footer,
                  VIEW_AMBASSADORS, offset)


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


def _agent_entry(agent: dict, busiest: int) -> list:
    """One agent as a name and a line of what is known about it.

    `busiest` is the highest sign-in count in the list, so the bar shows each
    agent against the best-performing one. When nothing has any sign-ins there
    is no bar: ten empty bars in a column say nothing and read as broken.
    """
    stats = agent.get('stats') or {}
    signins = stats.get('signInsCaused') or 0

    bits = [_where(agent.get('sections') or [])]
    if agent.get('studentCount'):
        bits.append(_plural(agent['studentCount'], 'student'))
    bits.append(_plural(signins, 'sign-in') if signins else 'no sign-ins yet')

    # Only shown once something has actually synced. Printing `usedBy: 0` and
    # `questionsThisWeek: null` as "0 chats" would report a quiet agent as a
    # measured fact when nothing has ever measured it.
    detail = ' · '.join(bits)
    if busiest:
        detail = f'{_bar(signins, busiest)}  {detail}'
    lines = [agent.get('name') or 'Untitled agent', detail]

    # Usage from the GE sync, on its own line. Appended to the one above it
    # made a run-on that wrapped to three lines in the chat pane.
    if agent.get('statsSyncedAt'):
        extra = []
        if stats.get('usedBy') is not None:
            extra.append(f'used by {_plural(stats["usedBy"], "student")}')
        if stats.get('questionsThisWeek') is not None:
            extra.append(f'{stats["questionsThisWeek"]} chats this week')
        if stats.get('topUnanswered'):
            extra.append(f'most asked, least answered: {stats["topUnanswered"]}')
        if extra:
            lines.append(' · '.join(extra))
    return lines


def agent_usage(state, agents: list, offset: int = 0) -> list:
    """The professor's agents, busiest first, with the unsent ones summarised.

    Two groups, because they are two different things. An agent published to
    sections is doing a job and can be compared with the others; an agent that
    was never sent to anyone has no audience, no sign-ins and nothing to rank —
    listing it row-for-row alongside the rest fills the card with zeroes and
    buries the four agents the professor actually wants to see.
    """
    agents = list(agents or [])
    sent = [a for a in agents if a.get('sections')]
    unsent = [a for a in agents if not a.get('sections')]

    def busiest_first(agent):
        stats = agent.get('stats') or {}
        return (
            -(stats.get('signInsCaused') or 0),
            -(agent.get('studentCount') or 0),
            str(agent.get('name') or ''),
        )

    sent.sort(key=busiest_first)
    busiest = max(
        ((a.get('stats') or {}).get('signInsCaused') or 0) for a in sent
    ) if sent else 0

    # Student counts cannot be summed across agents -- several of these go to
    # the same section, and adding them would invent an audience far larger
    # than the college has. Distinct sections is the honest reach.
    reach = len({str(s) for a in sent for s in (a.get('sections') or [])})

    summary = _plural(len(agents), 'agent')
    if sent:
        summary += (f' — {len(sent)} sent to '
                    f'{_plural(reach, "section")}')
        if unsent:
            summary += f', {len(unsent)} not sent yet'
    elif unsent:
        summary += ' — none sent to students yet'

    header = ['Your agents', summary]
    if sent:
        header.append('Busiest first.')
    elif unsent:
        # The footer names them; a bare "nothing to show" over a list of
        # agents the professor can see reads as a contradiction.
        header.append('None of them has been sent to a section yet.')
    rows = [_agent_entry(a, busiest) for a in sent]

    footer = []
    if unsent:
        names = ', '.join(str(a.get('name') or 'Untitled') for a in unsent[:4])
        if len(unsent) > 4:
            names += f', and {len(unsent) - 4} more'
        footer.append(f'Not sent to anyone yet: {names}.')
    # Judged over every agent, not just the sent ones: with nothing sent, an
    # empty `sent` list would otherwise report the figures as live and current.
    if agents and all(a.get('statsSyncedAt') for a in agents):
        footer.append('Sign-in counts come from share-link clicks and are live.')
    else:
        footer.append(
            'Sign-ins come from share-link clicks. Chat volume and unanswered '
            'topics have not synced yet.'
        )
    return _paged(state, 'agentuse', header, rows, footer,
                  VIEW_AGENT_USAGE, offset)


# Which builder a paged view re-enters, so a "Show more" tap redraws the same
# card from the payload already in session state.
BUILDERS = {
    VIEW_DEPARTMENT: department_dashboard,
    VIEW_LEADERBOARD: leaderboard,
    VIEW_AMBASSADORS: ambassador_roster,
    VIEW_AGENT_USAGE: agent_usage,
}
