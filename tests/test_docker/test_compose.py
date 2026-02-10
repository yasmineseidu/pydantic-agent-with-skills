"""Tests for docker-compose configuration files."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DOCKER_DIR = ROOT / "docker"


class TestComposeFilesExist:
    """Verify all expected docker-compose files exist."""

    def test_compose_files_exist(self) -> None:
        """docker-compose.yml and docker-compose.test.yml must exist."""
        assert (DOCKER_DIR / "docker-compose.yml").exists()
        assert (DOCKER_DIR / "docker-compose.test.yml").exists()

    def test_entrypoint_exists(self) -> None:
        """docker/entrypoint.sh must exist and be executable."""
        entrypoint = DOCKER_DIR / "entrypoint.sh"
        assert entrypoint.exists(), "docker/entrypoint.sh not found"
        # Check executable bit (unix only)
        import os

        assert os.access(entrypoint, os.X_OK), "entrypoint.sh is not executable"


class TestComposeServices:
    """Verify docker-compose.yml service definitions."""

    def test_compose_contains_all_services(self) -> None:
        """docker-compose.yml must define api, worker, beat, postgres, redis."""
        content = (DOCKER_DIR / "docker-compose.yml").read_text()
        for service in ["api:", "worker:", "beat:", "postgres:", "redis:"]:
            assert service in content, f"Missing service: {service}"

    def test_compose_services_count(self) -> None:
        """docker-compose.yml must define exactly 5 services."""
        data = yaml.safe_load((DOCKER_DIR / "docker-compose.yml").read_text())
        assert len(data["services"]) == 5


class TestComposeHealthChecks:
    """Verify health checks are configured in docker-compose.yml."""

    def test_postgres_healthcheck(self) -> None:
        """postgres service must have a healthcheck with pg_isready."""
        data = yaml.safe_load((DOCKER_DIR / "docker-compose.yml").read_text())
        pg = data["services"]["postgres"]
        assert "healthcheck" in pg, "postgres missing healthcheck"
        assert "pg_isready" in str(pg["healthcheck"]["test"])

    def test_redis_healthcheck(self) -> None:
        """redis service must have a healthcheck with redis-cli ping."""
        data = yaml.safe_load((DOCKER_DIR / "docker-compose.yml").read_text())
        redis_svc = data["services"]["redis"]
        assert "healthcheck" in redis_svc, "redis missing healthcheck"
        assert "ping" in str(redis_svc["healthcheck"]["test"])

    def test_api_depends_on_healthy_postgres(self) -> None:
        """api service must depend on postgres with condition: service_healthy."""
        data = yaml.safe_load((DOCKER_DIR / "docker-compose.yml").read_text())
        api = data["services"]["api"]
        assert "depends_on" in api
        pg_dep = api["depends_on"].get("postgres", {})
        assert pg_dep.get("condition") == "service_healthy"

    def test_api_depends_on_healthy_redis(self) -> None:
        """api service must depend on redis with condition: service_healthy."""
        data = yaml.safe_load((DOCKER_DIR / "docker-compose.yml").read_text())
        api = data["services"]["api"]
        assert "depends_on" in api
        redis_dep = api["depends_on"].get("redis", {})
        assert redis_dep.get("condition") == "service_healthy"

    def test_worker_depends_on_healthy_services(self) -> None:
        """worker service must depend on healthy postgres and redis."""
        data = yaml.safe_load((DOCKER_DIR / "docker-compose.yml").read_text())
        worker = data["services"]["worker"]
        assert "depends_on" in worker
        pg_dep = worker["depends_on"].get("postgres", {})
        assert pg_dep.get("condition") == "service_healthy"
        redis_dep = worker["depends_on"].get("redis", {})
        assert redis_dep.get("condition") == "service_healthy"


class TestTestComposeHealthChecks:
    """Verify test compose also has health checks."""

    def test_test_compose_has_healthchecks(self) -> None:
        """docker-compose.test.yml must have health checks for postgres and redis."""
        data = yaml.safe_load((DOCKER_DIR / "docker-compose.test.yml").read_text())
        assert "healthcheck" in data["services"]["postgres"]
        assert "healthcheck" in data["services"]["redis"]

    def test_test_compose_api_depends_on_healthy(self) -> None:
        """docker-compose.test.yml api must use service_healthy conditions."""
        data = yaml.safe_load((DOCKER_DIR / "docker-compose.test.yml").read_text())
        api = data["services"]["api"]
        pg_dep = api["depends_on"].get("postgres", {})
        assert pg_dep.get("condition") == "service_healthy"
