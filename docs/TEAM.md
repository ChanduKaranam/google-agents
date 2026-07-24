---
leads:
  - name: Purna Chandra Rao
    github: Purna-Chandra-Rao-Karanam
    email: purna@tilicho.in
devs: []
---

# Job Helper Agent Team Roster

> **Source of truth** for who can approve tickets (`leads`) and who can pick them up (`leads + devs`).
> Loaded by `/new-feature`, `/groom-ticket`, `/review-ticket`, and `/claim-ticket`.

## Roles

- **Lead** — runs `/review-ticket` to approve groomed tickets. Tickets they create via `/new-feature` are auto-approved.
- **Dev** — runs `/new-feature`, `/groom-ticket`, `/claim-ticket`. Their `/new-feature` output starts as `TODO` and must travel through `/groom-ticket` → lead's `/review-ticket` → `APPROVED` before they can `/claim-ticket`.

## How identity is decided

Claude reads `git config user.email` and looks it up in this file. If the email isn't present in either list, all four ticket commands refuse to run.

## Updating

Edit the YAML frontmatter above, commit on a `feature/...` branch, open a PR to `pre-dev`. Effective immediately on merge.

## Why a roster file

The approval workflow runs inside Claude Code on a dev's machine. Claude decides locally, before any push, whether the runner is a lead. A repo-checked-in roster is the most portable answer: auditable in git, no API call required, survives machine swaps.
