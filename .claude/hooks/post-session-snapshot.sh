#!/bin/bash
# Stop hook: saves git state to docs/sessions/ for handoff continuity.
BRANCH=$(git branch --show-current 2>/dev/null || echo "unknown")
TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
SNAPSHOT_DIR="docs/sessions"
SNAPSHOT_FILE="${SNAPSHOT_DIR}/${TIMESTAMP}_${BRANCH//\//-}.md"
mkdir -p "$SNAPSHOT_DIR"
cat > "$SNAPSHOT_FILE" << EOF
# Session Snapshot
**Timestamp:** $(date -u +"%Y-%m-%dT%H:%M:%SZ")
**Branch:** $BRANCH

## Last 10 Commits
\`\`\`
$(git log --oneline -10 2>/dev/null || echo "No commits yet")
\`\`\`

## Modified Files (unstaged + staged)
\`\`\`
$(git status --short 2>/dev/null || echo "Clean")
\`\`\`

## Changed Files Since Last Commit
\`\`\`
$(git diff --name-only HEAD 2>/dev/null || echo "None")
\`\`\`

## Session Changes Log (today)
\`\`\`
$(tail -20 docs/sessions/changes.log 2>/dev/null || echo "No changes logged")
\`\`\`
EOF
echo "Session snapshot saved: $SNAPSHOT_FILE"
