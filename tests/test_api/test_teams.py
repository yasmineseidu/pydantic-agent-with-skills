"""Unit tests for team CRUD and membership endpoints."""

import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.routers.teams import (
    list_teams,
    create_team,
    get_team,
    update_team,
    list_members,
    add_member,
    remove_member,
    get_usage,
)
from src.api.schemas.teams import (
    TeamCreate,
    TeamUpdate,
    MemberAdd,
)
from src.db.models.user import UserORM, TeamORM, TeamMembershipORM, UserRole


class TestListTeams:
    """Tests for GET /v1/teams endpoint."""

    @pytest.mark.asyncio
    async def test_list_teams_returns_user_teams(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """list_teams returns all teams the user is a member of."""
        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[test_team]))
        )
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await list_teams(current_user=(test_user, None), db=db_session)

        assert len(result) == 1
        assert result[0].id == test_team.id
        assert result[0].name == test_team.name
        assert result[0].slug == test_team.slug
        assert result[0].owner_id == test_team.owner_id

    @pytest.mark.asyncio
    async def test_list_teams_returns_empty_list_for_no_teams(
        self, test_user: UserORM, db_session: AsyncSession
    ) -> None:
        """list_teams returns empty list when user has no teams."""
        # Mock database query result with empty list
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=[])))
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await list_teams(current_user=(test_user, None), db=db_session)

        assert len(result) == 0
        assert result == []

    @pytest.mark.asyncio
    async def test_list_teams_response_structure(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """list_teams response includes all required fields."""
        # Mock database query result
        mock_result = MagicMock()
        mock_result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[test_team]))
        )
        db_session.execute = AsyncMock(return_value=mock_result)

        result = await list_teams(current_user=(test_user, None), db=db_session)

        team = result[0]
        assert hasattr(team, "id")
        assert hasattr(team, "name")
        assert hasattr(team, "slug")
        assert hasattr(team, "owner_id")
        assert hasattr(team, "settings")
        assert hasattr(team, "shared_skill_names")
        assert hasattr(team, "created_at")
        assert hasattr(team, "updated_at")


class TestCreateTeam:
    """Tests for POST /v1/teams endpoint."""

    @pytest.mark.asyncio
    async def test_create_team_success(
        self, test_user: UserORM, test_team_id: UUID, db_session: AsyncSession
    ) -> None:
        """create_team creates team with user as owner."""
        team_data = TeamCreate(name="New Team", slug="new-team")

        # Track added objects to set their IDs
        added_objects = []

        def mock_add(obj):
            added_objects.append(obj)
            if isinstance(obj, TeamORM):
                obj.id = test_team_id
                obj.created_at = datetime.now(timezone.utc)
                obj.updated_at = datetime.now(timezone.utc)

        db_session.add = MagicMock(side_effect=mock_add)
        db_session.flush = AsyncMock()
        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        result = await create_team(
            team_data=team_data, current_user=(test_user, None), db=db_session
        )

        assert result.name == "New Team"
        assert result.slug == "new-team"
        assert result.owner_id == test_user.id
        assert db_session.add.call_count == 2  # Team + Membership
        db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_team_duplicate_slug_raises_409(
        self, test_user: UserORM, db_session: AsyncSession
    ) -> None:
        """create_team raises 409 when slug already exists."""
        from fastapi import HTTPException

        team_data = TeamCreate(name="Duplicate Team", slug="duplicate-slug")

        # Mock IntegrityError on flush (duplicate slug)
        db_session.flush = AsyncMock(side_effect=IntegrityError("duplicate", None, None))
        db_session.add = MagicMock()
        db_session.rollback = AsyncMock()

        with pytest.raises(HTTPException) as exc_info:
            await create_team(team_data=team_data, current_user=(test_user, None), db=db_session)

        assert exc_info.value.status_code == 409
        assert "already exists" in exc_info.value.detail
        db_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_team_creates_owner_membership(
        self, test_user: UserORM, test_team_id: UUID, db_session: AsyncSession
    ) -> None:
        """create_team creates membership with role='owner'."""
        team_data = TeamCreate(name="Test Team", slug="test-team")

        # Track calls to db.add
        added_objects = []

        def mock_add(obj):
            added_objects.append(obj)
            if isinstance(obj, TeamORM):
                obj.id = test_team_id
                obj.created_at = datetime.now(timezone.utc)
                obj.updated_at = datetime.now(timezone.utc)

        db_session.add = MagicMock(side_effect=mock_add)
        db_session.flush = AsyncMock()
        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        await create_team(team_data=team_data, current_user=(test_user, None), db=db_session)

        # Verify both TeamORM and TeamMembershipORM were added
        assert len(added_objects) == 2
        assert any(isinstance(obj, TeamORM) for obj in added_objects)
        assert any(isinstance(obj, TeamMembershipORM) for obj in added_objects)

        # Find the membership and verify role
        membership = next(
            (obj for obj in added_objects if isinstance(obj, TeamMembershipORM)), None
        )
        assert membership is not None
        assert membership.role == UserRole.OWNER.value


class TestGetTeam:
    """Tests for GET /v1/teams/{slug} endpoint."""

    @pytest.mark.asyncio
    async def test_get_team_success(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """get_team returns team details when user is member."""
        # Mock team lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=test_team)
        db_session.execute = AsyncMock(return_value=mock_result)

        # Mock get_user_team_role to return member role
        with patch(
            "src.api.routers.teams.get_user_team_role",
            new=AsyncMock(return_value=UserRole.MEMBER.value),
        ):
            result = await get_team(slug="test-team", current_user=(test_user, None), db=db_session)

            assert result.id == test_team.id
            assert result.name == test_team.name
            assert result.slug == test_team.slug

    @pytest.mark.asyncio
    async def test_get_team_not_found_raises_404(
        self, test_user: UserORM, db_session: AsyncSession
    ) -> None:
        """get_team raises 404 when team does not exist."""
        from fastapi import HTTPException

        # Mock team lookup returning None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        db_session.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(HTTPException) as exc_info:
            await get_team(slug="nonexistent", current_user=(test_user, None), db=db_session)

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_get_team_not_member_raises_403(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """get_team raises 403 when user is not a team member."""
        from fastapi import HTTPException

        # Mock team lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=test_team)
        db_session.execute = AsyncMock(return_value=mock_result)

        # Mock get_user_team_role to return None (not a member)
        with patch("src.api.routers.teams.get_user_team_role", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await get_team(slug="test-team", current_user=(test_user, None), db=db_session)

            assert exc_info.value.status_code == 403
            assert "not a member" in exc_info.value.detail


class TestUpdateTeam:
    """Tests for PATCH /v1/teams/{slug} endpoint."""

    @pytest.mark.asyncio
    async def test_update_team_success(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """update_team updates team fields when user is owner."""
        team_data = TeamUpdate(name="Updated Name", settings={"max_tokens": 8000})

        # Mock team lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=test_team)
        db_session.execute = AsyncMock(return_value=mock_result)

        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        # Mock permission check to return True
        with patch("src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=True)):
            result = await update_team(
                slug="test-team", team_data=team_data, current_user=(test_user, None), db=db_session
            )

            assert result.name == "Updated Name"
            assert result.settings == {"max_tokens": 8000}
            db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_team_not_owner_raises_403(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """update_team raises 403 when user is not owner."""
        from fastapi import HTTPException

        team_data = TeamUpdate(name="Unauthorized Update")

        # Mock team lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=test_team)
        db_session.execute = AsyncMock(return_value=mock_result)

        # Mock permission check to return False
        with patch(
            "src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=False)
        ):
            with pytest.raises(HTTPException) as exc_info:
                await update_team(
                    slug="test-team",
                    team_data=team_data,
                    current_user=(test_user, None),
                    db=db_session,
                )

            assert exc_info.value.status_code == 403
            assert "owner" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_update_team_partial_update(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """update_team supports partial updates."""
        team_data = TeamUpdate(name="Only Name Updated")

        # Mock team lookup
        original_settings = test_team.settings.copy()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=test_team)
        db_session.execute = AsyncMock(return_value=mock_result)

        db_session.commit = AsyncMock()
        db_session.refresh = AsyncMock()

        # Mock permission check
        with patch("src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=True)):
            result = await update_team(
                slug="test-team", team_data=team_data, current_user=(test_user, None), db=db_session
            )

            # Name should be updated
            assert result.name == "Only Name Updated"
            # Settings should remain unchanged
            assert result.settings == original_settings


class TestListMembers:
    """Tests for GET /v1/teams/{slug}/members endpoint."""

    @pytest.mark.asyncio
    async def test_list_members_success(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """list_members returns all team members."""
        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock membership
        mock_membership = MagicMock(spec=TeamMembershipORM)
        mock_membership.user_id = test_user.id
        mock_membership.team_id = test_team.id
        mock_membership.role = UserRole.OWNER.value
        mock_membership.created_at = datetime.now(timezone.utc)

        # Mock members query result
        mock_members_result = MagicMock()
        mock_members_result.all = MagicMock(return_value=[(mock_membership, test_user)])

        # Setup execute to return different results based on call order
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_members_result

        db_session.execute = mock_execute

        # Mock get_user_team_role
        from src.auth import permissions

        original_func = permissions.get_user_team_role
        permissions.get_user_team_role = AsyncMock(return_value=UserRole.OWNER.value)

        try:
            result = await list_members(
                slug="test-team", current_user=(test_user, None), db=db_session
            )

            assert len(result) == 1
            assert result[0].user_id == test_user.id
            assert result[0].role == UserRole.OWNER.value
            assert result[0].email == test_user.email
        finally:
            permissions.get_user_team_role = original_func

    @pytest.mark.asyncio
    async def test_list_members_not_member_raises_403(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """list_members raises 403 when user is not a team member."""
        from fastapi import HTTPException

        # Mock team lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=test_team)
        db_session.execute = AsyncMock(return_value=mock_result)

        # Mock get_user_team_role to return None
        with patch("src.api.routers.teams.get_user_team_role", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await list_members(slug="test-team", current_user=(test_user, None), db=db_session)

            assert exc_info.value.status_code == 403


class TestAddMember:
    """Tests for POST /v1/teams/{slug}/members endpoint."""

    @pytest.mark.asyncio
    async def test_add_member_success(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """add_member adds new member to team."""
        member_data = MemberAdd(email="newuser@example.com", role="member")

        # Mock new user
        new_user = MagicMock(spec=UserORM)
        new_user.id = UUID("22222222-2222-2222-2222-222222222222")
        new_user.email = "newuser@example.com"
        new_user.display_name = "New User"

        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock user lookup
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none = MagicMock(return_value=new_user)

        # Setup execute to return different results
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_user_result

        db_session.execute = mock_execute
        db_session.commit = AsyncMock()

        # Mock add to set membership created_at
        added_memberships = []

        def mock_add(obj):
            added_memberships.append(obj)
            if isinstance(obj, TeamMembershipORM):
                obj.created_at = datetime.now(timezone.utc)

        db_session.add = MagicMock(side_effect=mock_add)
        db_session.refresh = AsyncMock()

        # Mock permission check
        with patch("src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=True)):
            result = await add_member(
                slug="test-team",
                member_data=member_data,
                current_user=(test_user, None),
                db=db_session,
            )

            assert result.email == "newuser@example.com"
            assert result.role == "member"
            db_session.add.assert_called_once()
            db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_add_member_user_not_found_raises_404(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """add_member raises 404 when user email does not exist."""
        from fastapi import HTTPException

        member_data = MemberAdd(email="nonexistent@example.com", role="member")

        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock user lookup returning None
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none = MagicMock(return_value=None)

        # Setup execute
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_user_result

        db_session.execute = mock_execute

        # Mock permission check
        with patch("src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=True)):
            with pytest.raises(HTTPException) as exc_info:
                await add_member(
                    slug="test-team",
                    member_data=member_data,
                    current_user=(test_user, None),
                    db=db_session,
                )

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_add_member_already_member_raises_409(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """add_member raises 409 when user is already a member."""
        from fastapi import HTTPException

        member_data = MemberAdd(email="existing@example.com", role="member")

        # Mock existing user
        existing_user = MagicMock(spec=UserORM)
        existing_user.id = UUID("33333333-3333-3333-3333-333333333333")
        existing_user.email = "existing@example.com"

        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock user lookup
        mock_user_result = MagicMock()
        mock_user_result.scalar_one_or_none = MagicMock(return_value=existing_user)

        # Setup execute
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_user_result

        db_session.execute = mock_execute
        db_session.add = MagicMock()
        db_session.commit = AsyncMock(side_effect=IntegrityError("duplicate", None, None))
        db_session.rollback = AsyncMock()

        # Mock permission check
        with patch("src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=True)):
            with pytest.raises(HTTPException) as exc_info:
                await add_member(
                    slug="test-team",
                    member_data=member_data,
                    current_user=(test_user, None),
                    db=db_session,
                )

            assert exc_info.value.status_code == 409
            assert "already a member" in exc_info.value.detail
            db_session.rollback.assert_called_once()


class TestRemoveMember:
    """Tests for DELETE /v1/teams/{slug}/members/{member_user_id} endpoint."""

    @pytest.mark.asyncio
    async def test_remove_member_success(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """remove_member removes member from team."""
        member_to_remove = UUID("44444444-4444-4444-4444-444444444444")

        # Mock membership
        mock_membership = MagicMock(spec=TeamMembershipORM)
        mock_membership.user_id = member_to_remove
        mock_membership.team_id = test_team.id
        mock_membership.role = UserRole.MEMBER.value

        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock membership lookup
        mock_membership_result = MagicMock()
        mock_membership_result.scalar_one_or_none = MagicMock(return_value=mock_membership)

        # Setup execute
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_membership_result

        db_session.execute = mock_execute
        db_session.delete = AsyncMock()
        db_session.commit = AsyncMock()

        # Mock permission check
        with patch("src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=True)):
            result = await remove_member(
                slug="test-team",
                member_user_id=member_to_remove,
                current_user=(test_user, None),
                db=db_session,
            )

            assert result is None  # 204 No Content
            db_session.delete.assert_called_once()
            db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_remove_member_cannot_remove_owner_raises_400(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """remove_member raises 400 when attempting to remove owner."""
        from fastapi import HTTPException

        owner_id = test_team.owner_id

        # Mock membership with owner role
        mock_membership = MagicMock(spec=TeamMembershipORM)
        mock_membership.user_id = owner_id
        mock_membership.team_id = test_team.id
        mock_membership.role = UserRole.OWNER.value

        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock membership lookup
        mock_membership_result = MagicMock()
        mock_membership_result.scalar_one_or_none = MagicMock(return_value=mock_membership)

        # Setup execute
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_membership_result

        db_session.execute = mock_execute

        # Mock permission check
        with patch("src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=True)):
            with pytest.raises(HTTPException) as exc_info:
                await remove_member(
                    slug="test-team",
                    member_user_id=owner_id,
                    current_user=(test_user, None),
                    db=db_session,
                )

            assert exc_info.value.status_code == 400
            assert "owner" in exc_info.value.detail.lower()

    @pytest.mark.asyncio
    async def test_remove_member_membership_not_found_raises_404(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """remove_member raises 404 when membership does not exist."""
        from fastapi import HTTPException

        nonexistent_member = UUID("55555555-5555-5555-5555-555555555555")

        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock membership lookup returning None
        mock_membership_result = MagicMock()
        mock_membership_result.scalar_one_or_none = MagicMock(return_value=None)

        # Setup execute
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_membership_result

        db_session.execute = mock_execute

        # Mock permission check
        with patch("src.api.routers.teams.check_team_permission", new=AsyncMock(return_value=True)):
            with pytest.raises(HTTPException) as exc_info:
                await remove_member(
                    slug="test-team",
                    member_user_id=nonexistent_member,
                    current_user=(test_user, None),
                    db=db_session,
                )

            assert exc_info.value.status_code == 404
            assert "not found" in exc_info.value.detail.lower()


class TestGetUsage:
    """Tests for GET /v1/teams/{slug}/usage endpoint."""

    @pytest.mark.asyncio
    async def test_get_usage_success(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """get_usage returns aggregated usage statistics."""
        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock usage aggregation result
        mock_usage_row = MagicMock()
        mock_usage_row.total_input = 5000
        mock_usage_row.total_output = 3000
        mock_usage_row.total_embedding = 1000
        mock_usage_row.total_cost = Decimal("0.50")
        mock_usage_row.request_count = 25
        mock_usage_row.period_start = datetime(2026, 2, 1, tzinfo=timezone.utc)
        mock_usage_row.period_end = datetime(2026, 2, 10, tzinfo=timezone.utc)

        mock_usage_result = MagicMock()
        mock_usage_result.one = MagicMock(return_value=mock_usage_row)

        # Setup execute
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_usage_result

        db_session.execute = mock_execute

        # Mock get_user_team_role
        from src.auth import permissions

        original_func = permissions.get_user_team_role
        permissions.get_user_team_role = AsyncMock(return_value=UserRole.MEMBER.value)

        try:
            result = await get_usage(
                slug="test-team", current_user=(test_user, None), db=db_session
            )

            assert result.team_id == test_team.id
            assert result.total_input_tokens == 5000
            assert result.total_output_tokens == 3000
            assert result.total_embedding_tokens == 1000
            assert result.estimated_cost_usd == 0.50
            assert result.request_count == 25
        finally:
            permissions.get_user_team_role = original_func

    @pytest.mark.asyncio
    async def test_get_usage_no_logs_returns_zero_stats(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """get_usage returns zero stats when no usage logs exist."""
        # Mock team lookup
        mock_team_result = MagicMock()
        mock_team_result.scalar_one_or_none = MagicMock(return_value=test_team)

        # Mock usage aggregation with zero values
        mock_usage_row = MagicMock()
        mock_usage_row.total_input = 0
        mock_usage_row.total_output = 0
        mock_usage_row.total_embedding = 0
        mock_usage_row.total_cost = Decimal("0")
        mock_usage_row.request_count = 0
        mock_usage_row.period_start = None
        mock_usage_row.period_end = None

        mock_usage_result = MagicMock()
        mock_usage_result.one = MagicMock(return_value=mock_usage_row)

        # Setup execute
        call_count = 0

        async def mock_execute(stmt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_team_result
            else:
                return mock_usage_result

        db_session.execute = mock_execute

        # Mock get_user_team_role
        from src.auth import permissions

        original_func = permissions.get_user_team_role
        permissions.get_user_team_role = AsyncMock(return_value=UserRole.MEMBER.value)

        try:
            result = await get_usage(
                slug="test-team", current_user=(test_user, None), db=db_session
            )

            assert result.total_input_tokens == 0
            assert result.total_output_tokens == 0
            assert result.total_embedding_tokens == 0
            assert result.estimated_cost_usd == 0.0
            assert result.request_count == 0
            # period_start should fall back to team.created_at
            assert result.period_start == test_team.created_at
        finally:
            permissions.get_user_team_role = original_func

    @pytest.mark.asyncio
    async def test_get_usage_not_member_raises_403(
        self, test_user: UserORM, test_team: TeamORM, db_session: AsyncSession
    ) -> None:
        """get_usage raises 403 when user is not a team member."""
        from fastapi import HTTPException

        # Mock team lookup
        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=test_team)
        db_session.execute = AsyncMock(return_value=mock_result)

        # Mock get_user_team_role to return None
        with patch("src.api.routers.teams.get_user_team_role", new=AsyncMock(return_value=None)):
            with pytest.raises(HTTPException) as exc_info:
                await get_usage(slug="test-team", current_user=(test_user, None), db=db_session)

            assert exc_info.value.status_code == 403
            assert "not a member" in exc_info.value.detail
