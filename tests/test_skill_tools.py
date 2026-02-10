"""Unit tests for progressive disclosure skill tools."""

import pytest
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from src.skill_tools import load_skill, read_skill_file, list_skill_files
from src.skill_loader import SkillLoader, SkillMetadata


@dataclass
class MockDependencies:
    """Mock dependencies for testing."""

    skill_loader: Optional[SkillLoader] = None


@dataclass
class MockContext:
    """Mock RunContext for testing tools."""

    deps: MockDependencies = field(default_factory=MockDependencies)


def create_test_skill(tmp_path: Path, name: str, description: str, body: str) -> SkillMetadata:
    """Helper to create a test skill with SKILL.md."""
    skill_dir = tmp_path / name
    skill_dir.mkdir(exist_ok=True)

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"""---
name: {name}
description: {description}
version: 1.0.0
---

{body}
"""
    )

    return SkillMetadata(
        name=name,
        description=description,
        version="1.0.0",
        author="",
        skill_path=skill_dir,
    )


class TestLoadSkill:
    """Tests for load_skill tool."""

    @pytest.mark.asyncio
    async def test_load_skill_returns_instructions(self, tmp_path: Path) -> None:
        """Test that load_skill returns full skill instructions."""
        skill = create_test_skill(
            tmp_path,
            "test_skill",
            "A test skill",
            "# Test Skill\n\nThis is the skill body.",
        )

        loader = SkillLoader(tmp_path)
        loader.skills = {"test_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await load_skill(ctx, "test_skill")

        assert "# Test Skill" in result
        assert "This is the skill body" in result
        # Should not include frontmatter
        assert "---" not in result
        assert "name:" not in result

    @pytest.mark.asyncio
    async def test_load_skill_not_found(self, tmp_path: Path) -> None:
        """Test error message for missing skill."""
        loader = SkillLoader(tmp_path)
        loader.skills = {}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await load_skill(ctx, "nonexistent_skill")

        assert "Error" in result
        assert "nonexistent_skill" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_load_skill_shows_available_skills(self, tmp_path: Path) -> None:
        """Test that error shows available skills."""
        skill = create_test_skill(tmp_path, "weather", "Weather skill", "Weather body")

        loader = SkillLoader(tmp_path)
        loader.skills = {"weather": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await load_skill(ctx, "calendar")

        assert "Error" in result
        assert "weather" in result

    @pytest.mark.asyncio
    async def test_load_skill_no_loader_initialized(self) -> None:
        """Test error when skill_loader is None."""
        ctx = MockContext(deps=MockDependencies(skill_loader=None))

        result = await load_skill(ctx, "any_skill")

        assert "Error" in result
        assert "not initialized" in result


class TestReadSkillFile:
    """Tests for read_skill_file tool."""

    @pytest.mark.asyncio
    async def test_read_skill_file_valid(self, tmp_path: Path) -> None:
        """Test reading a valid file from skill directory."""
        skill = create_test_skill(tmp_path, "test_skill", "Test", "Body")

        # Create a reference file
        refs_dir = tmp_path / "test_skill" / "references"
        refs_dir.mkdir()
        ref_file = refs_dir / "api_reference.md"
        ref_file.write_text("# API Reference\n\nAPI documentation here.")

        loader = SkillLoader(tmp_path)
        loader.skills = {"test_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await read_skill_file(ctx, "test_skill", "references/api_reference.md")

        assert "# API Reference" in result
        assert "API documentation here" in result

    @pytest.mark.asyncio
    async def test_read_skill_file_not_found(self, tmp_path: Path) -> None:
        """Test error for missing file."""
        skill = create_test_skill(tmp_path, "test_skill", "Test", "Body")

        loader = SkillLoader(tmp_path)
        loader.skills = {"test_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await read_skill_file(ctx, "test_skill", "nonexistent.md")

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_read_skill_file_security_traversal(self, tmp_path: Path) -> None:
        """Test that directory traversal is blocked."""
        skill = create_test_skill(tmp_path, "test_skill", "Test", "Body")

        # Create a file outside skill directory
        outside_file = tmp_path / "secret.txt"
        outside_file.write_text("SECRET DATA")

        loader = SkillLoader(tmp_path)
        loader.skills = {"test_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        # Attempt directory traversal
        result = await read_skill_file(ctx, "test_skill", "../secret.txt")

        assert "Error" in result
        assert "denied" in result.lower() or "invalid" in result.lower()

    @pytest.mark.asyncio
    async def test_read_skill_file_skill_not_found(self, tmp_path: Path) -> None:
        """Test error when skill doesn't exist."""
        loader = SkillLoader(tmp_path)
        loader.skills = {}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await read_skill_file(ctx, "nonexistent", "file.md")

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_read_skill_file_no_loader_initialized(self) -> None:
        """Test error when skill_loader is None."""
        ctx = MockContext(deps=MockDependencies(skill_loader=None))

        result = await read_skill_file(ctx, "any_skill", "file.md")

        assert "Error" in result
        assert "not initialized" in result


class TestListSkillFiles:
    """Tests for list_skill_files tool."""

    @pytest.mark.asyncio
    async def test_list_skill_files_returns_files(self, tmp_path: Path) -> None:
        """Test listing all files in a skill."""
        skill = create_test_skill(tmp_path, "test_skill", "Test", "Body")

        # Create additional files
        refs_dir = tmp_path / "test_skill" / "references"
        refs_dir.mkdir()
        (refs_dir / "api_reference.md").write_text("API docs")
        (refs_dir / "guide.md").write_text("Guide")

        scripts_dir = tmp_path / "test_skill" / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "helper.py").write_text("# helper")

        loader = SkillLoader(tmp_path)
        loader.skills = {"test_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await list_skill_files(ctx, "test_skill")

        assert "SKILL.md" in result
        assert "references" in result or "api_reference.md" in result
        assert "scripts" in result or "helper.py" in result

    @pytest.mark.asyncio
    async def test_list_skill_files_subdirectory(self, tmp_path: Path) -> None:
        """Test listing files in a subdirectory."""
        skill = create_test_skill(tmp_path, "test_skill", "Test", "Body")

        # Create files in references
        refs_dir = tmp_path / "test_skill" / "references"
        refs_dir.mkdir()
        (refs_dir / "api_reference.md").write_text("API docs")
        (refs_dir / "guide.md").write_text("Guide")

        loader = SkillLoader(tmp_path)
        loader.skills = {"test_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await list_skill_files(ctx, "test_skill", "references")

        assert "api_reference.md" in result
        assert "guide.md" in result

    @pytest.mark.asyncio
    async def test_list_skill_files_empty_skill(self, tmp_path: Path) -> None:
        """Test listing files when skill has only SKILL.md."""
        skill = create_test_skill(tmp_path, "minimal_skill", "Minimal", "Body")

        loader = SkillLoader(tmp_path)
        loader.skills = {"minimal_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await list_skill_files(ctx, "minimal_skill")

        # Should at least have SKILL.md
        assert "SKILL.md" in result

    @pytest.mark.asyncio
    async def test_list_skill_files_skill_not_found(self, tmp_path: Path) -> None:
        """Test error when skill doesn't exist."""
        loader = SkillLoader(tmp_path)
        loader.skills = {}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await list_skill_files(ctx, "nonexistent")

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_list_skill_files_directory_not_found(self, tmp_path: Path) -> None:
        """Test error when subdirectory doesn't exist."""
        skill = create_test_skill(tmp_path, "test_skill", "Test", "Body")

        loader = SkillLoader(tmp_path)
        loader.skills = {"test_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await list_skill_files(ctx, "test_skill", "nonexistent_dir")

        assert "Error" in result
        assert "not found" in result

    @pytest.mark.asyncio
    async def test_list_skill_files_security_traversal(self, tmp_path: Path) -> None:
        """Test that directory traversal is blocked."""
        skill = create_test_skill(tmp_path, "test_skill", "Test", "Body")

        loader = SkillLoader(tmp_path)
        loader.skills = {"test_skill": skill}

        ctx = MockContext(deps=MockDependencies(skill_loader=loader))

        result = await list_skill_files(ctx, "test_skill", "..")

        assert "Error" in result
        assert "denied" in result.lower() or "invalid" in result.lower()

    @pytest.mark.asyncio
    async def test_list_skill_files_no_loader_initialized(self) -> None:
        """Test error when skill_loader is None."""
        ctx = MockContext(deps=MockDependencies(skill_loader=None))

        result = await list_skill_files(ctx, "any_skill")

        assert "Error" in result
        assert "not initialized" in result
