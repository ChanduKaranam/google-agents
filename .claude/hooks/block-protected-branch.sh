#!/usr/bin/env bash
# PreToolUse hook: block edits to protected branches.
# Protected branches: main (pipe-separated).
# Customize by updating the case pattern below after /setup generates this file.
set -e
BRANCH=$(git branch --show-current 2>/dev/null)
case "$BRANCH" in
  main)
    printf '{"block": true, "message": "Direct edits to %s are blocked. Branch off pre-dev: git switch -c feature/your-feature pre-dev"}\n' "$BRANCH" >&2
    exit 2
    ;;
esac
exit 0
