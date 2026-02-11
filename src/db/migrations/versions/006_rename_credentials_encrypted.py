"""Rename credentials_encrypted to credentials_json (was never encrypted).

Revision ID: 006
Revises: 005
Create Date: 2026-02-10
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "platform_connection",
        "credentials_encrypted",
        new_column_name="credentials_json",
    )


def downgrade() -> None:
    op.alter_column(
        "platform_connection",
        "credentials_json",
        new_column_name="credentials_encrypted",
    )
