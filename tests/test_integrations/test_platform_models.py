"""Unit tests for platform ORM models."""

from uuid import uuid4

from src.db.models.platform import (
    PlatformConnectionORM,
    PlatformStatusEnum,
    PlatformTypeEnum,
    WebhookDeliveryLogORM,
)


class TestPlatformTypeEnum:
    """Tests for PlatformTypeEnum."""

    def test_enum_values(self) -> None:
        """Test all enum values exist."""
        assert PlatformTypeEnum.TELEGRAM == "telegram"
        assert PlatformTypeEnum.SLACK == "slack"
        assert PlatformTypeEnum.DISCORD == "discord"
        assert PlatformTypeEnum.WHATSAPP == "whatsapp"

    def test_enum_count(self) -> None:
        """Test exactly 4 platform types."""
        assert len(PlatformTypeEnum) == 4


class TestPlatformStatusEnum:
    """Tests for PlatformStatusEnum."""

    def test_enum_values(self) -> None:
        """Test all enum values exist."""
        assert PlatformStatusEnum.ACTIVE == "active"
        assert PlatformStatusEnum.PAUSED == "paused"
        assert PlatformStatusEnum.ERROR == "error"
        assert PlatformStatusEnum.DISCONNECTED == "disconnected"

    def test_enum_count(self) -> None:
        """Test exactly 4 status values."""
        assert len(PlatformStatusEnum) == 4


class TestPlatformConnectionORM:
    """Tests for PlatformConnectionORM."""

    def test_instantiation(self) -> None:
        """Test creating a PlatformConnectionORM instance."""
        team_id = uuid4()
        agent_id = uuid4()
        connection = PlatformConnectionORM(
            team_id=team_id,
            agent_id=agent_id,
            platform=PlatformTypeEnum.TELEGRAM,
            credentials_json={"bot_token": "encrypted_value"},
            status=PlatformStatusEnum.ACTIVE,
        )
        assert connection.team_id == team_id
        assert connection.agent_id == agent_id
        assert connection.platform == PlatformTypeEnum.TELEGRAM
        assert connection.credentials_json["bot_token"] == "encrypted_value"
        assert connection.status == PlatformStatusEnum.ACTIVE

    def test_optional_fields(self) -> None:
        """Test optional fields default to None."""
        connection = PlatformConnectionORM(
            team_id=uuid4(),
            agent_id=uuid4(),
            platform=PlatformTypeEnum.SLACK,
            credentials_json={},
            status=PlatformStatusEnum.ACTIVE,
        )
        assert connection.webhook_url is None
        assert connection.external_bot_id is None
        assert connection.last_event_at is None
        assert connection.error_message is None

    def test_tablename(self) -> None:
        """Test table name is correct."""
        assert PlatformConnectionORM.__tablename__ == "platform_connection"

    def test_unique_constraint_exists(self) -> None:
        """Test unique constraint on agent_id + platform is defined."""
        constraints = [
            c.name for c in PlatformConnectionORM.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "uq_platform_agent" in constraints

    def test_indexes_exist(self) -> None:
        """Test required indexes are defined."""
        index_names = [
            c.name for c in PlatformConnectionORM.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "idx_platform_team" in index_names
        assert "idx_platform_external" in index_names


class TestWebhookDeliveryLogORM:
    """Tests for WebhookDeliveryLogORM."""

    def test_instantiation(self) -> None:
        """Test creating a WebhookDeliveryLogORM instance."""
        team_id = uuid4()
        delivery = WebhookDeliveryLogORM(
            team_id=team_id,
            event_type="conversation.created",
            event_id="evt_abc123",
            payload={"conversation_id": "conv_123"},
            webhook_url="https://example.com/webhook",
        )
        assert delivery.team_id == team_id
        assert delivery.event_type == "conversation.created"
        assert delivery.event_id == "evt_abc123"
        assert delivery.payload["conversation_id"] == "conv_123"

    def test_explicit_values(self) -> None:
        """Test explicit attempt and max_attempts override server defaults."""
        delivery = WebhookDeliveryLogORM(
            team_id=uuid4(),
            event_type="message.created",
            event_id="evt_xyz",
            payload={},
            webhook_url="https://example.com/hook",
            attempt=3,
            max_attempts=10,
        )
        assert delivery.attempt == 3
        assert delivery.max_attempts == 10

    def test_server_defaults_defined(self) -> None:
        """Test server_default SQL expressions are configured for attempt and max_attempts."""
        attempt_col = WebhookDeliveryLogORM.__table__.c.attempt
        max_attempts_col = WebhookDeliveryLogORM.__table__.c.max_attempts
        assert str(attempt_col.server_default.arg) == "1"
        assert str(max_attempts_col.server_default.arg) == "5"

    def test_optional_fields(self) -> None:
        """Test optional fields default to None."""
        delivery = WebhookDeliveryLogORM(
            team_id=uuid4(),
            event_type="job.completed",
            event_id="evt_def",
            payload={},
            webhook_url="https://example.com/hook",
        )
        assert delivery.http_status is None
        assert delivery.response_body is None
        assert delivery.next_retry_at is None
        assert delivery.delivered_at is None
        assert delivery.failed_at is None

    def test_tablename(self) -> None:
        """Test table name is correct."""
        assert WebhookDeliveryLogORM.__tablename__ == "webhook_delivery_log"

    def test_unique_constraint_event_id(self) -> None:
        """Test unique constraint on event_id is defined."""
        constraints = [
            c.name for c in WebhookDeliveryLogORM.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "uq_webhook_event_id" in constraints

    def test_indexes_exist(self) -> None:
        """Test required indexes are defined."""
        index_names = [
            c.name for c in WebhookDeliveryLogORM.__table_args__ if hasattr(c, "name") and c.name
        ]
        assert "idx_webhook_pending" in index_names
        assert "idx_webhook_team" in index_names
