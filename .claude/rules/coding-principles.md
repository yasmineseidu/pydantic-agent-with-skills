---
paths: ["src/**", "tests/**", "skills/**"]
---

# Core Principles

## 1. FRAMEWORK AGNOSTIC

- Skills work with any AI framework, not just Claude
- No vendor lock-in to Claude Desktop/Code
- Portable skills across different agent implementations

## 2. PROGRESSIVE DISCLOSURE IS KEY

- Level 1: Metadata in system prompt (~100 tokens/skill)
- Level 2: Full instructions loaded via tool call
- Level 3: Resources loaded via tool call only when referenced
- Never consume unnecessary context

## 3. TYPE SAFETY IS NON-NEGOTIABLE

- All functions, methods, and variables MUST have type annotations
- Use Pydantic models for all data structures (skills, metadata)
- No `Any` types without explicit justification
- Pydantic Settings for configuration

## 4. KISS (Keep It Simple, Stupid)

- Prefer simple, readable solutions over clever abstractions
- Don't build fallback mechanisms unless absolutely necessary
- Trust the progressive disclosure pattern - don't over-engineer

## 5. YAGNI (You Aren't Gonna Need It)

- Don't build features until they're actually needed
- MVP first, enhancements later
- Focus on demonstrating the core pattern

## 6. REFERENCE THE EXAMPLES FOLDER

- `examples/` contains production-quality MongoDB RAG agent
- **DO NOT MODIFY** files in `examples/` - they are reference only
- Copy patterns and code from examples, adapt for skills
- Maintain same architecture and design patterns
