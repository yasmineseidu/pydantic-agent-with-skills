"""Tests for Dockerfile structure and content."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCKER_DIR = ROOT / "docker"


class TestDockerfileStructure:
    """Verify Dockerfile multi-stage build structure."""

    def test_dockerfile_exists(self) -> None:
        """docker/Dockerfile must exist."""
        assert (DOCKER_DIR / "Dockerfile").exists()

    def test_dockerfile_worker_exists(self) -> None:
        """docker/Dockerfile.worker must exist."""
        assert (DOCKER_DIR / "Dockerfile.worker").exists()

    def test_dockerfile_multistage_deps(self) -> None:
        """Dockerfile must have a deps stage (FROM ... AS deps)."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "AS deps" in content, "Missing deps stage in Dockerfile"

    def test_dockerfile_multistage_app(self) -> None:
        """Dockerfile must have an app stage (FROM ... AS app)."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "AS app" in content, "Missing app stage in Dockerfile"

    def test_dockerfile_worker_multistage(self) -> None:
        """Dockerfile.worker must have deps and worker stages."""
        content = (DOCKER_DIR / "Dockerfile.worker").read_text()
        assert "AS deps" in content, "Missing deps stage in Dockerfile.worker"
        assert "AS worker" in content, "Missing worker stage in Dockerfile.worker"


class TestDockerfileCopyInstructions:
    """Verify required files are copied into the Docker image."""

    def test_dockerfile_copies_src(self) -> None:
        """Dockerfile must COPY src/ directory."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "COPY src/ src/" in content

    def test_dockerfile_copies_workers(self) -> None:
        """Dockerfile must COPY workers/ directory."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "COPY workers/ workers/" in content

    def test_dockerfile_copies_skills(self) -> None:
        """Dockerfile must COPY skills/ directory."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "COPY skills/ skills/" in content

    def test_dockerfile_copies_alembic_ini(self) -> None:
        """Dockerfile must COPY alembic.ini for migrations."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "alembic.ini" in content

    def test_dockerfile_copies_entrypoint(self) -> None:
        """Dockerfile must COPY entrypoint.sh."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "entrypoint.sh" in content


class TestDockerfileEntrypoint:
    """Verify ENTRYPOINT and CMD configuration."""

    def test_dockerfile_has_entrypoint(self) -> None:
        """Dockerfile must use ENTRYPOINT for migration automation."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "ENTRYPOINT" in content, "Missing ENTRYPOINT in Dockerfile"
        assert "entrypoint.sh" in content

    def test_dockerfile_exposes_8000(self) -> None:
        """Dockerfile must EXPOSE port 8000."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "EXPOSE 8000" in content

    def test_dockerfile_cmd_uvicorn(self) -> None:
        """Dockerfile CMD must run uvicorn."""
        content = (DOCKER_DIR / "Dockerfile").read_text()
        assert "uvicorn" in content

    def test_dockerfile_worker_has_entrypoint(self) -> None:
        """Dockerfile.worker must use ENTRYPOINT for migration automation."""
        content = (DOCKER_DIR / "Dockerfile.worker").read_text()
        assert "ENTRYPOINT" in content, "Missing ENTRYPOINT in Dockerfile.worker"
        assert "entrypoint.sh" in content

    def test_dockerfile_worker_cmd_celery(self) -> None:
        """Dockerfile.worker CMD must run celery worker."""
        content = (DOCKER_DIR / "Dockerfile.worker").read_text()
        assert "celery" in content
        assert "worker" in content


class TestDockerignore:
    """Verify .dockerignore excludes non-production files."""

    def test_root_dockerignore_exists(self) -> None:
        """Root .dockerignore must exist."""
        assert (ROOT / ".dockerignore").exists()

    def test_dockerignore_excludes_tests(self) -> None:
        """Root .dockerignore must exclude tests/ directory."""
        content = (ROOT / ".dockerignore").read_text()
        assert "tests/" in content, ".dockerignore missing tests/ exclusion"

    def test_dockerignore_excludes_env(self) -> None:
        """Root .dockerignore must exclude .env files."""
        content = (ROOT / ".dockerignore").read_text()
        assert ".env" in content

    def test_dockerignore_excludes_venv(self) -> None:
        """Root .dockerignore must exclude virtual environment directories."""
        content = (ROOT / ".dockerignore").read_text()
        assert ".venv" in content

    def test_dockerignore_excludes_claude(self) -> None:
        """Root .dockerignore must exclude .claude/ directory."""
        content = (ROOT / ".dockerignore").read_text()
        assert ".claude/" in content

    def test_dockerignore_excludes_plan(self) -> None:
        """Root .dockerignore must exclude plan/ directory."""
        content = (ROOT / ".dockerignore").read_text()
        assert "plan/" in content

    def test_dockerignore_excludes_reports(self) -> None:
        """Root .dockerignore must exclude reports/ directory."""
        content = (ROOT / ".dockerignore").read_text()
        assert "reports/" in content

    def test_dockerignore_excludes_markdown(self) -> None:
        """Root .dockerignore must exclude *.md documentation."""
        content = (ROOT / ".dockerignore").read_text()
        assert "*.md" in content

    def test_dockerignore_excludes_examples(self) -> None:
        """Root .dockerignore must exclude examples/ directory."""
        content = (ROOT / ".dockerignore").read_text()
        assert "examples/" in content
