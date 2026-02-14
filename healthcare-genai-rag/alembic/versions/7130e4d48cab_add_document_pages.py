"""add document_pages

Revision ID: 7130e4d48cab
Revises: ebb95735a74f
Create Date: 2026-02-14 08:22:09.660963

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7130e4d48cab'
down_revision: Union[str, Sequence[str], None] = 'ebb95735a74f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_pages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "page_number", name="uq_document_pages_document_id_page_number"),
    )
    op.create_index(op.f("ix_document_pages_document_id"), "document_pages", ["document_id"], unique=False)
    op.create_index(op.f("ix_document_pages_page_number"), "document_pages", ["page_number"], unique=False)

    # remove server_default so new rows must explicitly set text (or ORM default kicks in)
    op.alter_column("document_pages", "text", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_document_pages_page_number"), table_name="document_pages")
    op.drop_index(op.f("ix_document_pages_document_id"), table_name="document_pages")
    op.drop_table("document_pages")
