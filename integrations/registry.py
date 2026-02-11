"""Platform adapter registry for getting the right adapter by platform type."""

from typing import Dict, Type

from integrations.base import PlatformAdapter
from integrations.models import PlatformConfig, PlatformType


class AdapterRegistry:
    """Registry of platform adapters.

    Maps platform types to adapter classes. Used by webhook routers and
    workers to get the correct adapter for processing messages.
    """

    def __init__(self) -> None:
        """Initialize empty adapter registry."""
        self._adapters: Dict[PlatformType, Type[PlatformAdapter]] = {}

    def register(self, platform: PlatformType, adapter_class: Type[PlatformAdapter]) -> None:
        """Register an adapter class for a platform.

        Args:
            platform: Platform type identifier.
            adapter_class: PlatformAdapter subclass.
        """
        self._adapters[platform] = adapter_class

    def get_adapter(self, platform: PlatformType, config: PlatformConfig) -> PlatformAdapter:
        """Get an adapter instance for the given platform.

        Args:
            platform: Platform type identifier.
            config: Platform connection configuration.

        Returns:
            Instantiated adapter for the platform.

        Raises:
            ValueError: If platform is not registered.
        """
        adapter_class = self._adapters.get(platform)
        if adapter_class is None:
            raise ValueError(
                f"No adapter registered for platform '{platform}'. "
                f"Available platforms: {list(self._adapters.keys())}"
            )
        return adapter_class(config)

    def list_platforms(self) -> list[PlatformType]:
        """List all registered platforms.

        Returns:
            List of platform identifiers.
        """
        return list(self._adapters.keys())


# Global default registry instance (populated by adapters)
default_registry = AdapterRegistry()
