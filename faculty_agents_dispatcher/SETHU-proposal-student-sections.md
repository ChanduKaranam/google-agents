# Proposal: a student-facing "which sections am I in?" endpoint

**For:** Sethu backend team
**From:** Faculty dispatcher GE agent (Tilicho Labs)
**Date:** 2026-08-04
**Status:** proposal — needs your decision on path and response shape

## What we need

One read-only endpoint that answers, for the **signed-in student**, which
sections they belong to.

```
GET /student/sections
Header: Authorization: Bearer <agent token minted for a STUDENT user>
```

## What it is for

Professors want a course agent to be usable only by the sections they sent it
to. Today it is usable by anyone in the college.

When a professor publishes an agent to `CSE · Year 1 · Sec A`, the WhatsApp
message goes to that section — but the message is only a **notification**, not
a restriction. The Gemini Enterprise link carries no secret, and the agents are
shared `ALL_USERS`, so any student in the organisation who has the link, or who
simply browses the GE agent list, can open and use it.

### Why we cannot solve this in Gemini Enterprise

GE's agent sharing has exactly three scopes: `ALL_USERS`, `RESTRICTED`
("shared based on the IAM policy"), and unspecified. `RESTRICTED` would be the
right answer, except **the Discovery Engine API exposes no per-agent IAM policy
method** — `setIamPolicy` exists only at the *engine* level, covering the whole
GE app. So there is no way to restrict one agent to one section from the
platform side.

The alternative — a Google Group per section, 55 of them, kept in sync with
enrolment — duplicates data you already own into Workspace, where it will drift
the moment a student transfers.

### So the check belongs in the agent, and the answer belongs to you

Each course agent asks, on the student's first message: *are you in one of the
sections I was published to?* If not, it declines.

You already mint per-user tokens for any signed-in Google account via
`POST /auth/agent-tokens/exchange`. Our faculty dispatcher uses the `FACULTY`
path today. This proposal is the `STUDENT` equivalent: the same exchange, then
one call to find out where that student sits.

That keeps section membership in Sethu, which owns it, instead of copying it
into IAM or hardcoding it per agent. Enrolment changes take effect immediately.

## Proposed response

Modelled on `GET /faculty/sections` so the shape is already familiar. Path,
field names and nesting are yours to decide — tell us and we will follow it.

```json
{
  "data": {
    "sections": [
      {
        "department": "CSE",
        "year": 1,
        "section": "A",
        "label": "CSE · Year 1 · Sec A"
      }
    ]
  },
  "error": null,
  "meta": { "timestamp": "…", "requestId": "…" }
}
```

A student normally belongs to exactly one section, but returning an array keeps
it uniform with the faculty endpoint and survives electives or re-enrolment.

**`label` must match `GET /faculty/sections` exactly.** That is the string a
professor's agent was published with, so an agent compares its own published
labels against this list. Any divergence in spacing or separators silently
denies every student.

Please do **not** include the student's name, phone number or email in the
response. The agent only needs to know which sections the caller is in — it
already knows who they are from the token.

## How a course agent would use it

1. GE forwards the student's OAuth access token.
2. Agent exchanges it at `POST /auth/agent-tokens/exchange` — same call our
   faculty agent makes, expecting `role: "STUDENT"`.
3. Agent calls `GET /student/sections`.
4. It intersects that against the sections it was published to. Empty
   intersection → decline politely; otherwise proceed.

## Steps for the backend team

1. **Confirm the exchange works for student accounts** and what `role` it
   returns. We have only ever exercised the `FACULTY` path.
2. **Decide the path and response shape.** We will not guess — a wrong guess
   here has already cost us a day on this integration.
3. **Add the route** under the existing Bearer auth used by `/faculty/*`.
4. **Scope it to the caller.** It must read the student from the token, never
   from a query parameter, or any student could enumerate another's sections.
5. **Include the `email` claim in student tokens too.** `/faculty/sections`
   returned 403 to every faculty member because the exchanged token lacked
   `email`. Please make sure the student path does not repeat it.
6. **Return `200` with an empty array** for a student in no sections — not
   `403`. We must distinguish "not enrolled" from "not allowed to ask".
7. **Add it to `sethu_openapi.json`.**

## How we will verify it

- `200` and the correct section for an enrolled student.
- `200 []` for a student with no enrolment.
- `401` with a missing or invalid token.
- A student token cannot retrieve another student's sections by any parameter.
- Labels match `GET /faculty/sections` byte for byte.

## Effort split

| Work | Owner |
| --- | --- |
| Decide path, shape, student role semantics | Backend |
| Implement route, scope to token | Backend |
| Update OpenAPI document | Backend |
| Section check inside each course agent | Whoever builds the course agents |
| Dispatcher changes | None — it publishes and notifies; it does not gate access |

## What we are not asking for

- No write endpoints.
- No student names, phone numbers or email addresses.
- No lookup of *other* students' sections.
- No change to the faculty endpoints.

## Known limitation of this approach

This gates what an agent **does**, not whether it **opens**. A student outside
the section can still launch the agent and receive a refusal. Making the agent
invisible would need per-agent IAM in Gemini Enterprise, which does not
currently exist. For course agents, opening to a polite refusal is acceptable —
the content sits behind the check.
