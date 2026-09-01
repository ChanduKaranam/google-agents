#!/usr/bin/env bash
# Stop hook: append a Token Ledger row to the active ticket file.
# Reads the Stop event JSON from stdin.
set -e
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
STATE_FILE="$REPO_ROOT/docs/STATE.md"
LEDGER_FILE="$REPO_ROOT/docs/sessions/_token-ledger.jsonl"
[[ -f "$STATE_FILE" ]] || exit 0
TICKET_ID=$(grep -E '^ticket:' "$STATE_FILE" | head -1 | sed -E 's/^ticket:\s*//' | tr -d '"' | xargs)
[[ -z "$TICKET_ID" || "$TICKET_ID" == "none" ]] && exit 0
TICKET_FILE=$(find "$REPO_ROOT/docs/tickets" -maxdepth 1 -name "${TICKET_ID}*.md" 2>/dev/null | head -1)
if [[ -z "$TICKET_FILE" ]]; then
  FEATURE_SLUG=$(grep -E '^feature:' "$STATE_FILE" | head -1 | sed -E 's/^feature:\s*//' | tr -d '"' | xargs)
  TICKET_FILE="$REPO_ROOT/docs/tickets/${FEATURE_SLUG}.md"
fi
[[ -f "$TICKET_FILE" ]] || exit 0
EVENT=$(cat)
[[ -z "$EVENT" ]] && exit 0
SESSION_ID=$(echo "$EVENT" | jq -r '.session_id // empty')
TRANSCRIPT=$(echo "$EVENT" | jq -r '.transcript_path // empty')
if [[ -z "$SESSION_ID" || -z "$TRANSCRIPT" || ! -f "$TRANSCRIPT" ]]; then
  exit 0
fi
TOTALS=$(jq -s '[.[] | select(.type == "assistant") | .message.usage] as $u | {input:([$u[].input_tokens // 0] | add), output:([$u[].output_tokens // 0] | add), cache_read:([$u[].cache_read_input_tokens // 0] | add)}' "$TRANSCRIPT")
INPUT=$(echo "$TOTALS" | jq -r '.input // 0')
OUTPUT=$(echo "$TOTALS" | jq -r '.output // 0')
CACHE_READ=$(echo "$TOTALS" | jq -r '.cache_read // 0')
DEV_NAME=$(git config user.name 2>/dev/null || echo "unknown")
STARTED_AT=$(date -u +%Y-%m-%dT%H:%MZ)
LEDGER_ROW="| ${SESSION_ID:0:8} | $DEV_NAME | $STARTED_AT | — | $INPUT | $OUTPUT | $CACHE_READ | — |"
echo "$LEDGER_ROW" >> "$TICKET_FILE"
mkdir -p "$(dirname "$LEDGER_FILE")"
jq -nc --arg session_id "$SESSION_ID" --arg ticket "$TICKET_ID" --arg dev "$DEV_NAME" --arg started_at "$STARTED_AT" --argjson input "$INPUT" --argjson output "$OUTPUT" --argjson cache_read "$CACHE_READ" '{session_id:$session_id,ticket:$ticket,dev:$dev,started_at:$started_at,input_tokens:$input,output_tokens:$output,cache_read_tokens:$cache_read}' >> "$LEDGER_FILE"
exit 0
