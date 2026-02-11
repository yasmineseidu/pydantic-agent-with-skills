"""Unit tests for PlatformAdapter ABC and AdapterRegistry."""

from typing import Optional

import pytest
from fastapi import Request

from integrations.base import PlatformAdapter
from integrations.models import IncomingMessage, PlatformConfig
from integrations.registry import AdapterRegistry


class MockAdapter(PlatformAdapter):
    """Mock adapter for testing."""

    async def validate_webhook(self, request: Request) -> bool:
        """Mock validation."""
        return True

    async def parse_message(self, payload: dict) -> IncomingMessage:
        """Mock parse."""
        return IncomingMessage(
            platform="telegram",
            external_user_id="123",
            external_channel_id="456",
            text="mock",
        )

    async def send_response(
        self, channel_id: str, content: str, thread_id: Optional[str] = None
    ) -> None:
        """Mock send."""
        pass

    def format_response(self, text: str) -> str:
        """Mock format."""
        return text


class TestPlatformAdapter:
    """Tests for PlatformAdapter ABC."""

    def test_cannot_instantiate_abc(self) -> None:
        """Test PlatformAdapter cannot be instantiated (is abstract)."""
        config = PlatformConfig(platform="telegram", credentials={})
        with pytest.raises(TypeError):
            PlatformAdapter(config)  # type: ignore[abstract]

    def test_mock_adapter_satisfies_interface(self) -> None:
        """Test a concrete adapter implementation works."""
        config = PlatformConfig(platform="telegram", credentials={})
        adapter = MockAdapter(config)
        assert isinstance(adapter, PlatformAdapter)
        assert adapter.config == config

    def test_adapter_stores_config(self) -> None:
        """Test adapter stores config in self.config."""
        config = PlatformConfig(
            platform="slack",
            credentials={"bot_token": "xoxb-123"},
            webhook_url="https://example.com",
        )
        adapter = MockAdapter(config)
        assert adapter.config.platform == "slack"
        assert adapter.config.webhook_url == "https://example.com"


class TestAdapterRegistry:
    """Tests for AdapterRegistry."""

    def test_register_adapter(self) -> None:
        """Test registering an adapter."""
        registry = AdapterRegistry()
        registry.register("telegram", MockAdapter)
        assert "telegram" in registry.list_platforms()

    def test_get_adapter_returns_instance(self) -> None:
        """Test get_adapter returns correct adapter instance."""
        registry = AdapterRegistry()
        registry.register("telegram", MockAdapter)
        config = PlatformConfig(platform="telegram", credentials={})
        adapter = registry.get_adapter("telegram", config)
        assert isinstance(adapter, MockAdapter)
        assert adapter.config == config

    def test_get_adapter_unknown_platform_raises(self) -> None:
        """Test get_adapter raises ValueError for unknown platform."""
        registry = AdapterRegistry()
        config = PlatformConfig(platform="telegram", credentials={})
        with pytest.raises(ValueError, match="No adapter registered"):
            registry.get_adapter("discord", config)

    def test_list_platforms(self) -> None:
        """Test list_platforms returns registered platforms."""
        registry = AdapterRegistry()
        registry.register("telegram", MockAdapter)
        registry.register("slack", MockAdapter)
        platforms = registry.list_platforms()
        assert "telegram" in platforms
        assert "slack" in platforms

    def test_empty_registry(self) -> None:
        """Test empty registry returns empty list."""
        registry = AdapterRegistry()
        assert registry.list_platforms() == []
