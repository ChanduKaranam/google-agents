"""Render session state as A2UI v0.8 so Gemini Enterprise draws real widgets.

Deterministic on purpose. The documented ADK path injects an A2UI system prompt
and has the model emit the JSON itself; we do not. Everything rendered here is
structured data a tool already wrote to session state, so there is nothing for a
model to compose -- and letting one compose it would turn `NO_INVENTION` from a
structural guarantee into a prompt. A hallucinated company is a sentence; a
hallucinated company with a clickable button is worse. A value that is not in
state cannot be rendered by this module.

Wire format, from the A2UI v0.8 renderer test data
(`renderers/angular/src/v0_8/test_data/mocks/`): a flat list of messages, each
carrying one of `surfaceUpdate` / `dataModelUpdate` / `beginRendering`.
Components are a flat list of `{"id": ..., "component": {"<Type>": {...}}}` and
reference each other by id. We inline every value as `literalString` and skip
`dataModelUpdate` entirely -- the split data model exists to save tokens on long
conversations, which is not a problem a deterministic renderer has.

Gemini Enterprise supports **v0.8 only**, and identifies the payload by the
`mimeType` on the DataPart metadata (`a2ui/a2a/parts.py`). v0.8 uses
`application/json+a2ui`; the newer `application/a2ui+json` will not render there.
"""

from __future__ import annotations

import json

from google.genai import types

# a2ui/a2a/parts.py calls this the deprecated spelling, but it is the one v0.8
# clients -- which is all Gemini Enterprise supports -- actually look for.
A2UI_MIME_TYPE = "application/json+a2ui"

# How ADK smuggles an A2A DataPart out of a genai Part: inline_data with this
# mime whose bytes are the serialised DataPart between these tags gets converted
# back into a real DataPart (`google/adk/a2a/converters/part_converter.py:231-245`).
_ADK_DATAPART_MIME = "text/plain"
_ADK_START_TAG = b"<a2a_datapart_json>"
_ADK_END_TAG = b"</a2a_datapart_json>"

_PIPELINE_SURFACE = "job-helper-pipeline"

# Ordered worst-to-best so the board reads as progress. Mirrors STATUSES in
# tools.py; anything not listed sorts last rather than being dropped, because
# silently hiding a student's application is worse than an odd sort order.
_STATUS_ORDER = (
    "Offer",
    "Interview",
    "OA Scheduled",
    "Referral Requested",
    "Applied",
    "Rejected",
)


def _text(component_id: str, value: str, hint: str = "body") -> dict:
    return {
        "id": component_id,
        "component": {
            "Text": {"text": {"literalString": value}, "usageHint": hint}
        },
    }


def _column(component_id: str, children: list[str]) -> dict:
    return {
        "id": component_id,
        "component": {"Column": {"children": {"explicitList": children}}},
    }


def _row(component_id: str, children: list[str]) -> dict:
    return {
        "id": component_id,
        "component": {
            "Row": {"children": {"explicitList": children}, "alignment": "center"}
        },
    }


def _status_rank(status: str) -> int:
    try:
        return _STATUS_ORDER.index(status)
    except ValueError:
        return len(_STATUS_ORDER)


def pipeline_board(applications: list[dict]) -> list[dict] | None:
    """Build the tracked-application board, or None if there is nothing real.

    Returning None rather than an empty board matters: a student who has
    tracked nothing must not be shown a widget implying otherwise.
    """
    if not applications:
        return None

    components: list[dict] = []
    body: list[str] = ["title", "subtitle"]

    components.append(_text("title", "Your application pipeline", "h2"))
    count = len(applications)
    components.append(
        _text(
            "subtitle",
            f"{count} application{'' if count == 1 else 's'} tracked",
            "caption",
        )
    )

    ordered = sorted(
        applications, key=lambda a: _status_rank(str(a.get("status", "")))
    )
    for index, app in enumerate(ordered):
        company = str(app.get("company") or "").strip()
        role = str(app.get("role") or "").strip()
        status = str(app.get("status") or "").strip()
        notes = str(app.get("notes") or "").strip()
        if not company:
            # No company means no row. There is nothing truthful to draw.
            continue

        prefix = f"app{index}"
        heading = company if not role else f"{company} — {role}"
        children = [f"{prefix}-heading", f"{prefix}-status"]
        components.append(_text(f"{prefix}-heading", heading, "h3"))
        components.append(_text(f"{prefix}-status", status or "Applied", "body"))
        if notes:
            children.append(f"{prefix}-notes")
            components.append(_text(f"{prefix}-notes", notes, "caption"))

        components.append(_column(f"{prefix}-col", children))
        body.append(f"{prefix}-col")

        if index < len(ordered) - 1:
            divider_id = f"{prefix}-divider"
            components.append({"id": divider_id, "component": {"Divider": {}}})
            body.append(divider_id)

    if len(body) <= 2:  # title + subtitle only: every row was unrenderable
        return None

    components.append(_column("body", body))
    components.append({"id": "root", "component": {"Card": {"child": "body"}}})

    return [
        {
            "surfaceUpdate": {
                "surfaceId": _PIPELINE_SURFACE,
                "components": components,
            }
        },
        {"beginRendering": {"surfaceId": _PIPELINE_SURFACE, "root": "root"}},
    ]


def _surface(surface_id: str, components: list[dict]) -> list[dict]:
    return [
        {"surfaceUpdate": {"surfaceId": surface_id, "components": components}},
        {"beginRendering": {"surfaceId": surface_id, "root": "root"}},
    ]


def _card(components: list[dict], body: list[str]) -> list[dict]:
    components.append(_column("body", body))
    components.append({"id": "root", "component": {"Card": {"child": "body"}}})
    return components


def company_shortlist(companies_data: dict) -> list[dict] | None:
    """Draw the matched companies, one block per company."""
    companies = (companies_data or {}).get("companies") or []
    if not companies:
        return None

    components: list[dict] = [_text("title", "Companies worth your time", "h2")]
    body = ["title"]

    for index, company in enumerate(companies):
        name = str(company.get("name") or "").strip()
        if not name:
            continue
        prefix = f"co{index}"
        children = [f"{prefix}-name"]
        fit = str(company.get("fit") or "").strip()
        components.append(
            _text(f"{prefix}-name", f"{name} — {fit}" if fit else name, "h3")
        )

        why = str(company.get("why_it_fits") or "").strip()
        if why:
            children.append(f"{prefix}-why")
            components.append(_text(f"{prefix}-why", why, "body"))

        meta = " · ".join(
            v
            for v in (
                str(company.get("industry") or "").strip(),
                str(company.get("size_or_stage") or "").strip(),
            )
            if v
        )
        if meta:
            children.append(f"{prefix}-meta")
            components.append(_text(f"{prefix}-meta", meta, "caption"))

        # The opening link is rendered as text, not as a Text markdown link:
        # v0.8 Text explicitly excludes links, and a Button dispatches a
        # client-side action rather than opening a URL. Showing the URL plainly
        # is the honest option -- a link that silently does nothing is worse.
        url = str(company.get("opening_url") or "").strip()
        if url:
            title = str(company.get("opening_title") or "Open role").strip()
            children.append(f"{prefix}-role")
            components.append(_text(f"{prefix}-role", f"{title}: {url}", "caption"))

        components.append(_column(f"{prefix}-col", children))
        body.append(f"{prefix}-col")
        if index < len(companies) - 1:
            components.append({"id": f"{prefix}-div", "component": {"Divider": {}}})
            body.append(f"{prefix}-div")

    if len(body) == 1:
        return None

    note = str((companies_data or {}).get("note") or "").strip()
    if note:
        components.append(_text("note", note, "caption"))
        body.append("note")

    return _surface("job-helper-companies", _card(components, body))


def alumni_cards(alumni_data: dict) -> list[dict] | None:
    """Draw verified contacts, or the searches the student can run themselves.

    An empty alumni list is the ordinary case, not a failure: public search
    cannot answer "who from college X works at company Y". So when there is
    nobody verifiable we render the LinkedIn searches from `links.py` instead --
    never a padded list of guessed names.
    """
    data = alumni_data or {}
    alumni = data.get("alumni") or []
    links = data.get("search_links") or {}

    components: list[dict] = []
    body: list[str] = []

    if alumni:
        components.append(_text("title", "People who could refer you", "h2"))
        body.append("title")
        for index, person in enumerate(alumni):
            name = str(person.get("name") or "").strip()
            url = str(person.get("profile_url") or "").strip()
            # No link, no person. This is REAL_PEOPLE_RULES made structural:
            # the student cannot verify an unlinked name, so we never draw one.
            if not name or not url:
                continue
            prefix = f"al{index}"
            children = [f"{prefix}-name"]
            role = str(person.get("role") or "").strip()
            company = str(person.get("company") or "").strip()
            headline = " · ".join(v for v in (role, company) if v)
            components.append(_text(f"{prefix}-name", name, "h3"))
            if headline:
                children.append(f"{prefix}-role")
                components.append(_text(f"{prefix}-role", headline, "body"))
            shared = str(person.get("shared_context") or "").strip()
            if shared:
                children.append(f"{prefix}-shared")
                components.append(_text(f"{prefix}-shared", shared, "caption"))
            children.append(f"{prefix}-link")
            components.append(_text(f"{prefix}-link", url, "caption"))
            components.append(_column(f"{prefix}-col", children))
            body.append(f"{prefix}-col")

    people = str(links.get("people_search") or "").strip()
    school = str(links.get("school_page_search") or "").strip()
    if people or school:
        heading = (
            "Search LinkedIn yourself"
            if alumni
            else "No verifiable contacts found — search LinkedIn yourself"
        )
        components.append(_text("links-title", heading, "h3"))
        components.append(
            _text(
                "links-help",
                "Open these while signed in to LinkedIn. The school page search"
                " then its People tab and 'Where they work' filter gives the"
                " fullest list.",
                "caption",
            )
        )
        body += ["links-title", "links-help"]
        if people:
            components.append(_text("links-people", people, "caption"))
            body.append("links-people")
        if school:
            components.append(_text("links-school", school, "caption"))
            body.append("links-school")

    if not body:
        return None

    return _surface("job-helper-alumni", _card(components, body))


def upload_prompt(state: dict) -> list[dict] | None:
    """Ask for the resume, but only until there is a profile.

    Gemini Enterprise delivers an attached file as an artifact plus empty
    `<start_of_user_uploaded_file: name>` markers, and the root agent already
    holds `load_artifacts` to read it -- so the attach control the student
    needs is GE's own, and what is missing is simply being told to use it.
    """
    getter = getattr(state, "get", None)
    if not callable(getter):
        return None
    if getter("profile"):
        return None

    components = [
        _text("title", "Start with your resume", "h2"),
        _text(
            "help",
            "Attach your resume (PDF or DOCX) using the attachment button, or"
            " paste its text here. Everything else — matching companies,"
            " finding alumni, tracking applications — runs off it.",
            "body",
        ),
    ]
    return _surface("job-helper-upload", _card(components, ["title", "help"]))


def build_a2ui_messages(state: dict) -> list[dict]:
    """Render whatever the session state supports. Empty list renders nothing.

    Only `applications` is here because only `applications` is structured: it is
    written by `tools.track_application`. The other state keys (`companies`,
    `alumni`, `matches`, `gaps`) hold the specialists' prose, since they come
    from `output_key` on an LlmAgent -- there is no reliable structure to draw
    cards from. Rendering those needs those specialists to emit structured
    output first; see the ticket-2 notes in the design spec.
    """
    # Take the mapping by `.get` rather than converting it. ADK hands callbacks
    # a `State`, and `dict(State)` raises `KeyError: 0` -- dict() finds no
    # keys() and falls back to reading it as a sequence of pairs. That failure
    # was swallowed by the caller's guard, so the widget silently never drew.
    getter = getattr(state, "get", None)
    if not callable(getter):
        return []

    messages: list[dict] = []
    for surface in (
        upload_prompt(state),
        company_shortlist(getter("companies") or {}),
        alumni_cards(getter("alumni") or {}),
        pipeline_board(getter("applications") or []),
    ):
        if surface:
            messages += surface
    return messages


def to_genai_parts(messages: list[dict]) -> list[types.Part]:
    """Wrap A2UI messages so ADK converts them into A2A DataParts.

    One DataPart per message, which is what makes incremental painting possible
    on the client -- the format is a flat list of small messages precisely so a
    renderer can draw as they arrive.
    """
    parts: list[types.Part] = []
    for message in messages:
        data_part = {"data": message, "metadata": {"mimeType": A2UI_MIME_TYPE}}
        payload = json.dumps(data_part, separators=(",", ":")).encode("utf-8")
        parts.append(
            types.Part(
                inline_data=types.Blob(
                    mime_type=_ADK_DATAPART_MIME,
                    data=_ADK_START_TAG + payload + _ADK_END_TAG,
                )
            )
        )
    return parts
