# Complete Guide: Pydantic Skill Agent

_For Non-Technical Readers_


## What This Is

**Simple Description**: This is an AI chatbot that can learn new abilities on the fly by reading instruction files, without needing to load everything into memory at once.

**Real-World Comparison**: Think of this like a doctor who does not memorize every medical textbook, but instead keeps a brief index of all textbooks on a shelf. When a patient describes symptoms, the doctor looks at the index, picks the right textbook, and reads only the relevant chapter. If the chapter mentions a reference table, the doctor flips to that appendix. This project gives an AI assistant the same ability: it only reads what it needs, when it needs it.

**Who Uses It**: Developers who want to build AI assistants that can handle many different tasks without running out of "brain space" (context window). Also serves as a workshop demonstration for teaching this pattern.

**What It Does For Them**:
- Lets an AI assistant support dozens or hundreds of skills without slowing down
- Each skill is a self-contained folder that anyone can create or modify
- The assistant only loads detailed instructions when it actually needs them, saving memory
- Works with multiple AI providers (OpenRouter, OpenAI, local models via Ollama)

**The Problem It Solves**: AI assistants have a limited amount of text they can "think about" at one time (the context window). If you try to load instructions for every possible task upfront, you fill that space quickly and the assistant becomes less effective. This project solves that by loading instructions in stages -- only what is needed, when it is needed.


---


## The Project Structure (Like a Filing Cabinet)

### Overview

```
pydantic-agent-with-skills/
|-- src/                  Main application code (the "engine")
|-- skills/               Skill library (the "instruction manuals")
|   |-- weather/          Weather lookup skill
|   |-- code_review/      Code quality review skill
|   |-- recipe_finder/    Recipe search skill
|   |-- research_assistant/ Academic paper search skill
|   |-- world_clock/      Timezone and world clock skill
|-- tests/                Quality checks
|   |-- evals/            AI behavior tests
|-- scripts/              Utility scripts for validation and testing
|-- pyproject.toml        Project metadata and dependencies
|-- .env.example          Template for configuration secrets
|-- uv.lock              Locked dependency versions
```


### Folder-by-Folder Breakdown


#### src/ -- The Engine Room

**What's Inside**: The core application code that makes everything work. This is where the AI assistant is defined, configured, and connected to skills.

**Why It Exists**: Separates the "how it works" logic from the skill content. You can change the engine without touching any skills, and vice versa.

**Think of it as**: The car engine. The skills are the destinations on the GPS -- the engine gets you there, but the destinations are defined separately.

**Important Files**:

- **agent.py**: The main AI assistant definition. Creates the assistant, wires it up with skills, and sets up optional performance monitoring (Logfire). This is the central hub that connects everything together.

- **cli.py**: The chat interface. When you run the application, this is what you see -- a terminal-based conversation window where you type messages and the assistant responds in real time. Shows you which tools the assistant is using as it works.

- **dependencies.py**: The supply kit. Packages up everything the assistant needs to do its job (settings, skill loader) into a single bundle that gets passed around. Like packing a toolbox before heading to a job site.

- **skill_loader.py**: The librarian. Scans the skills folder, reads the brief summary at the top of each skill file, and builds an index of what skills are available. This index is what the assistant sees in its initial instructions.

- **skill_tools.py**: The three core actions the assistant can take with skills:
  1. "Load a skill" -- read the full instruction manual for a specific skill
  2. "Read a skill file" -- open a specific reference document within a skill
  3. "List skill files" -- see what reference documents are available in a skill
  Includes security checks to prevent the assistant from reading files outside of skill folders.

- **skill_toolset.py**: Packages the three skill actions (above) into a reusable tool bundle using Pydantic AI's toolset system. This makes it easy to register all three tools with the assistant at once.

- **http_tools.py**: The web browser. Gives the assistant the ability to fetch data from the internet (GET requests) and send data to websites (POST requests). Used by skills like weather and recipes to call external APIs. Includes automatic retry logic for when services are temporarily busy.

- **providers.py**: The translator. Handles connecting to different AI services -- OpenRouter, OpenAI, or Ollama (a local AI server). Each service speaks a slightly different "dialect," and this file handles the translation so the rest of the code does not need to care which service is being used.

- **settings.py**: The settings panel. Reads configuration from a .env file (like which AI service to use, API keys, what folder contains skills). Uses Pydantic Settings for automatic validation -- if a required setting is missing, it tells you exactly what is wrong.

- **prompts.py**: The script. Contains the master instructions that the assistant follows. This template includes a slot where skill summaries get injected, tells the assistant how to use skills, and provides examples of correct behavior.

**How Files Connect**:
```
settings.py (reads .env config)
    |
    v
providers.py (creates AI connection)
    |
    v
agent.py (creates the assistant, loads prompts.py template)
    |
    +-- skill_toolset.py (registers skill tools)
    |       |
    |       +-- skill_tools.py (actual tool logic)
    |               |
    |               +-- skill_loader.py (finds and indexes skills)
    |
    +-- http_tools.py (web request tools)
    |
    v
cli.py (chat interface the user sees)
    |
    +-- dependencies.py (bundles everything together)
```


#### skills/ -- The Instruction Manuals

**What's Inside**: Five self-contained skill folders, each with its own instructions and reference materials. Anyone can add a new skill by creating a new folder with the right structure.

**Why It Exists**: Skills are separate from the engine so they can be added, removed, or updated independently. A new skill is just a new folder -- no code changes needed.

**Think of it as**: A bookshelf of instruction manuals. Each manual covers one topic, has a brief summary on the cover, detailed instructions inside, and appendix materials at the back.

**Each Skill Folder Contains**:
- **SKILL.md**: The main instruction file. Has a brief machine-readable summary at the top (name, description) and detailed step-by-step instructions below.
- **references/**: Supporting documents like API documentation, checklists, and guides.
- **scripts/**: Optional helper scripts (only the code review skill has one).

**The Five Skills**:

| Skill | What It Does | External Service Used |
|-------|-------------|----------------------|
| **weather** | Looks up current weather for any city | Open-Meteo API (free, no key needed) |
| **code_review** | Reviews code for quality, security, and bad patterns | None (uses its own checklists) |
| **recipe_finder** | Searches for recipes by ingredients, cuisine, or diet | TheMealDB and Spoonacular APIs |
| **research_assistant** | Finds academic papers and citations | Semantic Scholar API (free) |
| **world_clock** | Gets current time in any timezone | WorldTimeAPI (free) |


#### tests/ -- Quality Checks

**What's Inside**: Automated tests that verify the system works correctly, plus evaluation tests that check the AI assistant's behavior.

**Why It Exists**: Every time someone changes the code, these tests run to make sure nothing is broken. They catch problems before they reach users.

**Think of it as**: A quality inspector who runs through a checklist every time a product comes off the assembly line.

**Important Files**:

- **test_skill_loader.py**: 11 tests that verify the librarian (skill loader) correctly finds skills, reads their summaries, handles missing or broken skill files gracefully, and generates the right index.

- **test_skill_tools.py**: 12 tests that verify the three skill actions work correctly -- loading skills, reading files, listing files, handling errors, and blocking unauthorized file access (security).

- **test_agent.py**: 25 tests that verify the full system works together -- that all skills are discovered, tools are registered, the system prompt contains skill information, skills can be loaded and read, and reference files are substantial enough to be useful.

- **evals/**: A separate evaluation system that tests the AI's actual behavior (not just the code). Sends real questions to the AI and checks whether it correctly identifies and loads the right skill. For example: "What's the weather in New York?" should trigger the weather skill.


#### scripts/ -- Utility Tools

**What's Inside**: Helper scripts for validating skills and running the full test pipeline.

**Why It Exists**: Makes it easy to check that everything is working with a single command.

**Important Files**:

- **validate_skills.py**: Checks every skill folder has the right structure (SKILL.md exists, frontmatter is present, reference folders are not empty).

- **run_full_validation.py**: Runs everything in sequence: unit tests, integration tests, skill validation, and AI behavior evaluations. A one-command health check.

- **test_agent.py**: Sends predefined questions to the assistant and displays the responses. Useful for manually checking how the assistant handles different types of requests.


---


## How Everything Works Together


### The Three-Level System (Progressive Disclosure)

This is the key innovation. Instead of loading all instructions upfront, the system reveals information in three stages:

```
LEVEL 1: Summaries (always loaded)
+------------------------------------------+
| weather: Get weather for locations       |  ~20 words per skill
| code_review: Review code quality         |  Always in the assistant's
| recipe_finder: Search recipes            |  initial instructions
| research_assistant: Find papers          |
| world_clock: Get time in timezones       |
+------------------------------------------+

         | User asks a question
         | Assistant checks summaries
         v

LEVEL 2: Full Instructions (loaded on demand)
+------------------------------------------+
| # Weather Skill                          |
| Step 1: Identify the location            |  Full multi-page
| Step 2: Look up coordinates              |  instruction manual
| Step 3: Call the weather API             |  Only loaded when
| Step 4: Format the response              |  the skill is needed
| ...                                      |
+------------------------------------------+

         | Instructions mention a reference
         | Assistant loads the specific file
         v

LEVEL 3: Reference Documents (loaded on demand)
+------------------------------------------+
| # Open-Meteo API Reference              |
| Endpoint: api.open-meteo.com/v1/...     |  Detailed technical
| Parameters:                              |  reference material
|   latitude: float                        |  Only loaded when
|   longitude: float                       |  specifically needed
| ...                                      |
+------------------------------------------+
```

**Why this matters**: If all five skills loaded everything upfront, the assistant would need to process thousands of words of instructions before answering a single question. With progressive disclosure, it starts with about 100 words total (the summaries) and only loads more when relevant.


### A Typical Conversation

**User types**: "What's the weather in Tokyo?"

Here is what happens behind the scenes:

```
1. User types question
       |
       v
2. CLI (cli.py) sends question to the assistant
       |
       v
3. Assistant reads its system prompt, which contains:
   "weather: Get weather information for locations"
       |
       v
4. Assistant decides: "This is a weather question"
   Calls tool: load_skill_tool("weather")
       |
       v
5. skill_tools.py reads skills/weather/SKILL.md
   Returns full instructions (coordinates table, API details, etc.)
       |
       v
6. Assistant reads instructions, finds Tokyo coordinates (35.69, 139.69)
   Instructions say: "read references/api_reference.md for API params"
   Calls tool: read_skill_file_tool("weather", "references/api_reference.md")
       |
       v
7. skill_tools.py reads the API reference file, returns it
       |
       v
8. Assistant constructs the API URL with correct parameters
   Calls tool: http_get_tool("https://api.open-meteo.com/v1/forecast?...")
       |
       v
9. http_tools.py fetches weather data from the internet
   Returns JSON with temperature, conditions, etc.
       |
       v
10. Assistant formats a friendly response:
    "It's currently 18C (64F) and partly cloudy in Tokyo..."
       |
       v
11. CLI streams the response to the user's screen in real time
```


### Data Flow

```
User Input --> CLI --> Agent --> System Prompt (Level 1 summaries)
                                    |
                                    v
                              Skill Tools (Level 2 instructions)
                                    |
                                    v
                              Skill Files (Level 3 references)
                                    |
                                    v
                              HTTP Tools --> External APIs
                                    |
                                    v
                              Agent formats response
                                    |
                                    v
                              CLI streams to user
```


---


## Technologies Used (Plain English)


### Python 3.11
- **What it is**: The programming language everything is written in. A general-purpose language known for being readable and having a large ecosystem of tools.
- **Why this one**: Good for AI applications, has strong typing support, and the Pydantic AI framework requires it.


### Pydantic AI
- **What it is**: A framework for building AI assistants. Provides the structure for creating an assistant, giving it tools, and managing conversations.
- **Why it is used**: Type-safe (catches errors early), supports streaming responses, and handles the complex plumbing of talking to AI services.
- **What it provides**: The Agent class, tool registration, dependency injection, and conversation management.


### Pydantic / Pydantic Settings
- **What it is**: A data validation library. When you define what shape your data should have, Pydantic checks that incoming data matches and gives clear error messages if it does not.
- **Why it is used**: Ensures skill metadata is well-formed, settings are valid, and configuration errors are caught early with helpful messages.


### Rich
- **What it is**: A library for making terminal output look polished -- colored text, tables, panels, progress indicators.
- **Why it is used**: Makes the chat interface and validation reports visually clear and easy to read.


### PyYAML
- **What it is**: A library for reading YAML files. YAML is a human-readable data format (like a simplified version of a spreadsheet).
- **Why it is used**: Each skill's summary (name, description, version) is written in YAML at the top of its SKILL.md file. This library reads that structured data.


### httpx
- **What it is**: A modern library for making web requests. Like a web browser that code can use to fetch data from websites and APIs.
- **Why it is used**: The weather, recipe, research, and world clock skills all need to fetch data from external services on the internet.


### Logfire (Optional)
- **What it is**: A monitoring service that tracks what the assistant is doing -- which tools it calls, how long requests take, and whether errors occur.
- **Why it is used**: Helps developers understand and debug the assistant's behavior. Completely optional; the system works without it.


### uv
- **What it is**: A fast Python package manager. Handles installing libraries and managing the project environment.
- **Why it is used**: Faster and more reliable than the standard pip tool for managing dependencies.


### External APIs (Used by Skills)

| Service | Used By | What It Does | Cost |
|---------|---------|-------------|------|
| Open-Meteo | Weather skill | Provides weather data worldwide | Free, no key needed |
| TheMealDB | Recipe skill | Recipe search database | Free, no key needed |
| Spoonacular | Recipe skill | Advanced recipe and nutrition data | Free tier (150 calls/day) |
| Semantic Scholar | Research skill | Academic paper database (214M+ papers) | Free, no key needed |
| WorldTimeAPI | World Clock skill | Current time in any timezone | Free, no key needed |
| OpenRouter | AI Provider | Routes requests to various AI models | Pay per use |
| OpenAI | AI Provider (alt) | Direct access to OpenAI models | Pay per use |
| Ollama | AI Provider (alt) | Run AI models locally on your computer | Free (local) |


---


## Security and Privacy


### How User Data Is Protected

- **Directory traversal prevention**: When the assistant reads skill files, the system verifies the requested file is actually inside the skill folder. This prevents the assistant from being tricked into reading sensitive files elsewhere on the computer.

- **No credentials in code**: API keys and secrets are stored in a .env file that is excluded from version control (listed in .gitignore). The .env.example file shows what settings are needed without exposing actual values.

- **Input validation**: All configuration is validated through Pydantic Settings. Invalid or missing values produce clear error messages rather than silent failures.


### What Data Flows Where

- **User messages** go to whichever AI provider is configured (OpenRouter, OpenAI, or Ollama)
- **Skill content** stays local -- it is read from files on disk and passed to the AI provider as part of the conversation
- **API calls** (weather, recipes, etc.) go to free public APIs with no user-identifying information
- **Logfire monitoring** (if enabled) sends telemetry data to the Logfire service


---


## Testing and Quality


### How We Know It Works

Three layers of testing ensure quality:

**Layer 1 -- Unit Tests (48 tests)**
Tests individual components in isolation. Examples: "Does the skill loader correctly parse YAML frontmatter?" and "Does the directory traversal security check actually block unauthorized file access?"

**Layer 2 -- Integration Tests (25 tests)**
Tests components working together. Examples: "Can the full agent discover all five skills?" and "Does loading a skill return its complete instructions without the metadata header?"

**Layer 3 -- AI Behavior Evaluations (8 test cases)**
Tests the actual AI assistant's decision-making. Sends real questions and checks: "Did the assistant load the correct skill?" and "Did the assistant call the right tools?" and "Is the response long enough to be useful?"

**Validation Pipeline**:
All three layers can be run with a single command (`python -m scripts.run_full_validation`), which executes them in order and produces a pass/fail summary.


---


## Key Concepts Explained


### Progressive Disclosure
**Simple explanation**: Revealing information in stages -- start with a brief summary, then provide full details only when needed.
**Like**: A restaurant menu shows dish names and short descriptions. You only ask for the full recipe or allergen information when you are interested in a specific dish.
**How it is used here**: The assistant starts with one-line skill summaries. Full instructions are loaded only when relevant to the user's question.


### Context Window
**Simple explanation**: The limited amount of text an AI can "think about" at one time.
**Like**: A person's working memory -- you can only hold so many things in mind at once. Writing notes lets you handle more, but your desk only has so much space.
**How it is used here**: Progressive disclosure keeps the context window free for the actual conversation, only loading skill instructions when needed.


### Dependency Injection
**Simple explanation**: Instead of each part of the system finding what it needs on its own, everything it needs is handed to it from outside.
**Like**: A chef being handed ingredients by a prep cook, rather than having to go to the pantry every time.
**How it is used here**: The AgentDependencies class bundles the skill loader and settings together, and passes them to every tool that needs them.


### YAML Frontmatter
**Simple explanation**: A block of structured data at the very top of a text file, enclosed in triple dashes (---).
**Like**: The label on a file folder -- quick facts (name, category, date) before you open the folder and read the contents.
**How it is used here**: Each SKILL.md starts with YAML frontmatter containing the skill name and description. The system reads just this header to build the index, without reading the full instructions.


### Toolsets
**Simple explanation**: A bundle of related actions that the AI assistant can perform.
**Like**: A Swiss Army knife -- one object that contains a blade, a screwdriver, and a bottle opener. You register the whole knife, not each tool individually.
**How it is used here**: The three skill-related tools (load, read file, list files) are bundled into a single toolset and registered with the assistant all at once.


---


## Glossary

**Agent**: An AI assistant that can use tools and follow instructions to complete tasks.

**API (Application Programming Interface)**: A way for programs to request data from external services. Like ordering from a menu at a restaurant -- you make a specific request, and the kitchen (server) prepares and delivers the result.

**CLI (Command Line Interface)**: A text-based interface where you type commands and see text responses. The terminal or command prompt on your computer.

**Context Window**: The maximum amount of text an AI model can process in a single conversation. Measured in tokens (roughly 3/4 of a word each).

**Dependency Injection**: A design pattern where components receive their dependencies from outside rather than creating them internally.

**Frontmatter**: Structured metadata at the top of a file, typically in YAML format between --- delimiters.

**Pydantic**: A Python library for data validation using type annotations.

**Streaming**: Displaying the AI's response word by word as it is generated, rather than waiting for the complete response.

**Token**: The smallest unit of text that an AI model processes. Roughly equivalent to 3/4 of a word.

**Toolset**: A collection of related tools bundled together for registration with an AI agent.

**YAML**: A human-readable data format used for configuration files. Uses indentation and colons to represent structured data.


---


## Common Questions

**Q: How do I run this?**
A: Install Python 3.11+, copy .env.example to .env, fill in your API key, install dependencies with `uv pip install -e .`, then run `python -m src.cli` to start chatting.

**Q: How do I add a new skill?**
A: Create a new folder inside `skills/` with a SKILL.md file that has a YAML header (name and description) and body instructions. Optionally add a `references/` subfolder with supporting documents. The system discovers new skills automatically on startup.

**Q: What AI models does it work with?**
A: Any model available through OpenRouter (Claude, GPT, Llama, Mistral, and many others), OpenAI directly, or local models via Ollama. The default is Claude Sonnet 4.5 through OpenRouter.

**Q: Is this free to run?**
A: The skill system itself is free. The external APIs used by skills (weather, recipes, etc.) are all free. The only cost is the AI model usage, which depends on your provider and model choice. Using Ollama with a local model is completely free.

**Q: What happens if something breaks?**
A: The system is designed to fail gracefully. Missing skills are skipped with a warning. Bad YAML frontmatter is logged and the skill is ignored. Failed API calls return clear error messages. The assistant continues working even if individual skills have problems.

**Q: How many skills can it handle?**
A: Practically unlimited. Each skill adds only about 20 words to the initial system prompt (Level 1 summary). Even with 100 skills, that is only about 2,000 words of summaries -- well within any model's context window. Full instructions are only loaded when needed.

**Q: Is it secure?**
A: The system includes directory traversal protection (the assistant cannot read files outside skill folders), configuration secrets are kept in .env files excluded from version control, and input validation catches configuration errors early. API keys are never logged.


---


## Summary

**In One Sentence**: A Python-based AI assistant framework that uses a three-level progressive disclosure system to support many modular skills without overloading the AI's context window.

**Key Points**:
- Skills are self-contained folders with instructions and reference materials that anyone can create
- The three-level loading system (summaries, instructions, references) keeps the AI focused and efficient
- Works with multiple AI providers and free external APIs out of the box
- Includes comprehensive testing across unit tests, integration tests, and AI behavior evaluations

**For Business Stakeholders**:
- **Value**: Demonstrates how to build AI assistants that scale to handle many capabilities without degradation
- **Capability**: Framework-agnostic pattern that is not locked to any single AI vendor
- **Impact**: Reduces AI token costs by only loading relevant instructions, improves response quality by providing focused context, and makes the system extensible by non-developers who can create skills in plain text files
