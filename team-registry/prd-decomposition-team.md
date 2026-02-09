# Team: PRD Decomposition

## Purpose
Takes a feature idea in any form (verbal description, rough notes, uploaded doc,
conversation) and produces a complete, decomposed, build-ready task tree.
Every task is atomic -- one agent can complete it in one session.

## When to Use
- Starting a new feature or major change
- User says "plan", "design", "break down", "decompose", "PRD", "spec", "architect"
- User says "I want to build...", "let's plan...", "figure out what we need for..."
- User provides a requirements doc and wants it turned into tasks
- Before any Plan-Then-Execute team run

## Modes

### Fresh Codebase Mode (no existing code to integrate with)
1. Extract requirements from user input
2. Research best practices via Grep MCP and web search
3. Design architecture (data model, API design, component structure)
4. Produce PRD document
5. Decompose into atomic tasks with dependencies
6. Present for approval

### Existing Codebase Mode (integrating into current code)
1. Extract requirements from user input
2. Scan existing codebase via LSP and Grep
3. Map integration points (what exists, what needs changing, what's new)
4. Research patterns that match existing architecture
5. Design changes that respect current conventions
6. Produce PRD document with "existing" vs "new" clearly marked
7. Decompose into atomic tasks -- some modify existing, some create new
8. Present for approval

## Team Members

### Coordinator
- Agent: .claude/agents/prd-team-coordinator.md
- Model: opus
- Role: Manages the decomposition process, drives the interview,
  synthesizes team output, produces final task tree, presents for approval

### Requirements Extractor
- Agent: .claude/agents/requirements-extractor.md
- Model: sonnet (default), opus when complexity score >= 7 or ambiguity >= 2
- Role: Interviews user, extracts structured requirements from unstructured input,
  identifies gaps, asks clarifying questions, produces requirements document
- Output: reports/prd/requirements.md

### Technical Researcher
- Agent: .claude/agents/technical-researcher.md
- Model: sonnet
- Role: Researches implementation approaches via Grep MCP and web search,
  finds reference implementations, identifies libraries and patterns
- Output: reports/prd/technical-research.md

### Architecture Designer
- Agent: .claude/agents/architecture-designer.md
- Model: opus
- Role: Designs the technical architecture based on requirements and research.
  For existing codebases: maps current architecture first, designs changes that fit.
  Produces data models, API contracts, component structure, state management approach.
- Output: reports/prd/architecture.md

### Task Decomposer
- Agent: .claude/agents/task-decomposer.md
- Model: sonnet (default), opus when complexity score >= 7 or 15+ expected tasks
- Role: Takes the PRD and architecture, breaks into atomic task units.
  Each task has: title, description, acceptance criteria, agent assignment,
  file ownership, dependencies (addBlockedBy), estimated complexity.
  Produces the final task tree ready for TaskCreate.
- Output: reports/prd/task-tree.md

## Execution Pattern

### Phase 1: Extract (coordinator + requirements-extractor)
Coordinator spawns requirements-extractor with user's input.
Requirements-extractor interviews user (via coordinator relaying questions),
produces structured requirements document.
Coordinator reviews for gaps, may request another extraction round.

### Phase 2: Research (technical-researcher, parallel with Phase 1 completion)
FRESH MODE: Research best practices, libraries, patterns for the tech stack.
EXISTING MODE: Scan codebase via LSP documentSymbol, goToDefinition, findReferences
  to map current architecture. THEN research patterns that match.
Output: technical research document with recommended approaches.

### Phase 3: Design (architecture-designer)
Reads: requirements + research + (EXISTING: current codebase scan).
FRESH MODE: Designs architecture from scratch.
EXISTING MODE: Maps integration points, designs changes that fit existing patterns.
Output: architecture document with data models, API contracts, components.

### Phase 4: Decompose (task-decomposer)
Reads: requirements + architecture + research.
Breaks everything into atomic tasks.
EXISTING MODE: separates "modify existing" tasks from "create new" tasks.
Output: task tree document.

### Phase 5: Present (coordinator)
Coordinator synthesizes all outputs into a single PRD document.
Presents the PRD + task tree to user for approval.
User can request changes -- coordinator routes modifications to relevant member.
On approval, coordinator creates the full task tree via TaskCreate with dependencies.

## File Ownership
- Coordinator: reports/prd/ (creates directory), reports/prd/final-prd.md
- Requirements Extractor: reports/prd/requirements.md (exclusive)
- Technical Researcher: reports/prd/technical-research.md (exclusive)
- Architecture Designer: reports/prd/architecture.md (exclusive)
- Task Decomposer: reports/prd/task-tree.md (exclusive)
- Shared (append-only): learnings.md

## Communication Protocol
- Layer 1 (output files): always -- each member writes to their exclusive file
- Layer 3 (coordinator routing): always -- coordinator passes relevant context between phases
- Layer 2 (messages): not needed -- phases are sequential, coordinator handles handoffs

## Done Conditions
- requirements.md exists and covers all user requirements
- technical-research.md exists with implementation approaches
- architecture.md exists with data models, APIs, components
- task-tree.md exists with atomic tasks, dependencies, agent assignments
- final-prd.md synthesizes everything
- User has approved the plan
- TaskCreate called for every task in the tree (with addBlockedBy for deps)
- Run log written to team-registry/run-logs/

## What Worked

## What Didn't Work
