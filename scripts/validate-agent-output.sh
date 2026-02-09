#!/usr/bin/env bash
# Validates agent output after SubagentStop
# Called by coordinator SubagentStop hooks
# Checks: file ownership violations, test status
# Usage: validate-agent-output.sh [agent-name]

AGENT_NAME="${1:-unknown}"
PROJECT_DIR="${PROJECT_DIR:-.}"
LOG="$PROJECT_DIR/reports/.pipeline-log"

echo "[$AGENT_NAME] $(date +%H:%M:%S) validating output" >> "$LOG"

# Check 1: Were any protected paths modified?
PROTECTED_CHANGES=$(git diff --name-only 2>/dev/null | grep -E "^(examples/|\.env$)" || true)
if [ -n "$PROTECTED_CHANGES" ]; then
  echo "[VALIDATION FAIL] $AGENT_NAME modified protected paths: $PROTECTED_CHANGES" >> "$LOG"
  echo "VALIDATION FAIL: Protected paths modified: $PROTECTED_CHANGES" >&2
fi

# Check 2: Do tests still pass? (quick check - exit code only)
if command -v pytest &>/dev/null; then
  if ! pytest tests/ -x -q --no-header 2>/dev/null; then
    echo "[VALIDATION WARN] $AGENT_NAME: tests failing after changes" >> "$LOG"
    echo "VALIDATION WARN: Tests failing after agent changes" >&2
  fi
fi

# Check 3: Does lint pass?
if command -v ruff &>/dev/null; then
  LINT_ERRORS=$(ruff check src/ tests/ 2>/dev/null | head -5 || true)
  if [ -n "$LINT_ERRORS" ]; then
    echo "[VALIDATION INFO] $AGENT_NAME: lint issues: $LINT_ERRORS" >> "$LOG"
  fi
fi

echo "[$AGENT_NAME] $(date +%H:%M:%S) validation complete" >> "$LOG"
exit 0
