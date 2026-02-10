# Phase 9: Platform Integrations

> **Timeline**: Week 6 | **Prerequisites**: Phase 8 (Docker), Phase 4 (API), Phase 6 (Background Processing) | **Status**: Not Started

## Goal

Telegram and Slack adapters with webhook receivers. Enable users to interact with agents through external messaging platforms, with webhook signature validation, platform-specific message formatting, and asynchronous response delivery via Celery workers.

## Dependencies (Install)

```toml
[project]
dependencies = [
    # ... existing ...
    # Phase 9: Platform integrations
    "python-telegram-bot~=21.0",       # Telegram Bot API client
    "slack-sdk~=3.27",                 # Slack Web API + Events API client
]
```

## Settings Extensions

```python
# src/settings.py -- FeatureFlags additions
class FeatureFlags(BaseModel):
    """Simple boolean feature flags via environment variables."""
    # ... existing flags ...
    enable_webhooks: bool = Field(default=False)         # Phase 9: Outbound webhooks
    enable_integrations: bool = Field(default=False)     # Phase 9: Telegram/Slack

# .env additions:
# TELEGRAM_BOT_TOKEN=...          (per-connection, stored encrypted in platform_connection)
# SLACK_SIGNING_SECRET=...        (per-connection, stored encrypted in platform_connection)
# SLACK_BOT_TOKEN=...             (per-connection, stored encrypted in platform_connection)
```

## New Directories & Files

```
integrations/
    __init__.py
    base.py                  # Abstract PlatformAdapter
    models.py                # IncomingMessage, OutgoingMessage, PlatformConfig
    telegram/
        __init__.py
        adapter.py           # TelegramAdapter (format, send, parse)
        webhook.py           # Webhook receiver + signature validation
    slack/
        __init__.py
        adapter.py           # SlackAdapter (Block Kit formatting)
        webhook.py           # Event receiver + signature verification

api/routers/
    webhooks.py              # POST /v1/webhooks/telegram, POST /v1/webhooks/slack

workers/tasks/
    platform_tasks.py        # Celery task: handle_platform_message

tests/test_integrations/
    __init__.py
    test_telegram.py         # Webhook validation, message parsing, response formatting
    test_slack.py            # Same for Slack
    test_adapter.py          # Abstract adapter contract tests
```

## Database Tables Introduced

| Table | Key Columns | Notes |
|-------|-------------|-------|
| `platform_connection` | `id`, `team_id` (FK team), `agent_id` (FK agent), `platform` (platform_type ENUM: 'telegram', 'slack', 'discord', 'whatsapp'), `credentials_encrypted` (JSONB), `webhook_url`, `external_bot_id`, `status` (platform_status ENUM: 'active', 'paused', 'error', 'disconnected'), `last_event_at`, `error_message`, `created_at`, `updated_at` | External platform bot connections. UNIQUE constraint on (agent_id, platform) -- one connection per agent per platform. Credentials are encrypted at application level. |
| `webhook_delivery_log` | `id`, `team_id` (FK team), `event_type`, `event_id` (idempotency key), `payload` (JSONB), `webhook_url`, `http_status`, `response_body`, `attempt`, `max_attempts`, `next_retry_at`, `delivered_at`, `failed_at`, `created_at` | Tracks outbound webhook deliveries and retries. UNIQUE constraint on event_id for idempotency. |

Reference: `plan/sql/schema.sql` (Phase 9 section, lines 581-638)

### Full SQL from schema.sql

```sql
-- platform_connection
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

-- webhook_delivery_log
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

-- Indexes
CREATE INDEX idx_platform_team ON platform_connection (team_id, status);
CREATE INDEX idx_platform_external ON platform_connection (platform, external_bot_id);
-- Query: "find connection for incoming webhook by platform + bot ID"

CREATE INDEX idx_webhook_pending ON webhook_delivery_log (next_retry_at)
    WHERE delivered_at IS NULL AND failed_at IS NULL;
CREATE INDEX idx_webhook_team ON webhook_delivery_log (team_id, created_at DESC);
-- Query: "find webhooks pending retry"
-- Query: "webhook delivery history for team"

-- Trigger
CREATE TRIGGER set_updated_at_platform_connection
    BEFORE UPDATE ON platform_connection
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();
```

### Enum Types (from Phase 1 migration, used here)

```sql
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
```

## Implementation Details

### 9.1 Abstract Platform Adapter

```python
class PlatformAdapter(ABC):
    """Base class for messaging platform integrations."""

    @abstractmethod
    async def validate_webhook(self, request: Request) -> bool: ...

    @abstractmethod
    async def parse_message(self, payload: dict) -> IncomingMessage: ...

    @abstractmethod
    async def send_response(
        self, channel_id: str, content: str, thread_id: Optional[str] = None
    ) -> None: ...

    @abstractmethod
    def format_response(self, text: str) -> str:
        """Convert markdown to platform-specific format."""
```

The abstract adapter defines the contract that all platform integrations must implement:
- **validate_webhook**: Verify the incoming request is authentic (HMAC signature check)
- **parse_message**: Convert platform-specific payload to a normalized `IncomingMessage`
- **send_response**: Send a formatted response back to the platform
- **format_response**: Convert agent markdown output to platform-specific format

### 9.2 Telegram Adapter

Implements `PlatformAdapter` for Telegram Bot API:
- **Webhook validation**: HMAC verification of Telegram webhook signatures
- **Message parsing**: Extract chat_id, user info, message text from Telegram update payload
- **Response formatting**: Convert markdown to Telegram's MarkdownV2 format
- **Send response**: Use `python-telegram-bot` library to send messages via Bot API

### 9.3 Slack Adapter

Implements `PlatformAdapter` for Slack Events API:
- **Webhook validation**: Verify Slack signing secret (X-Slack-Signature header)
- **Message parsing**: Handle @mentions and DMs from Slack event payloads
- **Response formatting**: Convert markdown to Slack Block Kit format
- **Send response**: Use `slack-sdk` to post messages via Slack Web API

### 9.4 Integration Flow

```
External platform
    |
    +-> POST /v1/webhooks/telegram (or /slack)
    |
    +-> Validate signature (HMAC for Telegram, signing secret for Slack)
    |
    +-> Parse incoming message -> IncomingMessage
    |
    +-> Resolve agent (by platform connection config)
    |
    +-> Respond 200 immediately (Slack requires < 3s)
    |
    +-> Dispatch to Celery: agent_tasks.handle_platform_message
    |
    +-> Worker: run agent -> format response -> send via platform API
```

Key design decisions:
- **Respond 200 immediately**: Slack requires webhook acknowledgment within 3 seconds. The actual agent processing happens asynchronously via Celery.
- **Resolve agent by platform connection**: The `platform_connection` table maps external bot IDs to agents. When a webhook arrives, we look up which agent handles this bot.
- **Worker handles full pipeline**: The Celery task runs the agent, extracts memories, formats the response, and sends it back via the platform API.

### 9.5 Outbound Webhook Events

When a team configures a webhook URL, these events are delivered:

| Event | Payload | Trigger |
|-------|---------|---------|
| `conversation.created` | `{conversation_id, agent_slug, user_id}` | New conversation started |
| `conversation.completed` | `{conversation_id, message_count, duration_s}` | Conversation ended |
| `message.created` | `{message_id, conversation_id, role, content_preview}` | New message (user or assistant) |
| `memory.created` | `{memory_id, memory_type, content_preview, importance}` | New memory extracted |
| `agent.status_changed` | `{agent_id, old_status, new_status}` | Agent activated/paused/archived |
| `job.completed` | `{job_id, agent_id, result_preview}` | Scheduled job finished |
| `job.failed` | `{job_id, agent_id, error}` | Scheduled job failed |

### 9.6 Webhook Delivery (Outbound)

```
Event occurs
    |
    +-> Serialize payload + add metadata (event_id, timestamp, team_id)
    +-> Sign with HMAC-SHA256 (team's webhook secret)
    +-> POST to webhook URL with headers:
    |     X-Webhook-Signature: sha256=...
    |     X-Webhook-Event: conversation.created
    |     X-Webhook-ID: evt_abc123
    |
    +-> Success (2xx): done
    +-> Failure: retry with exponential backoff
        Attempt 1: immediate
        Attempt 2: 1 min
        Attempt 3: 5 min
        Attempt 4: 30 min
        Attempt 5: 2 hours
        After 5 failures: mark webhook as `failing`, notify team admin
```

## Tests

```
tests/test_integrations/
    __init__.py
    test_telegram.py         # Webhook validation, message parsing, response formatting
    test_slack.py            # Same for Slack
    test_adapter.py          # Abstract adapter contract tests
```

### Key Test Scenarios

- Telegram webhook with valid HMAC signature passes validation
- Telegram webhook with invalid/missing signature is rejected (401)
- Telegram message payload is correctly parsed to `IncomingMessage`
- Telegram response formatting converts markdown to MarkdownV2
- Telegram adapter sends message via Bot API
- Slack webhook with valid signing secret passes validation
- Slack webhook with invalid/expired signature is rejected (401)
- Slack @mention payload is correctly parsed to `IncomingMessage`
- Slack DM payload is correctly parsed to `IncomingMessage`
- Slack response formatting converts markdown to Block Kit
- Slack adapter sends message via Web API
- Abstract adapter contract tests verify all implementations satisfy the interface
- Platform connection lookup resolves correct agent from external bot ID
- Webhook endpoint responds 200 immediately (before agent processing)
- Celery task `handle_platform_message` dispatches correctly
- Memory extraction runs on platform messages (same as API messages)
- Outbound webhook delivery creates `webhook_delivery_log` record
- Failed webhook delivery retries with exponential backoff
- After 5 failures, webhook is marked as `failing`

## Acceptance Criteria

- [ ] Telegram bot receives and responds to messages
- [ ] Slack app handles @mentions and DMs
- [ ] Webhook signatures validated (rejects invalid)
- [ ] Responses formatted for each platform (Markdown -> Telegram, Block Kit -> Slack)
- [ ] Platform messages trigger memory extraction

## Critical Constraint

After this phase completes:

```bash
python -m src.cli                    # CLI still works
.venv/bin/python -m pytest tests/ -v # All tests pass
ruff check src/ tests/               # Lint clean
mypy src/                            # Types pass
docker-compose up                    # All services healthy (including integrations)
```

## Rollback Strategy

**Phase 9 (Integrations)**: Delete `integrations/` directory. Run `alembic downgrade` to drop `platform_connection` and `webhook_delivery_log` tables. Remove webhook router from API. Remove platform Celery tasks from workers.

**Database Migration Safety:**

```bash
# Before any migration in production:
1. Backup database: pg_dump -Fc skill_agent > backup_$(date +%Y%m%d).dump
2. Test migration on staging first
3. Run migration: alembic upgrade head
4. Verify: alembic current
5. If broken: alembic downgrade -1  (revert last migration)
6. If catastrophic: pg_restore -d skill_agent backup_YYYYMMDD.dump
```

**Feature Flags**: Two flags control Phase 9 features independently:
- `enable_webhooks` (default `False`): Controls outbound webhook event delivery
- `enable_integrations` (default `False`): Controls Telegram/Slack inbound adapters

Both can be toggled without deployment. When disabled, webhook endpoints return 404 and no outbound events are dispatched.

## Links to Main Plan

- **Section 4, Phase 9**: Platform Integrations (lines 2387-2481)
- **Section 6**: New Directory Summary (integrations/)
- **Section 13**: Implementation Sequence Diagram (Phase 9 timeline)
- **Section 20**: Webhook Event Catalog (outbound events + delivery flow)
- **Section 21**: Phase Dependency Graph (Phase 8 -> Phase 9)
- **Section 23**: Rollback Strategy (Phase 9 rollback details)
- **SQL Schema**: `plan/sql/schema.sql` Phase 9 section (platform_connection, webhook_delivery_log)
