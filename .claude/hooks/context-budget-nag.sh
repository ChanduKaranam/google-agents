#!/usr/bin/env bash
# PostToolUse hook: warn at 50/80 tool calls to encourage /compact.
set -e
SESSION_ID="${CLAUDE_SESSION_ID:-pid-$PPID}"
COUNTER_FILE="/tmp/claude-nag-${SESSION_ID}.count"
NAGGED_50="/tmp/claude-nag-${SESSION_ID}.50"
NAGGED_80="/tmp/claude-nag-${SESSION_ID}.80"
COUNT=$(( $(cat "$COUNTER_FILE" 2>/dev/null || echo 0) + 1 ))
echo "$COUNT" > "$COUNTER_FILE"
if [[ "$COUNT" -ge 80 && ! -f "$NAGGED_80" ]]; then
  touch "$NAGGED_80"
  printf '{"feedback":"Tool call #%d — context likely heavy. Run /compact NOW or expect quota wall."}\n' "$COUNT"
elif [[ "$COUNT" -ge 50 && ! -f "$NAGGED_50" ]]; then
  touch "$NAGGED_50"
  printf '{"feedback":"Tool call #%d — consider /compact before next subagent dispatch or large read."}\n' "$COUNT"
fi
exit 0
