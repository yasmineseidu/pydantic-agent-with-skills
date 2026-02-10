"""Tests for docker-compose configuration files."""

from __future__ import annotations

from pathlib import Path


def test_compose_files_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    compose = root / "docker" / "docker-compose.yml"
    compose_test = root / "docker" / "docker-compose.test.yml"

    assert compose.exists()
    assert compose_test.exists()


def test_compose_contains_services() -> None:
    root = Path(__file__).resolve().parents[2]
    content = (root / "docker" / "docker-compose.yml").read_text()

    for service in ["api:", "worker:", "beat:", "postgres:", "redis:"]:
        assert service in content
