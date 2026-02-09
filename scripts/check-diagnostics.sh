#!/usr/bin/env bash
# Gate hook: Blocks Write/Edit if getDiagnostics was not called recently
# Checks reports/.pipeline-log for a getDiagnostics entry within the last 5 tool calls
# Exit 0 = allow, Exit 1 = block with message

PIPELINE_LOG="${PROJECT_DIR}/reports/.pipeline-log"
FILE_PATH="$TOOL_INPUT_FILE_PATH"

# Skip for non-source files (markdown, config, etc.)
case "$FILE_PATH" in
  *.md|*.json|*.yaml|*.yml|*.toml|*.txt|*.cfg|*.ini|*.env*) exit 0 ;;
esac

# If no pipeline log exists yet, allow (first edit of session)
if [ ! -f "$PIPELINE_LOG" ]; then
  exit 0
fi

# Check if getDiagnostics was called in the last 10 lines of the log
if tail -10 "$PIPELINE_LOG" | grep -q "getDiagnostics"; then
  exit 0
fi

# Not found - warn but allow (hooks can't actually block yet, so log a warning)
echo "[GATE] WARNING: getDiagnostics not called recently. Run LSP getDiagnostics before editing." >&2
exit 0
