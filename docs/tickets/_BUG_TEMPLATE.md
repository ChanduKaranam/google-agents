---
bug: BUG-XXX
feature: { feature-slug }          # the feature this broke — link its ticket below
branch: fix/{bug-slug}
status: REPORTED   # REPORTED | DIAGNOSED | IN_PROGRESS | READY_FOR_REVIEW | COMPLETED
severity: MEDIUM   # LOW | MEDIUM | HIGH | CRITICAL
reported_by: ""
reported_at: ""
reproduced: false
root_cause_confirmed_by: ""
root_cause_confirmed_at: ""
fixed_by: ""
fixed_at: ""
---

# BUG-XXX — {one line, the symptom, not the guess}

**Broke:** TICKET-XXX — {feature name}
**Depends on:** none

---

## Symptom

What the user sees. Written from their side of the screen, not the system's.

- **Expected:** {what should happen}
- **Actual:** {what happens instead}
- **Error text:** {verbatim, or "none — it fails silently"}
- **Affects:** {who / how many / which surface}

---

## Reproduction

> _Filled by `/fix-bug`. If it can't be reproduced, it can't be fixed — the command stops here and says so._

1. {step}
2. {step}
3. {step}

**Reproduces:** always / intermittently ({n} in {m}) / only under {condition}
**First broken in:** {commit or "unknown"} — `git log -S` the symptom, don't guess
**Last known good:** {commit or version}

---

## Root Cause

> _Filled by `/fix-bug` via the `superpowers:systematic-debugging` skill. **This section gets confirmed by a human before any code is written.**_

**Where:** `{path/to/file.ts}:{line}` — `{functionName}`

**Why it produces this symptom:** {the causal chain, traced backward from the symptom to the source. Not "probably" — traced.}

**Evidence:** {what you observed that proves it — the instrumentation output, the failing assertion, the diff that introduced it}

---

## Blast Radius

> _Filled by `/fix-bug` before the fix. The ticket named one broken path; this is every path that routes through the same root cause._

**Callers of `{functionName}`:**

| Caller | Also broken? | Covered by this fix? |
|--------|--------------|----------------------|
| `{path}:{line}` | yes / no | yes / no — {why} |

**Patching only the reported path would leave broken:** {list, or "nothing — this is the only caller"}

---

## The Fix

> _One change, at the root cause. A guard in the shared function beats a guard in every caller — it is both the smaller diff and the one that fixes the siblings._

**Approach:** {prose, one paragraph}
**Files:** `{path}`
**Rejected alternatives:** {what you didn't do, and why — especially any symptom-level patch}

---

## Regression Test

> _Written **before** the fix. It must fail with the reported symptom, for the reported reason._

**Path:** `{path/to/test}`
**Asserts:** {the behavior that was broken}

- [ ] Written, and observed FAILING against the unfixed code
- [ ] Observed PASSING against the fix
- [ ] Red-green proven: fix reverted, test went red again, fix restored

The third box is not ceremony. A regression test that passes against the unfixed code tests nothing.

---

## Verification Log

Filled by `/fix-bug` and `/complete-feature` via `superpowers:verification-before-completion` — do not edit manually. Every row is a command that was actually run, with its actual output.

| Check | Command | Result | Date |
|-------|---------|--------|------|
| —     | —       | —      | —    |

---

## Change Log

| Date | Change | Commit |
|------|--------|--------|
| —    | —      | —      |

---

## Delays & Blockers

**Active blockers:** none

> Three failed fixes means stop. Record the failed hypotheses here and bring it back to the user — the design is wrong, not the code, and fix number four will not find that out.
