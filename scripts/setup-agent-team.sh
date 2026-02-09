#!/usr/bin/env bash
set -euo pipefail

###############################################################################
# Agent Team System Setup Script
# Sets up a 3-agent (lite) or 19-agent (full) persistent agent team system
# for any project using Claude Code.
#
# Usage: bash scripts/setup-agent-team.sh
#
# This script is self-contained and does NOT depend on any external templates.
# All agent, skill, and team definitions are embedded as heredocs.
###############################################################################

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Globals (populated by detect/prompt)
PROJECT_DIR="$(pwd)"
PROJECT_NAME=""
PROJECT_DESC=""
LANGUAGE=""
SRC_DIR=""
TESTS_DIR=""
FORMATTER=""
FORMATTER_CMD=""
LINTER=""
LINTER_CMD=""
TYPE_CHECKER=""
TYPE_CHECKER_CMD=""
TEST_RUNNER=""
TEST_CMD=""
PACKAGE_MANAGER=""
RUN_CMD=""
INSTALL_CMD=""
PROTECTED_PATHS=".env"
PROFILE=""  # lite or full

###############################################################################
# Banner
###############################################################################
print_banner() {
  echo ""
  echo -e "${BLUE}${BOLD}+==========================================+${NC}"
  echo -e "${BLUE}${BOLD}|     Agent Team System Setup              |${NC}"
  echo -e "${BLUE}${BOLD}|     3-agent Lite or 19-agent Full        |${NC}"
  echo -e "${BLUE}${BOLD}+==========================================+${NC}"
  echo ""
  echo -e "  Working directory: ${CYAN}${PROJECT_DIR}${NC}"
  echo ""
}

###############################################################################
# Utility: prompt with default
###############################################################################
prompt_with_default() {
  local prompt_text="$1"
  local default_val="$2"
  local var_name="$3"
  local input

  if [ -n "$default_val" ]; then
    read -r -p "$(echo -e "${BOLD}${prompt_text}${NC} [${GREEN}${default_val}${NC}]: ")" input
    eval "$var_name=\"${input:-$default_val}\""
  else
    read -r -p "$(echo -e "${BOLD}${prompt_text}${NC}: ")" input
    eval "$var_name=\"$input\""
  fi
}

###############################################################################
# Step 1: Auto-detect stack
###############################################################################
detect_stack() {
  echo -e "${YELLOW}Detecting project stack...${NC}"
  echo ""

  # Detect language
  if [ -f "pyproject.toml" ] || [ -f "setup.py" ] || [ -f "setup.cfg" ] || [ -f "requirements.txt" ]; then
    LANGUAGE="python"
  elif [ -f "package.json" ]; then
    LANGUAGE="javascript"
    # Check for TypeScript
    if [ -f "tsconfig.json" ]; then
      LANGUAGE="typescript"
    fi
  elif [ -f "Cargo.toml" ]; then
    LANGUAGE="rust"
  elif [ -f "go.mod" ]; then
    LANGUAGE="go"
  elif [ -f "pom.xml" ]; then
    LANGUAGE="java"
  elif [ -f "build.gradle" ] || [ -f "build.gradle.kts" ]; then
    LANGUAGE="java"
  else
    LANGUAGE=""
  fi

  # Detect source directory
  if [ -d "src" ]; then
    SRC_DIR="src/"
  elif [ -d "lib" ]; then
    SRC_DIR="lib/"
  elif [ -d "app" ]; then
    SRC_DIR="app/"
  else
    SRC_DIR="src/"
  fi

  # Detect test directory
  if [ -d "tests" ]; then
    TESTS_DIR="tests/"
  elif [ -d "test" ]; then
    TESTS_DIR="test/"
  elif [ -d "__tests__" ]; then
    TESTS_DIR="__tests__/"
  elif [ -d "spec" ]; then
    TESTS_DIR="spec/"
  else
    TESTS_DIR="tests/"
  fi

  # Detect package manager
  case "$LANGUAGE" in
    python)
      if command -v uv &>/dev/null && [ -f "pyproject.toml" ]; then
        PACKAGE_MANAGER="uv"
        INSTALL_CMD="uv pip install -e ."
      elif command -v pip &>/dev/null; then
        PACKAGE_MANAGER="pip"
        INSTALL_CMD="pip install -e ."
      fi
      ;;
    javascript|typescript)
      if [ -f "pnpm-lock.yaml" ]; then
        PACKAGE_MANAGER="pnpm"
        INSTALL_CMD="pnpm install"
      elif [ -f "yarn.lock" ]; then
        PACKAGE_MANAGER="yarn"
        INSTALL_CMD="yarn install"
      elif [ -f "bun.lockb" ]; then
        PACKAGE_MANAGER="bun"
        INSTALL_CMD="bun install"
      else
        PACKAGE_MANAGER="npm"
        INSTALL_CMD="npm install"
      fi
      ;;
    rust)
      PACKAGE_MANAGER="cargo"
      INSTALL_CMD="cargo build"
      ;;
    go)
      PACKAGE_MANAGER="go"
      INSTALL_CMD="go mod download"
      ;;
    java)
      if [ -f "pom.xml" ]; then
        PACKAGE_MANAGER="maven"
        INSTALL_CMD="mvn install"
      else
        PACKAGE_MANAGER="gradle"
        INSTALL_CMD="gradle build"
      fi
      ;;
  esac

  # Detect formatter
  case "$LANGUAGE" in
    python)
      if grep -q "ruff" pyproject.toml 2>/dev/null || [ -f "ruff.toml" ] || [ -f ".ruff.toml" ]; then
        FORMATTER="ruff"
        FORMATTER_CMD="ruff format ${SRC_DIR} ${TESTS_DIR}"
      elif [ -f ".style.yapf" ] || grep -q "yapf" pyproject.toml 2>/dev/null; then
        FORMATTER="yapf"
        FORMATTER_CMD="yapf -i -r ${SRC_DIR}"
      elif command -v black &>/dev/null || grep -q "black" pyproject.toml 2>/dev/null; then
        FORMATTER="black"
        FORMATTER_CMD="black ${SRC_DIR} ${TESTS_DIR}"
      fi
      ;;
    javascript|typescript)
      if [ -f ".prettierrc" ] || [ -f ".prettierrc.json" ] || [ -f "prettier.config.js" ] || [ -f "prettier.config.mjs" ]; then
        FORMATTER="prettier"
        FORMATTER_CMD="npx prettier --write ."
      elif [ -f "biome.json" ] || [ -f "biome.jsonc" ]; then
        FORMATTER="biome"
        FORMATTER_CMD="npx biome format --write ."
      fi
      ;;
    rust)
      FORMATTER="rustfmt"
      FORMATTER_CMD="cargo fmt"
      ;;
    go)
      FORMATTER="gofmt"
      FORMATTER_CMD="gofmt -w ."
      ;;
  esac

  # Detect linter
  case "$LANGUAGE" in
    python)
      if grep -q "ruff" pyproject.toml 2>/dev/null || [ -f "ruff.toml" ] || [ -f ".ruff.toml" ]; then
        LINTER="ruff"
        LINTER_CMD="ruff check ${SRC_DIR} ${TESTS_DIR}"
      elif [ -f ".flake8" ] || grep -q "flake8" pyproject.toml 2>/dev/null; then
        LINTER="flake8"
        LINTER_CMD="flake8 ${SRC_DIR} ${TESTS_DIR}"
      elif [ -f ".pylintrc" ] || grep -q "pylint" pyproject.toml 2>/dev/null; then
        LINTER="pylint"
        LINTER_CMD="pylint ${SRC_DIR}"
      fi
      ;;
    javascript|typescript)
      if [ -f ".eslintrc" ] || [ -f ".eslintrc.json" ] || [ -f ".eslintrc.js" ] || [ -f "eslint.config.js" ] || [ -f "eslint.config.mjs" ]; then
        LINTER="eslint"
        LINTER_CMD="npx eslint ."
      elif [ -f "biome.json" ] || [ -f "biome.jsonc" ]; then
        LINTER="biome"
        LINTER_CMD="npx biome lint ."
      fi
      ;;
    rust)
      LINTER="clippy"
      LINTER_CMD="cargo clippy"
      ;;
    go)
      LINTER="golangci-lint"
      LINTER_CMD="golangci-lint run"
      ;;
  esac

  # Detect type checker
  case "$LANGUAGE" in
    python)
      if grep -q "mypy" pyproject.toml 2>/dev/null || [ -f "mypy.ini" ] || [ -f ".mypy.ini" ]; then
        TYPE_CHECKER="mypy"
        TYPE_CHECKER_CMD="mypy ${SRC_DIR}"
      elif grep -q "pyright" pyproject.toml 2>/dev/null || [ -f "pyrightconfig.json" ]; then
        TYPE_CHECKER="pyright"
        TYPE_CHECKER_CMD="pyright ${SRC_DIR}"
      fi
      ;;
    typescript)
      TYPE_CHECKER="tsc"
      TYPE_CHECKER_CMD="npx tsc --noEmit"
      ;;
    rust)
      TYPE_CHECKER="rustc"
      TYPE_CHECKER_CMD="cargo check"
      ;;
  esac

  # Detect test runner
  case "$LANGUAGE" in
    python)
      TEST_RUNNER="pytest"
      TEST_CMD="pytest ${TESTS_DIR} -v"
      ;;
    javascript|typescript)
      if grep -q "vitest" package.json 2>/dev/null; then
        TEST_RUNNER="vitest"
        TEST_CMD="npx vitest run"
      elif grep -q "jest" package.json 2>/dev/null; then
        TEST_RUNNER="jest"
        TEST_CMD="npx jest"
      elif grep -q "mocha" package.json 2>/dev/null; then
        TEST_RUNNER="mocha"
        TEST_CMD="npx mocha"
      fi
      ;;
    rust)
      TEST_RUNNER="cargo"
      TEST_CMD="cargo test"
      ;;
    go)
      TEST_RUNNER="go"
      TEST_CMD="go test ./..."
      ;;
    java)
      if [ -f "pom.xml" ]; then
        TEST_RUNNER="maven"
        TEST_CMD="mvn test"
      else
        TEST_RUNNER="gradle"
        TEST_CMD="gradle test"
      fi
      ;;
  esac

  # Detect run command
  case "$LANGUAGE" in
    python)
      if [ -f "manage.py" ]; then
        RUN_CMD="python manage.py runserver"
      elif [ -d "src" ] && [ -f "src/cli.py" ]; then
        RUN_CMD="python -m src.cli"
      elif [ -f "main.py" ]; then
        RUN_CMD="python main.py"
      elif [ -f "app.py" ]; then
        RUN_CMD="python app.py"
      fi
      ;;
    javascript|typescript)
      if grep -q '"dev"' package.json 2>/dev/null; then
        RUN_CMD="${PACKAGE_MANAGER} run dev"
      elif grep -q '"start"' package.json 2>/dev/null; then
        RUN_CMD="${PACKAGE_MANAGER} start"
      fi
      ;;
    rust)
      RUN_CMD="cargo run"
      ;;
    go)
      RUN_CMD="go run ."
      ;;
  esac

  # Print detected values
  echo -e "  Language:        ${GREEN}${LANGUAGE:-not detected}${NC}"
  echo -e "  Source dir:      ${GREEN}${SRC_DIR:-not detected}${NC}"
  echo -e "  Tests dir:      ${GREEN}${TESTS_DIR:-not detected}${NC}"
  echo -e "  Package manager: ${GREEN}${PACKAGE_MANAGER:-not detected}${NC}"
  echo -e "  Formatter:       ${GREEN}${FORMATTER:-not detected}${NC}"
  echo -e "  Linter:          ${GREEN}${LINTER:-not detected}${NC}"
  echo -e "  Type checker:    ${GREEN}${TYPE_CHECKER:-not detected}${NC}"
  echo -e "  Test runner:     ${GREEN}${TEST_RUNNER:-not detected}${NC}"
  echo ""
}

###############################################################################
# Step 2: Prompt for configuration
###############################################################################
prompt_config() {
  echo -e "${YELLOW}Configure your agent team:${NC}"
  echo ""

  # Project name
  local default_name
  default_name="$(basename "$PROJECT_DIR")"
  prompt_with_default "Project name" "$default_name" PROJECT_NAME

  # Project description
  prompt_with_default "Project description" "" PROJECT_DESC

  # Language
  prompt_with_default "Language" "$LANGUAGE" LANGUAGE

  # Source directory
  prompt_with_default "Source directory" "$SRC_DIR" SRC_DIR

  # Tests directory
  prompt_with_default "Tests directory" "$TESTS_DIR" TESTS_DIR

  # Formatter
  prompt_with_default "Formatter" "${FORMATTER:-none}" FORMATTER
  if [ "$FORMATTER" != "none" ] && [ -n "$FORMATTER" ]; then
    prompt_with_default "Format command" "$FORMATTER_CMD" FORMATTER_CMD
  fi

  # Linter
  prompt_with_default "Linter" "${LINTER:-none}" LINTER
  if [ "$LINTER" != "none" ] && [ -n "$LINTER" ]; then
    prompt_with_default "Lint command" "$LINTER_CMD" LINTER_CMD
  fi

  # Type checker
  prompt_with_default "Type checker" "${TYPE_CHECKER:-none}" TYPE_CHECKER
  if [ "$TYPE_CHECKER" != "none" ] && [ -n "$TYPE_CHECKER" ]; then
    prompt_with_default "Type check command" "$TYPE_CHECKER_CMD" TYPE_CHECKER_CMD
  fi

  # Test runner
  prompt_with_default "Test runner" "${TEST_RUNNER:-none}" TEST_RUNNER
  if [ "$TEST_RUNNER" != "none" ] && [ -n "$TEST_RUNNER" ]; then
    prompt_with_default "Test command" "$TEST_CMD" TEST_CMD
  fi

  # Package manager
  prompt_with_default "Package manager" "${PACKAGE_MANAGER:-none}" PACKAGE_MANAGER

  # Run command
  prompt_with_default "Run command" "${RUN_CMD:-none}" RUN_CMD

  # Install command
  prompt_with_default "Install command" "${INSTALL_CMD:-none}" INSTALL_CMD

  # Protected paths
  prompt_with_default "Protected paths (comma-separated)" "$PROTECTED_PATHS" PROTECTED_PATHS

  # Profile
  echo ""
  echo -e "${BOLD}Profile:${NC}"
  echo -e "  ${CYAN}lite${NC}  - 3 agents (orchestrator, builder, tester)"
  echo -e "  ${CYAN}full${NC}  - 19 agents (6 core + 6 coordinators + 7 specialists)"
  echo ""
  prompt_with_default "Profile (lite/full)" "lite" PROFILE

  echo ""

  # Build the format hook command based on language
  FORMAT_HOOK_CMD=""
  case "$FORMATTER" in
    ruff)
      FORMAT_HOOK_CMD="${FORMATTER} format \"\$TOOL_INPUT_FILE_PATH\" 2>/dev/null || true"
      ;;
    black)
      FORMAT_HOOK_CMD="black \"\$TOOL_INPUT_FILE_PATH\" 2>/dev/null || true"
      ;;
    prettier)
      FORMAT_HOOK_CMD="npx prettier --write \"\$TOOL_INPUT_FILE_PATH\" 2>/dev/null || true"
      ;;
    biome)
      FORMAT_HOOK_CMD="npx biome format --write \"\$TOOL_INPUT_FILE_PATH\" 2>/dev/null || true"
      ;;
    rustfmt)
      FORMAT_HOOK_CMD="rustfmt \"\$TOOL_INPUT_FILE_PATH\" 2>/dev/null || true"
      ;;
    gofmt)
      FORMAT_HOOK_CMD="gofmt -w \"\$TOOL_INPUT_FILE_PATH\" 2>/dev/null || true"
      ;;
    *)
      FORMAT_HOOK_CMD="echo '' > /dev/null"
      ;;
  esac

  # Build non-source file extensions for hook skip
  case "$LANGUAGE" in
    python) SKIP_EXTENSIONS="*.md|*.json|*.yaml|*.yml|*.toml|*.txt|*.cfg|*.ini|*.env*" ;;
    javascript|typescript) SKIP_EXTENSIONS="*.md|*.json|*.yaml|*.yml|*.txt|*.env*" ;;
    rust) SKIP_EXTENSIONS="*.md|*.json|*.yaml|*.yml|*.toml|*.txt|*.env*" ;;
    go) SKIP_EXTENSIONS="*.md|*.json|*.yaml|*.yml|*.txt|*.env*" ;;
    *) SKIP_EXTENSIONS="*.md|*.json|*.yaml|*.yml|*.toml|*.txt|*.cfg|*.ini|*.env*" ;;
  esac
}

###############################################################################
# Utility: safe mkdir + create file (idempotent)
###############################################################################
ensure_dir() {
  mkdir -p "$1"
}

write_file_if_new() {
  local filepath="$1"
  local content="$2"

  if [ -f "$filepath" ]; then
    echo -e "  ${YELLOW}EXISTS${NC}: $filepath (skipping)"
    return 0
  fi

  ensure_dir "$(dirname "$filepath")"
  echo "$content" > "$filepath"
  echo -e "  ${GREEN}CREATE${NC}: $filepath"
}

# Variant that overwrites - for settings.json which may need updating
write_file_force() {
  local filepath="$1"
  local content="$2"

  ensure_dir "$(dirname "$filepath")"
  echo "$content" > "$filepath"
  echo -e "  ${GREEN}WRITE${NC}: $filepath"
}

###############################################################################
# Generate: .claude/settings.json
###############################################################################
generate_settings_json() {
  echo -e "${YELLOW}Creating .claude/settings.json...${NC}"

  local filepath=".claude/settings.json"

  if [ -f "$filepath" ]; then
    echo -e "  ${YELLOW}EXISTS${NC}: $filepath"
    read -r -p "  Overwrite? (y/N): " overwrite
    if [ "$overwrite" != "y" ] && [ "$overwrite" != "Y" ]; then
      echo -e "  ${YELLOW}SKIP${NC}: $filepath"
      return
    fi
  fi

  ensure_dir ".claude"

  cat > "$filepath" << 'SETTINGS_EOF'
{
  "customInstructions": "MANDATORY: Grep local codebase FIRST. Then use grep-mcp (grep_query tool) to search GitHub for battle-tested patterns. NEVER write substantial code without grepping both local and GitHub. Keep LEARNINGS.md entries to 1 line, max 120 chars.",
  "mcpServers": {
    "grep-mcp": {
      "command": "uvx",
      "args": ["grep-mcp"]
    }
  }
}
SETTINGS_EOF

  echo -e "  ${GREEN}WRITE${NC}: $filepath"
}

###############################################################################
# Generate: LEARNINGS.md
###############################################################################
generate_learnings() {
  echo -e "${YELLOW}Creating LEARNINGS.md...${NC}"

  write_file_if_new "LEARNINGS.md" "# Agent Team Learnings

**FORMAT: 1 line per item. No paragraphs. \`CATEGORY: what -> fix/reuse\`**

## Mistakes (do NOT repeat)


## Patterns That Work


## Gotchas


## Architecture


## Useful Grep Patterns


## Run Log
"
}

###############################################################################
# Generate: reports/ directory
###############################################################################
generate_reports_dir() {
  echo -e "${YELLOW}Creating reports/ directory...${NC}"
  ensure_dir "reports"
  ensure_dir "reports/prd"
  # Create .gitkeep to preserve empty dirs
  touch "reports/.gitkeep"
  touch "reports/prd/.gitkeep"
  echo -e "  ${GREEN}CREATE${NC}: reports/"
}

###############################################################################
# Generate: Coding Conventions Skill
###############################################################################
generate_coding_conventions_skill() {
  echo -e "${YELLOW}Creating coding-conventions skill...${NC}"

  local filepath=".claude/skills/coding-conventions/SKILL.md"

  if [ -f "$filepath" ]; then
    echo -e "  ${YELLOW}EXISTS${NC}: $filepath (skipping)"
    return
  fi

  ensure_dir ".claude/skills/coding-conventions"

  cat > "$filepath" << SKILL_EOF
---
name: coding-conventions
description: Enforces existing codebase patterns for ${PROJECT_NAME}. Covers formatting, naming, imports, error handling, type annotations, and module boundaries.
version: 1.0.0
author: Agent Team System
---

# Coding Conventions

Codified patterns from the existing codebase. All agents MUST follow these conventions. Do NOT impose new patterns.

## Formatting

- **Tool**: ${FORMATTER:-none}
- **Command**: \`${FORMATTER_CMD:-N/A}\`

## Naming Conventions

### Files & Modules
- Follow existing naming conventions in the project
- Check existing files before creating new ones with different naming patterns

### Functions & Variables
- Follow the language's standard naming conventions
- Match existing code style exactly

## Import Ordering

Follow existing import ordering in the project. Verify by reading existing files before writing new code.

## Error Handling

### Pattern: Match existing error handling in the codebase
\`\`\`
1. Grep the codebase for existing error handling patterns
2. Read the existing code and follow the same patterns
3. Use structured logging format
\`\`\`

### Rules:
- Always catch specific exceptions first, then general
- Return error strings from tool functions (don't raise) where applicable
- Use structured logging format

## Type Annotations

Required everywhere. Follow existing patterns in the codebase.

## Documentation Style

Follow the project's existing documentation style. When in doubt, use the language's standard doc format.

## Grep Local Codebase (MANDATORY - DO THIS FIRST)

**Before writing ANY code, grep THIS project to study existing patterns.**
This is the FIRST step. Always. No exceptions.

### Required Searches Before Coding
\`\`\`
Grep for import patterns in ${SRC_DIR}
Grep for class/function definitions in ${SRC_DIR}
Grep for error handling patterns in ${SRC_DIR}
Read the file you're about to modify
\`\`\`

### What You're Looking For
- How existing code handles the same problem (don't reinvent)
- Import style, naming conventions, error return format
- Test patterns for the module you're changing
- Whether the function/class already exists somewhere

### Anti-Patterns
- Writing code without reading the target file first
- Assuming import style instead of grepping for it
- Creating a new utility that already exists in ${SRC_DIR}

## Grep MCP (MANDATORY - NON-NEGOTIABLE)

**AFTER grepping local, use \`grep_query\` to search millions of GitHub repos for battle-tested code.**
MCP server: \`grep-mcp\` (configured in \`.claude/settings.json\`).
Applies to ALL coding agents.

### How to Search
\`\`\`
grep_query: query="{feature} {framework}", language="${LANGUAGE}"
grep_query: query="{pattern} implementation", language="${LANGUAGE}"
grep_query: query="{error message}", language="${LANGUAGE}"
\`\`\`

### Workflow
1. \`grep_query\` with language="${LANGUAGE}" to find battle-tested implementations
2. Read the matched code snippets (includes file paths + line numbers)
3. Adapt to this project's conventions
4. If your approach differs from battle-tested code, justify why

### Skip ONLY When
- Typo/string fix or < 5 lines changed
- Pattern already exists in this codebase (found via local grep)

## LSP Operations (MANDATORY - NON-NEGOTIABLE)

**Every code-editing agent MUST use LSP.** No exceptions.

### After EVERY Edit
\`\`\`
LSP getDiagnostics on the edited file
-> If errors: fix immediately before continuing
-> If warnings: evaluate, fix if relevant
\`\`\`

### Before Modifying a Function
\`\`\`
LSP goToDefinition on the function
-> Read and understand current implementation
-> Check return type, parameters, side effects
\`\`\`

### Before Renaming or Refactoring
\`\`\`
LSP findReferences for the symbol
-> Count all usages across the codebase
-> Plan changes for ALL call sites before starting
-> Never rename without checking every reference
\`\`\`

## Plan Before Execute (MANDATORY)

**Every agent MUST plan before executing non-trivial work.**

### Plan Format (write in your output BEFORE coding)
\`\`\`markdown
### Plan: [what you're about to do]
1. **Read**: [files you need to read first]
2. **Search**: [GitHub patterns to search for]
3. **Changes**: [exact list of changes, file by file]
4. **Dependencies**: [what must happen in what order]
5. **Verification**: [how you'll verify each change works]
\`\`\`

### Skip Planning ONLY When
- Fixing a typo or single-line change
- Running tests or linting (no code changes)

## Learning Protocol (MANDATORY - ALL AGENTS)

**Read LEARNINGS.md first. Write learnings last. Keep entries to 1 line each.**

### Startup
1. Read LEARNINGS.md
2. Grep LEARNINGS.md for keywords related to your task
3. Check "Mistakes" section for relevant traps

### Shutdown -- Write Concise Learnings
\`\`\`markdown
### Learnings
- MISTAKE: {what went wrong} -> {fix} (1 line)
- PATTERN: {what worked} -> {how to reuse} (1 line)
- GOTCHA: {surprise} -> {workaround} (1 line)
\`\`\`

## Task Progress Tracking (MANDATORY - ALL AGENTS)

**Every piece of work MUST be tracked via TaskUpdate.** No untracked work.

### When You Receive a Task
\`\`\`
TaskUpdate: status = "in_progress"
\`\`\`

### When Complete
\`\`\`
TaskUpdate: status = "completed"
-> Only mark complete when ALL verification passes
-> NEVER mark complete if tests fail or errors remain
\`\`\`

## Enforcement Layers

1. **Grep MCP**: Search GitHub before writing new code (NON-NEGOTIABLE)
2. **LSP**: getDiagnostics after every edit, goToDefinition before modifying (NON-NEGOTIABLE)
3. **Plan**: Outline changes before implementing (NON-NEGOTIABLE)
4. **Learning**: Read LEARNINGS.md first, write learnings last (NON-NEGOTIABLE)
5. **Task tracking**: TaskUpdate in_progress/completed on every task (NON-NEGOTIABLE)
6. **Formatter**: Auto-formats on save/hook
7. **Linter**: Linting errors block commits
8. **Test runner**: Test failures block merges
SKILL_EOF

  echo -e "  ${GREEN}CREATE${NC}: $filepath"
}

###############################################################################
# Generate: Orchestrator agent
###############################################################################
generate_orchestrator() {
  echo -e "${YELLOW}Creating orchestrator agent...${NC}"

  local filepath=".claude/agents/orchestrator.md"
  write_file_if_new "$filepath" "---
name: orchestrator
description: >
  Routes tasks to specialized agents, manages workflows, and ensures quality.
  Use PROACTIVELY as the catch-all router when no specific agent matches, or
  when the user needs help deciding which agent/team to use, \"help me with\",
  \"I need to\", multi-step workflows, unclear requests, or any task requiring
  coordination between multiple agents. Does NOT edit code directly.
model: opus
tools:
  - Task
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - AskUserQuestion
  - Read
  - Glob
  - Grep
  - Bash
  - WebSearch
disallowedTools:
  - Edit
  - MultiEdit
  - Write
permissionMode: default
memory: project
maxTurns: 120
skills:
  - team-coordination
hooks:
  SubagentStart:
    - hooks:
        - type: command
          command: \"echo '[orchestrator] '\$(date +%H:%M:%S)' spawned agent' >> \$PROJECT_DIR/reports/.pipeline-log\"
  SubagentStop:
    - hooks:
        - type: command
          command: \"echo '[orchestrator] '\$(date +%H:%M:%S)' agent completed' >> \$PROJECT_DIR/reports/.pipeline-log\"
  Stop:
    - hooks:
        - type: command
          command: \"echo '[orchestrator] '\$(date +%Y-%m-%d' '%H:%M)': Orchestration session complete' >> \$PROJECT_DIR/LEARNINGS.md\"
---

You are the orchestrator for the ${PROJECT_NAME} project. You route tasks to
specialized agents, manage workflows, and ensure quality. You NEVER edit code directly.

## MANDATORY: Grep MCP For Routing Decisions

**Use \`grep_query\` to verify patterns before assigning work to agents.**

\`\`\`
grep_query: query=\"{feature} {framework}\", language=\"${LANGUAGE}\"
grep_query: query=\"{pattern} multi-agent\", language=\"${LANGUAGE}\"
\`\`\`

## MANDATORY STARTUP (do this FIRST, every session)

1. **Read LEARNINGS.md** -- check for routing mistakes, agent failures, known blockers
2. **TaskList** for in-progress work
3. Determine routing based on user request

## MANDATORY SHUTDOWN (do this LAST, every session)

1. **TaskUpdate** your task to \`completed\` (ONLY if all spawned agents succeeded)
2. Update **LEARNINGS.md** with: routing decisions, agent failures, patterns discovered
3. Include **### Learnings** in your output: what worked, what didn't, routing improvements

## Routing Table

| User Request Pattern | Route To | Type |
|---------------------|----------|------|
| \"build/implement/add/create [feature]\" | builder (simple) or feature-team-coordinator (complex) | Agent/Team |
| \"review/check [code]\" | review-team-coordinator | Team |
| \"test/verify [functionality]\" | tester | Agent |
| \"research/find/explore [topic]\" | research-swarm-coordinator | Team |
| \"plan/design/break down/decompose/PRD/spec/architect\" | prd-team-coordinator | Team |
| \"document/explain [module]\" | documenter | Agent |
| \"debug/fix [error]\" | builder (simple) or hypothesis-team-coordinator (complex) | Agent/Team |
| \"create agent/add team/new skill/extend team\" | system-architect | Agent |
| \"refactor [module]\" | plan-execute-coordinator | Team |
| \"assess risk/risk analysis\" | risk-assessor | Agent |

## Detected Commands

- **Run**: \`${RUN_CMD:-N/A}\`
- **Run tests**: \`${TEST_CMD:-N/A}\`
- **Format**: \`${FORMATTER_CMD:-N/A}\`
- **Lint**: \`${LINTER_CMD:-N/A}\`
- **Type check**: \`${TYPE_CHECKER_CMD:-N/A}\`
- **Install deps**: \`${INSTALL_CMD:-N/A}\`

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Builder agent
###############################################################################
generate_builder() {
  echo -e "${YELLOW}Creating builder agent...${NC}"

  local filepath=".claude/agents/builder.md"
  write_file_if_new "$filepath" "---
name: builder
description: >
  Writes production code for the ${PROJECT_NAME} project. Use PROACTIVELY
  when user asks to build, implement, add, create, code, write, fix a bug,
  modify a file, update a function, change behavior, \"add a feature\",
  \"implement this\", \"write code for\", \"fix this\", \"change X to Y\",
  \"update the handler\", or any request that requires modifying source code.
model: sonnet
tools:
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - Bash
  - LSP
  - WebSearch
  - WebFetch
  - TaskUpdate
disallowedTools:
  - Task
  - TaskCreate
  - TaskList
  - TaskGet
permissionMode: acceptEdits
memory: project
maxTurns: 40
skills:
  - coding-conventions
hooks:
  PreToolUse:
    - matcher: \"Write\"
      hooks:
        - type: command
          command: \"echo '[builder] '\$(date +%H:%M:%S)' WRITE: '\\\"\\\$TOOL_INPUT_FILE_PATH\\\" >> \\\$PROJECT_DIR/reports/.pipeline-log\"
    - matcher: \"Edit\"
      hooks:
        - type: command
          command: \"echo '[builder] '\$(date +%H:%M:%S)' EDIT: '\\\"\\\$TOOL_INPUT_FILE_PATH\\\" >> \\\$PROJECT_DIR/reports/.pipeline-log\"
  PostToolUse:
    - matcher: \"Write\"
      hooks:
        - type: command
          command: \"${FORMAT_HOOK_CMD}\"
    - matcher: \"Edit\"
      hooks:
        - type: command
          command: \"${FORMAT_HOOK_CMD}\"
    - matcher: \"MultiEdit\"
      hooks:
        - type: command
          command: \"${FORMAT_HOOK_CMD}\"
  Stop:
    - hooks:
        - type: command
          command: \"echo '[builder] '\$(date +%Y-%m-%d' '%H:%M)': Build session complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You write code for the ${PROJECT_NAME} project. You follow existing patterns exactly.

## MANDATORY STARTUP (do this FIRST, every session)

1. **Read LEARNINGS.md** -- check \"Mistakes\" section for traps
2. **TaskUpdate** your assigned task to \`in_progress\`
3. **Grep local codebase** to study patterns before writing anything:
   \`\`\`
   Grep for import patterns in ${SRC_DIR}
   Grep for class/function patterns in ${SRC_DIR}
   Read the file you'll modify
   \`\`\`

## MANDATORY SHUTDOWN (do this LAST, every session)

1. **TaskUpdate** your task to \`completed\` (ONLY if all verification passes)
2. Write **### Learnings** -- 1 line per item, max 120 chars each:
   - \`MISTAKE: {what} -> {fix}\`
   - \`PATTERN: {what} -> {reuse}\`
   - \`GOTCHA: {surprise} -> {workaround}\`
3. Never mark complete if tests fail or errors remain

## MANDATORY: Grep MCP Before Writing Code

**BEFORE writing ANY substantial new code, use \`grep_query\` to search GitHub.**
NON-NEGOTIABLE.

\`\`\`
grep_query: query=\"{feature} {framework}\", language=\"${LANGUAGE}\"
grep_query: query=\"{pattern} implementation\", language=\"${LANGUAGE}\"
\`\`\`

## MANDATORY Before Every Edit

1. **Grep local codebase** for existing patterns (FIRST)
2. **grep_query** for battle-tested GitHub patterns
3. **Read the target file** (never assume contents)
4. **LSP goToDefinition** before modifying any function
5. **LSP findReferences** before renaming or refactoring

## MANDATORY After Every Edit

1. **LSP getDiagnostics** on the edited file
2. **Formatter** runs on changed files (auto-runs via hook)
3. **Linter**: \`${LINTER_CMD:-N/A}\`
4. **Tests**: \`${TEST_CMD:-N/A}\`

## Critical Rules

1. **Read before writing**: Always read nearby files before creating or modifying code
2. **Match existing style**: Follow patterns in \`${SRC_DIR}\` exactly
3. **Type everything**: Full type annotations on all functions, variables, class fields
4. **Never touch protected paths**: $(echo "$PROTECTED_PATHS" | tr ',' ' ')

## Build Commands

- Format: \`${FORMATTER_CMD:-N/A}\`
- Lint check: \`${LINTER_CMD:-N/A}\`
- Type check: \`${TYPE_CHECKER_CMD:-N/A}\`
- Run tests: \`${TEST_CMD:-N/A}\`

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Tester agent
###############################################################################
generate_tester() {
  echo -e "${YELLOW}Creating tester agent...${NC}"

  local filepath=".claude/agents/tester.md"
  write_file_if_new "$filepath" "---
name: tester
description: >
  Runs tests and reports failures for the ${PROJECT_NAME} project. Use
  PROACTIVELY when user asks to test, verify, check coverage, run tests,
  \"run the tests\", \"does this work?\", \"verify the fix\", \"check coverage\",
  \"test this feature\", \"write tests for\", \"are tests passing?\".
  Reports failures with file:line + suggested fix. Does NOT fix code directly.
model: sonnet
tools:
  - Read
  - Bash
  - Glob
  - Grep
  - LSP
  - TaskUpdate
disallowedTools:
  - Edit
  - MultiEdit
  - Write
  - Task
  - TaskCreate
permissionMode: default
memory: project
maxTurns: 35
skills:
  - coding-conventions
hooks:
  Stop:
    - hooks:
        - type: command
          command: \"echo '[tester] '\$(date +%Y-%m-%d' '%H:%M)': Test session complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You run tests and report results for the ${PROJECT_NAME} project.
You do NOT fix code -- you report failures with file:line and suggested fixes.

## MANDATORY: Grep MCP For Test Patterns

**Use \`grep_query\` to find proven test patterns for similar code.**

\`\`\`
grep_query: query=\"{module} test\", language=\"${LANGUAGE}\"
grep_query: query=\"{pattern} mock\", language=\"${LANGUAGE}\"
\`\`\`

## MANDATORY STARTUP (do this FIRST, every session)

1. **Read LEARNINGS.md** -- check for known test issues, flaky tests, env gotchas
2. **TaskUpdate** your assigned task to \`in_progress\`
3. **Grep local codebase** to understand test patterns

## MANDATORY SHUTDOWN (do this LAST, every session)

1. **TaskUpdate** your task to \`completed\` (ONLY if all test analysis is thorough)
2. Write **### Learnings** -- 1 line per item, max 120 chars

## Test Infrastructure

- **Runner**: ${TEST_RUNNER:-N/A}
- **Test paths**: \`${TESTS_DIR}\`
- **Run command**: \`${TEST_CMD:-N/A}\`

## Failure Reporting Format

When tests fail, report EACH failure as:

\`\`\`markdown
### FAILURE: test_name
- **File**: ${TESTS_DIR}test_file:42
- **Source**: ${SRC_DIR}module:17 (the actual failing code)
- **Error**: ExactErrorMessage
- **Suggested Fix**: What the builder should change
- **Severity**: CRITICAL|HIGH|MEDIUM|LOW
\`\`\`

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Reviewer agent (full profile only)
###############################################################################
generate_reviewer() {
  echo -e "${YELLOW}Creating reviewer agent...${NC}"

  local filepath=".claude/agents/reviewer.md"
  write_file_if_new "$filepath" "---
name: reviewer
description: >
  Reviews code for quality, security, and pattern compliance with fix capability.
  Use PROACTIVELY when user asks to review, check, audit, inspect, validate code,
  \"review this PR\", \"check the code\", \"is this secure?\", \"code quality check\",
  \"find issues in\". Can fix issues it finds.
model: sonnet
tools:
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - Bash
  - LSP
  - WebSearch
  - WebFetch
  - TaskUpdate
disallowedTools: []
permissionMode: default
memory: project
maxTurns: 40
skills:
  - coding-conventions
  - security-standards
hooks:
  PreToolUse:
    - matcher: \"Edit\"
      hooks:
        - type: command
          command: \"echo '[reviewer] '\$(date +%H:%M:%S)' EDIT: '\\\"\\\$TOOL_INPUT_FILE_PATH\\\" >> \\\$PROJECT_DIR/reports/.fix-log\"
    - matcher: \"Write\"
      hooks:
        - type: command
          command: \"echo '[reviewer] '\$(date +%H:%M:%S)' WRITE: '\\\"\\\$TOOL_INPUT_FILE_PATH\\\" >> \\\$PROJECT_DIR/reports/.fix-log\"
  PostToolUse:
    - matcher: \"Write\"
      hooks:
        - type: command
          command: \"${FORMAT_HOOK_CMD}\"
    - matcher: \"Edit\"
      hooks:
        - type: command
          command: \"${FORMAT_HOOK_CMD}\"
    - matcher: \"MultiEdit\"
      hooks:
        - type: command
          command: \"${FORMAT_HOOK_CMD}\"
  Stop:
    - hooks:
        - type: command
          command: \"echo '[reviewer] '\$(date +%Y-%m-%d' '%H:%M)': Review session complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You perform code reviews for the ${PROJECT_NAME} project. You check quality,
security, and pattern compliance. You CAN fix issues you find.

## MANDATORY: Grep MCP Before Fixing Code

**BEFORE applying any non-trivial fix, use \`grep_query\` to find battle-tested solutions.**

\`\`\`
grep_query: query=\"{error pattern} fix\", language=\"${LANGUAGE}\"
grep_query: query=\"{pattern} best practice\", language=\"${LANGUAGE}\"
\`\`\`

## Review Checklist

### 1. Pattern Compliance
- [ ] Follows import ordering
- [ ] Uses correct naming conventions
- [ ] Has documentation on all public functions
- [ ] Full type annotations

### 2. Security Review
- [ ] No hardcoded secrets
- [ ] File paths validated for traversal
- [ ] HTTP requests have timeouts
- [ ] No dangerous eval/exec with dynamic input

### 3. Code Quality
- [ ] No code duplication
- [ ] Functions are focused (single responsibility)
- [ ] No dead code or unused imports
- [ ] Tests exist for new functionality

## Verification Commands

- Format check: \`${FORMATTER_CMD:-N/A}\`
- Lint: \`${LINTER_CMD:-N/A}\`
- Type check: \`${TYPE_CHECKER_CMD:-N/A}\`
- Tests: \`${TEST_CMD:-N/A}\`

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Researcher agent (full profile only)
###############################################################################
generate_researcher() {
  echo -e "${YELLOW}Creating researcher agent...${NC}"

  local filepath=".claude/agents/researcher.md"
  write_file_if_new "$filepath" "---
name: researcher
description: >
  Researches solutions, packages, patterns, and best practices. Use PROACTIVELY
  when user asks to research, find, explore, evaluate, compare, \"what library
  should we use?\", \"find a solution for\", \"look into\", \"what are the options\",
  \"compare X vs Y\", \"best practices for\", \"how does X work?\".
  Read-only -- never modifies code.
model: sonnet
tools:
  - Read
  - Glob
  - Grep
  - Bash
  - WebSearch
  - WebFetch
  - TaskUpdate
disallowedTools:
  - Edit
  - MultiEdit
  - Write
  - Task
  - TaskCreate
permissionMode: default
memory: project
maxTurns: 35
skills:
  - research-patterns
  - coding-conventions
hooks:
  Stop:
    - hooks:
        - type: command
          command: \"echo '[researcher] '\$(date +%Y-%m-%d' '%H:%M)': Research session complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You research solutions, packages, and patterns for the ${PROJECT_NAME} project.
You are READ-ONLY. You never modify code files.

## MANDATORY: Grep MCP Before External Research

**Use \`grep_query\` to search GitHub for existing solutions.** NON-NEGOTIABLE.

\`\`\`
grep_query: query=\"{topic} {framework}\", language=\"${LANGUAGE}\"
grep_query: query=\"{library} example\", language=\"${LANGUAGE}\"
\`\`\`

## Research Protocol

### Step 1: Search Codebase First
Before any external research:
\`\`\`
Glob \"**/*.${LANGUAGE}\" or similar to find relevant files
Grep \"pattern\" ${SRC_DIR} to find existing implementations
Read relevant files for full context
\`\`\`

### Step 2: External Research
Use WebSearch and WebFetch for documentation and examples.

### Step 3: Evaluate and Report
Provide structured findings with recommendations.

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Documenter agent (full profile only)
###############################################################################
generate_documenter() {
  echo -e "${YELLOW}Creating documenter agent...${NC}"

  local filepath=".claude/agents/documenter.md"
  write_file_if_new "$filepath" "---
name: documenter
description: >
  Writes and maintains documentation and reference files. Use PROACTIVELY when
  user asks to document, explain, write docs, update README, create guide,
  \"document this\", \"explain this module\", \"update the docs\", \"write a guide\".
model: sonnet
tools:
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - TaskUpdate
disallowedTools:
  - Task
  - TaskCreate
  - Bash
  - MultiEdit
permissionMode: acceptEdits
memory: project
maxTurns: 35
skills:
  - coding-conventions
hooks:
  PostToolUse:
    - matcher: \"Write\"
      hooks:
        - type: command
          command: \"echo '' > /dev/null\"
    - matcher: \"Edit\"
      hooks:
        - type: command
          command: \"echo '' > /dev/null\"
  Stop:
    - hooks:
        - type: command
          command: \"echo '[documenter] '\$(date +%Y-%m-%d' '%H:%M)': Documentation session complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You write and maintain documentation for the ${PROJECT_NAME} project.

## MANDATORY STARTUP

1. **Read LEARNINGS.md** -- check for documentation gaps
2. **TaskUpdate** your assigned task to \`in_progress\`
3. **Grep local codebase** to understand what you're documenting

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Skill Builder agent (full profile only)
###############################################################################
generate_skill_builder() {
  echo -e "${YELLOW}Creating skill-builder agent...${NC}"

  local filepath=".claude/agents/skill-builder.md"
  write_file_if_new "$filepath" "---
name: skill-builder
description: >
  Creates and modifies skills. Use PROACTIVELY when user asks to \"create a skill\",
  \"add a new skill\", \"modify skill X\", \"build a skill for\", \"new skill\".
model: sonnet
tools:
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - Bash
  - WebSearch
  - WebFetch
  - LSP
  - TaskUpdate
disallowedTools:
  - Task
  - TaskCreate
  - TaskList
  - TaskGet
permissionMode: acceptEdits
memory: project
maxTurns: 35
skills:
  - coding-conventions
hooks:
  PreToolUse:
    - matcher: \"Write\"
      hooks:
        - type: command
          command: \"echo '[skill-builder] '\$(date +%H:%M:%S)' WRITE: '\\\"\\\$TOOL_INPUT_FILE_PATH\\\" >> \\\$PROJECT_DIR/reports/.pipeline-log\"
  PostToolUse:
    - matcher: \"Write\"
      hooks:
        - type: command
          command: \"${FORMAT_HOOK_CMD}\"
    - matcher: \"Edit\"
      hooks:
        - type: command
          command: \"${FORMAT_HOOK_CMD}\"
  Stop:
    - hooks:
        - type: command
          command: \"echo '[skill-builder] '\$(date +%Y-%m-%d' '%H:%M)': Skill build session complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You create and modify skills for the ${PROJECT_NAME} project.

## MANDATORY: Grep MCP Before Writing Skills

\`\`\`
grep_query: query=\"{api_name} client\", language=\"${LANGUAGE}\"
grep_query: query=\"{service} integration example\", language=\"${LANGUAGE}\"
\`\`\`

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: System Architect agent (full profile only)
###############################################################################
generate_system_architect() {
  echo -e "${YELLOW}Creating system-architect agent...${NC}"

  local filepath=".claude/agents/system-architect.md"
  write_file_if_new "$filepath" "---
name: system-architect
description: >
  Creates, designs, and integrates new agents, teams, skills, and pipelines.
  Use PROACTIVELY when user asks to create an agent, add a team, build a skill,
  extend a team, \"I need an agent for...\", \"can we add a team that...\".
  Does NOT build application features -- builds the SYSTEM ITSELF.
model: opus
tools:
  - Task
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - AskUserQuestion
  - Read
  - Write
  - Edit
  - MultiEdit
  - Glob
  - Grep
  - LS
  - Bash
  - LSP
  - WebSearch
  - WebFetch
disallowedTools: []
permissionMode: acceptEdits
memory: project
maxTurns: 100
skills:
  - coding-conventions
  - team-coordination
hooks:
  PreToolUse:
    - matcher: \"Write\"
      hooks:
        - type: command
          command: \"echo '[system-architect] '\$(date +%H:%M:%S)' WRITE: '\\\"\\\$TOOL_INPUT_FILE_PATH\\\" >> \\\$PROJECT_DIR/reports/.pipeline-log\"
  Stop:
    - hooks:
        - type: command
          command: \"echo '[system-architect] '\$(date +%Y-%m-%d' '%H:%M)': System modification complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You are the System Architect. You design and build the agent infrastructure --
new agents, teams, skills, and pipelines. You do NOT build application features.

## Design Rules

1. SINGLE RESPONSIBILITY: one agent, one job
2. MINIMUM TOOLS: only what's needed
3. OPUS FOR JUDGMENT: coordinators, security review, architecture
4. SONNET FOR EXECUTION: builders, testers, researchers
5. HOOKS ARE MANDATORY: format on edit, knowledge on stop, pipeline on spawn
6. LSP IS MANDATORY: getDiagnostics after every edit on code-editing agents
7. FILE OWNERSHIP IS NON-NEGOTIABLE: no two parallel agents write the same file

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Risk Assessor agent (full profile only)
###############################################################################
generate_risk_assessor() {
  echo -e "${YELLOW}Creating risk-assessor agent...${NC}"

  local filepath=".claude/agents/risk-assessor.md"
  write_file_if_new "$filepath" "---
name: risk-assessor
description: >
  Identifies risks in proposed changes and recommends mitigations. Use
  PROACTIVELY when user asks to \"assess risk\", \"risk analysis\", \"what could
  go wrong\", \"is this safe?\", \"security implications\", \"evaluate risk of\".
  Read-only -- never modifies code.
model: sonnet
tools:
  - Read
  - Glob
  - Grep
  - Bash
  - TaskUpdate
disallowedTools:
  - Edit
  - MultiEdit
  - Write
  - Task
  - TaskCreate
permissionMode: default
memory: project
maxTurns: 35
skills:
  - security-standards
  - coding-conventions
hooks:
  Stop:
    - hooks:
        - type: command
          command: \"echo '[risk-assessor] '\$(date +%Y-%m-%d' '%H:%M)': Risk assessment complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You identify risks in proposed changes and recommend mitigations.
You are READ-ONLY. You never modify code files.

## Risk Categories

1. **Integration Risk**: Changes that might break existing functionality
2. **Security Risk**: Changes that might introduce vulnerabilities
3. **Pattern Risk**: Changes that diverge from established patterns
4. **Scope Risk**: Changes larger than expected
5. **Test Risk**: Changes not adequately testable

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Coordinator agents (full profile only)
###############################################################################
generate_coordinator() {
  local name="$1"
  local display_name="$2"
  local description="$3"
  local team_def="$4"
  local log_prefix="$5"

  echo -e "${YELLOW}Creating ${name} agent...${NC}"

  local filepath=".claude/agents/${name}.md"
  write_file_if_new "$filepath" "---
name: ${name}
description: >
  ${description}
  Does NOT edit code directly.
model: sonnet
tools:
  - Task
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - Read
  - Glob
  - Grep
  - LS
  - Bash
disallowedTools:
  - Edit
  - MultiEdit
  - Write
permissionMode: default
memory: project
maxTurns: 60
skills:
  - team-coordination
  - coding-conventions
hooks:
  SubagentStart:
    - hooks:
        - type: command
          command: \"echo '[${log_prefix}] '\$(date +%H:%M:%S)' spawned agent' >> \\\$PROJECT_DIR/reports/.pipeline-log\"
  SubagentStop:
    - hooks:
        - type: command
          command: \"echo '[${log_prefix}] '\$(date +%H:%M:%S)' agent completed' >> \\\$PROJECT_DIR/reports/.pipeline-log && \\\$PROJECT_DIR/scripts/validate-agent-output.sh ${log_prefix}\"
  Stop:
    - hooks:
        - type: command
          command: \"echo '[${log_prefix}] '\$(date +%Y-%m-%d' '%H:%M)': ${display_name} complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You coordinate ${display_name} for the ${PROJECT_NAME} project.
You do NOT edit code directly.

## MANDATORY STARTUP (do this FIRST, every session)

1. **Read LEARNINGS.md** -- check for prior issues
2. **TaskList** for in-progress work
3. **TaskUpdate** your assigned task to \`in_progress\`
4. Read \`${team_def}\`

## MANDATORY SHUTDOWN (do this LAST, every session)

1. **TaskUpdate** your task to \`completed\` (ONLY if all verified)
2. Include **### Learnings** in your output

## Communication Protocol

- Grep ALL agent outputs for CROSS-DOMAIN and BLOCKER tags
- CROSS-DOMAIN tag found -> create follow-up task for target agent
- BLOCKER found -> check blocker status, re-spawn when resolved

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: PRD Team Coordinator (full profile only)
###############################################################################
generate_prd_coordinator() {
  echo -e "${YELLOW}Creating prd-team-coordinator agent...${NC}"

  local filepath=".claude/agents/prd-team-coordinator.md"
  write_file_if_new "$filepath" "---
name: prd-team-coordinator
description: >
  Coordinates PRD creation and task decomposition. Use PROACTIVELY when user
  wants to plan a feature, create a PRD, break down requirements, decompose
  a project, \"I want to build...\", \"let's plan...\", \"break this down\".
model: opus
tools:
  - Task
  - TaskCreate
  - TaskUpdate
  - TaskList
  - TaskGet
  - Read
  - Glob
  - Grep
  - LS
  - Bash
  - Write
disallowedTools:
  - Edit
  - MultiEdit
memory: project
maxTurns: 80
skills:
  - coding-conventions
  - team-coordination
hooks:
  SubagentStart:
    - hooks:
        - type: command
          command: \"echo '[prd-coordinator] '\$(date +%H:%M:%S)' spawned' >> \\\$PROJECT_DIR/reports/.pipeline-log\"
  SubagentStop:
    - hooks:
        - type: command
          command: \"echo '[prd-coordinator] '\$(date +%H:%M:%S)' completed' >> \\\$PROJECT_DIR/reports/.pipeline-log && \\\$PROJECT_DIR/scripts/validate-agent-output.sh prd-coordinator\"
  Stop:
    - hooks:
        - type: command
          command: \"echo '[prd-coordinator] '\$(date +%Y-%m-%d' '%H:%M)': PRD decomposition complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You are the PRD Decomposition Coordinator. You turn feature ideas into
build-ready task trees.

## Phases

1. **Extract**: Requirements extraction from user input
2. **Research**: Technical research and codebase scan
3. **Design**: Architecture design
4. **Decompose**: Task tree creation
5. **Present**: Synthesis and user approval

## Team Members

- **requirements-extractor** - Extracts structured requirements
- **technical-researcher** - Codebase + tech research
- **architecture-designer** - Architecture design
- **task-decomposer** - Task breakdown

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: PRD specialist agents (full profile only)
###############################################################################
generate_requirements_extractor() {
  echo -e "${YELLOW}Creating requirements-extractor agent...${NC}"

  local filepath=".claude/agents/requirements-extractor.md"
  write_file_if_new "$filepath" "---
name: requirements-extractor
description: >
  Extracts structured requirements from unstructured input. Use as part of
  the PRD decomposition team. Identifies functional requirements, non-functional
  requirements, edge cases, constraints, and success criteria.
model: sonnet
tools:
  - Read
  - Write
  - Glob
  - Grep
  - LS
  - TaskUpdate
disallowedTools:
  - Edit
  - MultiEdit
  - Task
  - TaskCreate
memory: project
maxTurns: 40
skills:
  - coding-conventions
hooks:
  Stop:
    - hooks:
        - type: command
          command: \"echo '[requirements-extractor] '\$(date +%Y-%m-%d' '%H:%M)': Extraction complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You are the Requirements Extractor. You turn unstructured feature descriptions
into structured, complete requirements documents.

Output: reports/prd/requirements.md

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

generate_technical_researcher() {
  echo -e "${YELLOW}Creating technical-researcher agent...${NC}"

  local filepath=".claude/agents/technical-researcher.md"
  write_file_if_new "$filepath" "---
name: technical-researcher
description: >
  Researches implementation approaches for PRD features. Searches GitHub
  for reference implementations, reads API docs, evaluates libraries.
  Part of the PRD decomposition team.
model: sonnet
tools:
  - Read
  - WebSearch
  - WebFetch
  - Grep
  - Glob
  - LS
  - LSP
  - Bash
  - TaskUpdate
disallowedTools:
  - Edit
  - MultiEdit
  - Write
  - Task
  - TaskCreate
memory: project
maxTurns: 50
skills:
  - research-patterns
  - coding-conventions
hooks:
  Stop:
    - hooks:
        - type: command
          command: \"echo '[technical-researcher] '\$(date +%Y-%m-%d' '%H:%M)': Research complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You are the Technical Researcher for PRD decomposition. You find the best
implementation approaches before anyone writes code.

## MANDATORY: Grep MCP Before Researching

\`\`\`
grep_query: query=\"{feature} {framework}\", language=\"${LANGUAGE}\"
grep_query: query=\"{pattern} implementation\", language=\"${LANGUAGE}\"
\`\`\`

Output: reports/prd/technical-research.md

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

generate_architecture_designer() {
  echo -e "${YELLOW}Creating architecture-designer agent...${NC}"

  local filepath=".claude/agents/architecture-designer.md"
  write_file_if_new "$filepath" "---
name: architecture-designer
description: >
  Designs technical architecture for PRD features. Creates data models,
  API contracts, component structure. Part of the PRD decomposition team.
model: opus
tools:
  - Read
  - Write
  - Glob
  - Grep
  - LS
  - LSP
  - TaskUpdate
disallowedTools:
  - Edit
  - MultiEdit
  - Task
  - TaskCreate
memory: project
maxTurns: 55
skills:
  - coding-conventions
  - security-standards
hooks:
  Stop:
    - hooks:
        - type: command
          command: \"echo '[architecture-designer] '\$(date +%Y-%m-%d' '%H:%M)': Architecture design complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You are the Architecture Designer. You design technical solutions that are
buildable by individual agents in atomic tasks.

Output: reports/prd/architecture.md

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

generate_task_decomposer() {
  echo -e "${YELLOW}Creating task-decomposer agent...${NC}"

  local filepath=".claude/agents/task-decomposer.md"
  write_file_if_new "$filepath" "---
name: task-decomposer
description: >
  Decomposes PRD architecture into atomic, build-ready task units. Each task
  is sized for one agent to complete in one session. Part of the PRD team.
model: sonnet
tools:
  - Read
  - Write
  - Glob
  - Grep
  - LS
  - TaskUpdate
disallowedTools:
  - Edit
  - MultiEdit
  - Task
  - TaskCreate
memory: project
maxTurns: 50
skills:
  - coding-conventions
  - team-coordination
hooks:
  Stop:
    - hooks:
        - type: command
          command: \"echo '[task-decomposer] '\$(date +%Y-%m-%d' '%H:%M)': Decomposition complete' >> \\\$PROJECT_DIR/LEARNINGS.md\"
---

You are the Task Decomposer. You break architecture into atomic tasks
that agents can execute independently.

## The Atomic Task Rule

A task is atomic when ALL of these are true:
- One agent can complete it in one session
- It has clear inputs and outputs
- It has testable acceptance criteria
- Its file ownership doesn't overlap with parallel tasks

Output: reports/prd/task-tree.md

## Protected Paths (NEVER MODIFY)

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
}

###############################################################################
# Generate: Team Coordination Skill (full profile only)
###############################################################################
generate_team_coordination_skill() {
  echo -e "${YELLOW}Creating team-coordination skill...${NC}"

  local filepath=".claude/skills/team-coordination/SKILL.md"
  write_file_if_new "$filepath" "---
name: team-coordination
description: Protocol for multi-agent team coordination. Covers output format, messaging, file ownership, status tracking, and done checklists.
version: 1.0.0
author: Agent Team System
---

# Team Coordination Protocol

Language-agnostic protocol for coordinating multi-agent teams.

## Output Format (Structured Output Files)

Every agent MUST structure output as:

\`\`\`markdown
# [Role] Report
Status: COMPLETE | IN-PROGRESS | BLOCKED | FAILED

## [Agent Name] - [Action Summary]

**Files touched**: [list of files modified]
**Tests affected**: [list of test files]

### Findings / Changes Made
- [bullet list of changes or findings]

### Cross-Domain Tags
- CROSS-DOMAIN:{TARGET}: {message}
- BLOCKER:{TARGET}: {what you need}

### Verification
- [ ] Code compiles/runs
- [ ] Tests pass
- [ ] No lint errors

### Knowledge Base Additions
[Patterns worth adding to LEARNINGS.md]
\`\`\`

## CROSS-DOMAIN and BLOCKER Protocol

### CROSS-DOMAIN:{TARGET}
Used when an agent finds something that affects another agent's domain.
Coordinator action: Create follow-up task for TARGET agent with the actual finding.

### BLOCKER:{TARGET}
Used when an agent is blocked by another agent's work.
Coordinator action: Check blocker status. If resolved, re-spawn blocked agent.

## Context Loading Tiers

### ALWAYS Load (every agent, every session)
- \`LEARNINGS.md\`
- Conventions skill (coding-conventions)
- Team-coordination skill (this file)

### LOAD When Relevant (per task)
- Files directly related to current task
- Interface contracts for cross-module work

### NEVER Load
- Other stages' intermediate outputs (unless directly needed)
- Superseded versions of documents

## Task Decomposition (MANDATORY - ALL COORDINATORS)

### Before Spawning ANY Agent
\`\`\`
1. TaskCreate for each unit of work
2. Only THEN spawn the agent with the task ID
\`\`\`

### Task Granularity Rules
- Each task = one agent, one session, clear done criteria
- If two tasks write the same file, merge them or sequence them

## Done Checklist

Before marking ANY task as complete, verify:
- [ ] Formatter passes: \`${FORMATTER_CMD:-N/A}\`
- [ ] Linter passes: \`${LINTER_CMD:-N/A}\`
- [ ] Type checker passes: \`${TYPE_CHECKER_CMD:-N/A}\`
- [ ] Tests pass: \`${TEST_CMD:-N/A}\`

## Model Selection (Complexity-Based)

### Complexity Score
Score each dimension 0-2, sum for total:

| Dimension | 0 (Low) | 1 (Medium) | 2 (High) |
|-----------|---------|------------|----------|
| Ambiguity | Clear requirements | Some undefined | Vague, many unknowns |
| Integration | 0-2 touchpoints | 3-5 touchpoints | 6+ touchpoints |
| Novelty | Extends existing | Mix existing+new | Entirely new architecture |
| Risk | Low-impact | Moderate impact | Security-critical |
| Scale | < 5 files | 5-15 files | 15+ files |

### Model Decision
| Score | Model |
|-------|-------|
| 0-1 | haiku |
| 2-3 | sonnet |
| 4-6 | sonnet default, opus if ambiguity or risk >= 2 |
| 7-10 | opus |

## Retry Limits

| Operation | Max Retries | Action on Failure |
|-----------|-------------|-------------------|
| Build + Test | 3 | Escalate to orchestrator |
| Review + Fix | 5 | Escalate to orchestrator |
| Research | 2 | Report findings, move on |

## Escalation Protocol

1. Agent hits retry limit -> Reports to coordinator
2. Coordinator can't resolve -> Reports to orchestrator
3. Orchestrator can't resolve -> Reports to user
"
}

###############################################################################
# Generate: Security Standards Skill (full profile only)
###############################################################################
generate_security_standards_skill() {
  echo -e "${YELLOW}Creating security-standards skill...${NC}"

  local filepath=".claude/skills/security-standards/SKILL.md"
  write_file_if_new "$filepath" "---
name: security-standards
description: Security standards for the ${PROJECT_NAME} codebase. Covers secrets management, input validation, path traversal prevention.
version: 1.0.0
author: Agent Team System
---

# Security Standards

Security requirements for the ${PROJECT_NAME} codebase.

## Secrets Management

### Environment Variables
- ALL secrets in \`.env\` file only
- Access via settings/config -- never \`os.getenv()\` directly
- \`.env.example\` must use PLACEHOLDER values, never real keys

### Secret Patterns to Flag
- Hardcoded API keys, passwords, tokens
- Real credentials in example/test files

## Input Validation

### Path Traversal Prevention
For all file access:
- Validate file paths are within expected directories
- Use resolve() + is_relative_to() (Python) or equivalent
- Never construct file paths from unvalidated user input

### URL Validation
- Validate URL scheme (http/https only)
- Timeout all HTTP requests
- Truncate large responses

## Security Review Checklist

1. [ ] No hardcoded secrets
2. [ ] File paths validated for traversal
3. [ ] HTTP requests use timeouts
4. [ ] No eval/exec with dynamic input
5. [ ] Logging doesn't include secret values
6. [ ] New dependencies are from trusted sources
7. [ ] Error messages don't leak internal paths

## Incident Response

If a security issue is found:
1. **Stop**: Don't deploy or merge
2. **Document**: Record in LEARNINGS.md under \"Security Issues\"
3. **Fix**: Prioritize fix above all other work
4. **Verify**: Security review of the fix
"
}

###############################################################################
# Generate: Research Patterns Skill (full profile only)
###############################################################################
generate_research_patterns_skill() {
  echo -e "${YELLOW}Creating research-patterns skill...${NC}"

  local filepath=".claude/skills/research-patterns/SKILL.md"
  write_file_if_new "$filepath" "---
name: research-patterns
description: Research methodology for the ${PROJECT_NAME} project. Covers source evaluation, search strategies, output format.
version: 1.0.0
author: Agent Team System
---

# Research Patterns

Methodology for research agents working in this codebase.

## Search Strategy

### Codebase Search (Always First)
\`\`\`
1. Glob to find relevant files
2. Grep for implementation patterns in ${SRC_DIR}
3. Read specific files for full context
4. Grep for test patterns in ${TESTS_DIR}
\`\`\`

### External Research
Use WebSearch and WebFetch for documentation.

### Source Evaluation
\`\`\`
Official docs > GitHub source > Published packages > Community posts > LLM knowledge
\`\`\`

## Output Format

\`\`\`markdown
## Research: [Topic]

**Query**: [What was researched]
**Confidence**: [High|Medium|Low]

### Findings
[Structured findings with sources]

### Recommendation
[Actionable recommendation]

### Codebase Context
[How findings relate to existing code]
\`\`\`

## Deliverables

1. Structured findings
2. Actionable recommendation
3. Codebase context
4. Risk assessment
5. LEARNINGS.md update if new patterns discovered
"
}

###############################################################################
# Generate: Team Registry (full profile only)
###############################################################################
generate_team_registry() {
  echo -e "${YELLOW}Creating team registry...${NC}"

  ensure_dir "team-registry"
  ensure_dir "team-registry/run-logs"
  touch "team-registry/run-logs/.gitkeep"

  # teams.md
  write_file_if_new "team-registry/teams.md" "# Team Registry

## Team 1: Core Agents (Standalone)

| Agent | Role | Model |
|-------|------|-------|
| orchestrator | Routes tasks, manages workflow | opus |
| builder | Writes code | sonnet |
| reviewer | Code review | sonnet |
| tester | Tests | sonnet |
| researcher | Research | sonnet |
| documenter | Documentation | sonnet |

## Team 2: Parallel Review Team

| Agent | Role | Model |
|-------|------|-------|
| review-team-coordinator | Coordinates reviews | sonnet |
| reviewer | Pattern + security review + fix | sonnet |
| tester | Test coverage check | sonnet |

**Trigger**: \"review\", \"check code\", \"audit\"
**Team Definition**: team-registry/parallel-review-team.md

## Team 3: Cross-Layer Feature Team

| Agent | Role | Model |
|-------|------|-------|
| feature-team-coordinator | Coordinates feature dev | sonnet |
| builder | Core implementation | sonnet |
| skill-builder | Skills changes | sonnet |
| tester | Test coverage | sonnet |
| reviewer | Reviews completed work | sonnet |

**Trigger**: \"build feature\", \"add feature\", \"implement\"
**Team Definition**: team-registry/cross-layer-feature-team.md

## Team 4: Competing Hypotheses Team

| Agent | Role | Model |
|-------|------|-------|
| hypothesis-team-coordinator | Manages parallel investigations | sonnet |
| researcher (x2-3) | Investigates hypotheses | sonnet |

**Trigger**: \"debug complex\", \"compare approaches\", \"investigate\"
**Team Definition**: team-registry/competing-hypotheses-team.md

## Team 5: Research Swarm Team

| Agent | Role | Model |
|-------|------|-------|
| research-swarm-coordinator | Coordinates research | sonnet |
| researcher (x2-4) | Parallel research | sonnet |

**Trigger**: \"research\", \"find library\", \"evaluate options\"
**Team Definition**: team-registry/research-swarm-team.md

## Team 6: Plan-Then-Execute Team

| Agent | Role | Model |
|-------|------|-------|
| plan-execute-coordinator | Plans then coordinates | sonnet |
| builder | Executes code changes | sonnet |
| tester | Verifies each step | sonnet |

**Trigger**: \"refactor\", \"migrate\", \"multi-step change\"
**Team Definition**: team-registry/plan-then-execute-team.md

## Team 7: PRD Decomposition Team

| Agent | Role | Model |
|-------|------|-------|
| prd-team-coordinator | Coordinates PRD decomposition | opus |
| requirements-extractor | Extracts structured requirements | sonnet |
| technical-researcher | Codebase + tech research | sonnet |
| architecture-designer | Architecture design | opus |
| task-decomposer | Task breakdown | sonnet |

**Trigger**: \"plan feature\", \"decompose PRD\", \"break down\"
**Team Definition**: team-registry/prd-decomposition-team.md

## Standalone Agents

| Agent | Role | Model |
|-------|------|-------|
| system-architect | Creates agents/teams/skills | opus |
| risk-assessor | Risk identification | sonnet |
"

  # README.md
  write_file_if_new "team-registry/README.md" "# Team Registry

Team definitions and run logs for the persistent agent teams system.

## Structure

\`\`\`
team-registry/
  README.md
  teams.md
  prd-decomposition-team.md
  parallel-review-team.md
  cross-layer-feature-team.md
  competing-hypotheses-team.md
  research-swarm-team.md
  plan-then-execute-team.md
  run-logs/
\`\`\`

## Adding a New Team

1. Create team definition file in \`team-registry/\`
2. Add team to \`teams.md\` master registry
3. Create coordinator agent in \`.claude/agents/\`
4. Add routing entry to \`CLAUDE.md\`
"

  # Individual team definitions
  write_file_if_new "team-registry/parallel-review-team.md" "# Parallel Review Team

## Purpose
Coordinate parallel code reviews across pattern compliance, security, and test coverage.

## When to Use
- Code review requested
- Security audit needed
- Quality check before merge

## Members

| Member | Agent File | Model | Role |
|--------|-----------|-------|------|
| Coordinator | review-team-coordinator.md | sonnet | Spawns reviewers, synthesizes |
| Reviewer | reviewer.md | sonnet | Pattern + security review, can fix |
| Tester | tester.md | sonnet | Test coverage, run tests |

## Done Conditions
- [ ] All agents completed
- [ ] CROSS-DOMAIN tags addressed
- [ ] Unified report written
- [ ] Decision issued (APPROVE / REQUEST_CHANGES)

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
"

  write_file_if_new "team-registry/cross-layer-feature-team.md" "# Cross-Layer Feature Team

## Purpose
Coordinate cross-module feature development with strict file ownership.

## When to Use
- Feature spans multiple modules
- Multiple agents need to write different files
- Integration verification required

## Members

| Member | Agent File | Model | Role |
|--------|-----------|-------|------|
| Coordinator | feature-team-coordinator.md | sonnet | Decomposes, spawns, manages |
| Builder | builder.md | sonnet | Core implementation |
| Skill Builder | skill-builder.md | sonnet | Skills changes |
| Tester | tester.md | sonnet | Test verification |
| Reviewer | reviewer.md | sonnet | Reviews completed work |

## Execution Pattern

\`\`\`
Phase 1: Core changes (builder)
Phase 2: Implementation (builder)
Phase 3: Skills (skill-builder) -- can parallel with Phase 2
Phase 4: Tests (tester) -- after Phase 2+3
Phase 5: Review (reviewer) -- after Phase 4
\`\`\`

## Done Conditions
- [ ] All phases complete
- [ ] Tests pass: \`${TEST_CMD:-N/A}\`
- [ ] Lint passes: \`${LINTER_CMD:-N/A}\`
- [ ] No file ownership conflicts
- [ ] Review APPROVE issued

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
"

  write_file_if_new "team-registry/competing-hypotheses-team.md" "# Competing Hypotheses Team

## Purpose
Investigate complex problems by testing multiple hypotheses in parallel.

## When to Use
- Bug with unclear root cause
- Architecture decision with multiple valid approaches
- Performance issue with several optimization candidates

## Members

| Member | Agent File | Model | Role |
|--------|-----------|-------|------|
| Coordinator | hypothesis-team-coordinator.md | sonnet | Formulates hypotheses, compares |
| Investigator A | researcher.md or builder.md | sonnet | Investigates Hypothesis A |
| Investigator B | researcher.md or builder.md | sonnet | Investigates Hypothesis B |
| Investigator C | researcher.md or builder.md | sonnet | Investigates Hypothesis C (optional) |

## Done Conditions
- [ ] All investigators returned verdicts
- [ ] Comparison matrix completed
- [ ] Winner selected with reasoning
- [ ] Action items defined

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
"

  write_file_if_new "team-registry/research-swarm-team.md" "# Research Swarm Team

## Purpose
Coordinate parallel research across multiple sources and topics.

## When to Use
- Evaluating multiple packages/libraries
- Researching a topic across different sources
- Comparing approaches with documentation

## Members

| Member | Agent File | Model | Role |
|--------|-----------|-------|------|
| Coordinator | research-swarm-coordinator.md | sonnet | Decomposes query, synthesizes |
| Researcher 1 | researcher.md | sonnet | Sub-query 1 |
| Researcher 2 | researcher.md | sonnet | Sub-query 2 |
| Researcher 3 | researcher.md | sonnet | Sub-query 3 (optional) |
| Researcher 4 | researcher.md | sonnet | Sub-query 4 (optional) |

## Done Conditions
- [ ] All researchers completed
- [ ] Contradictions identified
- [ ] Unified synthesis report written
- [ ] Actionable recommendations provided

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
"

  write_file_if_new "team-registry/plan-then-execute-team.md" "# Plan-Then-Execute Team

## Purpose
Plan implementation strategies then coordinate execution for refactoring and migrations.

## When to Use
- Refactoring that touches multiple files
- Migrating from one pattern to another
- Any change where getting the order wrong causes breakage

## Members

| Member | Agent File | Model | Role |
|--------|-----------|-------|------|
| Coordinator | plan-execute-coordinator.md | sonnet | Plans, spawns executors |
| Builder | builder.md | sonnet | Executes code changes |
| Tester | tester.md | sonnet | Verifies each step |
| Reviewer | reviewer.md | sonnet | Final review (optional) |

## Execution Pattern

### Phase 1: Plan (Cheap)
Coordinator scans, maps dependencies, creates execution plan.

### Phase 2: Execute (Team)
Sequential steps verified individually, parallel where safe.

## Done Conditions
- [ ] All plan steps completed
- [ ] Tests pass: \`${TEST_CMD:-N/A}\`
- [ ] Lint passes: \`${LINTER_CMD:-N/A}\`
- [ ] No regressions

## What Worked

(Updated after each run)

## What Didn't Work

(Updated after each run)
"

  write_file_if_new "team-registry/prd-decomposition-team.md" "# Team: PRD Decomposition

## Purpose
Takes a feature idea and produces a complete, decomposed, build-ready task tree.

## When to Use
- Starting a new feature or major change
- User says \"plan\", \"design\", \"break down\", \"decompose\", \"PRD\"
- Before any Plan-Then-Execute team run

## Team Members

### Coordinator
- Agent: .claude/agents/prd-team-coordinator.md
- Model: opus

### Requirements Extractor
- Agent: .claude/agents/requirements-extractor.md
- Model: sonnet (default), opus on high complexity
- Output: reports/prd/requirements.md

### Technical Researcher
- Agent: .claude/agents/technical-researcher.md
- Model: sonnet
- Output: reports/prd/technical-research.md

### Architecture Designer
- Agent: .claude/agents/architecture-designer.md
- Model: opus
- Output: reports/prd/architecture.md

### Task Decomposer
- Agent: .claude/agents/task-decomposer.md
- Model: sonnet (default), opus on high complexity
- Output: reports/prd/task-tree.md

## Phases
1. Extract (requirements-extractor)
2. Research (technical-researcher)
3. Design (architecture-designer)
4. Decompose (task-decomposer)
5. Present (coordinator)

## Done Conditions
- requirements.md exists
- technical-research.md exists
- architecture.md exists
- task-tree.md exists
- final-prd.md synthesizes everything
- User has approved the plan
- TaskCreate called for every task in the tree

## What Worked

## What Didn't Work
"
}

###############################################################################
# Generate: Validation scripts (full profile only)
###############################################################################
generate_validation_scripts() {
  echo -e "${YELLOW}Creating validation scripts...${NC}"

  ensure_dir "scripts"

  write_file_if_new "scripts/check-diagnostics.sh" '#!/usr/bin/env bash
# Gate hook: Warns if getDiagnostics was not called recently
# Exit 0 = allow (hooks cannot actually block)

PIPELINE_LOG="${PROJECT_DIR}/reports/.pipeline-log"
FILE_PATH="$TOOL_INPUT_FILE_PATH"

# Skip for non-source files
case "$FILE_PATH" in
  *.md|*.json|*.yaml|*.yml|*.toml|*.txt|*.cfg|*.ini|*.env*) exit 0 ;;
esac

# If no pipeline log exists yet, allow
if [ ! -f "$PIPELINE_LOG" ]; then
  exit 0
fi

# Check if getDiagnostics was called in the last 10 lines
if tail -10 "$PIPELINE_LOG" | grep -q "getDiagnostics"; then
  exit 0
fi

echo "[GATE] WARNING: getDiagnostics not called recently." >&2
exit 0
'

  write_file_if_new "scripts/validate-agent-output.sh" '#!/usr/bin/env bash
# Validates agent output after SubagentStop
# Usage: validate-agent-output.sh [agent-name]

AGENT_NAME="${1:-unknown}"
PROJECT_DIR="${PROJECT_DIR:-.}"
LOG="$PROJECT_DIR/reports/.pipeline-log"

echo "[$AGENT_NAME] $(date +%H:%M:%S) validating output" >> "$LOG"

# Check 1: Were any protected paths modified?
PROTECTED_CHANGES=$(git diff --name-only 2>/dev/null | grep -E "^(\.env$)" || true)
if [ -n "$PROTECTED_CHANGES" ]; then
  echo "[VALIDATION FAIL] $AGENT_NAME modified protected paths: $PROTECTED_CHANGES" >> "$LOG"
  echo "VALIDATION FAIL: Protected paths modified: $PROTECTED_CHANGES" >&2
fi

# Check 2: Do tests still pass?
if command -v pytest &>/dev/null; then
  if ! pytest tests/ -x -q --no-header 2>/dev/null; then
    echo "[VALIDATION WARN] $AGENT_NAME: tests failing after changes" >> "$LOG"
    echo "VALIDATION WARN: Tests failing after agent changes" >&2
  fi
fi

echo "[$AGENT_NAME] $(date +%H:%M:%S) validation complete" >> "$LOG"
exit 0
'

  chmod +x "scripts/check-diagnostics.sh" 2>/dev/null || true
  chmod +x "scripts/validate-agent-output.sh" 2>/dev/null || true
}

###############################################################################
# Generate: CLAUDE.md agent team section
###############################################################################
append_claude_md_section() {
  echo -e "${YELLOW}Updating CLAUDE.md...${NC}"

  local section_marker="# Agent Team System"

  # Check if section already exists
  if [ -f "CLAUDE.md" ] && grep -q "$section_marker" "CLAUDE.md" 2>/dev/null; then
    echo -e "  ${YELLOW}EXISTS${NC}: Agent Team section already in CLAUDE.md (skipping)"
    return
  fi

  # Build the section
  local section=""

  if [ "$PROFILE" = "lite" ]; then
    section="

${section_marker}

## Task Routing

| Request Pattern | Route To |
|----------------|----------|
| \"build/implement/add\" | builder |
| \"test/verify\" | tester |
| other | orchestrator |

## Agent Table

| Agent | Purpose | Model |
|-------|---------|-------|
| orchestrator | Routes tasks, manages workflow | opus |
| builder | Writes code following existing patterns | sonnet |
| tester | Runs tests, reports failures | sonnet |

## Mandatory Practices

1. **Grep Local Codebase FIRST**: Before writing ANY code, grep THIS project
2. **Grep MCP**: Use \`grep_query\` to search GitHub for battle-tested code
3. **LSP After Every Edit**: \`getDiagnostics\` after EVERY edit
4. **Plan Before Execute**: Outline plan BEFORE non-trivial changes
5. **Learn From Mistakes**: Read \`LEARNINGS.md\` at start, write learnings at end
6. **Task Management**: ALL work tracked via TaskUpdate

## Detected Commands

\`\`\`bash
${RUN_CMD:+# Run}
${RUN_CMD:-# Run: not detected}
${RUN_CMD:+$RUN_CMD}
${TEST_CMD:+# Tests}
${TEST_CMD:-# Tests: not detected}
${TEST_CMD:+$TEST_CMD}
${FORMATTER_CMD:+# Format}
${FORMATTER_CMD:-# Format: not detected}
${FORMATTER_CMD:+$FORMATTER_CMD}
${LINTER_CMD:+# Lint}
${LINTER_CMD:-# Lint: not detected}
${LINTER_CMD:+$LINTER_CMD}
${TYPE_CHECKER_CMD:+# Type check}
${TYPE_CHECKER_CMD:-# Type check: not detected}
${TYPE_CHECKER_CMD:+$TYPE_CHECKER_CMD}
${INSTALL_CMD:+# Install}
${INSTALL_CMD:-# Install: not detected}
${INSTALL_CMD:+$INSTALL_CMD}
\`\`\`

## Protected Paths

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)
"
  else
    section="

${section_marker}

## Task Routing

| Request Pattern | Route To | Type |
|----------------|----------|------|
| \"build/implement/add [simple]\" | builder | Agent |
| \"build/implement [complex]\" | feature-team-coordinator | Team |
| \"review/check/audit\" | review-team-coordinator | Team |
| \"test/verify\" | tester | Agent |
| \"research/find/explore\" | research-swarm-coordinator | Team |
| \"plan/design/decompose/PRD\" | prd-team-coordinator | Team |
| \"document/explain\" | documenter | Agent |
| \"debug/fix [simple]\" | builder | Agent |
| \"debug/investigate [complex]\" | hypothesis-team-coordinator | Team |
| \"refactor/migrate\" | plan-execute-coordinator | Team |
| \"create agent/team/skill\" | system-architect | Agent |
| \"assess risk\" | risk-assessor | Agent |

## Agent Table

### Core Agents (6)
| Agent | Purpose | Model |
|-------|---------|-------|
| orchestrator | Routes tasks, manages workflow | opus |
| builder | Writes code following existing patterns | sonnet |
| reviewer | Code review + fix capability | sonnet |
| tester | Runs tests, reports failures | sonnet |
| researcher | Researches solutions and packages | sonnet |
| documenter | Documentation and reference files | sonnet |

### Team Coordinators (6)
| Coordinator | Team | Purpose |
|-------------|------|---------|
| review-team-coordinator | Parallel Review | Coordinates parallel code reviews |
| feature-team-coordinator | Cross-Layer Feature | Coordinates cross-module feature dev |
| hypothesis-team-coordinator | Competing Hypotheses | Manages parallel investigation |
| research-swarm-coordinator | Research Swarm | Coordinates parallel research |
| plan-execute-coordinator | Plan-Then-Execute | Plans then coordinates execution |
| prd-team-coordinator | PRD Decomposition | Decomposes PRDs into tasks |

### Specialist Agents (7)
| Agent | Purpose | Model |
|-------|---------|-------|
| skill-builder | Creates/modifies skills | sonnet |
| requirements-extractor | Extracts structured requirements | sonnet |
| technical-researcher | Codebase + tech research | sonnet |
| architecture-designer | Architecture design | opus |
| task-decomposer | Task breakdown | sonnet |
| risk-assessor | Risk identification (read-only) | sonnet |
| system-architect | Creates new agents/teams/skills | opus |

## Agent Skills

| Skill | Location | Used By |
|-------|----------|---------|
| coding-conventions | \`.claude/skills/coding-conventions/\` | all agents |
| team-coordination | \`.claude/skills/team-coordination/\` | all coordinators |
| security-standards | \`.claude/skills/security-standards/\` | reviewer, risk-assessor |
| research-patterns | \`.claude/skills/research-patterns/\` | researcher, technical-researcher |

## Mandatory Practices

1. **Grep Local Codebase FIRST**: Before writing ANY code, grep THIS project
2. **Grep MCP**: Use \`grep_query\` to search GitHub for battle-tested code
3. **LSP After Every Edit**: \`getDiagnostics\` after EVERY edit
4. **Plan Before Execute**: Outline plan BEFORE non-trivial changes
5. **Learn From Mistakes**: Read \`LEARNINGS.md\` at start, write learnings at end
6. **Task Management**: ALL work tracked via TaskUpdate

## Detected Commands

\`\`\`bash
${RUN_CMD:+# Run}
${RUN_CMD:-# Run: not detected}
${RUN_CMD:+$RUN_CMD}
${TEST_CMD:+# Tests}
${TEST_CMD:-# Tests: not detected}
${TEST_CMD:+$TEST_CMD}
${FORMATTER_CMD:+# Format}
${FORMATTER_CMD:-# Format: not detected}
${FORMATTER_CMD:+$FORMATTER_CMD}
${LINTER_CMD:+# Lint}
${LINTER_CMD:-# Lint: not detected}
${LINTER_CMD:+$LINTER_CMD}
${TYPE_CHECKER_CMD:+# Type check}
${TYPE_CHECKER_CMD:-# Type check: not detected}
${TYPE_CHECKER_CMD:+$TYPE_CHECKER_CMD}
${INSTALL_CMD:+# Install}
${INSTALL_CMD:-# Install: not detected}
${INSTALL_CMD:+$INSTALL_CMD}
\`\`\`

## Protected Paths

$(echo "$PROTECTED_PATHS" | tr ',' '\n' | sed 's/^ *//;s/ *$//' | while read -r p; do echo "- \`$p\`"; done)

## Retry Limits

| Operation | Max Retries | On Failure |
|-----------|-------------|------------|
| Build + Test | 3 | Escalate to orchestrator |
| Review + Fix | 5 | Escalate to orchestrator |
| Research | 2 | Report partial findings |
"
  fi

  # Append or create
  if [ -f "CLAUDE.md" ]; then
    echo "$section" >> "CLAUDE.md"
    echo -e "  ${GREEN}APPEND${NC}: CLAUDE.md (agent team section)"
  else
    echo "$section" > "CLAUDE.md"
    echo -e "  ${GREEN}CREATE${NC}: CLAUDE.md"
  fi
}

###############################################################################
# Generate: Lite profile (3 agents)
###############################################################################
generate_lite() {
  echo ""
  echo -e "${BLUE}${BOLD}Generating Lite profile (3 agents)...${NC}"
  echo ""

  generate_settings_json
  generate_learnings
  generate_reports_dir
  generate_coding_conventions_skill
  generate_orchestrator
  generate_builder
  generate_tester
  append_claude_md_section
}

###############################################################################
# Generate: Full profile (19 agents)
###############################################################################
generate_full() {
  echo ""
  echo -e "${BLUE}${BOLD}Generating Full profile (19 agents)...${NC}"
  echo ""

  # Settings and shared files
  generate_settings_json
  generate_learnings
  generate_reports_dir

  # Skills (4)
  generate_coding_conventions_skill
  generate_team_coordination_skill
  generate_security_standards_skill
  generate_research_patterns_skill

  # Core agents (6)
  generate_orchestrator
  generate_builder
  generate_tester
  generate_reviewer
  generate_researcher
  generate_documenter

  # Specialist agents (3)
  generate_skill_builder
  generate_system_architect
  generate_risk_assessor

  # Coordinators (6)
  generate_coordinator \
    "review-team-coordinator" \
    "parallel code reviews" \
    "Coordinates parallel code reviews with reviewer + tester agents. Use
  PROACTIVELY when user asks for \"review\", \"check code\", \"audit\", \"code review\",
  \"full review\", \"security audit\", \"quality check\"." \
    "team-registry/parallel-review-team.md" \
    "review-coordinator"

  generate_coordinator \
    "feature-team-coordinator" \
    "cross-module feature development" \
    "Coordinates cross-module feature development with builder + skill-builder +
  tester + reviewer. Use PROACTIVELY when user asks to \"build a feature\",
  \"add a feature\", \"implement [complex feature]\", \"create [multi-module change]\"." \
    "team-registry/cross-layer-feature-team.md" \
    "feature-coordinator"

  generate_coordinator \
    "hypothesis-team-coordinator" \
    "parallel investigation of competing hypotheses" \
    "Manages parallel investigation of competing hypotheses for complex problems.
  Use PROACTIVELY when user asks to \"debug complex issue\", \"compare approaches\",
  \"investigate [unclear problem]\", \"find root cause\", \"which approach is better?\"." \
    "team-registry/competing-hypotheses-team.md" \
    "hypothesis-coordinator"

  generate_coordinator \
    "research-swarm-coordinator" \
    "parallel research across sources and topics" \
    "Coordinates parallel research across multiple sources and topics. Use
  PROACTIVELY when user asks to \"research [broad topic]\", \"find library\",
  \"evaluate options\", \"compare packages\", \"survey available solutions\"." \
    "team-registry/research-swarm-team.md" \
    "research-coordinator"

  generate_coordinator \
    "plan-execute-coordinator" \
    "plan-then-execute workflow" \
    "Plans implementation strategies then coordinates execution. Use PROACTIVELY
  when user asks to \"refactor\", \"migrate\", \"multi-step change\", \"reorganize\",
  \"restructure\", \"convert from X to Y\", \"upgrade [pattern]\"." \
    "team-registry/plan-then-execute-team.md" \
    "plan-execute-coordinator"

  generate_prd_coordinator

  # PRD specialists (4)
  generate_requirements_extractor
  generate_technical_researcher
  generate_architecture_designer
  generate_task_decomposer

  # Team registry
  generate_team_registry

  # Validation scripts
  generate_validation_scripts

  # CLAUDE.md
  append_claude_md_section
}

###############################################################################
# Step 5: Verify
###############################################################################
verify_setup() {
  echo ""
  echo -e "${BLUE}${BOLD}Verification${NC}"
  echo ""

  local agent_count=0
  local skill_count=0
  local team_count=0
  local errors=0

  # Count agents
  if [ -d ".claude/agents" ]; then
    agent_count=$(find .claude/agents -name "*.md" -type f 2>/dev/null | wc -l | tr -d ' ')
  fi

  # Count skills
  if [ -d ".claude/skills" ]; then
    skill_count=$(find .claude/skills -name "SKILL.md" -type f 2>/dev/null | wc -l | tr -d ' ')
  fi

  # Count team definitions
  if [ -d "team-registry" ]; then
    team_count=$(find team-registry -maxdepth 1 -name "*-team.md" -type f 2>/dev/null | wc -l | tr -d ' ')
  fi

  # Verify critical files
  echo -e "  Agent files:      ${GREEN}${agent_count}${NC}"
  echo -e "  Skill files:      ${GREEN}${skill_count}${NC}"
  echo -e "  Team definitions: ${GREEN}${team_count}${NC}"

  if [ -f ".claude/settings.json" ]; then
    echo -e "  settings.json:    ${GREEN}OK${NC}"
  else
    echo -e "  settings.json:    ${RED}MISSING${NC}"
    ((errors++))
  fi

  if [ -f "LEARNINGS.md" ]; then
    echo -e "  LEARNINGS.md:     ${GREEN}OK${NC}"
  else
    echo -e "  LEARNINGS.md:     ${RED}MISSING${NC}"
    ((errors++))
  fi

  if [ -d "reports" ]; then
    echo -e "  reports/:         ${GREEN}OK${NC}"
  else
    echo -e "  reports/:         ${RED}MISSING${NC}"
    ((errors++))
  fi

  if [ -f "CLAUDE.md" ] && grep -q "Agent Team System" "CLAUDE.md" 2>/dev/null; then
    echo -e "  CLAUDE.md:        ${GREEN}OK${NC} (agent team section present)"
  else
    echo -e "  CLAUDE.md:        ${YELLOW}WARN${NC} (agent team section may be missing)"
  fi

  echo ""

  # Expected counts
  if [ "$PROFILE" = "lite" ]; then
    if [ "$agent_count" -lt 3 ]; then
      echo -e "  ${YELLOW}WARN${NC}: Expected 3 agents, found ${agent_count}"
    fi
    if [ "$skill_count" -lt 1 ]; then
      echo -e "  ${YELLOW}WARN${NC}: Expected 1 skill, found ${skill_count}"
    fi
  else
    if [ "$agent_count" -lt 19 ]; then
      echo -e "  ${YELLOW}WARN${NC}: Expected 19 agents, found ${agent_count}"
    fi
    if [ "$skill_count" -lt 4 ]; then
      echo -e "  ${YELLOW}WARN${NC}: Expected 4 skills, found ${skill_count}"
    fi
    if [ "$team_count" -lt 6 ]; then
      echo -e "  ${YELLOW}WARN${NC}: Expected 6 team definitions, found ${team_count}"
    fi
  fi

  if [ "$errors" -gt 0 ]; then
    echo -e "  ${RED}${errors} error(s) found.${NC}"
  fi
}

###############################################################################
# Step 6: Update global settings
###############################################################################
update_global_settings() {
  echo ""
  echo -e "${YELLOW}Checking global Claude settings...${NC}"

  local global_settings="$HOME/.claude/settings.json"

  if [ -f "$global_settings" ]; then
    # Check if grep-mcp is already configured
    if grep -q "grep-mcp" "$global_settings" 2>/dev/null; then
      echo -e "  ${GREEN}OK${NC}: grep-mcp already in global settings"
      return
    fi
  fi

  echo ""
  read -r -p "$(echo -e "  Add grep-mcp to global settings (${global_settings})? (y/N): ")" add_global
  if [ "$add_global" = "y" ] || [ "$add_global" = "Y" ]; then
    ensure_dir "$HOME/.claude"

    if [ -f "$global_settings" ]; then
      # Try to merge -- but if JSON is complex, just warn
      echo -e "  ${YELLOW}NOTE${NC}: Global settings exist. Please manually add grep-mcp if not present."
      echo -e "  Add this to mcpServers:"
      echo -e "    \"grep-mcp\": { \"command\": \"uvx\", \"args\": [\"grep-mcp\"] }"
    else
      cat > "$global_settings" << 'GLOBAL_EOF'
{
  "customInstructions": "MANDATORY: Grep local codebase FIRST. Then use grep-mcp (grep_query tool) to search GitHub. Keep LEARNINGS.md entries to 1 line, max 120 chars.",
  "mcpServers": {
    "grep-mcp": {
      "command": "uvx",
      "args": ["grep-mcp"]
    }
  }
}
GLOBAL_EOF
      echo -e "  ${GREEN}CREATE${NC}: $global_settings"
    fi
  fi
}

###############################################################################
# Main
###############################################################################
main() {
  print_banner
  detect_stack
  prompt_config

  # Confirmation
  echo -e "${BOLD}Configuration Summary:${NC}"
  echo -e "  Project:     ${CYAN}${PROJECT_NAME}${NC}"
  echo -e "  Language:    ${CYAN}${LANGUAGE}${NC}"
  echo -e "  Profile:     ${CYAN}${PROFILE}${NC}"
  echo -e "  Source:      ${CYAN}${SRC_DIR}${NC}"
  echo -e "  Tests:       ${CYAN}${TESTS_DIR}${NC}"
  echo -e "  Formatter:   ${CYAN}${FORMATTER:-none}${NC}"
  echo -e "  Linter:      ${CYAN}${LINTER:-none}${NC}"
  echo -e "  Type check:  ${CYAN}${TYPE_CHECKER:-none}${NC}"
  echo -e "  Test runner: ${CYAN}${TEST_RUNNER:-none}${NC}"
  echo -e "  Protected:   ${CYAN}${PROTECTED_PATHS}${NC}"
  echo ""

  read -r -p "$(echo -e "${BOLD}Proceed? (Y/n):${NC} ")" confirm
  if [ "$confirm" = "n" ] || [ "$confirm" = "N" ]; then
    echo -e "${RED}Aborted.${NC}"
    exit 0
  fi

  if [ "$PROFILE" = "lite" ]; then
    generate_lite
  else
    generate_full
  fi

  verify_setup
  update_global_settings

  echo ""
  echo -e "${GREEN}${BOLD}+==========================================+${NC}"
  echo -e "${GREEN}${BOLD}|  Agent team system installed!             |${NC}"
  echo -e "${GREEN}${BOLD}|  Profile: ${PROFILE}                            |${NC}"
  echo -e "${GREEN}${BOLD}+==========================================+${NC}"
  echo ""
  echo -e "Next steps:"
  echo -e "  1. Review the generated files in .claude/agents/"
  echo -e "  2. Customize agent descriptions for your project"
  echo -e "  3. Start using agents via Claude Code"
  echo ""
}

main "$@"
