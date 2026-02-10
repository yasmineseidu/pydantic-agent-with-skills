"""Tests for deployment configuration files (Railway, Render, CI)."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


class TestRailwayConfig:
    """Verify Railway deployment configuration."""

    def test_railway_toml_exists(self) -> None:
        """deploy/railway/railway.toml must exist."""
        assert (ROOT / "deploy" / "railway" / "railway.toml").exists()

    def test_railway_has_three_services(self) -> None:
        """railway.toml must define 3 services (api, worker, beat)."""
        content = (ROOT / "deploy" / "railway" / "railway.toml").read_text()
        assert content.count("[[services]]") == 3

    def test_railway_has_api_service(self) -> None:
        """railway.toml must define an api service."""
        content = (ROOT / "deploy" / "railway" / "railway.toml").read_text()
        assert 'name = "api"' in content

    def test_railway_has_worker_service(self) -> None:
        """railway.toml must define a worker service."""
        content = (ROOT / "deploy" / "railway" / "railway.toml").read_text()
        assert 'name = "worker"' in content

    def test_railway_has_beat_service(self) -> None:
        """railway.toml must define a beat service."""
        content = (ROOT / "deploy" / "railway" / "railway.toml").read_text()
        assert 'name = "beat"' in content

    def test_procfile_exists(self) -> None:
        """deploy/railway/Procfile must exist."""
        assert (ROOT / "deploy" / "railway" / "Procfile").exists()

    def test_procfile_has_web_worker_beat(self) -> None:
        """Procfile must define web, worker, and beat processes."""
        content = (ROOT / "deploy" / "railway" / "Procfile").read_text()
        assert "web:" in content
        assert "worker:" in content
        assert "beat:" in content


class TestRenderConfig:
    """Verify Render deployment configuration."""

    def test_render_yaml_exists(self) -> None:
        """deploy/render/render.yaml must exist."""
        assert (ROOT / "deploy" / "render" / "render.yaml").exists()

    def test_render_has_five_services(self) -> None:
        """render.yaml must define 5 services (web, worker, beat, redis, postgres)."""
        data = yaml.safe_load((ROOT / "deploy" / "render" / "render.yaml").read_text())
        assert len(data["services"]) == 5

    def test_render_has_web_service(self) -> None:
        """render.yaml must have a web service type."""
        data = yaml.safe_load((ROOT / "deploy" / "render" / "render.yaml").read_text())
        types = [s["type"] for s in data["services"]]
        assert "web" in types

    def test_render_has_worker_services(self) -> None:
        """render.yaml must have worker service types."""
        data = yaml.safe_load((ROOT / "deploy" / "render" / "render.yaml").read_text())
        types = [s["type"] for s in data["services"]]
        assert types.count("worker") == 2

    def test_render_has_redis(self) -> None:
        """render.yaml must have a redis service."""
        data = yaml.safe_load((ROOT / "deploy" / "render" / "render.yaml").read_text())
        types = [s["type"] for s in data["services"]]
        assert "redis" in types


class TestCIWorkflow:
    """Verify GitHub Actions CI configuration."""

    def test_ci_workflow_exists(self) -> None:
        """.github/workflows/ci.yml must exist."""
        assert (ROOT / ".github" / "workflows" / "ci.yml").exists()

    def test_ci_has_postgres_service(self) -> None:
        """CI workflow must define a postgres service."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "postgres:" in content
        assert "pgvector" in content

    def test_ci_has_redis_service(self) -> None:
        """CI workflow must define a redis service."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "redis:" in content

    def test_ci_runs_pytest(self) -> None:
        """CI workflow must run pytest."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "pytest" in content

    def test_ci_runs_ruff(self) -> None:
        """CI workflow must run ruff check."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "ruff check" in content

    def test_ci_runs_mypy(self) -> None:
        """CI workflow must run mypy."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "mypy" in content

    def test_ci_runs_migrations(self) -> None:
        """CI workflow must run alembic migrations before tests."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "alembic upgrade head" in content

    def test_ci_has_docker_build_job(self) -> None:
        """CI workflow must have a docker-build job."""
        content = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
        assert "docker-build:" in content
