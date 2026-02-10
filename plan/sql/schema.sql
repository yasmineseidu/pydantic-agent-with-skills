-- =============================================================================
-- MULTI-AGENT PLATFORM - COMPLETE DATABASE SCHEMA
-- =============================================================================
--
-- This file contains ALL tables, indexes, triggers, and functions needed
-- for the complete multi-agent platform. Tables are organized by the phase
-- in which they are introduced.
--
-- Total: 23 tables + extensions + enums + indexes + triggers + functions
--
-- Phase 1: Core (9 tables)  - user, team, team_membership, agent,
--                              conversation, message, memory, memory_log, memory_tag
-- Phase 4: Auth/API (4)     - api_key, refresh_token, usage_log, audit_log
-- Phase 6: Background (1)   - scheduled_job
-- Phase 7: Collaboration (7)- conversation_participant, agent_handoff, routing_decision_log,
--                              agent_task, agent_message, collaboration_session,
--                              collaboration_participant
-- Phase 9: Integrations (2) - platform_connection, webhook_delivery_log
--
-- Usage:
--   psql -d skill_agent -f schema.sql          # Full schema
--   alembic upgrade head                       # Via migrations (preferred)
--
-- =============================================================================


-- =============================================================================
-- EXTENSIONS
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";     -- gen_random_uuid() fallback
CREATE EXTENSION IF NOT EXISTS "pgcrypto";      -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "vector";        -- pgvector for embeddings


-- =============================================================================
-- ENUM TYPES
-- =============================================================================

CREATE TYPE user_role AS ENUM (
    'owner',
    'admin',
    'member',
    'viewer'
);

CREATE TYPE agent_status AS ENUM (
    'draft',        -- Being configured, not yet usable
    'active',       -- Accepting conversations
    'paused',       -- Temporarily unavailable
    'archived'      -- Soft-deleted, data preserved
);

CREATE TYPE message_role AS ENUM (
    'user',
    'assistant',
    'system',
    'tool'
);

CREATE TYPE memory_type_enum AS ENUM (
    'semantic',         -- Facts, preferences, knowledge
    'episodic',         -- Events, conversations, decisions
    'procedural',       -- Learned workflows, tool patterns
    'agent_private',    -- Per-agent learning, private insights
    'shared',           -- Team-wide knowledge
    'identity',         -- Agent self-knowledge (NEVER trimmed)
    'user_profile'      -- Persistent user facts across all agents
);

CREATE TYPE memory_status AS ENUM (
    'active',           -- Current, retrievable
    'superseded',       -- Replaced by newer version
    'archived',         -- Cold storage, still searchable
    'disputed'          -- Contradicts another memory, needs resolution
);

CREATE TYPE memory_tier AS ENUM (
    'hot',              -- Redis-cached, <5ms retrieval
    'warm',             -- PostgreSQL, <200ms retrieval (default)
    'cold'              -- Archived PostgreSQL, <2s retrieval
);

CREATE TYPE memory_source AS ENUM (
    'extraction',       -- LLM-extracted from conversation
    'explicit',         -- User said "remember this"
    'system',           -- System-generated (identity, defaults)
    'feedback',         -- Created/modified by user feedback
    'consolidation',    -- Created by memory consolidation job
    'compaction'        -- Created by compaction shield before context trim
);

CREATE TYPE conversation_status AS ENUM (
    'active',           -- Ongoing conversation
    'idle',             -- No messages for 30+ min
    'closed'            -- Explicitly ended
);

CREATE TYPE participant_role AS ENUM (
    'primary',          -- Main agent for this conversation
    'invited',          -- Added to multi-agent conversation
    'handoff_source'    -- Was primary before handoff
);

CREATE TYPE platform_type AS ENUM (
    'telegram',
    'slack',
    'discord',
    'whatsapp'
);

CREATE TYPE platform_status AS ENUM (
    'active',
    'paused',
    'error',
    'disconnected'
);


-- =============================================================================
-- PHASE 1: CORE TABLES (9 tables)
-- =============================================================================
-- These form the foundation. Must exist before all other phases.


-- ---------------------------------------------------------------------------
-- 1. user
-- ---------------------------------------------------------------------------
-- Platform users. Each user belongs to one or more teams.

CREATE TABLE "user" (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               TEXT NOT NULL,
    password_hash       TEXT NOT NULL,       -- bcrypt, min 12 rounds
    display_name        TEXT NOT NULL,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_user_email UNIQUE (email),
    CONSTRAINT ck_user_email_format CHECK (email ~* '^[^@]+@[^@]+\.[^@]+$')
);


-- ---------------------------------------------------------------------------
-- 2. team
-- ---------------------------------------------------------------------------
-- Multi-tenant root. ALL data is scoped to a team.

CREATE TABLE team (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL,
    slug                TEXT NOT NULL,       -- URL-safe unique identifier
    owner_id            UUID NOT NULL REFERENCES "user"(id),
    settings            JSONB NOT NULL DEFAULT '{}',
    -- Team-level shared skills available to all agents
    shared_skill_names  TEXT[] NOT NULL DEFAULT '{}',
    -- Webhook configuration (outbound events)
    webhook_url         TEXT,
    webhook_secret      TEXT,               -- HMAC-SHA256 signing secret
    -- Data retention settings
    conversation_retention_days INT NOT NULL DEFAULT 90,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_team_slug UNIQUE (slug),
    CONSTRAINT ck_team_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$')
);


-- ---------------------------------------------------------------------------
-- 3. team_membership
-- ---------------------------------------------------------------------------
-- RBAC: which users belong to which teams and with what role.

CREATE TABLE team_membership (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    role                user_role NOT NULL DEFAULT 'member',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_team_membership UNIQUE (user_id, team_id)
);


-- ---------------------------------------------------------------------------
-- 4. agent
-- ---------------------------------------------------------------------------
-- Stores AgentDNA (Section 3A). Each row is a complete agent identity.
-- Creating a new agent = INSERT one row. No code changes. No restart.

CREATE TABLE agent (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,

    -- === IDENTITY ===
    name                TEXT NOT NULL,       -- "Kyra" (display name)
    slug                TEXT NOT NULL,       -- "kyra" (URL-safe identifier)
    tagline             TEXT NOT NULL DEFAULT '',
    avatar_emoji        TEXT NOT NULL DEFAULT '',

    -- === PERSONALITY (serialized AgentPersonality) ===
    -- Contains: system_prompt_template, tone, verbosity, formality, language,
    --           traits, voice_examples, always_rules, never_rules, custom_instructions
    personality         JSONB NOT NULL DEFAULT '{}',

    -- === SKILLS ===
    shared_skill_names  TEXT[] NOT NULL DEFAULT '{}',   -- From team level
    custom_skill_names  TEXT[] NOT NULL DEFAULT '{}',   -- Agent-specific
    disabled_skill_names TEXT[] NOT NULL DEFAULT '{}',  -- Overrides shared

    -- === MODEL CONFIG (serialized AgentModelConfig) ===
    -- Contains: model_name, temperature, max_output_tokens, provider_overrides
    model_config_json   JSONB NOT NULL DEFAULT '{
        "model_name": "anthropic/claude-sonnet-4.5",
        "temperature": 0.7,
        "max_output_tokens": 4096
    }',

    -- === MEMORY CONFIG (serialized AgentMemoryConfig) ===
    -- Contains: token_budget, retrieval_weights, auto_extract, auto_pin_preferences,
    --           summarize_interval, remember_commands
    memory_config       JSONB NOT NULL DEFAULT '{
        "token_budget": 2000,
        "auto_extract": true,
        "auto_pin_preferences": true,
        "summarize_interval": 20,
        "retrieval_weights": {
            "semantic": 0.35,
            "recency": 0.20,
            "importance": 0.20,
            "continuity": 0.15,
            "relationship": 0.10
        }
    }',

    -- === BOUNDARIES (serialized AgentBoundaries) ===
    -- Contains: can_do, cannot_do, escalates_to, max_autonomy,
    --           allowed_domains, max_tool_calls_per_turn
    boundaries          JSONB NOT NULL DEFAULT '{
        "max_autonomy": "execute",
        "max_tool_calls_per_turn": 10
    }',

    -- === LIFECYCLE ===
    status              agent_status NOT NULL DEFAULT 'draft',
    created_by          UUID REFERENCES "user"(id),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_agent_team_slug UNIQUE (team_id, slug),
    CONSTRAINT ck_agent_slug_format CHECK (slug ~ '^[a-z0-9][a-z0-9-]*[a-z0-9]$')
);


-- ---------------------------------------------------------------------------
-- 5. conversation
-- ---------------------------------------------------------------------------
-- A conversation between a user and one or more agents.

CREATE TABLE conversation (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    agent_id            UUID NOT NULL REFERENCES agent(id),  -- Primary agent
    user_id             UUID NOT NULL REFERENCES "user"(id),
    title               TEXT,                -- Auto-generated from first message
    status              conversation_status NOT NULL DEFAULT 'active',
    message_count       INT NOT NULL DEFAULT 0,
    total_input_tokens  INT NOT NULL DEFAULT 0,
    total_output_tokens INT NOT NULL DEFAULT 0,
    summary             TEXT,                -- Rolling conversation summary
    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 6. message
-- ---------------------------------------------------------------------------
-- Individual messages within a conversation. Full history, never deleted.

CREATE TABLE message (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    -- Phase 7: which agent authored this message (NULL for user/system)
    agent_id            UUID REFERENCES agent(id),
    role                message_role NOT NULL,
    content             TEXT NOT NULL,
    -- Tool interactions
    tool_calls          JSONB,               -- [{name, args, id}]
    tool_results        JSONB,               -- [{tool_call_id, result}]
    -- Token usage for this message
    token_count         INT,
    model               TEXT,                -- Which LLM model generated this
    -- User feedback (Phase 22)
    feedback_rating     TEXT CHECK (feedback_rating IN ('positive', 'negative')),
    feedback_comment    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 7. memory (THE core table -- Section 3B)
-- ---------------------------------------------------------------------------
-- Single table for all 7 memory types (ADR-6: type discriminator).
-- Append-only semantics: memories are NEVER hard-deleted (ADR-8).
-- Superseded memories move to tier='cold', status='superseded'.

CREATE TABLE memory (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    agent_id            UUID REFERENCES agent(id),       -- NULL = shared/user-profile
    user_id             UUID REFERENCES "user"(id),      -- NULL = team-wide

    -- === CONTENT ===
    memory_type         memory_type_enum NOT NULL,
    content             TEXT NOT NULL,
    subject             TEXT,                -- Dot-notation: "user.preference.language"
    embedding           vector(1536),        -- pgvector embedding

    -- === SCORING ===
    importance          INT NOT NULL DEFAULT 5
                        CHECK (importance BETWEEN 1 AND 10),
    confidence          FLOAT NOT NULL DEFAULT 1.0
                        CHECK (confidence BETWEEN 0.0 AND 1.0),
    access_count        INT NOT NULL DEFAULT 0,
    is_pinned           BOOLEAN NOT NULL DEFAULT FALSE,

    -- === PROVENANCE ===
    source_type         memory_source NOT NULL DEFAULT 'extraction',
    source_conversation_id UUID REFERENCES conversation(id),
    source_message_ids  UUID[],              -- Exact messages this came from
    extraction_model    TEXT,                 -- Which LLM extracted this

    -- === VERSIONING & CONTRADICTIONS ===
    version             INT NOT NULL DEFAULT 1,
    superseded_by       UUID REFERENCES memory(id),     -- Newer version
    contradicts         UUID[],              -- IDs of conflicting memories

    -- === RELATIONSHIPS ===
    related_to          UUID[],              -- Soft links to related memories

    -- === METADATA ===
    -- Flexible JSONB for type-specific data:
    --   Procedural: {trigger, tool_sequence, success_rate, times_used}
    --   Tags, custom fields, etc.
    metadata            JSONB NOT NULL DEFAULT '{}',

    -- === LIFECYCLE ===
    tier                memory_tier NOT NULL DEFAULT 'warm',
    status              memory_status NOT NULL DEFAULT 'active',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_accessed_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at          TIMESTAMPTZ          -- NULL = never expires
);


-- ---------------------------------------------------------------------------
-- 8. memory_log (APPEND-ONLY AUDIT TRAIL -- Section 3B)
-- ---------------------------------------------------------------------------
-- NEVER modified. NEVER deleted. Every memory lifecycle event is recorded.
-- Enables point-in-time memory state reconstruction.
-- No FK on memory_id intentionally (survives even if memory row somehow lost).

CREATE TABLE memory_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id           UUID NOT NULL,       -- References memory(id) but NO FK
    action              TEXT NOT NULL,
    -- Actions: 'created', 'updated', 'superseded', 'promoted', 'demoted',
    --          'contradiction_detected', 'contradiction_resolved',
    --          'pinned', 'unpinned', 'accessed', 'expired',
    --          'consolidated', 'compaction_extracted'

    -- Change tracking
    old_content         TEXT,                -- NULL for 'created'
    new_content         TEXT,
    old_importance      INT,
    new_importance      INT,
    old_tier            TEXT,
    new_tier            TEXT,
    old_status          TEXT,
    new_status          TEXT,

    -- Attribution
    changed_by          TEXT NOT NULL,
    -- Values: 'system', 'user:{user_id}', 'consolidation', 'feedback',
    --         'compaction_shield', 'contradiction_detector', 'tier_manager'
    reason              TEXT,

    -- Provenance
    conversation_id     UUID,                -- Conversation context if applicable
    related_memory_ids  UUID[],              -- Other memories involved

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 9. memory_tag
-- ---------------------------------------------------------------------------
-- Categorical tagging for memories (searchable labels).

CREATE TABLE memory_tag (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id           UUID NOT NULL REFERENCES memory(id) ON DELETE CASCADE,
    tag                 TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_memory_tag UNIQUE (memory_id, tag)
);


-- =============================================================================
-- PHASE 4: AUTH & API TABLES (4 tables)
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 10. api_key
-- ---------------------------------------------------------------------------
-- Long-lived API keys for programmatic access (ska_ prefix).

CREATE TABLE api_key (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    user_id             UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,       -- "My CI/CD Key"
    key_hash            TEXT NOT NULL,       -- SHA-256 hash (never store plaintext)
    key_prefix          TEXT NOT NULL,       -- "ska_" + first 8 chars (for display)
    scopes              TEXT[] NOT NULL DEFAULT '{}',  -- Future: fine-grained perms
    last_used_at        TIMESTAMPTZ,
    expires_at          TIMESTAMPTZ,         -- NULL = never expires
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_api_key_hash UNIQUE (key_hash)
);


-- ---------------------------------------------------------------------------
-- 11. refresh_token
-- ---------------------------------------------------------------------------
-- Refresh tokens stored for revocation support.
-- Access tokens are stateless JWT (not stored).

CREATE TABLE refresh_token (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    token_hash          TEXT NOT NULL,       -- SHA-256 hash
    device_info         TEXT,                -- "Chrome/Mac", "API Client"
    expires_at          TIMESTAMPTZ NOT NULL,
    revoked_at          TIMESTAMPTZ,         -- NULL = active
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_refresh_token_hash UNIQUE (token_hash)
);


-- ---------------------------------------------------------------------------
-- 12. usage_log
-- ---------------------------------------------------------------------------
-- Token usage and cost tracking per API call.

CREATE TABLE usage_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    agent_id            UUID REFERENCES agent(id),
    user_id             UUID REFERENCES "user"(id),
    conversation_id     UUID REFERENCES conversation(id),
    request_id          TEXT,                -- X-Request-ID for tracing
    model               TEXT NOT NULL,
    input_tokens        INT NOT NULL DEFAULT 0,
    output_tokens       INT NOT NULL DEFAULT 0,
    embedding_tokens    INT NOT NULL DEFAULT 0,
    estimated_cost_usd  DECIMAL(10,6) NOT NULL DEFAULT 0,
    operation           TEXT NOT NULL DEFAULT 'chat',
    -- Operations: 'chat', 'embedding', 'extraction', 'consolidation',
    --             'compaction_shield', 'title_generation', 'summarization'

    -- MoE routing metadata (Section 3C)
    model_tier          TEXT,                -- 'fast', 'balanced', 'powerful' (NULL = no MoE)
    complexity_score    FLOAT,               -- 0.0-10.0 from QueryComplexityScorer
    routing_strategy    TEXT,                -- 'top_1', 'top_k', 'ensemble', 'cascade'
    agents_considered   INT,                 -- How many agents were scored by ExpertGate

    metadata            JSONB NOT NULL DEFAULT '{}',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 13. audit_log
-- ---------------------------------------------------------------------------
-- General system audit trail (distinct from memory_log).
-- Tracks administrative actions for compliance.

CREATE TABLE audit_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID REFERENCES team(id),
    user_id             UUID REFERENCES "user"(id),
    action              TEXT NOT NULL,
    -- Actions: 'user.created', 'user.deleted', 'agent.created', 'agent.updated',
    --          'agent.archived', 'team.settings_changed', 'api_key.created',
    --          'api_key.revoked', 'data_export.requested', 'data_deletion.completed'
    resource_type       TEXT NOT NULL,       -- 'user', 'agent', 'team', 'api_key'
    resource_id         UUID,
    changes             JSONB,               -- {old: {...}, new: {...}}
    ip_address          INET,
    user_agent          TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- PHASE 6: BACKGROUND PROCESSING (1 table)
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 14. scheduled_job
-- ---------------------------------------------------------------------------
-- User-configured scheduled agent runs ("Summarize my emails daily at 9am").

CREATE TABLE scheduled_job (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    agent_id            UUID NOT NULL REFERENCES agent(id),
    user_id             UUID NOT NULL REFERENCES "user"(id),
    name                TEXT NOT NULL,       -- "Daily email summary"
    message             TEXT NOT NULL,       -- The prompt to run
    cron_expression     TEXT NOT NULL,       -- "0 9 * * *"
    timezone            TEXT NOT NULL DEFAULT 'UTC',
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    -- Execution tracking
    last_run_at         TIMESTAMPTZ,
    next_run_at         TIMESTAMPTZ,
    run_count           INT NOT NULL DEFAULT 0,
    consecutive_failures INT NOT NULL DEFAULT 0,
    last_error          TEXT,
    -- Delivery
    delivery_config     JSONB NOT NULL DEFAULT '{}',
    -- {webhook_url, email, slack_channel, telegram_chat_id}
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- =============================================================================
-- PHASE 7: AGENT COLLABORATION (2 tables)
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 15. conversation_participant
-- ---------------------------------------------------------------------------
-- Track which agents participate in a conversation (multi-agent support).

CREATE TABLE conversation_participant (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    agent_id            UUID NOT NULL REFERENCES agent(id),
    role                participant_role NOT NULL DEFAULT 'primary',
    joined_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    left_at             TIMESTAMPTZ,         -- NULL = still active

    CONSTRAINT uq_conversation_participant UNIQUE (conversation_id, agent_id)
);


-- ---------------------------------------------------------------------------
-- 16. agent_handoff
-- ---------------------------------------------------------------------------
-- History of agent-to-agent conversation transfers.

CREATE TABLE agent_handoff (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id     UUID NOT NULL REFERENCES conversation(id) ON DELETE CASCADE,
    from_agent_id       UUID NOT NULL REFERENCES agent(id),
    to_agent_id         UUID NOT NULL REFERENCES agent(id),
    reason              TEXT NOT NULL,
    context_summary     TEXT,                -- Summary passed to target agent
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 17. routing_decision_log (MoE analytics -- Section 3C)
-- ---------------------------------------------------------------------------
-- Records every MoE routing decision for analytics and continuous improvement.
-- Both Expert Gate (agent selection) and Model Router (tier selection) results.

CREATE TABLE routing_decision_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    conversation_id     UUID REFERENCES conversation(id),
    message_id          UUID REFERENCES message(id),

    -- Expert Gate results
    strategy            TEXT NOT NULL,       -- 'top_1', 'top_k', 'ensemble', 'cascade'
    scores              JSONB NOT NULL,      -- [{agent_slug, overall, skill_match, ...}]
    selected_agents     TEXT[] NOT NULL,      -- Agent slugs that were selected
    confidence_threshold FLOAT NOT NULL DEFAULT 0.6,
    fallback_used       BOOLEAN NOT NULL DEFAULT FALSE,

    -- Model Router results
    complexity_score    FLOAT,               -- 0.0-10.0
    complexity_dimensions JSONB,             -- {reasoning, domain, creativity, context, length}
    selected_tier       TEXT,                -- 'fast', 'balanced', 'powerful'
    selected_model      TEXT,                -- Actual model name used
    tier_override_reason TEXT,               -- 'force_tier', 'budget_cap', 'agent_config', NULL

    -- Cost tracking
    estimated_cost      FLOAT,
    actual_cost         FLOAT,

    -- Timing
    gate_latency_ms     FLOAT,               -- Time for expert scoring
    router_latency_ms   FLOAT,               -- Time for complexity scoring
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 18. agent_task (Section 3D: Task delegation between agents)
-- ---------------------------------------------------------------------------
-- Tracks tasks that agents assign to each other.
-- Supports sub-delegation chains (parent_task_id) with max depth 3.

CREATE TABLE agent_task (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    conversation_id     UUID REFERENCES conversation(id),

    -- Who
    created_by_agent_id UUID NOT NULL REFERENCES agent(id),
    assigned_to_agent_id UUID NOT NULL REFERENCES agent(id),
    parent_task_id      UUID REFERENCES agent_task(id),

    -- What
    task_type           TEXT NOT NULL,       -- 'research', 'review', 'analyze', 'generate', etc.
    title               TEXT NOT NULL,
    instructions        TEXT NOT NULL,
    context             TEXT,
    expected_output     TEXT,
    input_artifacts     JSONB NOT NULL DEFAULT '[]',

    -- Constraints
    priority            TEXT NOT NULL DEFAULT 'normal',
    max_tokens          INT NOT NULL DEFAULT 4000,
    max_tool_calls      INT NOT NULL DEFAULT 10,
    timeout_seconds     INT NOT NULL DEFAULT 120,
    model_tier          TEXT,
    delegation_depth    INT NOT NULL DEFAULT 0,

    -- Status
    status              TEXT NOT NULL DEFAULT 'pending',
    result              TEXT,
    result_artifacts    JSONB NOT NULL DEFAULT '[]',
    error               TEXT,

    -- Cost tracking
    tokens_used         INT NOT NULL DEFAULT 0,
    cost_usd            DECIMAL(10,6) NOT NULL DEFAULT 0,

    -- Timing
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at          TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,

    CONSTRAINT max_delegation_depth CHECK (delegation_depth <= 3),
    CONSTRAINT no_self_delegation CHECK (created_by_agent_id != assigned_to_agent_id)
);


-- ---------------------------------------------------------------------------
-- 19. agent_message (Section 3D: Inter-agent communication)
-- ---------------------------------------------------------------------------
-- Internal messages between agents. Not user-visible unless surfaced.

CREATE TABLE agent_message (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    from_agent_id       UUID NOT NULL REFERENCES agent(id),
    to_agent_id         UUID REFERENCES agent(id),          -- NULL = broadcast
    channel             TEXT NOT NULL DEFAULT 'direct',
    message_type        TEXT NOT NULL,
    content             TEXT NOT NULL,
    metadata            JSONB NOT NULL DEFAULT '{}',
    read_at             TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);


-- ---------------------------------------------------------------------------
-- 20. collaboration_session (Section 3D: Multi-agent workflows)
-- ---------------------------------------------------------------------------
-- Tracks multi-agent collaboration sessions with defined patterns.

CREATE TABLE collaboration_session (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    conversation_id     UUID REFERENCES conversation(id),
    lead_agent_id       UUID NOT NULL REFERENCES agent(id),

    pattern             TEXT NOT NULL,
    goal                TEXT NOT NULL,
    context             TEXT,
    max_duration_seconds INT NOT NULL DEFAULT 600,
    max_total_cost_usd  DECIMAL(10,6) NOT NULL DEFAULT 0.50,
    max_rounds          INT NOT NULL DEFAULT 5,

    status              TEXT NOT NULL DEFAULT 'planning',
    current_stage       INT,
    stages_completed    INT NOT NULL DEFAULT 0,
    total_cost_usd      DECIMAL(10,6) NOT NULL DEFAULT 0,

    final_output        TEXT,
    stage_outputs       JSONB NOT NULL DEFAULT '[]',

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);


-- ---------------------------------------------------------------------------
-- 21. collaboration_participant (Section 3D: Who's in each session)
-- ---------------------------------------------------------------------------

CREATE TABLE collaboration_participant (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id          UUID NOT NULL REFERENCES collaboration_session(id) ON DELETE CASCADE,
    agent_id            UUID NOT NULL REFERENCES agent(id),
    role                TEXT NOT NULL DEFAULT 'worker',
    stage               INT,
    task_id             UUID REFERENCES agent_task(id),
    status              TEXT NOT NULL DEFAULT 'waiting',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_collab_session_agent UNIQUE (session_id, agent_id)
);


-- =============================================================================
-- PHASE 9: PLATFORM INTEGRATIONS (2 tables)
-- =============================================================================


-- ---------------------------------------------------------------------------
-- 22. platform_connection
-- ---------------------------------------------------------------------------
-- External platform bot connections (Telegram, Slack, etc.).

CREATE TABLE platform_connection (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    agent_id            UUID NOT NULL REFERENCES agent(id),
    platform            platform_type NOT NULL,
    -- Encrypted bot credentials
    -- {bot_token, signing_secret, app_id, etc.}
    credentials_encrypted JSONB NOT NULL,
    webhook_url         TEXT,
    external_bot_id     TEXT,                -- Platform-specific bot identifier
    status              platform_status NOT NULL DEFAULT 'active',
    last_event_at       TIMESTAMPTZ,
    error_message       TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- One connection per agent per platform
    CONSTRAINT uq_platform_agent UNIQUE (agent_id, platform)
);


-- ---------------------------------------------------------------------------
-- 23. webhook_delivery_log
-- ---------------------------------------------------------------------------
-- Track outbound webhook deliveries and retries.

CREATE TABLE webhook_delivery_log (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    team_id             UUID NOT NULL REFERENCES team(id) ON DELETE CASCADE,
    event_type          TEXT NOT NULL,
    -- Events: 'conversation.created', 'conversation.completed',
    --         'message.created', 'memory.created', 'agent.status_changed',
    --         'job.completed', 'job.failed'
    event_id            TEXT NOT NULL,       -- evt_abc123 (idempotency key)
    payload             JSONB NOT NULL,
    webhook_url         TEXT NOT NULL,
    -- Delivery tracking
    http_status         INT,
    response_body       TEXT,
    attempt             INT NOT NULL DEFAULT 1,
    max_attempts        INT NOT NULL DEFAULT 5,
    next_retry_at       TIMESTAMPTZ,
    delivered_at        TIMESTAMPTZ,         -- NULL = not yet delivered
    failed_at           TIMESTAMPTZ,         -- NULL = not permanently failed
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_webhook_event_id UNIQUE (event_id)
);


-- =============================================================================
-- INDEXES
-- =============================================================================
-- Organized by table, with query patterns documented.


-- --- user ---
CREATE INDEX idx_user_email ON "user" (email);
-- Query: login by email


-- --- team ---
CREATE INDEX idx_team_slug ON team (slug);
-- Query: resolve team by slug from URL


-- --- team_membership ---
CREATE INDEX idx_membership_user ON team_membership (user_id);
CREATE INDEX idx_membership_team ON team_membership (team_id, role);
-- Query: "which teams does user X belong to?"
-- Query: "who are the admins of team Y?"


-- --- agent ---
CREATE INDEX idx_agent_team_status ON agent (team_id, status);
CREATE INDEX idx_agent_team_slug ON agent (team_id, slug);
-- Query: "list all active agents for team X"
-- Query: "resolve agent by slug within team"


-- --- conversation ---
CREATE INDEX idx_conversation_team ON conversation (team_id, created_at DESC);
CREATE INDEX idx_conversation_user ON conversation (user_id, created_at DESC);
CREATE INDEX idx_conversation_agent ON conversation (agent_id, created_at DESC);
CREATE INDEX idx_conversation_status ON conversation (team_id, status)
    WHERE status = 'active';
-- Query: "list conversations for team/user/agent, newest first"
-- Query: "find active conversations (for idle timeout job)"


-- --- message ---
CREATE INDEX idx_message_conversation ON message (conversation_id, created_at);
CREATE INDEX idx_message_feedback ON message (conversation_id)
    WHERE feedback_rating IS NOT NULL;
-- Query: "get messages for conversation in chronological order"
-- Query: "find messages with feedback for quality analysis"


-- --- memory (CRITICAL - most queried table) ---

-- Vector similarity search (THE hot path)
-- IVFFlat: good for 10K-1M vectors. Switch to HNSW at >1M.
CREATE INDEX idx_memory_embedding ON memory
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Filtered retrieval (most common query pattern)
-- "Get active memories for this team + agent scope"
CREATE INDEX idx_memory_team_type_status ON memory (team_id, memory_type, status)
    WHERE status IN ('active', 'disputed');

-- Agent-scoped retrieval
CREATE INDEX idx_memory_agent ON memory (agent_id, memory_type)
    WHERE agent_id IS NOT NULL AND status = 'active';

-- User-profile retrieval (cross-agent)
CREATE INDEX idx_memory_user_profile ON memory (team_id, user_id, memory_type)
    WHERE memory_type = 'user_profile' AND status = 'active';

-- Recency signal (for 5-signal retrieval)
CREATE INDEX idx_memory_recency ON memory (team_id, last_accessed_at DESC)
    WHERE status = 'active';

-- Importance signal (for pinned + high-importance retrieval)
CREATE INDEX idx_memory_importance ON memory (team_id, importance DESC)
    WHERE status = 'active' AND (is_pinned = TRUE OR importance >= 7);

-- Conversation continuity signal
CREATE INDEX idx_memory_conversation ON memory (source_conversation_id)
    WHERE source_conversation_id IS NOT NULL;

-- Contradiction lookup
CREATE INDEX idx_memory_subject ON memory (team_id, subject)
    WHERE subject IS NOT NULL AND status = 'active';

-- Tier management (for promotion/demotion jobs)
CREATE INDEX idx_memory_tier ON memory (tier, last_accessed_at)
    WHERE status = 'active';

-- Expiration (for cleanup jobs)
CREATE INDEX idx_memory_expiration ON memory (expires_at)
    WHERE expires_at IS NOT NULL AND status = 'active';


-- --- memory_log ---
CREATE INDEX idx_memory_log_memory ON memory_log (memory_id, created_at);
CREATE INDEX idx_memory_log_time ON memory_log (created_at);
-- Query: "get audit trail for memory X"
-- Query: "reconstruct memory state at timestamp T"


-- --- memory_tag ---
CREATE INDEX idx_memory_tag_tag ON memory_tag (tag);
CREATE INDEX idx_memory_tag_memory ON memory_tag (memory_id);
-- Query: "find all memories with tag X"


-- --- api_key ---
CREATE INDEX idx_api_key_hash ON api_key (key_hash)
    WHERE is_active = TRUE;
CREATE INDEX idx_api_key_team ON api_key (team_id);
-- Query: "validate API key on every request"


-- --- refresh_token ---
CREATE INDEX idx_refresh_token_user ON refresh_token (user_id)
    WHERE revoked_at IS NULL;
CREATE INDEX idx_refresh_token_expiry ON refresh_token (expires_at)
    WHERE revoked_at IS NULL;
-- Query: "find active refresh tokens for user"
-- Query: "cleanup expired tokens"


-- --- usage_log ---
CREATE INDEX idx_usage_team_time ON usage_log (team_id, created_at DESC);
CREATE INDEX idx_usage_agent ON usage_log (agent_id, created_at DESC)
    WHERE agent_id IS NOT NULL;
CREATE INDEX idx_usage_conversation ON usage_log (conversation_id)
    WHERE conversation_id IS NOT NULL;
-- Query: "GET /v1/teams/{slug}/usage?period=7d"


-- --- audit_log ---
CREATE INDEX idx_audit_team ON audit_log (team_id, created_at DESC);
CREATE INDEX idx_audit_user ON audit_log (user_id, created_at DESC);
CREATE INDEX idx_audit_resource ON audit_log (resource_type, resource_id);
-- Query: "show audit trail for team/user/resource"


-- --- scheduled_job ---
CREATE INDEX idx_job_next_run ON scheduled_job (next_run_at)
    WHERE is_active = TRUE;
CREATE INDEX idx_job_team ON scheduled_job (team_id);
-- Query: "find jobs due to run (Celery Beat polling)"


-- --- conversation_participant ---
CREATE INDEX idx_participant_conversation ON conversation_participant (conversation_id)
    WHERE left_at IS NULL;
CREATE INDEX idx_participant_agent ON conversation_participant (agent_id)
    WHERE left_at IS NULL;
-- Query: "which agents are in this conversation?"
-- Query: "which conversations is this agent in?"


-- --- agent_handoff ---
CREATE INDEX idx_handoff_conversation ON agent_handoff (conversation_id, created_at);
-- Query: "handoff history for conversation"


-- --- routing_decision_log (MoE) ---
CREATE INDEX idx_routing_log_team ON routing_decision_log (team_id, created_at DESC);
CREATE INDEX idx_routing_log_conversation ON routing_decision_log (conversation_id);
CREATE INDEX idx_routing_log_tier ON routing_decision_log (selected_tier, created_at DESC);
-- Query: "MoE routing analytics per team"
-- Query: "routing decisions for conversation"
-- Query: "model tier usage distribution over time"


-- --- usage_log MoE columns ---
CREATE INDEX idx_usage_tier ON usage_log (model_tier, created_at DESC)
    WHERE model_tier IS NOT NULL;
-- Query: "cost breakdown by model tier"


-- --- agent_task ---
CREATE INDEX idx_agent_task_team ON agent_task (team_id, status, created_at DESC);
CREATE INDEX idx_agent_task_assignee ON agent_task (assigned_to_agent_id, status);
CREATE INDEX idx_agent_task_creator ON agent_task (created_by_agent_id, created_at DESC);
CREATE INDEX idx_agent_task_parent ON agent_task (parent_task_id)
    WHERE parent_task_id IS NOT NULL;
CREATE INDEX idx_agent_task_conversation ON agent_task (conversation_id)
    WHERE conversation_id IS NOT NULL;
-- Query: "pending tasks for an agent"
-- Query: "delegation chain for a task"
-- Query: "all tasks in a conversation"


-- --- agent_message ---
CREATE INDEX idx_agent_message_recipient ON agent_message (to_agent_id, read_at)
    WHERE read_at IS NULL;
CREATE INDEX idx_agent_message_channel ON agent_message (channel, created_at DESC);
CREATE INDEX idx_agent_message_team ON agent_message (team_id, created_at DESC);
-- Query: "unread messages for agent"
-- Query: "messages in a channel"


-- --- collaboration_session ---
CREATE INDEX idx_collab_session_team ON collaboration_session (team_id, status, created_at DESC);
CREATE INDEX idx_collab_session_lead ON collaboration_session (lead_agent_id, status);
-- Query: "active collaborations in team"


-- --- collaboration_participant ---
CREATE INDEX idx_collab_participant_session ON collaboration_participant (session_id, role);
CREATE INDEX idx_collab_participant_agent ON collaboration_participant (agent_id, status);
-- Query: "participants in a session"
-- Query: "sessions an agent is involved in"


-- --- platform_connection ---
CREATE INDEX idx_platform_team ON platform_connection (team_id, status);
CREATE INDEX idx_platform_external ON platform_connection (platform, external_bot_id);
-- Query: "find connection for incoming webhook by platform + bot ID"


-- --- webhook_delivery_log ---
CREATE INDEX idx_webhook_pending ON webhook_delivery_log (next_retry_at)
    WHERE delivered_at IS NULL AND failed_at IS NULL;
CREATE INDEX idx_webhook_team ON webhook_delivery_log (team_id, created_at DESC);
-- Query: "find webhooks pending retry"
-- Query: "webhook delivery history for team"


-- =============================================================================
-- FUNCTIONS
-- =============================================================================


-- ---------------------------------------------------------------------------
-- Auto-update updated_at timestamp
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- Auto-increment conversation message_count and update last_message_at
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION trigger_update_conversation_stats()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE conversation
    SET message_count = message_count + 1,
        last_message_at = NEW.created_at
    WHERE id = NEW.conversation_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- Memory access tracking (called on retrieval, non-blocking)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION update_memory_access(memory_ids UUID[])
RETURNS VOID AS $$
BEGIN
    UPDATE memory
    SET access_count = access_count + 1,
        last_accessed_at = NOW()
    WHERE id = ANY(memory_ids);
END;
$$ LANGUAGE plpgsql;


-- ---------------------------------------------------------------------------
-- Point-in-time memory reconstruction
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION reconstruct_memory_at(
    p_memory_id UUID,
    p_timestamp TIMESTAMPTZ
)
RETURNS TABLE (
    content TEXT,
    importance INT,
    tier TEXT,
    status TEXT,
    as_of TIMESTAMPTZ
) AS $$
BEGIN
    -- Get the initial state and apply log entries up to timestamp
    RETURN QUERY
    WITH ordered_logs AS (
        SELECT
            ml.new_content,
            ml.new_importance,
            ml.new_tier,
            ml.new_status,
            ml.created_at,
            ROW_NUMBER() OVER (
                PARTITION BY ml.memory_id
                ORDER BY ml.created_at DESC
            ) AS rn
        FROM memory_log ml
        WHERE ml.memory_id = p_memory_id
          AND ml.created_at <= p_timestamp
    )
    SELECT
        ol.new_content AS content,
        ol.new_importance AS importance,
        ol.new_tier AS tier,
        ol.new_status AS status,
        ol.created_at AS as_of
    FROM ordered_logs ol
    WHERE ol.rn = 1;
END;
$$ LANGUAGE plpgsql;


-- =============================================================================
-- TRIGGERS
-- =============================================================================


-- Auto-update updated_at on tables that have it
CREATE TRIGGER set_updated_at_user
    BEFORE UPDATE ON "user"
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_team
    BEFORE UPDATE ON team
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_agent
    BEFORE UPDATE ON agent
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_conversation
    BEFORE UPDATE ON conversation
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_memory
    BEFORE UPDATE ON memory
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_scheduled_job
    BEFORE UPDATE ON scheduled_job
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

CREATE TRIGGER set_updated_at_platform_connection
    BEFORE UPDATE ON platform_connection
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- Auto-update conversation stats on new message
CREATE TRIGGER update_conversation_on_message
    AFTER INSERT ON message
    FOR EACH ROW EXECUTE FUNCTION trigger_update_conversation_stats();


-- =============================================================================
-- SEED DATA (Default agent personalities)
-- =============================================================================
-- Run via: python -m src.seed (not raw SQL -- uses AgentDNA Pydantic models)
-- See plan/multi-agent-platform.md Section 19 for seed logic.
--
-- Default agents created:
--   1. Kyra  (friendly generalist)  - tone: friendly, temp: 0.7
--   2. Luke  (code specialist)      - tone: direct, temp: 0.3


-- =============================================================================
-- NOTES
-- =============================================================================
--
-- 1. PARTITIONING: If memory table exceeds 10M rows, consider range partitioning
--    by created_at (monthly) or list partitioning by team_id.
--
-- 2. PGVECTOR INDEX: IVFFlat is used here (lists=100). For >1M vectors,
--    consider HNSW index: CREATE INDEX ... USING hnsw (embedding vector_cosine_ops)
--    WITH (m = 16, ef_construction = 200);
--
-- 3. MEMORY_LOG: This table grows indefinitely (append-only, ADR-8).
--    Partition by created_at (monthly) and archive old partitions to cold storage.
--
-- 4. USAGE_LOG: Retain for 365 days. Archive older records for compliance.
--
-- 5. ENCRYPTION: platform_connection.credentials_encrypted should use
--    application-level encryption (not DB-level) with a key from env vars.
--    Consider pgcrypto's pgp_sym_encrypt() as an alternative.
--
-- 6. ROW-LEVEL SECURITY (future): For additional multi-tenant isolation,
--    consider PostgreSQL RLS policies:
--    ALTER TABLE memory ENABLE ROW LEVEL SECURITY;
--    CREATE POLICY team_isolation ON memory
--      USING (team_id = current_setting('app.current_team_id')::UUID);
