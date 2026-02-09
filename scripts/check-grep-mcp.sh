#!/usr/bin/env bash
# Gate hook: Warns if grep_query (grep-mcp) was not called before Write/Edit on source files
# Checks reports/.pipeline-log for a grep_query or grep-mcp entry within the last 20 tool calls
# Used as PreToolUse hook on builder, reviewer, and skill-builder agents
# Exit 0 = allow (always, since hooks can't block yet)

PIPELINE_LOG="${PROJECT_DIR}/reports/.pipeline-log"
FILE_PATH="$TOOL_INPUT_FILE_PATH"

# Skip for non-source files (markdown, config, etc.)
case "$FILE_PATH" in
  *.md|*.json|*.yaml|*.yml|*.toml|*.txt|*.cfg|*.ini|*.env*) exit 0 ;;
esac

# Skip for agent definitions and non-source directories
case "$FILE_PATH" in
  */.claude/*) exit 0 ;;
  */reports/*) exit 0 ;;
  */team-registry/*) exit 0 ;;
  */scripts/*) exit 0 ;;
esac

# If no pipeline log exists yet, allow (first edit of session)
if [ ! -f "$PIPELINE_LOG" ]; then
  exit 0
fi

# Check if grep_query or grep-mcp was called in the last 20 lines of the log
if tail -20 "$PIPELINE_LOG" | grep -qE "grep_query|grep-mcp"; then
  exit 0
fi

# Not found - warn but allow (hooks can't actually block yet)
WARNING="[GATE] WARNING: grep_query (grep-mcp) not called recently. Search GitHub for existing patterns before writing source code."
echo "$WARNING" >&2
echo "$(date '+%Y-%m-%d %H:%M:%S') $WARNING" >> "$PIPELINE_LOG"
exit 0
