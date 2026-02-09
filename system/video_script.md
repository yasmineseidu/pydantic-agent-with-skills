Pydantic AI Skills Agent with Evals and Logfire Observability
Video Outline

I. Introduction
Skills give you modular, reusable capabilities that save thousands of tokens
Progressive disclosure: load skill details only when needed
Build once, use across any agent
Pattern works with any framework, not just Claude - we can build skills into our own agents, and I’ll be using Pydantic AI as my agent framework in this video (my favorite)
Three phases for doing this reliably: implementation, validation, observability
II. Why Skills Matter
A. Core Benefits

Progressive disclosure reduces token costs significantly
Modular, reusable capabilities across agents
Works with any framework
Separates skill discovery from execution

B. How It Works

Directory structure: SKILL.md + reference docs
Loading mechanism: manifest first, references on-demand
Token savings: thousands per conversation
Compare with loading everything upfront
III. Building the Agent
A. Overview

Quick walkthrough of Pydantic AI agent with CLI
Visualize tool calls for debugging
How skill discovery and loading works

B. Live Demo

Weather skill: Simple example
Code review skill: Complex multi-reference example
Walkthrough of request → skill loading → execution
IV. Creating Skills
A. Skill Structure

Weather skill: components and layout
Code review skill: manifest + references
Best practices for SKILL.md files

B. Pydantic AI Integration (code dive)

Showcase the skill loading mechanism (toolset for reusability)
Expose skills to agents
Handle errors and edge cases
V. Evals: Validating Skill Usage
A. Setup

Pydantic AI's built-in eval system
YAML test datasets: questions → expected tools

B. Evaluators

Custom evaluator for tool call verification - "Did the agent pick the right skill?"
LLM-as-judge evaluator for overall response quality
Run evals and interpret results
VI. Production Monitoring
A. Why Evals Aren't Enough

Runtime behavior differs from tests
Need production anomaly detection

B. Logfire

Instrument agent for telemetry
Configure dashboard for tool call monitoring
Analyze skill usage patterns in real-time
VII. Wrap Up
You've got the full pattern: build skills, validate with evals, monitor in production
Works with whatever framework you're using
Start simple, add observability as you scale
Links and resources in description (including skill toolset)
