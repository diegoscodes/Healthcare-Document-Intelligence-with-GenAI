"""add storage_path to documents

Revision ID: ebb95735a74f
Revises: e6387e61e252
Create Date: 2026-02-04 22:17:03.182304

"""
from __future__ import annotations
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ebb95735a74f'
down_revision: Union[str, Sequence[str], None] = 'e6387e61e252'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("storage_path", sa.String(length=500), nullable=False, server_default=""),
    )
    op.alter_column("documents", "storage_path", server_default=None)

def downgrade() -> None:
    op.drop_column("documents", "storage_path")
